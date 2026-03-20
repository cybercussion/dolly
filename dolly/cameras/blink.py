"""Blink camera source implementation."""

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from blinkpy.blinkpy import Blink
from blinkpy.auth import Auth
from blinkpy.auth import BlinkTwoFARequiredError
from blinkpy import api

from dolly.cameras.base import CameraSource, CameraInfo, MotionEvent

_LOGGER = logging.getLogger(__name__)

CRED_FILE = Path(__file__).resolve().parent.parent.parent / "blink.json"


class BlinkSource(CameraSource):
    def __init__(self, username: str, password: str):
        self._username = username
        self._password = password
        self._blink: Blink | None = None
        self._last_check: float = 0
        self._seen_events: set[str] = set()

    async def authenticate(self) -> None:
        blink = Blink()

        login_data = {"username": self._username, "password": self._password}
        if CRED_FILE.exists():
            login_data.update(json.loads(CRED_FILE.read_text()))

        auth = Auth(login_data)
        blink.auth = auth

        try:
            result = await blink.start()
        except BlinkTwoFARequiredError:
            code = input("Enter Blink 2FA code: ")
            result = await blink.send_2fa_code(code)

        if not result:
            raise RuntimeError("Blink authentication failed")

        self._save_credentials(auth)
        self._blink = blink
        self._last_check = time.time()

    def _save_credentials(self, auth: Auth) -> None:
        CRED_FILE.write_text(json.dumps(auth.login_attributes, indent=2))

    async def refresh(self) -> None:
        assert self._blink, "Call authenticate() first"
        await self._blink.refresh(force=True)

    async def list_cameras(self) -> list[CameraInfo]:
        await self.refresh()
        return [
            CameraInfo(
                name=name,
                brand="blink",
                model=cam.camera_type or "",
                network=cam.sync.name if cam.sync else "",
                armed=bool(cam.arm),
                motion_detected=bool(cam.motion_detected),
            )
            for name, cam in self._blink.cameras.items()
        ]

    async def get_new_events(self) -> list[MotionEvent]:
        """Check media/changed endpoint for new motion clips since last poll."""
        assert self._blink, "Call authenticate() first"

        since = datetime.fromtimestamp(self._last_check, tz=timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%S+00:00"
        )
        self._last_check = time.time()

        url = (
            f"{self._blink.urls.base_url}/api/v1/accounts/{self._blink.account_id}"
            f"/media/changed?since={since}&page=1"
        )
        resp = await api.http_get(self._blink, url)

        if not resp or not isinstance(resp, dict):
            _LOGGER.warning("Bad media response: %s", resp)
            return []

        media = resp.get("media", [])
        if not media:
            return []

        events = []
        for entry in media:
            # Skip deleted clips
            if entry.get("deleted", False):
                continue

            name = entry.get("device_name", "")
            created = entry.get("created_at", "")
            clip_url = entry.get("media", "")
            event_key = f"{name}:{created}"

            if event_key in self._seen_events:
                continue
            self._seen_events.add(event_key)

            # Skip if no clip URL (deleted or unavailable)
            if not clip_url:
                continue

            network = entry.get("network_name", "")
            cam = self._blink.cameras.get(name)
            if cam and cam.sync:
                network = cam.sync.name

            events.append(MotionEvent(
                camera_name=name,
                brand="blink",
                network=network,
                clip_url=clip_url,
                thumbnail_url=entry.get("thumbnail", ""),
                timestamp=created,
            ))

        # Keep seen set from growing forever — trim old entries
        if len(self._seen_events) > 500:
            self._seen_events = set(list(self._seen_events)[-200:])

        return events

    async def save_snapshot(
        self, camera_name: str, dest: Path, clip_url: str = "", thumbnail_url: str = ""
    ) -> Path:
        assert self._blink, "Call authenticate() first"

        dest.mkdir(parents=True, exist_ok=True)
        filepath = dest / f"{camera_name}.jpg"

        # Extract a frame from the motion clip (3s in — middle of a ~5s clip)
        if clip_url:
            full_url = f"{self._blink.urls.base_url}{clip_url}"
            video_path = dest / f"{camera_name}.mp4"

            response = await api.http_get(
                self._blink, url=full_url, stream=True, json=False
            )
            if response and response.status == 200:
                video_path.write_bytes(await response.read())
                if await self._extract_frame(video_path, filepath):
                    video_path.unlink(missing_ok=True)
                    return filepath
                video_path.unlink(missing_ok=True)

        # Fallback to event thumbnail
        if thumbnail_url:
            full_url = f"{self._blink.urls.base_url}{thumbnail_url}"
            response = await api.http_get(
                self._blink, url=full_url, stream=True, json=False
            )
            if response and response.status == 200:
                filepath.write_bytes(await response.read())
                return filepath

        raise RuntimeError(f"No image available for {camera_name}")

    @staticmethod
    async def _extract_frame(video: Path, output: Path, seek: int = 3) -> bool:
        """Extract a single frame from a video at the given second."""
        import asyncio
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y",
            "-ss", str(seek),
            "-i", str(video),
            "-frames:v", "1",
            "-q:v", "2",
            str(output),
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await proc.wait()
        return output.exists() and output.stat().st_size > 0

    async def close(self) -> None:
        if self._blink and self._blink.auth and self._blink.auth.session:
            await self._blink.auth.session.close()
        self._blink = None

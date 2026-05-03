"""Wyze camera source implementation."""

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

import aiohttp
from wyze_sdk import Client as WyzeClient
from wyze_sdk.errors import WyzeApiError
from wyze_sdk.models.events import EventAlarmType

from dolly.cameras.base import CameraSource, CameraInfo, MotionEvent

_LOGGER = logging.getLogger(__name__)


class WyzeSource(CameraSource):
    def __init__(self, email: str, password: str, key_id: str = "", api_key: str = ""):
        self._email = email
        self._password = password
        self._key_id = key_id
        self._api_key = api_key
        self._client: WyzeClient | None = None
        self._mac_to_name: dict[str, str] = {}
        self._seen_events: set[str] = set()
        self._last_check: datetime | None = None

    async def authenticate(self) -> None:
        loop = asyncio.get_running_loop()
        self._client = await loop.run_in_executor(
            None,
            lambda: WyzeClient(
                email=self._email,
                password=self._password,
                key_id=self._key_id or None,
                api_key=self._api_key or None,
            ),
        )
        devices = await loop.run_in_executor(None, self._client.devices_list)
        for d in devices:
            if d.type == "Camera":
                self._mac_to_name[d.mac] = d.nickname

        self._last_check = datetime.now(tz=timezone.utc)

    async def _reauth(self) -> None:
        """Re-authenticate to get a fresh access token."""
        _LOGGER.info("Wyze token expired — re-authenticating")
        await self.authenticate()

    async def refresh(self) -> None:
        pass

    async def _list_devices(self) -> list:
        """Fetch device list from Wyze API."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, self._client.devices_list)

    async def list_cameras(self) -> list[CameraInfo]:
        assert self._client, "Call authenticate() first"
        try:
            devices = await self._list_devices()
        except WyzeApiError as exc:
            if "expired" in str(exc).lower() or "2001" in str(exc):
                await self._reauth()
                devices = await self._list_devices()
            else:
                raise
        return [
            CameraInfo(
                name=d.nickname,
                brand="wyze",
                model=d.product.model or "",
                armed=bool(getattr(d, "is_on", True)),
                extra={"mac": d.mac},
            )
            for d in devices
            if d.type == "Camera"
        ]

    async def _fetch_events(self) -> list:
        """Fetch raw events from Wyze API."""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            None,
            lambda: self._client.events.list(
                device_ids=list(self._mac_to_name.keys()),
                event_values=[EventAlarmType.MOTION],
                begin=self._last_check,
                end=datetime.now(tz=timezone.utc),
                limit=20,
                order_by=2,
            ),
        )

    async def get_new_events(self) -> list[MotionEvent]:
        assert self._client, "Call authenticate() first"

        try:
            raw_events = await self._fetch_events()
        except WyzeApiError as exc:
            if "expired" in str(exc).lower() or "2001" in str(exc):
                await self._reauth()
                try:
                    raw_events = await self._fetch_events()
                except Exception:
                    _LOGGER.exception("Wyze retry failed after re-auth")
                    return []
            else:
                _LOGGER.exception("Wyze API error")
                return []
        except Exception:
            _LOGGER.exception("Failed to fetch Wyze events")
            return []

        self._last_check = datetime.now(tz=timezone.utc)

        events = []
        for ev in raw_events:
            event_key = str(ev.id)
            if event_key in self._seen_events:
                continue
            self._seen_events.add(event_key)

            name = self._mac_to_name.get(ev.mac, ev.mac)

            # Get thumbnail URL from file list
            thumbnail_url = ""
            for f in (ev.files or []):
                if f.url:
                    thumbnail_url = f.url
                    break

            # Extract AI tags (Person, Vehicle, Pet, etc.)
            tags = [t.description for t in (ev.tags or []) if t]
            tag_str = ", ".join(tags) if tags else ""

            events.append(MotionEvent(
                camera_name=name,
                brand="wyze",
                thumbnail_url=thumbnail_url,
                timestamp=str(ev.time) if ev.time else "",
                tags=tag_str,
            ))

        if len(self._seen_events) > 500:
            self._seen_events = set(list(self._seen_events)[-200:])

        return events

    async def save_snapshot(self, camera_name: str, dest: Path, clip_url: str = "", thumbnail_url: str = "") -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        filepath = dest / f"{camera_name}.jpg"

        if thumbnail_url:
            headers = {"User-Agent": "Wyze/2.44.5.3"}
            async with aiohttp.ClientSession(headers=headers) as session:
                async with session.get(thumbnail_url) as resp:
                    if resp.status == 200:
                        filepath.write_bytes(await resp.read())
                        return filepath

        raise RuntimeError(f"No image available for {camera_name}")

    async def close(self) -> None:
        self._client = None

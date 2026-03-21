"""Tuya camera source implementation.

Works with ieGeek, Ctronics, and other white-label Tuya-based cameras.
Requires a Tuya IoT Platform account (https://iot.tuya.com) with a
Cloud Project linked to your Smart Life / brand app account.

Data center endpoints:
  us  -> openapi.tuyaus.com
  eu  -> openapi.tuyaeu.com
  cn  -> openapi.tuyacn.com
  in  -> openapi.tuyain.com
"""

import asyncio
import hashlib
import hmac
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

import aiohttp

from dolly.cameras.base import CameraSource, CameraInfo, MotionEvent

_LOGGER = logging.getLogger(__name__)

REGION_HOSTS = {
    "us": "openapi.tuyaus.com",
    "eu": "openapi.tuyaeu.com",
    "cn": "openapi.tuyacn.com",
    "in": "openapi.tuyain.com",
}


class TuyaSource(CameraSource):
    """Poll Tuya Cloud API for motion events from Tuya-based cameras."""

    def __init__(
        self,
        access_id: str,
        access_secret: str,
        region: str = "us",
        device_ids: list[str] | None = None,
    ):
        self._access_id = access_id
        self._access_secret = access_secret
        self._host = REGION_HOSTS.get(region, REGION_HOSTS["us"])
        self._base_url = f"https://{self._host}"
        self._device_ids = device_ids or []
        self._token: str = ""
        self._token_expiry: float = 0
        self._device_names: dict[str, str] = {}
        self._seen_events: set[str] = set()
        self._last_check_ms: int = 0
        self._session: aiohttp.ClientSession | None = None

    # -- Auth helpers ----------------------------------------------------------

    def _sign(self, method: str, path: str, body: str = "", *, use_token: bool = True) -> dict:
        """Build signed headers for a Tuya Cloud API request."""
        t = str(int(time.time() * 1000))
        content_hash = hashlib.sha256(body.encode()).hexdigest()

        string_to_sign = "\n".join([method, content_hash, "", path])
        sign_str = self._access_id
        if use_token and self._token:
            sign_str += self._token
        sign_str += t + string_to_sign

        signature = hmac.new(
            self._access_secret.encode(),
            sign_str.encode(),
            hashlib.sha256,
        ).hexdigest().upper()

        headers = {
            "client_id": self._access_id,
            "sign": signature,
            "sign_method": "HMAC-SHA256",
            "t": t,
        }
        if use_token and self._token:
            headers["access_token"] = self._token
        return headers

    async def _request(self, method: str, path: str, body: str = "") -> dict:
        """Make a signed API request, refreshing the token if needed."""
        if time.time() >= self._token_expiry:
            await self._get_token()

        assert self._session
        headers = self._sign(method, path, body)
        if body:
            headers["Content-Type"] = "application/json"

        async with self._session.request(
            method, f"{self._base_url}{path}", headers=headers, data=body or None,
        ) as resp:
            data = await resp.json()

        if not data.get("success"):
            code = data.get("code", "?")
            msg = data.get("msg", "unknown error")
            # Token expired mid-session — refresh and retry once
            if code in (1010, 1011):
                await self._get_token()
                headers = self._sign(method, path, body)
                if body:
                    headers["Content-Type"] = "application/json"
                async with self._session.request(
                    method, f"{self._base_url}{path}", headers=headers, data=body or None,
                ) as resp:
                    data = await resp.json()
                if data.get("success"):
                    return data.get("result", {})
            _LOGGER.error("Tuya API error %s: %s (path=%s)", code, msg, path)
            return {}

        return data.get("result", {})

    async def _get_token(self) -> None:
        """Obtain or refresh an access token."""
        path = "/v1.0/token?grant_type=1"
        assert self._session
        headers = self._sign("GET", path, use_token=False)
        async with self._session.get(f"{self._base_url}{path}", headers=headers) as resp:
            data = await resp.json()

        if not data.get("success"):
            raise RuntimeError(f"Tuya auth failed: {data.get('msg', data)}")

        result = data["result"]
        self._token = result["access_token"]
        self._token_expiry = time.time() + result.get("expire_time", 7200) - 60
        _LOGGER.info("Tuya token acquired (expires in %ss)", result.get("expire_time", "?"))

    # -- CameraSource interface ------------------------------------------------

    async def authenticate(self) -> None:
        self._session = aiohttp.ClientSession()
        await self._get_token()
        await self._discover_devices()
        self._last_check_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        _LOGGER.info("Tuya authenticated — tracking %d camera(s)", len(self._device_names))

    async def _discover_devices(self) -> None:
        """Find all camera devices on the account."""
        # If user provided explicit device IDs, just fetch their names
        if self._device_ids:
            for did in self._device_ids:
                info = await self._request("GET", f"/v1.0/devices/{did}")
                if info:
                    self._device_names[did] = info.get("name", did)
            return

        # Otherwise discover all devices and filter to cameras
        result = await self._request("GET", "/v1.0/users/devices")
        if not result:
            _LOGGER.warning("No devices returned from Tuya — check cloud project link")
            return

        devices = result if isinstance(result, list) else result.get("devices", result.get("list", []))
        for d in devices:
            cat = d.get("category", "")
            # sp = smart camera, dj = doorbell, jtmspro = NVR
            if cat in ("sp", "dj", "jtmspro"):
                did = d["id"]
                self._device_names[did] = d.get("name", did)

    async def refresh(self) -> None:
        await self._discover_devices()

    async def list_cameras(self) -> list[CameraInfo]:
        cameras = []
        for did, name in self._device_names.items():
            info = await self._request("GET", f"/v1.0/devices/{did}")
            cameras.append(CameraInfo(
                name=name,
                brand="tuya",
                model=info.get("product_name", ""),
                armed=info.get("online", False),
                extra={"device_id": did, "category": info.get("category", "")},
            ))
        return cameras

    async def get_new_events(self) -> list[MotionEvent]:
        now_ms = int(datetime.now(tz=timezone.utc).timestamp() * 1000)
        events: list[MotionEvent] = []

        for did, name in self._device_names.items():
            try:
                path = f"/v1.0/devices/{did}/logs?type=7&start_time={self._last_check_ms}&end_time={now_ms}"
                result = await self._request("GET", path)

                logs = []
                if isinstance(result, dict):
                    logs = result.get("logs", result.get("list", []))
                elif isinstance(result, list):
                    logs = result

                for log in logs:
                    event_key = f"{did}:{log.get('event_time', log.get('id', ''))}"
                    if event_key in self._seen_events:
                        continue
                    self._seen_events.add(event_key)

                    ts = log.get("event_time", "")
                    if isinstance(ts, int):
                        ts = datetime.fromtimestamp(ts / 1000, tz=timezone.utc).isoformat()

                    events.append(MotionEvent(
                        camera_name=name.strip(),
                        brand="tuya",
                        timestamp=str(ts),
                    ))
            except Exception:
                _LOGGER.exception("Failed to fetch Tuya events for %s (%s)", name, did)

        self._last_check_ms = now_ms

        if len(self._seen_events) > 500:
            self._seen_events = set(list(self._seen_events)[-200:])

        return events

    async def save_snapshot(self, camera_name: str, dest: Path, clip_url: str = "", thumbnail_url: str = "") -> Path:
        dest.mkdir(parents=True, exist_ok=True)
        filepath = dest / f"{camera_name}.jpg"

        # Try thumbnail URL if provided
        if thumbnail_url and self._session:
            async with self._session.get(thumbnail_url) as resp:
                if resp.status == 200:
                    filepath.write_bytes(await resp.read())
                    return filepath

        # Try fetching a snapshot via Tuya stream API
        did = None
        for d, n in self._device_names.items():
            if n.strip() == camera_name:
                did = d
                break

        if did:
            result = await self._request("GET", f"/v1.0/devices/{did}/stream/actions/snapshot")
            url = result.get("url", "") if isinstance(result, dict) else ""
            if url and self._session:
                async with self._session.get(url) as resp:
                    if resp.status == 200:
                        filepath.write_bytes(await resp.read())
                        return filepath

        _LOGGER.warning("No snapshot available for %s — sending without image", camera_name)
        raise RuntimeError(f"No image available for {camera_name}")

    async def close(self) -> None:
        if self._session:
            await self._session.close()
            self._session = None

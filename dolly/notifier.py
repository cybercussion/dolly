"""Send rich image notifications via ntfy."""

import asyncio
import logging
from pathlib import Path

import aiohttp

_LOGGER = logging.getLogger(__name__)

_MAX_RETRIES = 3
_BACKOFF_BASE = 2  # seconds — doubles each attempt
_REQUEST_TIMEOUT = aiohttp.ClientTimeout(total=15)


class NtfyNotifier:
    def __init__(self, url: str, topic: str):
        self._url = url.rstrip("/")
        self._topic = topic
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(timeout=_REQUEST_TIMEOUT)
        return self._session

    async def _reset_session(self) -> None:
        """Close and discard the session so the next call gets a fresh one."""
        if self._session and not self._session.closed:
            await self._session.close()
        self._session = None

    async def send(
        self,
        title: str,
        message: str,
        image_path: Path | None = None,
        priority: str = "high",
        tags: str | None = None,
    ) -> bool:
        """Push a notification to ntfy, optionally with an image attachment.

        Retries up to _MAX_RETRIES times with exponential backoff on
        connection errors or timeouts (e.g. after an IP change).

        When an image is attached, ntfy delivers it as a BigPictureStyle
        notification on Android — which is what surfaces images on Wear OS.
        """
        endpoint = f"{self._url}/{self._topic}"

        headers = {
            "Title": title,
            "Priority": priority,
        }

        if tags:
            headers["Tags"] = tags

        headers["Message"] = message

        image_data: bytes | None = None
        if image_path and image_path.exists():
            with open(image_path, "rb") as f:
                image_data = f.read()

        for attempt in range(_MAX_RETRIES):
            session = await self._ensure_session()
            try:
                if image_data is not None:
                    async with session.put(endpoint, data=image_data, headers=headers) as resp:
                        if resp.status == 200:
                            _LOGGER.info("Notification sent: %s", title)
                            return True
                        _LOGGER.error("ntfy responded %s: %s", resp.status, await resp.text())
                        return False  # server error, don't retry
                else:
                    async with session.post(endpoint, headers=headers) as resp:
                        if resp.status == 200:
                            _LOGGER.info("Notification sent (no image): %s", title)
                            return True
                        _LOGGER.error("ntfy responded %s: %s", resp.status, await resp.text())
                        return False
            except (aiohttp.ClientError, asyncio.TimeoutError) as e:
                delay = _BACKOFF_BASE ** attempt
                _LOGGER.warning(
                    "ntfy attempt %d/%d failed (%s), retrying in %ds",
                    attempt + 1, _MAX_RETRIES, e, delay,
                )
                await self._reset_session()
                await asyncio.sleep(delay)

        _LOGGER.error("Failed to send notification after %d attempts: %s", _MAX_RETRIES, title)
        return False

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

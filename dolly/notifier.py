"""Send rich image notifications via ntfy."""

import logging
from pathlib import Path

import aiohttp

_LOGGER = logging.getLogger(__name__)


class NtfyNotifier:
    def __init__(self, url: str, topic: str):
        self._url = url.rstrip("/")
        self._topic = topic
        self._session: aiohttp.ClientSession | None = None

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession()
        return self._session

    async def send(
        self,
        title: str,
        message: str,
        image_path: Path | None = None,
        priority: str = "high",
    ) -> bool:
        """Push a notification to ntfy, optionally with an image attachment.

        When an image is attached, ntfy delivers it as a BigPictureStyle
        notification on Android — which is what surfaces images on Wear OS.
        """
        session = await self._ensure_session()
        endpoint = f"{self._url}/{self._topic}"

        headers = {
            "Title": title,
            "Priority": priority,
        }

        headers["Message"] = message

        try:
            if image_path and image_path.exists():
                with open(image_path, "rb") as f:
                    data = f.read()
                async with session.put(endpoint, data=data, headers=headers) as resp:
                    if resp.status == 200:
                        _LOGGER.info("Notification sent: %s", title)
                        return True
                    _LOGGER.error("ntfy responded %s: %s", resp.status, await resp.text())
            else:
                async with session.post(endpoint, headers=headers) as resp:
                    if resp.status == 200:
                        _LOGGER.info("Notification sent (no image): %s", title)
                        return True
                    _LOGGER.error("ntfy responded %s: %s", resp.status, await resp.text())
        except aiohttp.ClientError as e:
            _LOGGER.error("Failed to send notification: %s", e)

        return False

    async def close(self) -> None:
        if self._session and not self._session.closed:
            await self._session.close()

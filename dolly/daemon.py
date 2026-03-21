"""Main daemon loop — poll cameras for new motion clips, push notifications."""

import asyncio
import logging
import signal
from datetime import datetime
from pathlib import Path

from dolly.cameras.base import CameraSource, MotionEvent
from dolly.notifier import NtfyNotifier

_LOGGER = logging.getLogger(__name__)


class Dolly:
    def __init__(
        self,
        sources: list[CameraSource],
        notifier: NtfyNotifier,
        poll_interval: int = 30,
        snapshot_dir: str = "/tmp/dolly_snapshots",
    ):
        self._sources = sources
        self._notifier = notifier
        self._poll_interval = poll_interval
        self._snapshot_dir = Path(snapshot_dir)
        self._running = False
        self._stopped = False

    async def start(self) -> None:
        """Authenticate all sources and start the poll loop."""
        for source in self._sources:
            try:
                await source.authenticate()
            except RuntimeError as e:
                _LOGGER.error("%s — waiting 5 minutes before retry", e)
                await asyncio.sleep(300)
                raise

        self._running = True
        _LOGGER.info(
            "Dolly started — polling %d source(s) every %ds",
            len(self._sources),
            self._poll_interval,
        )

        while self._running:
            try:
                await self._poll()
            except Exception:
                _LOGGER.exception("Error during poll cycle")
            await asyncio.sleep(self._poll_interval)

    async def stop(self) -> None:
        """Shut down gracefully (safe to call more than once)."""
        if self._stopped:
            return
        self._stopped = True
        _LOGGER.info("Shutting down...")
        self._running = False
        for source in self._sources:
            try:
                await source.close()
            except Exception:
                _LOGGER.exception("Error closing %s", type(source).__name__)
        await self._notifier.close()

    async def _poll(self) -> None:
        """Single poll cycle across all sources."""
        for source in self._sources:
            src_name = type(source).__name__
            try:
                events = await source.get_new_events()
            except Exception:
                _LOGGER.exception("Failed to poll %s", src_name)
                continue

            for event in events:
                _LOGGER.info(
                    "Motion: %s [%s] at %s",
                    event.camera_name, event.network, event.timestamp,
                )
                await self._handle_event(source, event)

    async def _handle_event(self, source: CameraSource, event: MotionEvent) -> None:
        """Fetch snapshot and send notification."""
        image_path = None
        try:
            image_path = await source.save_snapshot(
                event.camera_name, self._snapshot_dir, event.clip_url, event.thumbnail_url
            )
            _LOGGER.info("Snapshot saved: %s", image_path)
        except Exception:
            _LOGGER.warning("Could not save snapshot for %s", event.camera_name)

        timestamp = datetime.now().strftime("%I:%M %p")
        title = f"{event.camera_name} ({event.tags})" if event.tags else event.camera_name
        message = f"{event.network} — {timestamp}"

        await self._notifier.send(
            title=title,
            message=message,
            image_path=image_path,
        )


def setup_signal_handlers(daemon: Dolly, loop: asyncio.AbstractEventLoop) -> None:
    """Register SIGINT/SIGTERM for clean shutdown."""
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, lambda: asyncio.ensure_future(daemon.stop()))

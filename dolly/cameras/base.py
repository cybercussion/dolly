"""Abstract camera source interface."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CameraInfo:
    name: str
    brand: str
    model: str = ""
    network: str = ""
    armed: bool = False
    motion_detected: bool = False
    extra: dict = field(default_factory=dict)


@dataclass
class MotionEvent:
    camera_name: str
    brand: str
    network: str = ""
    clip_url: str = ""
    thumbnail_url: str = ""
    timestamp: str = ""
    tags: str = ""


class CameraSource(ABC):
    """Interface that all camera integrations must implement."""

    @abstractmethod
    async def authenticate(self) -> None:
        """Authenticate with the camera service."""

    @abstractmethod
    async def refresh(self) -> None:
        """Refresh camera state from the service."""

    @abstractmethod
    async def list_cameras(self) -> list[CameraInfo]:
        """Return info for all cameras on the account."""

    @abstractmethod
    async def get_new_events(self) -> list[MotionEvent]:
        """Return motion events since last check."""

    @abstractmethod
    async def save_snapshot(self, camera_name: str, dest: Path, clip_url: str = "", thumbnail_url: str = "") -> Path:
        """Extract a frame from a motion clip or fetch the latest thumbnail.

        Returns the path to the saved image file.
        """

    @abstractmethod
    async def close(self) -> None:
        """Clean up resources."""

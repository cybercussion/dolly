"""Load and validate YAML configuration."""

from pathlib import Path

import yaml

from dolly.cameras.base import CameraSource
from dolly.cameras.blink import BlinkSource
from dolly.cameras.tuya import TuyaSource
from dolly.cameras.wyze import WyzeSource

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parent.parent / "config.yaml"


def load_config(path: Path | None = None) -> dict:
    path = path or DEFAULT_CONFIG_PATH
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found at {path}. Copy config.yaml.example to config.yaml and fill in your credentials."
        )
    with open(path) as f:
        cfg = yaml.safe_load(f)

    if not cfg.get("cameras"):
        raise ValueError("At least one camera source must be configured")

    return cfg


def build_sources(cfg: dict) -> list[CameraSource]:
    """Instantiate camera sources from config."""
    sources = []
    for entry in cfg["cameras"]:
        kind = entry["source"]
        if kind == "blink":
            sources.append(BlinkSource(entry["username"], entry["password"]))
        elif kind == "tuya":
            sources.append(TuyaSource(
                access_id=entry["access_id"],
                access_secret=entry["access_secret"],
                region=entry.get("region", "us"),
                device_ids=entry.get("device_ids"),
            ))
        elif kind == "wyze":
            sources.append(WyzeSource(
                email=entry["email"],
                password=entry["password"],
                key_id=entry.get("key_id", ""),
                api_key=entry.get("api_key", ""),
            ))
        else:
            raise ValueError(f"Unknown camera source: {kind}")
    return sources

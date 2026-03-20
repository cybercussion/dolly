#!/usr/bin/env python3
"""Debug: check what wyze-sdk returns."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dolly.config import load_config
from wyze_sdk import Client


def main() -> None:
    cfg = load_config()
    wyze_cfg = None
    for entry in cfg["cameras"]:
        if entry["source"] == "wyze":
            wyze_cfg = entry
            break

    if not wyze_cfg:
        print("No Wyze config found")
        return

    print(f"Logging in as {wyze_cfg['email']}...")
    client = Client(
        email=wyze_cfg["email"],
        password=wyze_cfg["password"],
        key_id=wyze_cfg.get("key_id") or None,
        api_key=wyze_cfg.get("api_key") or None,
    )

    print(f"Token: {client._token[:20]}..." if client._token else "No token!")

    print("\n=== All Devices ===")
    try:
        devices = client.devices_list()
        print(f"Found {len(devices)} total devices")
        for d in devices:
            print(f"  {d.nickname} | type={d.type} | model={d.product.model}")
    except Exception as e:
        print(f"devices_list error: {e}")

    print("\n=== Cameras ===")
    try:
        cams = client.cameras.list()
        print(f"Found {len(cams)} cameras")
        for c in cams:
            print(f"  {c.nickname} | model={c.product.model} | mac={c.mac}")
    except Exception as e:
        print(f"cameras.list error: {e}")


if __name__ == "__main__":
    main()

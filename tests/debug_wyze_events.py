#!/usr/bin/env python3
"""Debug: dump Wyze event data."""

import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dolly.config import load_config
from wyze_sdk import Client
from wyze_sdk.models.events import EventAlarmType


def main() -> None:
    cfg = load_config()
    wyze_cfg = None
    for entry in cfg["cameras"]:
        if entry["source"] == "wyze":
            wyze_cfg = entry
            break

    client = Client(
        email=wyze_cfg["email"],
        password=wyze_cfg["password"],
        key_id=wyze_cfg.get("key_id") or None,
        api_key=wyze_cfg.get("api_key") or None,
    )

    events = client.events.list(
        event_values=[EventAlarmType.MOTION],
        begin=datetime.now(tz=timezone.utc) - timedelta(hours=1),
        end=datetime.now(tz=timezone.utc),
        limit=5,
        order_by=2,
    )

    print(f"Found {len(events)} events\n")
    for ev in events:
        print(f"Camera MAC: {ev.mac}")
        print(f"Time: {ev.time}")
        print(f"Alarm: {ev.alarm_type}")
        print(f"Tags: {ev.tags}")
        print(f"Files ({len(ev.files)}):")
        for f in ev.files:
            print(f"  type={f.type} url={f.url}")
        print()


if __name__ == "__main__":
    main()

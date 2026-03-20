#!/usr/bin/env python3
"""Test Wyze thumbnail with Wyze app User-Agent."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dolly.config import load_config
from wyze_sdk import Client
from wyze_sdk.models.events import EventAlarmType

cfg = load_config()
wyze_cfg = [c for c in cfg["cameras"] if c["source"] == "wyze"][0]

client = Client(
    email=wyze_cfg["email"], password=wyze_cfg["password"],
    key_id=wyze_cfg.get("key_id"), api_key=wyze_cfg.get("api_key"),
)

ev = client.events.list(
    event_values=[EventAlarmType.MOTION],
    begin=datetime.now(tz=timezone.utc) - timedelta(hours=2),
    end=datetime.now(tz=timezone.utc), limit=1, order_by=2,
)[0]

url = ev.files[0].url
r = requests.get(url, headers={"User-Agent": "Wyze/2.44.5.3"})
print(f"Status: {r.status_code} ({len(r.content)} bytes)")

if r.status_code == 200:
    Path("/tmp/dolly_snapshots").mkdir(exist_ok=True)
    Path("/tmp/dolly_snapshots/wyze_test.jpg").write_bytes(r.content)
    print("Saved to /tmp/dolly_snapshots/wyze_test.jpg")
else:
    print(f"Body: {r.text}")

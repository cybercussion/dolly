#!/usr/bin/env python3
"""Debug: dump raw Blink API responses to find motion events."""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dolly.config import load_config, build_sources
from blinkpy import api
from blinkpy.helpers.util import get_time


async def main() -> None:
    cfg = load_config()
    sources = build_sources(cfg)
    source = sources[0]
    await source.authenticate()
    blink = source._blink

    # 1. Homescreen (returns raw response, need to parse manually)
    print("=== Homescreen ===")
    url = f"{blink.urls.base_url}/api/v3/accounts/{blink.account_id}/homescreen"
    resp = await api.http_get(blink, url)
    if resp and isinstance(resp, dict):
        print(json.dumps(resp, indent=2, default=str)[:3000])
    else:
        print(f"Type: {type(resp)}, value: {str(resp)[:200]}")

    # 2. Media changed with correct timestamp format
    print("\n=== Media Changed (last 24h) ===")
    since = get_time(time.time() - 86400)
    url = (
        f"{blink.urls.base_url}/api/v1/accounts/{blink.account_id}"
        f"/media/changed?since={since}&page=1"
    )
    resp = await api.http_get(blink, url)
    if resp and isinstance(resp, dict):
        media = resp.get("media", [])
        print(f"Found {len(media)} entries")
        for entry in media[:10]:
            print(f"  {entry.get('device_name')}: {entry.get('created_at')} | {str(entry.get('media', ''))[:60]}")
        if not media:
            print(f"  Raw: {json.dumps(resp, default=str)[:500]}")
    else:
        print(f"  Response: {str(resp)[:500]}")

    # 3. Notification flags
    print("\n=== Notification Flags ===")
    resp = await api.request_notification_flags(blink, force=True)
    if resp:
        print(json.dumps(resp, indent=2, default=str)[:500])

    # 4. Per-network status (may have recent events)
    print("\n=== Network Status ===")
    for sync_name, sync_mod in blink.sync.items():
        resp = await api.request_network_status(blink, sync_mod.network_id)
        if resp and isinstance(resp, dict):
            print(f"\n{sync_name}:")
            print(json.dumps(resp, indent=2, default=str)[:1000])

    await source.close()


if __name__ == "__main__":
    asyncio.run(main())

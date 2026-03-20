#!/usr/bin/env python3
"""Quick check: what does a media/changed entry actually look like?"""

import asyncio
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dolly.config import load_config, build_sources
from blinkpy import api


async def main() -> None:
    cfg = load_config()
    sources = build_sources(cfg)
    source = sources[0]
    await source.authenticate()
    blink = source._blink

    since = datetime.fromtimestamp(
        time.time() - 3600, tz=timezone.utc
    ).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    url = (
        f"{blink.urls.base_url}/api/v1/accounts/{blink.account_id}"
        f"/media/changed?since={since}&page=1"
    )
    resp = await api.http_get(blink, url)
    media = resp.get("media", []) if isinstance(resp, dict) else []

    if media:
        print("First entry (full):")
        print(json.dumps(media[0], indent=2, default=str))
    else:
        print("No media entries in last hour")

    await source.close()


if __name__ == "__main__":
    asyncio.run(main())

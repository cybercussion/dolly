#!/usr/bin/env python3
"""One-shot check: show thumbnail state per camera and detect new events."""

import asyncio
import sys
from pathlib import Path
from urllib.parse import urlparse, parse_qs

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dolly.config import load_config, build_sources


async def main() -> None:
    cfg = load_config()
    sources = build_sources(cfg)

    for source in sources:
        await source.authenticate()

        print(f"\n{'Name':<25} {'Network':<15} {'Thumbnail TS'}")
        print("-" * 60)
        for name, cam in source._blink.cameras.items():
            network = cam.sync.name if cam.sync else ""
            # Extract ts param from thumbnail URL
            ts = ""
            if cam.thumbnail:
                qs = parse_qs(urlparse(cam.thumbnail).query)
                ts = qs.get("ts", [""])[0]
            print(f"{name:<25} {network:<15} {ts}")

        print("\nChecking for new events...")
        events = await source.get_new_events()
        if events:
            for e in events:
                print(f"  NEW: {e.camera_name} [{e.network}]")
        else:
            print("  No new events (expected on first run).")
        print("  Run again after triggering a camera to see new events.")

        await source.close()


if __name__ == "__main__":
    asyncio.run(main())

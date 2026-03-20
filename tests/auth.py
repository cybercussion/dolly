#!/usr/bin/env python3
"""Test script: authenticate with all configured camera sources and list cameras.

Usage:
    python test_auth.py
    python test_auth.py --config /path/to/config.yaml

For Blink: on first run you'll be prompted for a 2FA code sent to your email/phone.
Subsequent runs use cached credentials from blink.json.
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dolly.config import load_config, build_sources


async def main(config_path: Path | None = None) -> None:
    try:
        cfg = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    sources = build_sources(cfg)

    for source in sources:
        brand = type(source).__name__.replace("Source", "")
        print(f"\n{'='*40}")
        print(f"  {brand}")
        print(f"{'='*40}")

        try:
            await source.authenticate()
            cameras = await source.list_cameras()

            if not cameras:
                print("  No cameras found.")
                continue

            print(f"  Found {len(cameras)} camera(s):\n")
            for cam in cameras:
                print(f"  - {cam.name}")
                if cam.network:
                    print(f"    Network : {cam.network}")
                if cam.model:
                    print(f"    Model   : {cam.model}")
                print(f"    Armed   : {cam.armed}")
                print(f"    Motion  : {cam.motion_detected}")
                if cam.extra:
                    for k, v in cam.extra.items():
                        print(f"    {k:8s}: {v}")
                print()
        except Exception as e:
            print(f"  Error: {e}", file=sys.stderr)
        finally:
            await source.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test camera authentication")
    parser.add_argument("--config", type=Path, help="Path to config.yaml")
    args = parser.parse_args()

    asyncio.run(main(args.config))

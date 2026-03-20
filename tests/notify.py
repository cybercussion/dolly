#!/usr/bin/env python3
"""Test script: send a test notification to ntfy.

Usage:
    python test_ntfy.py

Subscribe to your topic first:
    - Install ntfy app on Android
    - Subscribe to the topic in config.yaml (default: dolly-blink)
"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dolly.config import load_config
from dolly.notifier import NtfyNotifier


async def main() -> None:
    try:
        cfg = load_config()
    except (FileNotFoundError, ValueError) as e:
        print(f"Config error: {e}", file=sys.stderr)
        sys.exit(1)

    ntfy_cfg = cfg["ntfy"]
    notifier = NtfyNotifier(ntfy_cfg["url"], ntfy_cfg["topic"])

    print(f"Sending test notification to {ntfy_cfg['url']}/{ntfy_cfg['topic']}...")

    ok = await notifier.send(
        title="Dolly Test",
        message="If you see this, ntfy is working!",
        priority="default",
        tags="white_check_mark,test_tube",
    )

    if ok:
        print("Sent! Check your phone.")
    else:
        print("Failed to send. Check your ntfy config.", file=sys.stderr)

    await notifier.close()


if __name__ == "__main__":
    asyncio.run(main())

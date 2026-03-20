#!/usr/bin/env python3
"""Dolly daemon entry point."""

import argparse
import asyncio
import logging
import sys
from pathlib import Path

from dolly.config import load_config, build_sources
from dolly.notifier import NtfyNotifier
from dolly.daemon import Dolly, setup_signal_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logging.getLogger("wyze_sdk").setLevel(logging.WARNING)
logging.getLogger("blinkpy").setLevel(logging.WARNING)


async def main(config_path: Path | None = None) -> None:
    try:
        cfg = load_config(config_path)
    except (FileNotFoundError, ValueError) as e:
        logging.error("Config error: %s", e)
        sys.exit(1)

    sources = build_sources(cfg)
    ntfy_cfg = cfg["ntfy"]
    daemon_cfg = cfg.get("daemon", {})

    notifier = NtfyNotifier(ntfy_cfg["url"], ntfy_cfg["topic"])

    daemon = Dolly(
        sources=sources,
        notifier=notifier,
        poll_interval=daemon_cfg.get("poll_interval", 30),
        snapshot_dir=daemon_cfg.get("snapshot_dir", "/tmp/dolly_snapshots"),
    )

    loop = asyncio.get_running_loop()
    setup_signal_handlers(daemon, loop)

    await daemon.start()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dolly camera motion daemon")
    parser.add_argument("--config", type=Path, help="Path to config.yaml")
    args = parser.parse_args()

    asyncio.run(main(args.config))

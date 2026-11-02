#!/usr/bin/env python3
"""Standalone B3 smoke payload, run explicitly by Host-only tests only.

No network, peripheral, FPGA, flash, subprocess, import-time or service actions.
A successful run is NOT evidence of physical programming capability.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

VERSION = "0.1.0"


def main() -> int:
    parser = argparse.ArgumentParser(description="Read staged Bundle v3 data only")
    parser.add_argument("--root", type=Path, required=True,
                        help="Verified staging root (not the production root)")
    args = parser.parse_args()
    root = args.root.resolve(strict=True)
    device_path = root / "payload/packages/ic-catalog/data/device.json"
    geometry_path = root / "payload/packages/programming-profile/data/geometry.json"
    device = json.loads(device_path.read_text(encoding="utf-8"))
    geometry = json.loads(geometry_path.read_text(encoding="utf-8"))
    if (device.get("fixture_only") is not True
            or geometry.get("fixture_only") is not True
            or device.get("icpn") != "STM32F103C8T6"
            or geometry.get("flash_bytes") != 65536
            or geometry.get("page_bytes") != 1024
            or geometry.get("flash_base") != "0x08000000"):
        raise ValueError("SMOKE_FIXTURE_VALIDATION_FAILED")
    print(f"SMOKE_VERSION={VERSION}")
    print(f"ICPN={device['icpn']}")
    print(f"FLASH_BYTES={geometry['flash_bytes']}")
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

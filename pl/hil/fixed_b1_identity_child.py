"""F1-B B1 isolated read-only native MMIO child. NEVER import for probing.

Only the future separately approved Z2 root supervisor may invoke the
--internal-read-identity entry. No FPGA Manager writes, SWD writes or reset.
"""
from __future__ import annotations

import argparse
import json
import os
import platform
import sys

from pl.hil.fixed_b1_contract import (
    B1Blocked, FPGA_BASE, IDENTITY_OFFSETS, read_identity,
)


def read_with_port(port) -> dict:
    """Testable injected native 32-bit reader, zero writes."""
    return read_identity(port.read32)


def live_read_once() -> dict:
    """Real 32-bit ARMv7 /dev/mem. Must be isolated by caller OS process."""
    if (os.geteuid() != 0 or platform.machine() != "armv7l"
            or sys.byteorder != "little"
            or tuple(sys.version_info[:3]) != (3, 12, 13)
            or not os.path.realpath(sys.executable).startswith(
                "/opt/plasma/python/3.12.13/")):
        raise B1Blocked("B1_TARGET_NATIVE_RUNTIME_DENIED")
    from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOAperture
    with LinuxMMIO((
        MMIOAperture(FPGA_BASE, frozenset(IDENTITY_OFFSETS), frozenset()),
    ), device="/dev/mem", owner_lock="/run/lock/plasma-mmio.lock",
                   readonly=True) as mmio:
        return read_with_port(mmio)


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--internal-read-identity", action="store_true")
    args = p.parse_args()
    if not args.internal_read_identity:
        return 2
    try:
        result = live_read_once()
    except Exception:
        print("F1B_IDENTITY_CHILD_BLOCKED", file=sys.stderr)
        return 2
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

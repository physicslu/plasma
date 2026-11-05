#!/usr/bin/env python3
"""Deterministic host-only observations for existing Path 2 cpu-only dispatch.

No shell, subprocess, network, device, file traversal or arbitrary parameters.
Run only through the existing owner-authenticated, source-pinned Work Order
and SWPC Bubblewrap CPU-only sandbox. Stdout is ordinary evidence, not an
automatic acceptance of the surrounding task.
"""
from __future__ import annotations

import os
import sys


def observe(operation: str) -> str:
    """Return one bounded, single-line host-local observation."""
    if operation == "hostname":
        return os.uname().nodename
    if operation == "kernel-release":
        return os.uname().release
    if operation == "python-version":
        v = sys.version_info
        return f"{v.major}.{v.minor}.{v.micro}"
    raise ValueError("UNSUPPORTED_HOST_OBSERVATION")


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    if len(args) != 1:
        return 2
    try:
        result = observe(args[0])
    except ValueError:
        return 2
    if not result or len(result) > 256 or any(
        ord(ch) < 32 or ord(ch) == 127 for ch in result
    ):
        return 2
    print(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

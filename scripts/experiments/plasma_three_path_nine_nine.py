#!/usr/bin/env python3
"""Deterministic 9x9 multiplication CSV for the PLASMA three-path smoke test.

No network, hardware, dependencies, or persistent files. The identical
byte stream is the acceptance contract for all three execution paths.
"""
from __future__ import annotations

import sys


def render_table() -> str:
    header = "multiplicand,multiplier,product\n"
    rows = (
        f"{a},{b},{a * b}\n"
        for a in range(1, 10)
        for b in range(1, 10)
    )
    return header + "".join(rows)


def main() -> int:
    sys.stdout.write(render_table())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

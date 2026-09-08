#!/usr/bin/env python3
"""Phase 4.3J STM32F2 admission entry point backed by the bounded planner."""

from __future__ import annotations

import sys

from stm32f2_bounded_admission import main


if __name__ == "__main__":
    raise SystemExit(main(["--phase", "4.3J", *sys.argv[1:]]))

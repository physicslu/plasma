#!/usr/bin/env python3
"""Phase 4.3I STM32F2 policy entry point backed by the bounded policy engine."""

from __future__ import annotations

import sys

from stm32f2_bounded_policy import main


if __name__ == "__main__":
    raise SystemExit(main(["--phase", "4.3I", *sys.argv[1:]]))

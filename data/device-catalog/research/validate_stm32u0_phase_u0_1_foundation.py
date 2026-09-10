#!/usr/bin/env python3
"""Replay the immutable STM32U0 Phase U0.1 foundation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from stm32u0_phase_u0_1_foundation import build_foundation_report, read_catalog

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32u0-phase-u0.1-foundation-baseline.json"
EXPECTED_BASELINE_SHA256 = "55fd41eaa32c50571d4081321ce293ff87294c98db230386ddff418ee0579a20"


def main() -> None:
    observed_sha = hashlib.sha256(BASELINE.read_bytes()).hexdigest()
    if observed_sha != EXPECTED_BASELINE_SHA256:
        raise SystemExit(
            f"STM32U0 U0.1 foundation baseline SHA-256 drifted: {observed_sha}"
        )

    baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
    observed = build_foundation_report(read_catalog())
    if observed != baseline:
        raise SystemExit("STM32U0 U0.1 foundation replay does not match frozen baseline")

    claims = observed.get("claims")
    if not isinstance(claims, dict) or not claims or any(value is not False for value in claims.values()):
        raise SystemExit("STM32U0 U0.1 authority/capability boundary escaped fail-closed state")

    print(
        "STM32U0 U0.1 foundation replay PASS: "
        "48 source rows / 42 ordering patterns / 6 CMSIS aliases / "
        "3 deterministic representatives / 8 retained active exact ICPNs"
    )


if __name__ == "__main__":
    main()

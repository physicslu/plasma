#!/usr/bin/env python3
"""Validate the frozen STM32C0 C0.4 read-only admission plan."""
from __future__ import annotations

import json
import sys

from device_catalog_admission_framework import AdmissionError
from stm32c0_phase_c0_4_admission import (
    EXPECTED_ADMITTABLE_COUNT,
    EXPECTED_CAPABILITY_UNRESOLVED,
    admission_plan_is_clean,
    admission_summary,
    build_admission_plan,
    validate_frozen_plan,
)


def main() -> int:
    plan = build_admission_plan()
    if not admission_plan_is_clean(plan):
        raise AdmissionError("STM32C0 C0.4 admission plan is not clean")
    validate_frozen_plan(plan)
    if plan.get("capability_admittable_count") != EXPECTED_ADMITTABLE_COUNT:
        raise AdmissionError("STM32C0 C0.4 admittable count drifted")
    if set(plan.get("capability_unresolved_exact_icpns", [])) != set(EXPECTED_CAPABILITY_UNRESOLVED):
        raise AdmissionError("STM32C0 C0.4 unresolved exact set drifted")
    if plan.get("canonical_write_applied") is not False or plan.get("production_write_applied") is not False:
        raise AdmissionError("STM32C0 C0.4 must remain read-only")
    summary = admission_summary(plan)
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("STM32C0 C0.4 admission validation: VALID")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (AdmissionError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)

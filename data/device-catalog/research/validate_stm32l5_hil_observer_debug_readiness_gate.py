#!/usr/bin/env python3
from __future__ import annotations

import json

from device_catalog_admission_framework import AdmissionError
from stm32l5_hil_observer_debug_readiness import (
    PLAN,
    _read,
    build_gate_result,
    negative_controls,
    validate_plan,
)


def main() -> int:
    result = build_gate_result()
    if result["hil_test_cells"] != 20:
        raise SystemExit("FAIL: expected 20 HIL test cells")
    if result["exact_icpn_count"] != 1862:
        raise SystemExit("FAIL: exact ICPN count drifted")
    if result["hil_execution_ready"] or result["hil_executed"]:
        raise SystemExit("FAIL: readiness gate may not claim HIL execution")
    if result["production_manifest_admission_authorized"] or result["runtime_programming_authorized"]:
        raise SystemExit("FAIL: readiness gate opened unsafe capability")

    plan = _read(PLAN)
    rejected = 0
    for name, mutated in negative_controls(plan):
        try:
            validate_plan(mutated)
        except AdmissionError:
            rejected += 1
        else:
            raise SystemExit(f"FAIL: negative control admitted: {name}")

    if rejected != 5:
        raise SystemExit(f"FAIL: expected 5 rejected negative controls, got {rejected}")

    print(json.dumps({
        **result,
        "negative_controls_rejected": rejected,
        "validation": "PASS",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

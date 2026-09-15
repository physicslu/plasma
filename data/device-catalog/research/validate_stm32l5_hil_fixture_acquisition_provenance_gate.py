#!/usr/bin/env python3
from __future__ import annotations

import json

from device_catalog_admission_framework import AdmissionError
from stm32l5_hil_fixture_acquisition_provenance import (
    PLAN,
    _read,
    build_gate_result,
    negative_controls,
    validate_plan,
)


def main() -> int:
    result = build_gate_result()
    if result["stm32l5_commercial_icpn_count"] != 49:
        raise SystemExit("FAIL: expected 49 retained STM32L5 commercial ICPNs")
    if result["full_matrix_state_specific_fixture_slots"] != 14:
        raise SystemExit("FAIL: expected 14 state-specific fixture slots")
    if result["verified_acquired_fixture_count"] != 0 or result["verified_security_state_slots"] != 0:
        raise SystemExit("FAIL: unevidenced physical hardware claimed")
    if result["fixture_inventory_bound"] or result["hil_execution_ready"] or result["hil_executed"]:
        raise SystemExit("FAIL: acquisition gate prematurely opened HIL")
    if result["production_manifest_admission_authorized"] or result["runtime_programming_authorized"]:
        raise SystemExit("FAIL: acquisition gate opened unsafe capability")
    if result["exact_icpn_count"] != 1862:
        raise SystemExit("FAIL: exact ICPN count drifted")
    if result["next_research_gate"] is not None:
        raise SystemExit("FAIL: software-only gate chain did not stop at external hardware blocker")

    plan = _read(PLAN)
    rejected = 0
    for name, mutated in negative_controls(plan):
        try:
            validate_plan(mutated)
        except AdmissionError:
            rejected += 1
        else:
            raise SystemExit(f"FAIL: negative control admitted: {name}")

    if rejected != 7:
        raise SystemExit(f"FAIL: expected 7 rejected negative controls, got {rejected}")

    print(json.dumps({
        **result,
        "negative_controls_rejected": rejected,
        "validation": "PASS",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

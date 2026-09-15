#!/usr/bin/env python3
from __future__ import annotations

import json

from device_catalog_admission_framework import AdmissionError
from stm32u3_hil_observer_debug_readiness import PLAN, build_gate_result, negative_controls, validate_plan


def main() -> int:
    result = build_gate_result()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))

    if result["production_exact_icpn_count"] != 1862:
        raise AdmissionError("Production exact ICPN count drifted")
    if result["commercial_series"] != 4:
        raise AdmissionError("commercial-series count drifted")
    if result["candidate_only_subfamilies_excluded"] != 4:
        raise AdmissionError("candidate-only exclusion count drifted")
    if result["logical_security_states"] != 7:
        raise AdmissionError("logical security-state count drifted")
    if result["hil_test_cells"] != 40:
        raise AdmissionError("HIL test-cell count drifted")
    if result["required_evidence_fields"] != 21:
        raise AdmissionError("required evidence field count drifted")
    if result["rdp2_unconditionally_terminal"] is not False:
        raise AdmissionError("RDP2 incorrectly modeled terminal")
    for key in (
        "fixture_inventory_bound", "hil_execution_ready", "hil_executed",
        "observer_hil_validated", "oem_state_observer_hil_validated",
        "debug_attach_hil_validated", "production_manifest_admission_authorized",
        "runtime_programming_authorized", "oem_key_operation_authorized",
    ):
        if result[key] is not False:
            raise AdmissionError(f"{key}: premature claim")

    for name, mutated in negative_controls(plan):
        try:
            validate_plan(mutated)
        except AdmissionError:
            continue
        raise AdmissionError(f"negative control unexpectedly passed: {name}")

    print(json.dumps(result, sort_keys=True))
    print("STM32U3 HIL observer/debug matrix readiness gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

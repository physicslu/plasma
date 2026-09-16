#!/usr/bin/env python3
from __future__ import annotations

import json

from device_catalog_admission_framework import AdmissionError
from stm32u5_hil_observer_debug_readiness import PLAN, build_gate_result, negative_controls, validate_plan


def main() -> int:
    result = build_gate_result()
    plan = json.loads(PLAN.read_text(encoding="utf-8"))

    if result["canonical_active_identity_count"] != 265:
        raise AdmissionError("canonical Active identity count drifted")
    if result["quarantined_preview_exact_icpns"] != ["STM32U5G9ZJJ3Q"]:
        raise AdmissionError("Preview quarantine drifted")
    if result["production_exact_icpn_count"] != 2017:
        raise AdmissionError("Production exact ICPN count drifted")
    if result["active_subfamilies"] != 12:
        raise AdmissionError("Active subfamily count drifted")
    if result["logical_security_states"] != 7:
        raise AdmissionError("logical security-state count drifted")
    if result["hil_test_cells"] != 120:
        raise AdmissionError("HIL test-cell count drifted")
    if result["required_evidence_fields"] != 22:
        raise AdmissionError("required evidence field count drifted")
    if result["rdp2_unconditionally_terminal"] is not False:
        raise AdmissionError("RDP2 incorrectly modeled terminal")
    if result["u5_rdp0_5_debug_semantics_resolved"] is not False:
        raise AdmissionError("U5 RDP0.5 debug semantics falsely resolved")
    if result["u5_rdp1_debug_semantics_resolved"] is not False:
        raise AdmissionError("U5 RDP1 debug semantics falsely resolved")
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
    print("STM32U5 HIL observer/debug matrix readiness gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

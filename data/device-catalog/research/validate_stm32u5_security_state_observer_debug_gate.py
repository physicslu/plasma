#!/usr/bin/env python3
from __future__ import annotations

import json

from device_catalog_admission_framework import AdmissionError
from stm32u5_security_state_observer_debug import (
    POLICY,
    build_gate_result,
    negative_controls,
    validate_policy,
)


def main() -> int:
    result = build_gate_result()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    rejected = 0
    for name, mutated in negative_controls(policy):
        try:
            validate_policy(mutated)
        except AdmissionError:
            rejected += 1
            continue
        raise AdmissionError(f"negative control unexpectedly passed: {name}")

    if rejected != 12:
        raise AdmissionError(f"negative-control rejection count drifted: {rejected}")
    if result["modeled_security_states"] != 7:
        raise AdmissionError("observer/debug state count drifted")
    if result["debug_observations_required"] != 4:
        raise AdmissionError("debug observation count drifted")
    if result["public_oem_observations_modeled"] != 4:
        raise AdmissionError("public OEM observation count drifted")
    if result["canonical_active_identity_count"] != 265:
        raise AdmissionError("canonical Active identity count drifted")
    if result["quarantined_preview_exact_icpns"] != ["STM32U5G9ZJJ3Q"]:
        raise AdmissionError("Preview quarantine drifted")
    if result["production_exact_icpn_count"] != 2017:
        raise AdmissionError("Production exact ICPN count drifted")
    if result["rdp2_unconditionally_terminal"] is not False:
        raise AdmissionError("STM32U5 RDP2 incorrectly modeled terminal")
    if result["u5_rdp0_5_debug_semantics_resolved"] is not False:
        raise AdmissionError("STM32U5 RDP0.5 debug semantics prematurely resolved")
    if result["u5_rdp1_debug_semantics_resolved"] is not False:
        raise AdmissionError("STM32U5 RDP1 debug semantics prematurely resolved")
    if result["observer_hil_validated"] is not False:
        raise AdmissionError("observer HIL claim unexpectedly enabled")
    if result["debug_attach_hil_validated"] is not False:
        raise AdmissionError("debug HIL claim unexpectedly enabled")
    if result["production_manifest_admission_authorized"] is not False:
        raise AdmissionError("Production admission unexpectedly enabled")

    print(json.dumps({**result, "negative_controls_rejected": rejected}, sort_keys=True))
    print("STM32U5 security-state observer/debug gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

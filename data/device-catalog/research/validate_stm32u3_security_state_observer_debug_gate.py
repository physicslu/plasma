#!/usr/bin/env python3
from __future__ import annotations

import json

from device_catalog_admission_framework import AdmissionError
from stm32u3_security_state_observer_debug import (
    POLICY,
    build_gate_result,
    negative_controls,
    validate_policy,
)


def main() -> int:
    result = build_gate_result()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    for name, mutated in negative_controls(policy):
        try:
            validate_policy(mutated)
        except AdmissionError:
            continue
        raise AdmissionError(f"negative control unexpectedly passed: {name}")

    if result["modeled_security_states"] != 7:
        raise AdmissionError("observer/debug state count drifted")
    if result["debug_observations_required"] != 4:
        raise AdmissionError("debug observation count drifted")
    if result["public_oem_observations_modeled"] != 4:
        raise AdmissionError("public OEM observation count drifted")
    if result["production_exact_icpn_count"] != 1862:
        raise AdmissionError("Production exact ICPN count drifted")
    if result["rdp2_unconditionally_terminal"] is not False:
        raise AdmissionError("STM32U3 RDP2 incorrectly modeled terminal")

    print(json.dumps(result, sort_keys=True))
    print("STM32U3 security-state observer/debug gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
from pathlib import Path

from device_catalog_admission_framework import AdmissionError
from stm32l5_security_state_observer_debug import POLICY, build_gate_result, negative_controls, validate_policy


def main() -> int:
    result = build_gate_result()
    policy = json.loads(POLICY.read_text(encoding="utf-8"))

    for name, mutated in negative_controls(policy):
        try:
            validate_policy(mutated)
        except AdmissionError:
            continue
        raise SystemExit(f"negative control unexpectedly passed: {name}")

    print("STM32L5 security-state observer/debug gate: PASS")
    print(f"modeled_security_states={result['modeled_security_states']}")
    print("observer_hil_validated=false")
    print("debug_attach_hil_validated=false")
    print("target_touching_operation_authorized=false")
    print("production_manifest_admission_authorized=false")
    print("runtime_programming_authorized=false")
    print(f"exact_icpn_count={result['exact_icpn_count']}")
    print(f"next_research_gate={result['next_research_gate']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import json

from device_catalog_admission_framework import AdmissionError
from stm32u5_security_state_gate import (
    MODEL,
    _read_json,
    build_gate_result,
    negative_control_mutations,
    validate_model,
)


def main() -> int:
    model = _read_json(MODEL)
    validate_model(model)
    result = build_gate_result(MODEL)

    rejected = 0
    for label, mutated in negative_control_mutations(model):
        try:
            validate_model(mutated)
        except AdmissionError:
            rejected += 1
        else:
            raise AdmissionError(f"negative control unexpectedly passed: {label}")

    if rejected != 7:
        raise AdmissionError(f"negative-control rejection count drifted: {rejected}")

    print(json.dumps({**result, "negative_controls_rejected": rejected}, sort_keys=True))
    print("STM32U5 security-state admission gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

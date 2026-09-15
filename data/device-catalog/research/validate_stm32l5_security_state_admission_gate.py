#!/usr/bin/env python3
from __future__ import annotations

import json

from device_catalog_admission_framework import AdmissionError
from stm32l5_security_state_gate import (
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

    for label, mutated in negative_control_mutations(model):
        try:
            validate_model(mutated)
        except AdmissionError:
            pass
        else:
            raise AdmissionError(f"negative control unexpectedly passed: {label}")

    print(json.dumps(result, sort_keys=True))
    print("STM32L5 security-state admission gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

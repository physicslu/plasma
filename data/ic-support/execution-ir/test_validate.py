#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
VALIDATOR = HERE / "validate.py"
IR_FILE = HERE / "stm32f103c-programming-execution-ir-v0.json"


def load_module():
    spec = importlib.util.spec_from_file_location("execution_ir_validate", VALIDATOR)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load execution IR validator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def expect_rule(module, candidate, rule_id: str) -> None:
    try:
        module.validate_ir(candidate)
    except module.ExecutionIRValidationError as exc:
        assert str(exc).startswith(f"{rule_id}:"), str(exc)
        return
    raise AssertionError(f"expected {rule_id} failure")


def operation(candidate, operation_id: str):
    return next(item for item in candidate["operations"] if item["operation_id"] == operation_id)


def step(candidate, operation_id: str, step_id: str):
    return next(item for item in operation(candidate, operation_id)["steps"] if item["id"] == step_id)


def main() -> int:
    module = load_module()
    good = module.load_json(IR_FILE)
    module.validate_ir(good)

    bad = copy.deepcopy(good)
    step(bad, "flash_program_unit", "wait_not_busy")["expect"] = 1
    expect_rule(module, bad, "V002")

    bad = copy.deepcopy(good)
    step(bad, "flash_lock", "ensure_locked")["retry"] = {"max_attempts": 2}
    expect_rule(module, bad, "V003")

    bad = copy.deepcopy(good)
    step(bad, "flash_program_unit", "wait_not_busy")["on_timeout"]["controller_state"] = "known_idle"
    expect_rule(module, bad, "V004")

    bad = copy.deepcopy(good)
    step(bad, "flash_program_unit", "wait_not_busy")["on_timeout"]["terminate"] = False
    expect_rule(module, bad, "V005")

    bad = copy.deepcopy(good)
    operation(bad, "rdp_disable_transition")["continuation"] = "return"
    expect_rule(module, bad, "V006")

    bad = copy.deepcopy(good)
    operation(bad, "flash_program_unit").pop("address_constraints")
    expect_rule(module, bad, "V009")

    bad = copy.deepcopy(good)
    step(bad, "rdp_disable_transition", "erase_options")["on_failure"] = "ignore"
    expect_rule(module, bad, "V011")

    bad = copy.deepcopy(good)
    operation(bad, "flash_program_unit")["steps"] = [
        item for item in operation(bad, "flash_program_unit")["steps"] if item["id"] != "exit_mode"
    ]
    expect_rule(module, bad, "V012")

    bad = copy.deepcopy(good)
    operation(bad, "flash_program_unit")["steps"] = [
        item for item in operation(bad, "flash_program_unit")["steps"] if item["id"] != "clear_status"
    ]
    expect_rule(module, bad, "V013")

    print("Programming Execution IR regression PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

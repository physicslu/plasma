#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
IC_SUPPORT_ROOT = HERE.parent
PROFILE_ROOT = IC_SUPPORT_ROOT / "profiles"
DEFAULT_IR = HERE / "stm32f103c-programming-execution-ir-v0.json"
SCHEMA_FILE = HERE / "programming-execution-ir-v0.schema.json"


class ExecutionIRValidationError(RuntimeError):
    pass


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ExecutionIRValidationError(f"{path}: top-level JSON must be an object")
    return value


def fail(rule: str, message: str) -> None:
    raise ExecutionIRValidationError(f"{rule}: {message}")


def require(condition: bool, rule: str, message: str) -> None:
    if not condition:
        fail(rule, message)


def load_profiles(profile_root: Path = PROFILE_ROOT) -> dict[str, dict[str, Any]]:
    profiles: dict[str, dict[str, Any]] = {}
    for path in sorted(profile_root.glob("*/*.json")):
        profile = load_json(path)
        profile_id = profile.get("profile_id")
        require(isinstance(profile_id, str) and profile_id, "IR", f"{path}: profile_id is required")
        require(profile_id not in profiles, "IR", f"duplicate profile_id {profile_id}")
        profiles[profile_id] = profile
    require(bool(profiles), "IR", f"no canonical profiles found below {profile_root}")
    return profiles


def _steps(operation: dict[str, Any]) -> list[dict[str, Any]]:
    steps = operation.get("steps")
    require(isinstance(steps, list) and steps, "IR", f"{operation.get('operation_id')}: steps must be non-empty")
    for step in steps:
        require(isinstance(step, dict), "IR", f"{operation.get('operation_id')}: every step must be an object")
    return steps


def validate_profile_bindings(ir: dict[str, Any], profiles: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    refs = ir.get("profiles")
    require(isinstance(refs, dict), "IR", "profiles object is required")
    selected: dict[str, dict[str, Any]] = {}
    for kind in ("programming", "option", "security"):
        profile_id = refs.get(kind)
        require(isinstance(profile_id, str) and profile_id in profiles, "IR", f"missing canonical {kind} profile {profile_id!r}")
        profile = profiles[profile_id]
        require(profile.get("kind") == kind, "IR", f"profile {profile_id} is not kind {kind}")
        selected[kind] = profile

    targets = ir.get("targets")
    require(isinstance(targets, list) and targets, "IR", "targets must be non-empty")
    seen: set[str] = set()
    for target in targets:
        require(isinstance(target, dict), "IR", "target entries must be objects")
        icpn = target.get("icpn")
        geometry_id = target.get("memory_geometry_profile")
        require(isinstance(icpn, str) and icpn and icpn not in seen, "IR", f"invalid or duplicate target {icpn!r}")
        seen.add(icpn)
        require(isinstance(geometry_id, str) and geometry_id in profiles, "IR", f"{icpn}: missing geometry profile {geometry_id!r}")
        require(profiles[geometry_id].get("kind") == "memory_geometry", "IR", f"{icpn}: {geometry_id} is not memory_geometry")
    return selected


def validate_symbol_references(operation: dict[str, Any], programming: dict[str, Any]) -> None:
    op_id = str(operation.get("operation_id"))
    data = programming.get("data")
    require(isinstance(data, dict), "IR", "programming profile data is required")
    registers = data.get("registers")
    control_bits = data.get("control_bits")
    status_bits = data.get("status_bits")
    w1c_flags = set(data.get("w1c_status_flags") or [])
    require(isinstance(registers, dict), "IR", "programming.registers must be explicit")
    require(isinstance(control_bits, dict), "IR", "programming.control_bits must be explicit")
    require(isinstance(status_bits, dict), "IR", "programming.status_bits must be explicit")
    require(w1c_flags, "IR", "programming.w1c_status_flags must be explicit")

    for step in _steps(operation):
        register = step.get("register")
        if register is not None:
            require(register in registers, "IR", f"{op_id}.{step['id']}: unknown register {register!r}")
        kind = step.get("kind")
        if kind in {"ensure_bit_state", "enter_mode", "exit_mode", "set_control_bit"}:
            bit = step.get("bit")
            require(bit in control_bits, "IR", f"{op_id}.{step['id']}: unknown control bit {bit!r}")
        if kind in {"observe_bit", "poll_bit"}:
            bit = step.get("bit")
            require(bit in status_bits or bit in control_bits, "IR", f"{op_id}.{step['id']}: unknown bit {bit!r}")
        if kind == "clear_status_flags":
            flags = step.get("flags")
            require(isinstance(flags, list) and flags, "V013", f"{op_id}.{step['id']}: flags must be non-empty")
            for flag in flags:
                require(flag in status_bits, "IR", f"{op_id}.{step['id']}: unknown status flag {flag!r}")
                require(flag in w1c_flags, "V013", f"{op_id}.{step['id']}: {flag} is not declared W1C")
        if kind == "inspect_status":
            for flag in step.get("error_flags") or []:
                require(flag in status_bits, "IR", f"{op_id}.{step['id']}: unknown error flag {flag!r}")
            completion = step.get("completion_flag")
            require(completion in status_bits, "IR", f"{op_id}.{step['id']}: unknown completion flag {completion!r}")


def validate_ir(ir: dict[str, Any], profile_root: Path = PROFILE_ROOT) -> None:
    schema = load_json(SCHEMA_FILE)
    require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "IR", "unexpected execution IR schema")
    require(ir.get("schema_version") == "0.1.0", "IR", "unsupported schema_version")

    profiles = load_profiles(profile_root)
    selected = validate_profile_bindings(ir, profiles)
    programming = selected["programming"]

    operations = ir.get("operations")
    require(isinstance(operations, list) and operations, "IR", "operations must be non-empty")
    op_map: dict[str, dict[str, Any]] = {}
    for operation in operations:
        require(isinstance(operation, dict), "IR", "operation entries must be objects")
        op_id = operation.get("operation_id")
        require(isinstance(op_id, str) and op_id, "IR", "operation_id is required")
        require(op_id not in op_map, "IR", f"duplicate operation_id {op_id}")
        op_map[op_id] = operation
        validate_symbol_references(operation, programming)
        validate_operation(operation)

    for operation in operations:
        for step in _steps(operation):
            if step.get("kind") == "call":
                target = step.get("operation_id")
                require(target in op_map, "V011", f"{operation['operation_id']}: call target {target!r} does not exist")


def validate_operation(operation: dict[str, Any]) -> None:
    op_id = str(operation.get("operation_id"))
    steps = _steps(operation)
    step_ids: list[str] = []
    step_by_id: dict[str, dict[str, Any]] = {}
    for step in steps:
        sid = step.get("id")
        require(isinstance(sid, str) and sid, "IR", f"{op_id}: every step needs a unique id")
        require(sid not in step_by_id, "IR", f"{op_id}: duplicate step id {sid}")
        step_ids.append(sid)
        step_by_id[sid] = step

    for step in steps:
        if step.get("kind") in {"observe_bit", "poll_bit"}:
            require(step.get("expect") in {"set", "clear"}, "V002", f"{op_id}.{step['id']}: bit expectation must be 'set' or 'clear'")
        if step.get("kind") == "ensure_bit_state":
            require(step.get("desired") in {"set", "clear"}, "V002", f"{op_id}.{step['id']}: desired bit state must be 'set' or 'clear'")
            terminal = step.get("terminal_observation")
            require(isinstance(terminal, dict), "V003", f"{op_id}.{step['id']}: ensure_bit_state requires terminal observation")
            require(terminal.get("expect") == step.get("desired"), "V003", f"{op_id}.{step['id']}: terminal observation must verify desired state")

        retry = step.get("retry")
        if retry is not None:
            require(isinstance(retry, dict), "V003", f"{op_id}.{step['id']}: retry must be an object")
            observation = retry.get("success_observation")
            require(isinstance(observation, str) and observation in step_by_id, "V003", f"{op_id}.{step['id']}: retry success must reference a terminal observation")
            obs_step = step_by_id[observation]
            require(obs_step.get("kind") in {"observe_bit", "verify_memory", "verify_erased"}, "V003", f"{op_id}.{step['id']}: retry success reference is not an observation")
            require(step_ids.index(observation) > step_ids.index(step["id"]), "V003", f"{op_id}.{step['id']}: retry terminal observation must occur after retry")

    for step in steps:
        if step.get("kind") != "poll_bit":
            continue
        timeout = step.get("on_timeout")
        require(isinstance(timeout, dict), "V004", f"{op_id}.{step['id']}: poll requires on_timeout")
        require(timeout.get("controller_state") == "uncertain", "V004", f"{op_id}.{step['id']}: timeout must enter uncertain controller state")
        require(timeout.get("terminate") is True, "V005", f"{op_id}.{step['id']}: uncertain timeout must terminate the normal flow")
        require("cleanup_steps" not in timeout, "V005", f"{op_id}.{step['id']}: timeout must not request normal cleanup steps")

    if operation.get("risk") == "destructive":
        require(operation.get("requires_authorization") is True, "V006", f"{op_id}: destructive operation requires explicit authorization")
        auth_positions = [i for i, step in enumerate(steps) if step.get("kind") == "authorization_barrier"]
        require(auth_positions, "V006", f"{op_id}: destructive operation lacks authorization barrier")
        require(auth_positions[0] == 0, "V006", f"{op_id}: authorization barrier must be first step")
        if any(step.get("kind") == "system_reset" for step in steps):
            require(operation.get("continuation") == "stop_after_reset", "V006", f"{op_id}: destructive reset workflow must stop after reset/re-identification")

    address_kinds = {"write_memory", "write_address_register", "verify_memory", "verify_erased"}
    if any(step.get("kind") in address_kinds for step in steps):
        constraints = operation.get("address_constraints")
        require(isinstance(constraints, dict), "V009", f"{op_id}: address-bearing operation lacks address_constraints")
        require(constraints.get("bounds_source") in {"target_geometry", "option_profile"}, "V009", f"{op_id}: address bounds must come from target geometry or option profile")
        require(("alignment_source" in constraints) or isinstance(constraints.get("alignment_bytes"), int), "V009", f"{op_id}: address alignment must be explicit")

    for step in steps:
        if step.get("kind") == "call":
            require(step.get("on_failure") == "propagate", "V011", f"{op_id}.{step['id']}: sub-operation failure must propagate")
            require(step.get("on_uncertain") == "propagate", "V011", f"{op_id}.{step['id']}: uncertain sub-operation state must propagate")

    mode = operation.get("mode_bit")
    enters = [i for i, step in enumerate(steps) if step.get("kind") == "enter_mode"]
    exits = [i for i, step in enumerate(steps) if step.get("kind") == "exit_mode"]
    if mode is not None:
        require(len(enters) == 1 and len(exits) == 1, "V012", f"{op_id}: mode {mode} requires exactly one enter and one exit")
        require(steps[enters[0]].get("bit") == mode and steps[exits[0]].get("bit") == mode, "V012", f"{op_id}: enter/exit mode bit must match {mode}")
        require(enters[0] < exits[0], "V012", f"{op_id}: mode exit must occur after entry")
        polls = [i for i, step in enumerate(steps) if step.get("kind") == "poll_bit"]
        if polls:
            require(enters[0] < min(polls) < exits[0], "V012", f"{op_id}: mode must remain active through completion polling")
    else:
        require(not enters and not exits, "V012", f"{op_id}: enter/exit mode present without mode_bit")

    for index, step in enumerate(steps):
        if step.get("kind") != "inspect_status":
            continue
        clears = [(i, item) for i, item in enumerate(steps[:index]) if item.get("kind") == "clear_status_flags"]
        require(clears, "V013", f"{op_id}.{step['id']}: status must be cleared before inspection")
        clear_index, clear = clears[-1]
        require(clear.get("write_semantics") == "w1c_explicit", "V013", f"{op_id}.{clear['id']}: status clearing must use explicit W1C semantics")
        required_flags = set(step.get("error_flags") or [])
        completion = step.get("completion_flag")
        if completion:
            required_flags.add(completion)
        cleared_flags = set(clear.get("flags") or [])
        require(required_flags <= cleared_flags, "V013", f"{op_id}: stale status flags may survive into the current operation")
        action_positions = [i for i, item in enumerate(steps) if item.get("kind") in {"enter_mode", "write_memory", "write_address_register", "set_control_bit"}]
        if action_positions:
            require(clear_index < min(action_positions), "V013", f"{op_id}: stale status flags must be cleared before starting the operation")


def main() -> int:
    ir = load_json(DEFAULT_IR)
    validate_ir(ir)
    print(f"Programming Execution IR validation PASS: {len(ir['operations'])} operations")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ExecutionIRValidationError as exc:
        print(f"Programming Execution IR validation FAIL: {exc}")
        raise SystemExit(1)

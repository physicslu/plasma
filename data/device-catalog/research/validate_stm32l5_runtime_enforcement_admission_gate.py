#!/usr/bin/env python3
from __future__ import annotations

import copy
import json

from device_catalog_admission_framework import AdmissionError
from stm32l5_runtime_enforcement import (
    CONTROL_OPERATIONS,
    EXPECTED_STATE_IDS,
    POLICY,
    SECURITY_MUTATIONS,
    TARGET_OPERATIONS,
    TERMINAL_STATES,
    build_gate_result,
    decide,
    load_policy,
    validate_policy,
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def must_reject(label: str, policy: dict[str, object]) -> None:
    try:
        validate_policy(policy)
    except AdmissionError:
        return
    raise AdmissionError(f"negative control unexpectedly passed: {label}")


def main() -> int:
    policy = load_policy()
    result = build_gate_result()

    require(result["control_plane_operations_allowed"] == 3, "control-plane operation count drifted")
    require(result["target_plane_operations_modeled"] == 12, "target-plane operation count drifted")
    require(result["security_states_enforced"] == 7, "security-state enforcement count drifted")
    require(result["target_plane_decisions"] == 84, "target decision-matrix cardinality drifted")
    require(result["target_plane_allow_count"] == 0, "target plane unexpectedly contains an allow")
    require(result["default_deny_enforced"] is True, "default deny not enforced")
    require(result["force_override_supported"] is False, "force override unexpectedly supported")
    require(result["production_manifest_admission_authorized"] is False, "Production admission opened")
    require(result["runtime_programming_authorized"] is False, "runtime programming opened")
    require(result["hil_validated"] is False, "HIL claim unexpectedly enabled")

    for operation in CONTROL_OPERATIONS:
        decision = decide(operation, None, policy=policy)
        require(decision["decision"] == "allow", f"{operation}: host-only control operation denied")
        require(decision["plane"] == "control", f"{operation}: control-plane classification drifted")
        require(decision["state_requirement"] == "not_applicable", f"{operation}: target state incorrectly required")

    for state_id in EXPECTED_STATE_IDS:
        for operation in TARGET_OPERATIONS:
            decision = decide(operation, state_id, policy=policy)
            require(decision["decision"] == "deny", f"{state_id}/{operation}: target operation escaped deny")
            require(decision["plane"] == "target", f"{state_id}/{operation}: target-plane classification drifted")
        for operation in SECURITY_MUTATIONS:
            require(decide(operation, state_id, policy=policy)["decision"] == "deny", f"{state_id}/{operation}: security mutation escaped deny")

    for state_id in TERMINAL_STATES:
        for operation in TARGET_OPERATIONS:
            decision = decide(operation, state_id, policy=policy)
            require(decision["reason"] == "rdp2_terminal_target_access_denied", f"{state_id}/{operation}: RDP2 terminal deny reason drifted")

    for operation in TARGET_OPERATIONS:
        require(decide(operation, None, policy=policy)["reason"] == "security_state_unobserved", f"{operation}: unobserved-state request did not fail closed")
        require(decide(operation, "UNKNOWN", policy=policy)["reason"] == "unknown_security_state_default_deny", f"{operation}: unknown-state request did not fail closed")

    unknown = decide("future_unregistered_operation", "TZ0_RDP0", policy=policy)
    require(unknown == {
        "decision": "deny",
        "plane": "unknown",
        "reason": "unknown_operation_default_deny",
        "state_requirement": "not_applicable",
    }, "unknown operation did not default deny")

    opened_program = copy.deepcopy(policy)
    opened_program["operations"]["target_plane"]["flash_program"]["decision"] = "allow"
    must_reject("flash program allow", opened_program)

    force_override = copy.deepcopy(policy)
    force_override["execution_boundary"]["force_override_supported"] = True
    must_reject("force override enabled", force_override)

    unknown_fail_open = copy.deepcopy(policy)
    unknown_fail_open["execution_boundary"]["unknown_or_unobserved_state_decision"] = "allow"
    must_reject("unknown state fail-open", unknown_fail_open)

    state_fail_open = copy.deepcopy(policy)
    state_fail_open["state_enforcement"][0]["target_plane_default"] = "allow"
    must_reject("state target-plane default allow", state_fail_open)

    admitted = copy.deepcopy(policy)
    admitted["admission_result"]["production_manifest_admission_authorized"] = True
    must_reject("premature Production admission", admitted)

    print(json.dumps(result, sort_keys=True))
    print("STM32L5 runtime-enforcement admission gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

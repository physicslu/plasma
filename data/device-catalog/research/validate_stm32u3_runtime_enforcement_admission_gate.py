#!/usr/bin/env python3
from __future__ import annotations

import copy
import json

from device_catalog_admission_framework import AdmissionError
from stm32u3_runtime_enforcement import (
    CONTROL_OPERATIONS,
    EXPECTED_STATE_IDS,
    OEM_DEPENDENT_OPERATIONS,
    POLICY,
    RDP2_STATES,
    SECURITY_MUTATIONS,
    TARGET_OPERATIONS,
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
    policy = load_policy(POLICY)
    result = build_gate_result(POLICY)

    require(result["production_exact_icpn_count"] == 1862, "Production exact ICPN count drifted")
    require(result["control_plane_operations_allowed"] == 3, "control-plane operation count drifted")
    require(result["target_plane_operations_modeled"] == 15, "target-plane operation count drifted")
    require(result["security_states_enforced"] == 7, "security-state enforcement count drifted")
    require(result["target_plane_decisions"] == 105, "target decision-matrix cardinality drifted")
    require(result["target_plane_allow_count"] == 0, "target plane unexpectedly contains an allow")
    require(result["oem_dependent_operations"] == 4, "OEM-dependent operation count drifted")
    require(result["default_deny_enforced"] is True, "default deny not enforced")
    require(result["force_override_supported"] is False, "force override unexpectedly supported")
    require(result["rdp2_unconditionally_terminal"] is False, "STM32U3 RDP2 incorrectly modeled terminal")
    require(result["production_manifest_admission_authorized"] is False, "Production admission opened")
    require(result["runtime_programming_authorized"] is False, "runtime programming opened")
    require(result["oem_key_operation_authorized"] is False, "OEM key operation opened")
    require(result["hil_validated"] is False, "HIL claim unexpectedly enabled")

    for operation in CONTROL_OPERATIONS:
        decision = decide(operation, None, policy=policy)
        require(decision["decision"] == "allow", f"{operation}: host-only control operation denied")
        require(decision["plane"] == "control", f"{operation}: control-plane classification drifted")
        require(decision["state_requirement"] == "not_applicable", f"{operation}: target state incorrectly required")

    for state_id in EXPECTED_STATE_IDS:
        for operation in TARGET_OPERATIONS:
            decision = decide(operation, state_id, oem_state_observed=True, policy=policy)
            require(decision["decision"] == "deny", f"{state_id}/{operation}: target operation escaped deny")
            require(decision["plane"] == "target", f"{state_id}/{operation}: target-plane classification drifted")
        for operation in SECURITY_MUTATIONS:
            require(decide(operation, state_id, oem_state_observed=True, policy=policy)["decision"] == "deny", f"{state_id}/{operation}: security mutation escaped deny")

    for operation in TARGET_OPERATIONS:
        require(decide(operation, None, policy=policy)["reason"] == "lifecycle_state_unobserved", f"{operation}: unobserved lifecycle state did not fail closed")
        require(decide(operation, "UNKNOWN", policy=policy)["reason"] == "unknown_lifecycle_state_default_deny", f"{operation}: unknown lifecycle state did not fail closed")

    for state_id in EXPECTED_STATE_IDS:
        for operation in OEM_DEPENDENT_OPERATIONS:
            decision = decide(operation, state_id, oem_state_observed=False, policy=policy)
            require(decision["decision"] == "deny", f"{state_id}/{operation}: unknown OEM state escaped deny")
            require(decision["reason"] == "oem_state_unobserved_default_deny", f"{state_id}/{operation}: OEM fail-closed reason drifted")

    for state_id in RDP2_STATES:
        debug = decide("debug_attach", state_id, oem_state_observed=True, policy=policy)
        require(debug["reason"] == "rdp2_normal_debug_closed", f"{state_id}: RDP2 debug closure drifted")
        regression = decide("rdp_regression", state_id, oem_state_observed=True, policy=policy)
        require(regression["reason"] == "rdp2_conditional_regression_not_authorized", f"{state_id}: conditional RDP2 regression boundary drifted")

    unknown = decide("future_unregistered_operation", "TZ0_RDP0", policy=policy)
    require(unknown == {
        "decision": "deny",
        "plane": "unknown",
        "reason": "unknown_operation_default_deny",
        "state_requirement": "not_applicable",
        "oem_requirement": "not_applicable",
    }, "unknown operation did not default deny")

    opened_program = copy.deepcopy(policy)
    opened_program["operations"]["target_plane"]["flash_program"]["decision"] = "allow"
    must_reject("flash program allow", opened_program)

    force_override = copy.deepcopy(policy)
    force_override["execution_boundary"]["force_override_supported"] = True
    must_reject("force override enabled", force_override)

    unknown_lifecycle_fail_open = copy.deepcopy(policy)
    unknown_lifecycle_fail_open["execution_boundary"]["unknown_or_unobserved_lifecycle_state_decision"] = "allow"
    must_reject("unknown lifecycle state fail-open", unknown_lifecycle_fail_open)

    unknown_oem_fail_open = copy.deepcopy(policy)
    unknown_oem_fail_open["execution_boundary"]["unknown_or_unobserved_oem_state_decision"] = "allow"
    must_reject("unknown OEM state fail-open", unknown_oem_fail_open)

    terminal_rdp2 = copy.deepcopy(policy)
    next(item for item in terminal_rdp2["state_enforcement"] if item["state_id"] == "TZ0_RDP2")["unconditionally_terminal"] = True
    must_reject("RDP2 made unconditionally terminal", terminal_rdp2)

    key_logging = copy.deepcopy(policy)
    key_logging["oem_enforcement"]["key_material_logging_allowed"] = True
    must_reject("OEM key logging enabled", key_logging)

    oem_unlock = copy.deepcopy(policy)
    oem_unlock["operations"]["target_plane"]["oem_unlock_execute"]["decision"] = "allow"
    must_reject("OEM unlock execution enabled", oem_unlock)

    admitted = copy.deepcopy(policy)
    admitted["admission_result"]["production_manifest_admission_authorized"] = True
    must_reject("premature Production admission", admitted)

    print(json.dumps(result, sort_keys=True))
    print("STM32U3 runtime-enforcement admission gate: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

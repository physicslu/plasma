#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError
from stm32u3_security_state_gate import (
    EXPECTED_STATE_IDS,
    MODEL as SECURITY_MODEL,
    validate_model as validate_security_model,
)

HERE = Path(__file__).resolve().parent
POLICY = HERE / "stm32u3-runtime-enforcement-policy.json"
TRANSACTION = "stm32u3-runtime-enforcement-admission-gate"
NEXT_GATE = "stm32u3-security-state-observer-and-debug-validation-gate"
CONTROL_OPERATIONS = {"catalog_resolve", "metadata_resolve", "route_resolve"}
TARGET_OPERATIONS = {
    "read_security_state",
    "debug_attach",
    "flash_read",
    "flash_program",
    "flash_verify",
    "flash_erase",
    "option_byte_write",
    "tzen_change",
    "rdp_change",
    "rdp_regression",
    "oem1_key_provision",
    "oem2_key_provision",
    "oem_unlock_execute",
    "mass_erase",
    "enter_rdp2",
}
SECURITY_MUTATIONS = {
    "option_byte_write",
    "tzen_change",
    "rdp_change",
    "rdp_regression",
    "oem1_key_provision",
    "oem2_key_provision",
    "oem_unlock_execute",
    "mass_erase",
    "enter_rdp2",
}
OEM_DEPENDENT_OPERATIONS = {
    "rdp_regression",
    "oem1_key_provision",
    "oem2_key_provision",
    "oem_unlock_execute",
}
RDP2_STATES = {"TZ0_RDP2", "TZ1_RDP2"}
EXPECTED_OEM_OBSERVATIONS = [
    "oem1_key_state",
    "oem1_lock_state",
    "oem2_key_state",
    "oem2_lock_state",
]


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"{path.name}: root must be object")
    return value


def validate_upstream() -> dict[str, Any]:
    security_model = _read_json(SECURITY_MODEL)
    validate_security_model(security_model)
    _require(security_model.get("authority") == "research_only", "upstream security model escaped research-only")
    _require(security_model.get("production_exact_icpn_count") == 1862, "upstream Production ICPN count drifted")
    _require(len(security_model.get("states", [])) == 7, "upstream lifecycle-state cardinality drifted")
    admission = security_model.get("admission_result", {})
    _require(admission.get("production_manifest_admission_authorized") is False, "upstream Production fence opened")
    _require(admission.get("runtime_programming_authorized") is False, "upstream runtime programming fence opened")
    _require(admission.get("security_mutation_authorized") is False, "upstream security mutation fence opened")
    _require(admission.get("oem_key_operation_authorized") is False, "upstream OEM operation fence opened")
    _require(admission.get("rdp2_unconditionally_terminal") is False, "upstream RDP2 semantics regressed to terminal")
    _require(admission.get("unknown_oem_state_fail_closed") is True, "upstream OEM fail-closed boundary weakened")
    _require(security_model.get("next_research_gate") == TRANSACTION, "upstream next-gate continuity drifted")
    return security_model


def validate_policy(policy: dict[str, Any]) -> None:
    security_model = validate_upstream()
    _require(policy.get("schema_version") == 1, "runtime-enforcement schema drifted")
    _require(policy.get("transaction") == TRANSACTION, "runtime-enforcement transaction drifted")
    _require(policy.get("authority") == "research_only", "runtime-enforcement authority escaped research-only")
    _require(policy.get("family") == "STM32U3", "runtime-enforcement family drifted")
    _require(policy.get("production_exact_icpn_count") == 1862, "Production exact ICPN count drifted")
    _require(policy.get("upstream_security_state_model") == "stm32u3-security-state-model.json", "upstream model binding drifted")
    _require(policy.get("upstream_security_state_transaction") == "stm32u3-security-state-admission-gate", "upstream transaction binding drifted")
    _require(policy.get("modeled_lifecycle_states") == len(EXPECTED_STATE_IDS), "modeled lifecycle-state count drifted")

    boundary = policy.get("execution_boundary")
    _require(isinstance(boundary, dict), "execution boundary missing")
    expected_boundary = {
        "default_decision": "deny",
        "unknown_operation_decision": "deny",
        "unknown_or_unobserved_lifecycle_state_decision": "deny",
        "unknown_or_unobserved_oem_state_decision": "deny",
        "force_override_supported": False,
        "control_plane_may_touch_target": False,
        "target_plane_requires_observed_lifecycle_state": True,
        "oem_dependent_decision_requires_observed_oem_state": True,
        "security_state_observer_validated": False,
        "oem_state_observer_validated": False,
        "backend_state_enforcement_integrated": False,
    }
    _require(boundary == expected_boundary, "runtime execution boundary drifted")

    oem = policy.get("oem_enforcement")
    _require(isinstance(oem, dict), "OEM runtime enforcement policy missing")
    _require(oem.get("required_observations") == EXPECTED_OEM_OBSERVATIONS, "OEM observation set drifted")
    _require(oem.get("unknown_oem_state_decision") == "deny", "unknown OEM state escaped fail-closed policy")
    for key in (
        "self_attested_oem_state_is_sufficient",
        "key_material_input_allowed",
        "key_material_persistence_allowed",
        "key_material_logging_allowed",
        "oem_unlock_authorized",
        "oem_key_provisioning_authorized",
    ):
        _require(oem.get(key) is False, f"OEM runtime boundary fail-open: {key}")

    operations = policy.get("operations")
    _require(isinstance(operations, dict), "runtime operation policy missing")
    control = operations.get("control_plane")
    target = operations.get("target_plane")
    _require(isinstance(control, dict) and set(control) == CONTROL_OPERATIONS, "control-plane operation set drifted")
    _require(isinstance(target, dict) and set(target) == TARGET_OPERATIONS, "target-plane operation set drifted")
    for operation, rule in control.items():
        _require(isinstance(rule, dict), f"{operation}: control rule must be object")
        _require(rule.get("decision") == "allow", f"{operation}: host-only control operation unexpectedly denied")
        _require(rule.get("device_io") is False, f"{operation}: control plane may not touch target")
        _require(isinstance(rule.get("reason"), str) and rule["reason"], f"{operation}: missing decision reason")
    for operation, rule in target.items():
        _require(isinstance(rule, dict), f"{operation}: target rule must be object")
        _require(rule.get("decision") == "deny", f"{operation}: target operation escaped fail-closed policy")
        _require(isinstance(rule.get("reason"), str) and rule["reason"], f"{operation}: missing deny reason")
    for operation in SECURITY_MUTATIONS:
        _require(target[operation]["decision"] == "deny", f"{operation}: security mutation unexpectedly enabled")

    model_states = {item["id"]: item for item in security_model["states"]}
    enforcement = policy.get("state_enforcement")
    _require(isinstance(enforcement, list) and len(enforcement) == len(EXPECTED_STATE_IDS), "state enforcement cardinality drifted")
    by_state: dict[str, dict[str, Any]] = {}
    for item in enforcement:
        _require(isinstance(item, dict), "state enforcement entry must be object")
        state_id = item.get("state_id")
        _require(isinstance(state_id, str) and state_id in EXPECTED_STATE_IDS and state_id not in by_state, f"invalid/duplicate enforcement state {state_id}")
        _require(item.get("target_plane_default") == "deny", f"{state_id}: target plane escaped default deny")
        _require(item.get("unconditionally_terminal") is False, f"{state_id}: STM32U3 state must not become unconditionally terminal")
        expected_rdp2_closed = state_id in RDP2_STATES
        _require(item.get("rdp2_normal_debug_closed") is expected_rdp2_closed, f"{state_id}: RDP2 debug-closure binding drifted")
        _require(model_states[state_id].get("unconditionally_terminal") is False, f"{state_id}: upstream terminal semantics drifted")
        by_state[state_id] = item
    _require(set(by_state) == EXPECTED_STATE_IDS, "state enforcement set drifted")

    admission = policy.get("admission_result")
    _require(isinstance(admission, dict), "runtime admission result missing")
    expected_true = {
        "runtime_enforcement_contract_defined",
        "default_deny_enforced",
        "control_target_plane_separation_defined",
        "lifecycle_state_observation_required_before_target_operation",
        "oem_state_observation_policy_fail_closed",
    }
    expected_false = {
        "target_touching_operation_authorized",
        "security_state_observer_validated",
        "oem_state_observer_validated",
        "backend_state_enforcement_integrated",
        "production_manifest_admission_authorized",
        "runtime_programming_authorized",
        "security_mutation_authorized",
        "oem_key_operation_authorized",
        "hil_validated",
    }
    for key in expected_true:
        _require(admission.get(key) is True, f"{key}: required enforcement result missing")
    for key in expected_false:
        _require(admission.get(key) is False, f"{key}: unsafe enforcement result")
    _require(policy.get("next_research_gate") == NEXT_GATE, "next research gate drifted")


def load_policy(path: Path = POLICY) -> dict[str, Any]:
    policy = _read_json(path)
    validate_policy(policy)
    return policy


def decide(
    operation: str,
    lifecycle_state_id: str | None = None,
    *,
    oem_state_observed: bool = False,
    policy: dict[str, Any] | None = None,
) -> dict[str, str]:
    policy = load_policy() if policy is None else policy
    validate_policy(policy)
    operations = policy["operations"]

    if operation in CONTROL_OPERATIONS:
        rule = operations["control_plane"][operation]
        return {
            "decision": "allow",
            "plane": "control",
            "reason": rule["reason"],
            "state_requirement": "not_applicable",
            "oem_requirement": "not_applicable",
        }

    if operation not in TARGET_OPERATIONS:
        return {
            "decision": "deny",
            "plane": "unknown",
            "reason": "unknown_operation_default_deny",
            "state_requirement": "not_applicable",
            "oem_requirement": "not_applicable",
        }

    if lifecycle_state_id is None:
        return {
            "decision": "deny",
            "plane": "target",
            "reason": "lifecycle_state_unobserved",
            "state_requirement": "required",
            "oem_requirement": "not_evaluated",
        }
    if lifecycle_state_id not in EXPECTED_STATE_IDS:
        return {
            "decision": "deny",
            "plane": "target",
            "reason": "unknown_lifecycle_state_default_deny",
            "state_requirement": "required",
            "oem_requirement": "not_evaluated",
        }

    if operation in OEM_DEPENDENT_OPERATIONS and not oem_state_observed:
        return {
            "decision": "deny",
            "plane": "target",
            "reason": "oem_state_unobserved_default_deny",
            "state_requirement": "satisfied",
            "oem_requirement": "required",
        }

    if lifecycle_state_id in RDP2_STATES and operation == "debug_attach":
        return {
            "decision": "deny",
            "plane": "target",
            "reason": "rdp2_normal_debug_closed",
            "state_requirement": "satisfied_but_operation_blocked",
            "oem_requirement": "not_applicable",
        }
    if lifecycle_state_id in RDP2_STATES and operation in {"rdp_regression", "oem_unlock_execute"}:
        return {
            "decision": "deny",
            "plane": "target",
            "reason": "rdp2_conditional_regression_not_authorized",
            "state_requirement": "satisfied_but_operation_blocked",
            "oem_requirement": "observed_but_operation_blocked",
        }

    rule = operations["target_plane"][operation]
    return {
        "decision": "deny",
        "plane": "target",
        "reason": rule["reason"],
        "state_requirement": "satisfied_but_operation_blocked",
        "oem_requirement": "observed_but_operation_blocked" if operation in OEM_DEPENDENT_OPERATIONS else "not_applicable",
    }


def build_gate_result(path: Path = POLICY) -> dict[str, Any]:
    policy = load_policy(path)
    target_decisions = {
        state_id: {
            operation: decide(operation, state_id, oem_state_observed=True, policy=policy)["decision"]
            for operation in sorted(TARGET_OPERATIONS)
        }
        for state_id in sorted(EXPECTED_STATE_IDS)
    }
    _require(all(decision == "deny" for ops in target_decisions.values() for decision in ops.values()), "target decision matrix escaped fail-closed state")
    return {
        "schema_version": 1,
        "transaction": TRANSACTION,
        "authority": "research_only",
        "family": "STM32U3",
        "production_exact_icpn_count": 1862,
        "control_plane_operations_allowed": len(CONTROL_OPERATIONS),
        "target_plane_operations_modeled": len(TARGET_OPERATIONS),
        "security_states_enforced": len(EXPECTED_STATE_IDS),
        "target_plane_decisions": len(EXPECTED_STATE_IDS) * len(TARGET_OPERATIONS),
        "target_plane_allow_count": 0,
        "oem_dependent_operations": len(OEM_DEPENDENT_OPERATIONS),
        "default_deny_enforced": True,
        "force_override_supported": False,
        "rdp2_unconditionally_terminal": False,
        "target_touching_operation_authorized": False,
        "production_manifest_admission_authorized": False,
        "runtime_programming_authorized": False,
        "oem_key_operation_authorized": False,
        "hil_validated": False,
        "next_research_gate": policy["next_research_gate"],
    }


if __name__ == "__main__":
    print(json.dumps(build_gate_result(), sort_keys=True))

#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from device_catalog_admission_framework import AdmissionError
from stm32u3_admission_policy import build_plan as build_canonical_plan, plan_is_clean
from stm32u3_metadata_policy import FAMILY, load_security_fence

HERE = Path(__file__).resolve().parent
MODEL = HERE / "stm32u3-security-state-model.json"
TRANSACTION = "stm32u3-security-state-admission-gate"
EXPECTED_COMMERCIAL_SERIES = ["STM32U375", "STM32U385", "STM32U3B5", "STM32U3C5"]
EXPECTED_SUBFAMILIES = [
    "STM32U335", "STM32U345", "STM32U356", "STM32U366",
    "STM32U375", "STM32U385", "STM32U3B5", "STM32U3C5",
]
EXPECTED_STATE_IDS = {
    "TZ0_RDP0", "TZ0_RDP1", "TZ0_RDP2",
    "TZ1_RDP0", "TZ1_RDP0_5", "TZ1_RDP1", "TZ1_RDP2",
}
EXPECTED_LIFECYCLE_TRANSITION_IDS = {
    "enable_trustzone",
    "raise_to_rdp1",
    "rdp1_to_rdp0",
    "trustzone_rdp1_to_rdp0_5",
    "enter_rdp2",
    "rdp2_to_rdp1_with_oem2",
}
EXPECTED_OEM_CONFIGURATION_IDS = {
    "configure_oem1_transition_mechanism",
    "configure_oem2_transition_mechanism",
}
MUTATING_OPERATIONS = {
    "option_byte_write", "tzen_change", "rdp_change", "rdp_regression",
    "oem1_key_provision", "oem2_key_provision", "oem_unlock_execute",
    "mass_erase", "enter_rdp2",
}


def _read_json(path: Path = MODEL) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError("STM32U3 security-state model root must be object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def validate_model(model: dict[str, Any]) -> None:
    _require(model.get("schema_version") == 1, "security-state schema drifted")
    _require(model.get("transaction") == TRANSACTION, "security-state transaction drifted")
    _require(model.get("authority") == "research_only", "security-state authority escaped research-only")
    _require(model.get("family") == FAMILY, "security-state family drifted")
    _require(model.get("commercial_series_scope") == EXPECTED_COMMERCIAL_SERIES, "commercial series scope drifted")
    _require(model.get("candidate_subfamily_scope") == EXPECTED_SUBFAMILIES, "candidate subfamily scope drifted")
    _require(model.get("production_exact_icpn_count") == 1862, "Production exact ICPN count drifted")

    sources = model.get("manufacturer_sources")
    _require(isinstance(sources, list) and len(sources) >= 3, "manufacturer security evidence missing")
    source_ids: set[str] = set()
    for source in sources:
        _require(isinstance(source, dict), "manufacturer source must be object")
        sid = source.get("id")
        url = source.get("url")
        _require(isinstance(sid, str) and sid and sid not in source_ids, "duplicate/invalid security source id")
        _require(source.get("authority") == "STMicroelectronics", f"{sid}: non-ST security authority")
        _require(isinstance(url, str) and url.startswith("https://"), f"{sid}: invalid source URL")
        host = urlparse(url).hostname
        _require(host in {"www.st.com", "st.com", "wiki.st.com"}, f"{sid}: non-ST source host")
        observations = source.get("observations")
        _require(isinstance(observations, list) and observations, f"{sid}: observations missing")
        source_ids.add(sid)
    _require({"st-rm0487", "st-wiki-rdp-for-stm32u3"}.issubset(source_ids), "required STM32U3 security authorities missing")

    oem_policy = model.get("oem_state_policy")
    _require(isinstance(oem_policy, dict), "OEM state policy missing")
    required_true = {
        "orthogonal_to_lifecycle_state",
        "key_material_must_never_be_stored",
        "key_material_must_never_be_logged",
        "lock_and_provisioning_state_must_be_observed_before_regression_decision",
        "unknown_oem_state_is_deny",
    }
    required_false = {
        "self_attested_oem_state_is_sufficient",
        "oem_unlock_execution_authorized",
        "oem_key_provisioning_authorized",
    }
    for key in required_true:
        _require(oem_policy.get(key) is True, f"OEM policy weakened: {key}")
    for key in required_false:
        _require(oem_policy.get(key) is False, f"OEM policy fail-open: {key}")

    states = model.get("states")
    _require(isinstance(states, list) and len(states) == len(EXPECTED_STATE_IDS), "security-state cardinality drifted")
    by_id: dict[str, dict[str, Any]] = {}
    for state in states:
        _require(isinstance(state, dict), "security state must be object")
        sid = state.get("id")
        _require(isinstance(sid, str) and sid in EXPECTED_STATE_IDS and sid not in by_id, f"invalid/duplicate state {sid}")
        trustzone = state.get("trustzone")
        rdp = state.get("rdp")
        _require(trustzone in {"disabled", "enabled"}, f"{sid}: invalid TrustZone value")
        _require(rdp in {"0", "0.5", "1", "2"}, f"{sid}: invalid RDP value")
        if rdp == "0.5":
            _require(trustzone == "enabled", "RDP0.5 is valid only with TrustZone enabled")
        _require(state.get("unconditionally_terminal") is False, f"{sid}: STM32U3 lifecycle state must not be modeled unconditionally terminal")
        if rdp == "2":
            _require(state.get("debug_access") == "none", f"{sid}: RDP2 must close normal debug access")
            _require(state.get("conditional_exit") == "RDP2_to_RDP1_requires_verified_OEM2_unlock_mechanism", f"{sid}: RDP2 conditional exit drifted")
        else:
            _require("conditional_exit" not in state, f"{sid}: unexpected conditional exit")
        by_id[sid] = state
    _require(set(by_id) == EXPECTED_STATE_IDS, "security-state set drifted")

    transitions = model.get("lifecycle_transition_rules")
    _require(isinstance(transitions, list) and len(transitions) == len(EXPECTED_LIFECYCLE_TRANSITION_IDS), "lifecycle transition cardinality drifted")
    by_transition: dict[str, dict[str, Any]] = {}
    for transition in transitions:
        _require(isinstance(transition, dict), "lifecycle transition must be object")
        tid = transition.get("id")
        _require(isinstance(tid, str) and tid in EXPECTED_LIFECYCLE_TRANSITION_IDS and tid not in by_transition, f"invalid/duplicate lifecycle transition {tid}")
        _require(transition.get("plasma_policy") == "blocked", f"{tid}: lifecycle mutation escaped fail-closed policy")
        from_states = transition.get("from")
        to_states = transition.get("to")
        _require(isinstance(from_states, list) and from_states and set(from_states).issubset(EXPECTED_STATE_IDS), f"{tid}: invalid source states")
        _require(isinstance(to_states, list) and to_states and set(to_states).issubset(EXPECTED_STATE_IDS), f"{tid}: invalid destination states")
        by_transition[tid] = transition
    _require(set(by_transition) == EXPECTED_LIFECYCLE_TRANSITION_IDS, "lifecycle transition set drifted")

    enable = by_transition["enable_trustzone"]
    _require(enable["from"] == ["TZ0_RDP0"] and enable["to"] == ["TZ1_RDP0"], "TrustZone activation boundary drifted")

    enter2 = by_transition["enter_rdp2"]
    _require(enter2.get("unconditionally_irreversible") is False, "STM32U3 RDP2 must not be modeled unconditionally irreversible")
    _require(enter2.get("conditional_regression_requires_oem2") is True, "STM32U3 RDP2 OEM2 dependency missing")
    _require(set(enter2["to"]) == {"TZ0_RDP2", "TZ1_RDP2"}, "RDP2 destination boundary drifted")

    regress2 = by_transition["rdp2_to_rdp1_with_oem2"]
    _require(set(regress2["from"]) == {"TZ0_RDP2", "TZ1_RDP2"}, "RDP2 regression source boundary drifted")
    _require(set(regress2["to"]) == {"TZ0_RDP1", "TZ1_RDP1"}, "RDP2 regression destination boundary drifted")
    _require(regress2.get("conditional") is True, "RDP2 regression must remain conditional")
    requires = regress2.get("requires")
    _require(isinstance(requires, list) and any("OEM2" in item for item in requires), "RDP2 regression lost OEM2 prerequisite")
    _require(any("authentication" in item.lower() for item in requires), "RDP2 regression lost authentication prerequisite")

    regress1 = by_transition["rdp1_to_rdp0"]
    _require(any("OEM1" in item for item in regress1.get("requires", [])), "RDP1 to RDP0 lost OEM1 state dependency")
    regress05 = by_transition["trustzone_rdp1_to_rdp0_5"]
    _require(regress05["from"] == ["TZ1_RDP1"] and regress05["to"] == ["TZ1_RDP0_5"], "TrustZone RDP1 to RDP0.5 boundary drifted")
    _require(any("OEM2" in item for item in regress05.get("requires", [])), "RDP1 to RDP0.5 lost OEM2 state dependency")

    oem_rules = model.get("oem_configuration_rules")
    _require(isinstance(oem_rules, list) and len(oem_rules) == len(EXPECTED_OEM_CONFIGURATION_IDS), "OEM configuration rule cardinality drifted")
    seen_oem: set[str] = set()
    for rule in oem_rules:
        _require(isinstance(rule, dict), "OEM configuration rule must be object")
        rid = rule.get("id")
        _require(isinstance(rid, str) and rid in EXPECTED_OEM_CONFIGURATION_IDS and rid not in seen_oem, f"invalid/duplicate OEM configuration rule {rid}")
        _require(rule.get("reversible") is False, f"{rid}: OEM transition mechanism must not be modeled freely reversible")
        _require(rule.get("plasma_policy") == "blocked", f"{rid}: OEM configuration escaped fail-closed policy")
        seen_oem.add(rid)
    _require(seen_oem == EXPECTED_OEM_CONFIGURATION_IDS, "OEM configuration rule set drifted")

    unresolved = model.get("unresolved_security_semantics")
    _require(isinstance(unresolved, list) and len(unresolved) >= 3, "unresolved security semantics boundary missing")
    _require(any("TrustZone deactivation" in item for item in unresolved), "TrustZone deactivation uncertainty was hidden")

    operations = model.get("operation_policy")
    _require(isinstance(operations, dict), "operation policy missing")
    for operation in MUTATING_OPERATIONS:
        _require(operations.get(operation) == "blocked", f"{operation}: security mutation escaped fail-closed policy")
    _require(operations.get("flash_program") == "blocked_pending_programming_algorithm_and_state_validation", "flash program gate drifted")
    _require(operations.get("flash_erase") == "blocked_pending_programming_algorithm_and_state_validation", "flash erase gate drifted")

    admission = model.get("admission_result")
    _require(isinstance(admission, dict), "admission result missing")
    expected_true = {
        "security_state_admission_model_complete",
        "destructive_transition_policy_fail_closed",
        "rdp2_conditional_regression_boundary_modeled",
        "oem_transition_dependency_modeled",
        "unknown_oem_state_fail_closed",
        "execution_state_dependency_modeled",
        "canonical_identity_plan_remains_valid",
        "hil_required_before_runtime_enablement",
    }
    expected_false = {
        "all_security_transition_semantics_validated",
        "rdp2_unconditionally_terminal",
        "production_manifest_admission_authorized",
        "runtime_programming_authorized",
        "security_mutation_authorized",
        "oem_key_operation_authorized",
    }
    for key in expected_true:
        _require(admission.get(key) is True, f"{key}: required gate result missing")
    for key in expected_false:
        _require(admission.get(key) is False, f"{key}: unsafe/overstated gate result")
    _require(model.get("next_research_gate") == "stm32u3-runtime-enforcement-admission-gate", "next gate drifted")


def validate_upstream() -> None:
    foundation = load_security_fence()
    partition = foundation.get("research_partition", {})
    for key in (
        "production_admission_allowed", "option_byte_writes_allowed", "oem_key_provisioning_allowed",
        "oem_unlock_execution_allowed", "rdp_regression_allowed", "mass_erase_allowed",
        "runtime_programming_supported", "debug_attach_supported", "hil_validated",
    ):
        _require(partition.get(key) is False, f"foundation security fence unexpectedly open: {key}")

    invariants = foundation.get("u3_specific_security_invariants", {})
    _require(invariants.get("rdp0_5_requires_trustzone") is True, "foundation RDP0.5 invariant missing")
    _require(invariants.get("rdp2_is_unconditionally_terminal") is False, "foundation RDP2 semantics drifted")
    _require(invariants.get("rdp2_to_rdp1_requires_oem2_unlock_mechanism") is True, "foundation OEM2 regression dependency missing")
    _require(invariants.get("oem_key_lock_state_affects_regression_policy") is True, "foundation OEM lock dependency missing")
    _require(invariants.get("plasma_may_not_infer_oem_key_state") is True, "foundation OEM observation fence weakened")
    _require(invariants.get("plasma_may_not_mutate_security_state_for_discovery") is True, "foundation mutation fence weakened")

    plan = build_canonical_plan()
    _require(plan_is_clean(plan), "upstream STM32U3 canonical plan is not clean")
    _require(plan.get("planned_canonical_rows") == 106, "upstream canonical row count drifted")
    _require(plan.get("production_exact_icpn_count") == 1862, "upstream Production exact ICPN count drifted")
    _require(plan.get("claims", {}).get("production_admission_authorized") is False, "upstream canonical plan opened Production admission")
    _require(plan.get("next_research_gate") == TRANSACTION, "upstream canonical plan next-gate continuity drifted")


def build_gate_result(model_path: Path = MODEL) -> dict[str, Any]:
    validate_upstream()
    model = _read_json(model_path)
    validate_model(model)
    return {
        "schema_version": 1,
        "transaction": TRANSACTION,
        "authority": "research_only",
        "family": FAMILY,
        "modeled_lifecycle_states": len(model["states"]),
        "modeled_lifecycle_transition_rules": len(model["lifecycle_transition_rules"]),
        "modeled_oem_configuration_rules": len(model["oem_configuration_rules"]),
        "canonical_identity_count": 106,
        "production_exact_icpn_count": 1862,
        "security_state_admission_model_complete": True,
        "rdp2_unconditionally_terminal": False,
        "rdp2_conditional_regression_boundary_modeled": True,
        "oem_transition_dependency_modeled": True,
        "unknown_oem_state_fail_closed": True,
        "destructive_operations_fail_closed": True,
        "production_manifest_admission_authorized": False,
        "runtime_programming_authorized": False,
        "security_mutation_authorized": False,
        "oem_key_operation_authorized": False,
        "next_research_gate": model["next_research_gate"],
    }


def negative_control_mutations(model: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []

    terminal_rdp2 = copy.deepcopy(model)
    next(item for item in terminal_rdp2["states"] if item["id"] == "TZ0_RDP2")["unconditionally_terminal"] = True
    cases.append(("RDP2 falsely made unconditionally terminal", terminal_rdp2))

    no_oem2 = copy.deepcopy(model)
    rule = next(item for item in no_oem2["lifecycle_transition_rules"] if item["id"] == "rdp2_to_rdp1_with_oem2")
    rule["requires"] = ["RDP regression semantics validated"]
    cases.append(("RDP2 regression admitted without OEM2 prerequisite", no_oem2))

    bad_rdp05 = copy.deepcopy(model)
    bad_rdp05["states"].append({
        "id": "TZ0_RDP0_5", "trustzone": "disabled", "rdp": "0.5",
        "execution_state": "not_applicable", "debug_access": "open",
        "unconditionally_terminal": False,
    })
    cases.append(("RDP0.5 without TrustZone", bad_rdp05))

    opened_oem = copy.deepcopy(model)
    opened_oem["operation_policy"]["oem2_key_provision"] = "allowed"
    cases.append(("OEM2 key provisioning allowed", opened_oem))

    inferred_oem = copy.deepcopy(model)
    inferred_oem["oem_state_policy"]["unknown_oem_state_is_deny"] = False
    cases.append(("unknown OEM state fail-open", inferred_oem))

    admitted = copy.deepcopy(model)
    admitted["admission_result"]["production_manifest_admission_authorized"] = True
    cases.append(("Production admission opened", admitted))

    return cases

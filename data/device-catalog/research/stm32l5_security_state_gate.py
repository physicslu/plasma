#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from device_catalog_admission_framework import AdmissionError
from stm32l5_admission_policy import build_plan as build_canonical_plan, plan_is_clean
from stm32l5_metadata_policy import FAMILY, load_security_fence

HERE = Path(__file__).resolve().parent
MODEL = HERE / "stm32l5-security-state-model.json"
TRANSACTION = "stm32l5-security-state-admission-gate"
EXPECTED_STATE_IDS = {
    "TZ0_RDP0", "TZ0_RDP1", "TZ0_RDP2",
    "TZ1_RDP0", "TZ1_RDP0_5", "TZ1_RDP1", "TZ1_RDP2",
}
EXPECTED_TRANSITION_IDS = {
    "enable_trustzone",
    "trustzone_rdp1_to_rdp0_5",
    "trustzone_regress_to_rdp0",
    "disable_trustzone",
    "enter_rdp2",
}
MUTATING_OPERATIONS = {
    "option_byte_write", "tzen_change", "rdp_change", "rdp_regression", "mass_erase", "enter_rdp2"
}


def _read_json(path: Path = MODEL) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError("STM32L5 security-state model root must be object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def validate_model(model: dict[str, Any]) -> None:
    _require(model.get("schema_version") == 1, "security-state schema drifted")
    _require(model.get("transaction") == TRANSACTION, "security-state transaction drifted")
    _require(model.get("authority") == "research_only", "security-state authority escaped research-only")
    _require(model.get("family") == FAMILY, "security-state family drifted")
    _require(model.get("device_lines") == ["STM32L552", "STM32L562"], "security-state device-line scope drifted")

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
    _require({"st-rm0438", "st-trustzone-disable-guidance"}.issubset(source_ids), "required security authorities missing")

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
        if rdp == "2":
            _require(state.get("terminal") is True and state.get("debug_access") == "none", f"{sid}: RDP2 must be terminal/no-debug")
        else:
            _require(state.get("terminal") is False, f"{sid}: unexpected terminal state")
        by_id[sid] = state
    _require(set(by_id) == EXPECTED_STATE_IDS, "security-state set drifted")

    transitions = model.get("transition_rules")
    _require(isinstance(transitions, list) and len(transitions) == len(EXPECTED_TRANSITION_IDS), "transition-rule cardinality drifted")
    by_transition: dict[str, dict[str, Any]] = {}
    for transition in transitions:
        _require(isinstance(transition, dict), "transition must be object")
        tid = transition.get("id")
        _require(isinstance(tid, str) and tid in EXPECTED_TRANSITION_IDS and tid not in by_transition, f"invalid/duplicate transition {tid}")
        _require(transition.get("plasma_policy") == "blocked", f"{tid}: mutating transition escaped fail-closed policy")
        from_states = transition.get("from")
        to_states = transition.get("to")
        _require(isinstance(from_states, list) and from_states and set(from_states).issubset(EXPECTED_STATE_IDS), f"{tid}: invalid source states")
        _require(isinstance(to_states, list) and to_states and set(to_states).issubset(EXPECTED_STATE_IDS), f"{tid}: invalid destination states")
        by_transition[tid] = transition
    _require(set(by_transition) == EXPECTED_TRANSITION_IDS, "transition set drifted")

    enable = by_transition["enable_trustzone"]
    _require(enable["from"] == ["TZ0_RDP0"] and enable["to"] == ["TZ1_RDP0"], "TZEN activation must remain RDP0-only")
    disable = by_transition["disable_trustzone"]
    _require(set(disable["from"]) == {"TZ1_RDP0_5", "TZ1_RDP1"} and disable["to"] == ["TZ0_RDP0"], "TZEN deactivation boundary drifted")
    _require(disable.get("destructive") is True, "TZEN deactivation must remain destructive-class")
    enter2 = by_transition["enter_rdp2"]
    _require(enter2.get("irreversible") is True and set(enter2["to"]) == {"TZ0_RDP2", "TZ1_RDP2"}, "RDP2 irreversible boundary drifted")
    for transition in transitions:
        _require(not ({"TZ0_RDP2", "TZ1_RDP2"} & set(transition["from"])), "RDP2 must have no modeled outbound transition")

    operations = model.get("operation_policy")
    _require(isinstance(operations, dict), "operation policy missing")
    for operation in MUTATING_OPERATIONS:
        _require(operations.get(operation) == "blocked", f"{operation}: security mutation escaped fail-closed policy")
    _require(operations.get("flash_program") == "blocked_pending_programming_algorithm_and_state_validation", "flash program gate drifted")
    _require(operations.get("flash_erase") == "blocked_pending_programming_algorithm_and_state_validation", "flash erase gate drifted")

    admission = model.get("admission_result")
    _require(isinstance(admission, dict), "admission result missing")
    expected_true = {
        "security_state_model_complete",
        "destructive_transition_policy_fail_closed",
        "rdp2_irreversible_boundary_modeled",
        "execution_state_dependency_modeled",
        "canonical_identity_plan_remains_valid",
        "hil_required_before_runtime_enablement",
    }
    expected_false = {
        "production_manifest_admission_authorized",
        "runtime_programming_authorized",
        "security_mutation_authorized",
    }
    for key in expected_true:
        _require(admission.get(key) is True, f"{key}: required gate result missing")
    for key in expected_false:
        _require(admission.get(key) is False, f"{key}: unsafe gate result")
    _require(model.get("next_research_gate") == "stm32l5-runtime-enforcement-admission-gate", "next gate drifted")


def validate_upstream() -> None:
    foundation = load_security_fence()
    partition = foundation.get("research_partition", {})
    _require(partition.get("production_admission_allowed") is False, "foundation Production fence opened")
    _require(partition.get("option_byte_writes_allowed") is False, "foundation option-byte fence opened")
    _require(partition.get("rdp_regression_allowed") is False, "foundation RDP-regression fence opened")
    _require(partition.get("mass_erase_allowed") is False, "foundation mass-erase fence opened")
    plan = build_canonical_plan()
    _require(plan_is_clean(plan), "upstream STM32L5 canonical plan is not clean")
    _require(plan.get("planned_canonical_rows") == 49, "upstream canonical row count drifted")
    _require(plan.get("claims", {}).get("production_admission_authorized") is False, "upstream canonical plan opened Production admission")


def build_gate_result(model_path: Path = MODEL) -> dict[str, Any]:
    validate_upstream()
    model = _read_json(model_path)
    validate_model(model)
    return {
        "schema_version": 1,
        "transaction": TRANSACTION,
        "authority": "research_only",
        "family": FAMILY,
        "modeled_security_states": len(model["states"]),
        "modeled_transition_rules": len(model["transition_rules"]),
        "canonical_identity_count": 49,
        "security_state_model_complete": True,
        "destructive_operations_fail_closed": True,
        "production_manifest_admission_authorized": False,
        "runtime_programming_authorized": False,
        "security_mutation_authorized": False,
        "next_research_gate": model["next_research_gate"],
    }


def negative_control_mutations(model: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []

    opened_tzen = copy.deepcopy(model)
    next(item for item in opened_tzen["transition_rules"] if item["id"] == "enable_trustzone")["plasma_policy"] = "allowed"
    cases.append(("TZEN mutation allowed", opened_tzen))

    reversible_rdp2 = copy.deepcopy(model)
    next(item for item in reversible_rdp2["transition_rules"] if item["id"] == "enter_rdp2")["irreversible"] = False
    cases.append(("RDP2 made reversible", reversible_rdp2))

    bad_rdp05 = copy.deepcopy(model)
    bad_rdp05["states"].append({"id": "TZ0_RDP0_5", "trustzone": "disabled", "rdp": "0.5", "execution_state": "not_applicable", "debug_access": "open", "terminal": False})
    cases.append(("RDP0.5 without TrustZone", bad_rdp05))

    admitted = copy.deepcopy(model)
    admitted["admission_result"]["production_manifest_admission_authorized"] = True
    cases.append(("Production admission opened", admitted))

    return cases

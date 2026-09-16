#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError
from stm32u5_metadata_policy import ACTIVE_STATUS, EXPECTED_SUBFAMILIES, build_candidate_inputs
from stm32u5_security_state_observer_debug import (
    EXPECTED_STATES,
    build_gate_result as build_observer_gate_result,
)

HERE = Path(__file__).resolve().parent
PLAN = HERE / "stm32u5-hil-observer-debug-readiness.json"
OBSERVER_POLICY = HERE / "stm32u5-security-state-observer-debug-policy.json"
TRANSACTION = "stm32u5-hil-observer-debug-matrix-readiness-gate"
NEXT_GATE = "stm32u5-hil-fixture-inventory-binding-gate"
ACTIVE_SUBFAMILIES = set(EXPECTED_SUBFAMILIES)
QUARANTINED_PREVIEW = {"STM32U5G9ZJJ3Q"}
SPLIT_STATES = {"TZ1_RDP0", "TZ1_RDP0_5", "TZ1_RDP1"}
U5_UNRESOLVED_SPLIT_STATES = {"TZ1_RDP0_5", "TZ1_RDP1"}
SINGLE_STATES = {"TZ0_RDP0", "TZ0_RDP1", "TZ0_RDP2", "TZ1_RDP2"}
RDP2_STATES = {"TZ0_RDP2", "TZ1_RDP2"}
REQUIRED_TARGET_CONFIG = "tcl/target/stm32u5x.cfg"
REQUIRED_EVIDENCE = {
    "fixture_identifier", "subfamily", "exact_icpn", "fixture_provenance_digest",
    "preprovisioned_security_state", "execution_context", "debug_probe_identity",
    "debug_probe_firmware_version", "backend_identity_and_version", "canonical_target_config",
    "connection_mode", "raw_attach_result", "observed_tzen_state", "observed_rdp_level",
    "observed_execution_state", "observed_oem1_key_state", "observed_oem1_lock_state",
    "observed_oem2_key_state", "observed_oem2_lock_state", "timestamp_utc",
    "operator_or_automation_identity", "evidence_digest",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def _read(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path.name}: root must be object")
    return value


def validate_upstream() -> dict[str, Any]:
    upstream = build_observer_gate_result()
    _require(upstream.get("authority") == "research_only", "observer gate escaped research-only")
    _require(upstream.get("family") == "STM32U5", "observer family drifted")
    _require(upstream.get("canonical_active_identity_count") == 265, "canonical Active identity count drifted")
    _require(upstream.get("quarantined_preview_exact_icpns") == ["STM32U5G9ZJJ3Q"], "Preview quarantine drifted")
    _require(upstream.get("production_exact_icpn_count") == 2017, "Production exact ICPN count drifted")
    _require(upstream.get("modeled_security_states") == 7, "observer state count drifted")
    _require(upstream.get("observer_contract_defined") is True, "observer contract missing")
    _require(upstream.get("oem_observer_contract_defined") is True, "OEM observer contract missing")
    _require(upstream.get("debug_expectation_matrix_complete") is True, "debug matrix incomplete")
    _require(upstream.get("rdp2_unconditionally_terminal") is False, "RDP2 incorrectly became terminal")
    _require(upstream.get("u5_rdp0_5_debug_semantics_resolved") is False, "U5 RDP0.5 semantics falsely resolved")
    _require(upstream.get("u5_rdp1_debug_semantics_resolved") is False, "U5 RDP1 semantics falsely resolved")
    _require(upstream.get("observer_hil_validated") is False, "observer HIL unexpectedly claimed")
    _require(upstream.get("oem_state_observer_hil_validated") is False, "OEM observer HIL unexpectedly claimed")
    _require(upstream.get("debug_attach_hil_validated") is False, "debug HIL unexpectedly claimed")
    _require(upstream.get("runtime_programming_authorized") is False, "runtime programming fence opened")
    _require(upstream.get("production_manifest_admission_authorized") is False, "Production fence opened")
    _require(upstream.get("oem_key_operation_authorized") is False, "OEM key operation fence opened")
    _require(upstream.get("next_research_gate") == TRANSACTION, "upstream next-gate continuity drifted")

    candidates = build_candidate_inputs()
    active = [item for item in candidates if item["marketing_status"] == ACTIVE_STATUS]
    inactive = [item for item in candidates if item["marketing_status"] != ACTIVE_STATUS]
    _require(len(active) == 265, "Active exact identity count drifted")
    _require({item["series"] for item in active} == ACTIVE_SUBFAMILIES, "not every STM32U5 subfamily has an Active exact identity")
    _require({item["icpn"] for item in inactive} == QUARANTINED_PREVIEW, "Preview identity boundary drifted")
    return _read(OBSERVER_POLICY)


def validate_plan(plan: dict[str, Any]) -> None:
    observer = validate_upstream()
    _require(plan.get("schema_version") == 1, "HIL readiness schema drifted")
    _require(plan.get("transaction") == TRANSACTION, "HIL readiness transaction drifted")
    _require(plan.get("authority") == "research_only", "HIL readiness authority escaped research-only")
    _require(plan.get("family") == "STM32U5", "HIL readiness family drifted")
    _require(plan.get("canonical_active_identity_count") == 265, "canonical Active identity count drifted")
    _require(plan.get("quarantined_preview_exact_icpns") == ["STM32U5G9ZJJ3Q"], "Preview quarantine drifted")
    _require(plan.get("production_exact_icpn_count") == 2017, "Production exact ICPN count drifted")
    _require(set(plan.get("active_subfamily_scope", [])) == ACTIVE_SUBFAMILIES, "Active subfamily scope drifted")
    _require(plan.get("upstream_observer_policy") == OBSERVER_POLICY.name, "observer policy binding drifted")
    _require(plan.get("required_target_config") == REQUIRED_TARGET_CONFIG, "canonical target-config binding drifted")

    boundary = plan.get("readiness_boundary")
    _require(isinstance(boundary, dict), "readiness boundary missing")
    for key in (
        "hil_execution_authorized", "runtime_debug_attach_authorized", "runtime_programming_authorized",
        "production_manifest_admission_authorized", "preview_fixture_authorized",
        "security_state_creation_by_plasma_authorized", "security_mutation_by_test_harness_authorized",
        "oem_transition_execution_authorized", "secret_oem_key_material_required",
        "secret_oem_key_material_allowed", "observation_cache_reuse_authorized",
    ):
        _require(boundary.get(key) is False, f"{key}: unsafe readiness authorization")
    for key in (
        "fixture_state_must_be_preprovisioned", "fixture_provenance_required",
        "public_oem_metadata_observation_required",
    ):
        _require(boundary.get(key) is True, f"{key}: required readiness boundary missing")
    _require(boundary.get("unknown_or_stale_observation_decision") == "deny", "unknown/stale observation must deny")

    evidence = plan.get("required_hil_evidence")
    _require(isinstance(evidence, list) and set(evidence) == REQUIRED_EVIDENCE and len(evidence) == len(REQUIRED_EVIDENCE), "HIL evidence schema drifted")

    fixture = plan.get("fixture_policy")
    _require(isinstance(fixture, dict), "fixture policy missing")
    _require(fixture.get("normal_state_fixture_class") == "preprovisioned_recoverable_test_device", "normal fixture class drifted")
    _require(fixture.get("rdp2_fixture_class") == "preprovisioned_rdp2_dedicated_device", "RDP2 dedicated fixture class drifted")
    _require(fixture.get("rdp2_creation_by_plasma_authorized") is False, "Plasma may not create RDP2")
    _require(fixture.get("rdp2_regression_by_test_harness_authorized") is False, "test harness may not regress RDP2")
    _require(fixture.get("rdp2_recovery_assumed") is False, "RDP2 recovery must not be assumed")
    _require(fixture.get("oem2_unlock_execution_by_test_harness_authorized") is False, "test harness may not execute OEM2 unlock")
    for key in (
        "secret_oem_key_material_input_allowed", "secret_oem_key_material_persistence_allowed",
        "secret_oem_key_material_logging_allowed", "test_harness_may_write_option_bytes",
        "test_harness_may_regress_rdp", "test_harness_may_mass_erase",
        "test_harness_may_reset_for_state_discovery",
    ):
        _require(fixture.get(key) is False, f"{key}: unsafe fixture behavior")

    design = plan.get("matrix_design")
    _require(isinstance(design, dict), "matrix design missing")
    _require(design.get("active_subfamily_count") == 12, "Active subfamily count drifted")
    _require(design.get("logical_security_state_count") == 7, "logical security-state count drifted")
    _require(design.get("cell_template_count") == 10, "cell-template count drifted")
    _require(design.get("test_cell_count") == 120, "test-cell count drifted")
    _require(design.get("cells_per_active_subfamily") == 10, "cells-per-subfamily drifted")
    _require(set(design.get("execution_context_split_states", [])) == SPLIT_STATES, "split-state set drifted")
    _require(set(design.get("single_context_states", [])) == SINGLE_STATES, "single-context state set drifted")
    _require(design.get("coverage_rule") == "all_active_subfamilies_all_security_debug_contexts", "coverage rule drifted")

    upstream_rows = {row["state_id"]: row for row in observer["debug_expectations"]}
    templates = plan.get("test_cell_templates")
    _require(isinstance(templates, list) and len(templates) == 10, "HIL template matrix must contain exactly 10 templates")
    suffixes: set[str] = set()
    coverage: Counter[str] = Counter()
    split_contexts: dict[str, set[str]] = {}
    for cell in templates:
        _require(isinstance(cell, dict), "test-cell template must be object")
        suffix = cell.get("id_suffix")
        state = cell.get("state_id")
        context = cell.get("execution_context")
        _require(isinstance(suffix, str) and suffix and suffix not in suffixes, f"invalid/duplicate template suffix {suffix}")
        _require(state in EXPECTED_STATES, f"{suffix}: invalid security state")
        _require(context in {"not_applicable", "secure", "nonsecure", "unknown"}, f"{suffix}: invalid execution context")
        row = upstream_rows[state]
        if "expected_debug_class" in cell:
            _require(cell["expected_debug_class"] == row.get("expected_debug_class"), f"{suffix}: debug expectation drifted from upstream")
        if state in SPLIT_STATES:
            _require(context in {"secure", "nonsecure"}, f"{suffix}: split state requires explicit secure/nonsecure context")
            split_contexts.setdefault(state, set()).add(context)
            if state in U5_UNRESOLVED_SPLIT_STATES:
                expected = row["secure_execution_attach_expected"] if context == "secure" else row["nonsecure_execution_attach_expected"]
                _require(expected == "unknown_requires_hil", f"{suffix}: upstream U5 uncertainty unexpectedly resolved")
                _require(cell.get("expected_attach") == expected, f"{suffix}: attach expectation drifted from upstream")
        else:
            _require(context in {"not_applicable", "unknown"}, f"{suffix}: single-context state has invalid execution context")
        if state in RDP2_STATES:
            _require(cell.get("fixture_class") == "preprovisioned_rdp2_dedicated_device", f"{suffix}: RDP2 requires dedicated fixture")
            _require(cell.get("expected_debug_class") == "none", f"{suffix}: RDP2 normal debug must be none")
            _require(cell.get("unconditionally_terminal") is False, f"{suffix}: RDP2 must not be modeled terminal")
            _require(cell.get("conditional_lifecycle_exit_requires_oem2") is True, f"{suffix}: RDP2 conditional OEM2 boundary missing")
        suffixes.add(suffix)
        coverage[state] += 1

    for state in EXPECTED_STATES:
        expected_count = 2 if state in SPLIT_STATES else 1
        _require(coverage[state] == expected_count, f"{state}: HIL template coverage cardinality drifted")
    for state in SPLIT_STATES:
        _require(split_contexts.get(state) == {"secure", "nonsecure"}, f"{state}: execution contexts incomplete")
    _require(len(ACTIVE_SUBFAMILIES) * len(templates) == design["test_cell_count"], "expanded HIL cell count drifted")

    stops = plan.get("stop_conditions")
    _require(isinstance(stops, list) and len(stops) >= 10 and all(isinstance(x, str) and x for x in stops), "stop conditions incomplete")
    _require(any("STM32U5G9ZJJ3Q" in item for item in stops), "Preview quarantine stop condition missing")
    _require(any(REQUIRED_TARGET_CONFIG in item for item in stops), "target-config stop condition missing")

    result = plan.get("readiness_result")
    _require(isinstance(result, dict), "readiness result missing")
    for key in (
        "hil_matrix_plan_complete", "all_active_subfamilies_covered", "required_evidence_schema_complete",
        "destructive_state_creation_blocked", "rdp2_dedicated_fixture_policy_defined",
        "oem_public_metadata_evidence_required", "secret_oem_key_material_excluded",
        "u5_unresolved_debug_semantics_preserved", "preview_quarantine_remains_enforced",
    ):
        _require(result.get(key) is True, f"{key}: required readiness result missing")
    for key in (
        "fixture_inventory_bound", "hil_execution_ready", "hil_executed", "observer_hil_validated",
        "oem_state_observer_hil_validated", "debug_attach_hil_validated",
        "production_manifest_admission_authorized", "runtime_programming_authorized",
        "oem_key_operation_authorized",
    ):
        _require(result.get(key) is False, f"{key}: premature HIL/Production claim")
    _require(plan.get("next_research_gate") == NEXT_GATE, "next research gate drifted")


def build_gate_result(path: Path = PLAN) -> dict[str, Any]:
    plan = _read(path)
    validate_plan(plan)
    return {
        "schema_version": 1,
        "transaction": TRANSACTION,
        "authority": "research_only",
        "family": "STM32U5",
        "canonical_active_identity_count": 265,
        "quarantined_preview_exact_icpns": ["STM32U5G9ZJJ3Q"],
        "production_exact_icpn_count": 2017,
        "active_subfamilies": 12,
        "logical_security_states": 7,
        "hil_test_cells": 120,
        "required_evidence_fields": len(REQUIRED_EVIDENCE),
        "rdp2_unconditionally_terminal": False,
        "u5_rdp0_5_debug_semantics_resolved": False,
        "u5_rdp1_debug_semantics_resolved": False,
        "fixture_inventory_bound": False,
        "hil_execution_ready": False,
        "hil_executed": False,
        "observer_hil_validated": False,
        "oem_state_observer_hil_validated": False,
        "debug_attach_hil_validated": False,
        "production_manifest_admission_authorized": False,
        "runtime_programming_authorized": False,
        "oem_key_operation_authorized": False,
        "next_research_gate": plan["next_research_gate"],
    }


def negative_controls(plan: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []

    execute = copy.deepcopy(plan)
    execute["readiness_boundary"]["hil_execution_authorized"] = True
    cases.append(("HIL execution prematurely authorized", execute))

    missing_subfamily = copy.deepcopy(plan)
    missing_subfamily["active_subfamily_scope"] = missing_subfamily["active_subfamily_scope"][:-1]
    cases.append(("Active subfamily omitted", missing_subfamily))

    preview_fixture = copy.deepcopy(plan)
    preview_fixture["readiness_boundary"]["preview_fixture_authorized"] = True
    cases.append(("Preview fixture admitted", preview_fixture))

    missing_template = copy.deepcopy(plan)
    missing_template["test_cell_templates"] = missing_template["test_cell_templates"][:-1]
    cases.append(("HIL matrix template missing", missing_template))

    resolve_rdp05 = copy.deepcopy(plan)
    next(c for c in resolve_rdp05["test_cell_templates"] if c["id_suffix"] == "TZ1-RDP0_5-NS")["expected_attach"] = "allow"
    cases.append(("U5 RDP0.5 debug falsely resolved", resolve_rdp05))

    resolve_rdp1 = copy.deepcopy(plan)
    next(c for c in resolve_rdp1["test_cell_templates"] if c["id_suffix"] == "TZ1-RDP1-NS")["expected_attach"] = "allow"
    cases.append(("U5 RDP1 debug falsely resolved", resolve_rdp1))

    terminal_rdp2 = copy.deepcopy(plan)
    next(c for c in terminal_rdp2["test_cell_templates"] if c["state_id"] == "TZ0_RDP2")["unconditionally_terminal"] = True
    cases.append(("RDP2 falsely made terminal", terminal_rdp2))

    secret_key = copy.deepcopy(plan)
    secret_key["fixture_policy"]["secret_oem_key_material_input_allowed"] = True
    cases.append(("secret OEM key input enabled", secret_key))

    oem_unlock = copy.deepcopy(plan)
    oem_unlock["fixture_policy"]["oem2_unlock_execution_by_test_harness_authorized"] = True
    cases.append(("OEM2 unlock execution enabled", oem_unlock))

    target_drift = copy.deepcopy(plan)
    target_drift["required_target_config"] = "tcl/target/other.cfg"
    cases.append(("canonical target config drifted", target_drift))

    admitted = copy.deepcopy(plan)
    admitted["readiness_result"]["production_manifest_admission_authorized"] = True
    cases.append(("Production admission prematurely opened", admitted))

    return cases


if __name__ == "__main__":
    print(json.dumps(build_gate_result(), sort_keys=True))

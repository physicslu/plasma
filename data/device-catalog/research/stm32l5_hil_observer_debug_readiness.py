#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError
from stm32l5_security_state_observer_debug import (
    EXPECTED_STATES,
    build_gate_result as build_observer_gate_result,
)

HERE = Path(__file__).resolve().parent
PLAN = HERE / "stm32l5-hil-observer-debug-readiness.json"
OBSERVER_POLICY = HERE / "stm32l5-security-state-observer-debug-policy.json"
TRANSACTION = "stm32l5-hil-observer-debug-matrix-readiness-gate"
DEVICE_LINES = {"STM32L552", "STM32L562"}
SPLIT_STATES = {"TZ1_RDP0", "TZ1_RDP0_5", "TZ1_RDP1"}
SINGLE_STATES = {"TZ0_RDP0", "TZ0_RDP1", "TZ0_RDP2", "TZ1_RDP2"}
RDP2_STATES = {"TZ0_RDP2", "TZ1_RDP2"}
REQUIRED_EVIDENCE = {
    "fixture_identifier", "device_line", "commercial_icpn", "preprovisioned_security_state",
    "execution_context", "debug_probe_identity", "debug_probe_firmware_version",
    "backend_identity_and_version", "connection_mode", "raw_attach_result", "observed_tzen_state",
    "observed_rdp_level", "observed_execution_state", "timestamp_utc",
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
    _require(upstream.get("modeled_security_states") == 7, "observer state count drifted")
    _require(upstream.get("observer_contract_defined") is True, "observer contract missing")
    _require(upstream.get("debug_expectation_matrix_complete") is True, "debug matrix incomplete")
    _require(upstream.get("observer_hil_validated") is False, "observer HIL unexpectedly claimed")
    _require(upstream.get("debug_attach_hil_validated") is False, "debug HIL unexpectedly claimed")
    _require(upstream.get("runtime_programming_authorized") is False, "runtime programming fence opened")
    _require(upstream.get("production_manifest_admission_authorized") is False, "Production fence opened")
    _require(upstream.get("exact_icpn_count") == 1862, "Production exact ICPN count drifted")
    _require(upstream.get("next_research_gate") == TRANSACTION, "upstream next-gate continuity drifted")
    return _read(OBSERVER_POLICY)


def validate_plan(plan: dict[str, Any]) -> None:
    observer = validate_upstream()
    _require(plan.get("schema_version") == 1, "HIL readiness schema drifted")
    _require(plan.get("transaction") == TRANSACTION, "HIL readiness transaction drifted")
    _require(plan.get("authority") == "research_only", "HIL readiness authority escaped research-only")
    _require(plan.get("family") == "STM32L5", "HIL readiness family drifted")
    _require(set(plan.get("device_lines", [])) == DEVICE_LINES, "device-line scope drifted")
    _require(plan.get("upstream_observer_policy") == OBSERVER_POLICY.name, "observer policy binding drifted")
    _require(plan.get("exact_icpn_count") == 1862, "exact ICPN count drifted")

    boundary = plan.get("readiness_boundary")
    _require(isinstance(boundary, dict), "readiness boundary missing")
    for key in (
        "hil_execution_authorized", "runtime_debug_attach_authorized", "runtime_programming_authorized",
        "production_manifest_admission_authorized", "security_state_creation_by_plasma_authorized",
        "security_mutation_by_test_harness_authorized", "observation_cache_reuse_authorized",
    ):
        _require(boundary.get(key) is False, f"{key}: unsafe readiness authorization")
    _require(boundary.get("fixture_state_must_be_preprovisioned") is True, "preprovisioned fixture requirement missing")
    _require(boundary.get("fixture_provenance_required") is True, "fixture provenance requirement missing")
    _require(boundary.get("unknown_or_stale_observation_decision") == "deny", "unknown/stale state must deny")

    evidence = plan.get("required_hil_evidence")
    _require(isinstance(evidence, list) and set(evidence) == REQUIRED_EVIDENCE and len(evidence) == len(REQUIRED_EVIDENCE), "HIL evidence schema drifted")

    fixture = plan.get("fixture_policy")
    _require(isinstance(fixture, dict), "fixture policy missing")
    _require(fixture.get("rdp2_fixture_class") == "preprovisioned_terminal_sacrificial_device", "RDP2 sacrificial fixture class drifted")
    _require(fixture.get("rdp2_creation_by_plasma_authorized") is False, "Plasma may not create RDP2")
    _require(fixture.get("rdp2_recovery_expected") is False, "RDP2 recovery must not be expected")
    for key in ("test_harness_may_write_option_bytes", "test_harness_may_regress_rdp", "test_harness_may_mass_erase", "test_harness_may_reset_for_state_discovery"):
        _require(fixture.get(key) is False, f"{key}: unsafe HIL fixture behavior")

    design = plan.get("matrix_design")
    _require(isinstance(design, dict), "matrix design missing")
    _require(design.get("device_line_count") == 2, "device-line count drifted")
    _require(design.get("logical_security_state_count") == 7, "logical security-state count drifted")
    _require(design.get("test_cell_count") == 20, "test-cell count drifted")
    _require(design.get("cells_per_device_line") == 10, "cells-per-line drifted")
    _require(set(design.get("execution_context_split_states", [])) == SPLIT_STATES, "split-state set drifted")
    _require(set(design.get("single_context_states", [])) == SINGLE_STATES, "single-context state set drifted")

    upstream_rows = {row["state_id"]: row for row in observer["debug_expectations"]}
    cells = plan.get("test_cells")
    _require(isinstance(cells, list) and len(cells) == 20, "HIL matrix must contain exactly 20 cells")
    ids: set[str] = set()
    line_counts: Counter[str] = Counter()
    coverage: Counter[tuple[str, str]] = Counter()
    split_contexts: dict[tuple[str, str], set[str]] = {}
    for cell in cells:
        _require(isinstance(cell, dict), "test cell must be object")
        cid = cell.get("id")
        line = cell.get("device_line")
        state = cell.get("state_id")
        context = cell.get("execution_context")
        _require(isinstance(cid, str) and cid and cid not in ids, f"invalid/duplicate cell id {cid}")
        _require(line in DEVICE_LINES, f"{cid}: invalid device line")
        _require(state in EXPECTED_STATES, f"{cid}: invalid security state")
        _require(context in {"not_applicable", "secure", "nonsecure", "unknown"}, f"{cid}: invalid execution context")
        row = upstream_rows[state]
        if "expected_debug_class" in cell:
            _require(cell["expected_debug_class"] == row.get("expected_debug_class"), f"{cid}: debug expectation drifted from upstream")
        if state in SPLIT_STATES:
            _require(context in {"secure", "nonsecure"}, f"{cid}: split state requires explicit secure/nonsecure context")
            split_contexts.setdefault((line, state), set()).add(context)
            if state in {"TZ1_RDP0_5", "TZ1_RDP1"}:
                expected = row["secure_execution_attach_expected"] if context == "secure" else row["nonsecure_execution_attach_expected"]
                _require(cell.get("expected_attach") == expected, f"{cid}: attach expectation drifted from upstream")
        else:
            _require(context in {"not_applicable", "unknown"}, f"{cid}: single-context state has invalid execution context")
        if state in RDP2_STATES:
            _require(cell.get("fixture_class") == "preprovisioned_terminal_sacrificial_device", f"{cid}: RDP2 requires sacrificial fixture")
            _require(cell.get("expected_debug_class") == "none", f"{cid}: RDP2 debug must be none")
        if state == "TZ1_RDP1" and context == "nonsecure":
            _require(cell.get("connection_mode") == "hot_plug", f"{cid}: documented RDP1 non-secure case requires hot-plug plan")
        ids.add(cid)
        line_counts[line] += 1
        coverage[(line, state)] += 1

    _require(line_counts == Counter({"STM32L552": 10, "STM32L562": 10}), "per-device-line HIL cell count drifted")
    for line in DEVICE_LINES:
        for state in EXPECTED_STATES:
            expected_count = 2 if state in SPLIT_STATES else 1
            _require(coverage[(line, state)] == expected_count, f"{line}/{state}: HIL coverage cardinality drifted")
        for state in SPLIT_STATES:
            _require(split_contexts.get((line, state)) == {"secure", "nonsecure"}, f"{line}/{state}: execution contexts incomplete")

    stops = plan.get("stop_conditions")
    _require(isinstance(stops, list) and len(stops) >= 6 and all(isinstance(x, str) and x for x in stops), "stop conditions incomplete")

    result = plan.get("readiness_result")
    _require(isinstance(result, dict), "readiness result missing")
    for key in ("hil_matrix_plan_complete", "required_evidence_schema_complete", "destructive_state_creation_blocked", "rdp2_sacrificial_fixture_policy_defined"):
        _require(result.get(key) is True, f"{key}: required readiness result missing")
    for key in ("fixture_inventory_bound", "hil_execution_ready", "hil_executed", "observer_hil_validated", "debug_attach_hil_validated", "production_manifest_admission_authorized", "runtime_programming_authorized"):
        _require(result.get(key) is False, f"{key}: premature HIL/Production claim")
    _require(plan.get("next_research_gate") == "stm32l5-hil-fixture-inventory-binding-gate", "next research gate drifted")


def build_gate_result(path: Path = PLAN) -> dict[str, Any]:
    plan = _read(path)
    validate_plan(plan)
    return {
        "schema_version": 1,
        "transaction": TRANSACTION,
        "authority": "research_only",
        "family": "STM32L5",
        "device_lines": 2,
        "logical_security_states": 7,
        "hil_test_cells": 20,
        "fixture_inventory_bound": False,
        "hil_execution_ready": False,
        "hil_executed": False,
        "production_manifest_admission_authorized": False,
        "runtime_programming_authorized": False,
        "exact_icpn_count": 1862,
        "next_research_gate": plan["next_research_gate"],
    }


def negative_controls(plan: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []
    execute = copy.deepcopy(plan)
    execute["readiness_boundary"]["hil_execution_authorized"] = True
    cases.append(("HIL execution prematurely authorized", execute))

    create_rdp2 = copy.deepcopy(plan)
    create_rdp2["fixture_policy"]["rdp2_creation_by_plasma_authorized"] = True
    cases.append(("Plasma allowed to create RDP2", create_rdp2))

    missing = copy.deepcopy(plan)
    missing["test_cells"] = missing["test_cells"][:-1]
    cases.append(("HIL matrix cell missing", missing))

    bad_fixture = copy.deepcopy(plan)
    next(c for c in bad_fixture["test_cells"] if c["state_id"] == "TZ1_RDP2")["fixture_class"] = "recoverable_device"
    cases.append(("RDP2 fixture not sacrificial", bad_fixture))

    admitted = copy.deepcopy(plan)
    admitted["readiness_result"]["production_manifest_admission_authorized"] = True
    cases.append(("Production admission prematurely opened", admitted))
    return cases

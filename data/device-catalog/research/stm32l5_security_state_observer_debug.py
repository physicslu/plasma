#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from device_catalog_admission_framework import AdmissionError
from stm32l5_security_state_gate import build_gate_result as build_security_gate_result
from stm32l5_runtime_enforcement import build_gate_result as build_runtime_gate_result

HERE = Path(__file__).resolve().parent
POLICY = HERE / "stm32l5-security-state-observer-debug-policy.json"
TRANSACTION = "stm32l5-security-state-observer-and-debug-validation-gate"
EXPECTED_STATES = {
    "TZ0_RDP0", "TZ0_RDP1", "TZ0_RDP2",
    "TZ1_RDP0", "TZ1_RDP0_5", "TZ1_RDP1", "TZ1_RDP2",
}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def _read(path: Path = POLICY) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "observer/debug policy root must be object")
    return value


def validate_upstream() -> None:
    security = build_security_gate_result()
    runtime = build_runtime_gate_result()
    _require(security["security_state_model_complete"] is True, "security-state model not complete")
    _require(security["runtime_programming_authorized"] is False, "upstream security gate opened runtime programming")
    _require(runtime["default_deny_enforced"] is True, "runtime default-deny enforcement missing")
    _require(runtime["target_touching_operation_authorized"] is False, "upstream runtime gate opened target access")
    _require(runtime["production_manifest_admission_authorized"] is False, "upstream runtime gate opened Production")


def validate_policy(policy: dict[str, Any]) -> None:
    _require(policy.get("schema_version") == 1, "observer/debug schema drifted")
    _require(policy.get("transaction") == TRANSACTION, "observer/debug transaction drifted")
    _require(policy.get("authority") == "research_only", "observer/debug authority escaped research-only")
    _require(policy.get("family") == "STM32L5", "observer/debug family drifted")
    _require(policy.get("device_lines") == ["STM32L552", "STM32L562"], "observer/debug device-line scope drifted")

    sources = policy.get("manufacturer_sources")
    _require(isinstance(sources, list) and len(sources) >= 3, "manufacturer evidence missing")
    seen: set[str] = set()
    for src in sources:
        _require(isinstance(src, dict), "manufacturer source must be object")
        sid = src.get("id")
        url = src.get("url")
        _require(isinstance(sid, str) and sid and sid not in seen, "invalid/duplicate source id")
        _require(src.get("authority") == "STMicroelectronics", f"{sid}: non-ST authority")
        _require(isinstance(url, str) and url.startswith("https://"), f"{sid}: invalid URL")
        _require(urlparse(url).hostname in {"st.com", "www.st.com", "wiki.st.com"}, f"{sid}: non-ST host")
        _require(isinstance(src.get("observations"), list) and src["observations"], f"{sid}: observations missing")
        seen.add(sid)

    observer = policy.get("observer_contract")
    _require(isinstance(observer, dict), "observer contract missing")
    _require(observer.get("mode") == "passive_fail_closed", "observer must remain passive/fail-closed")
    _require(observer.get("required_observations") == ["tzen_state", "rdp_level", "cpu_security_execution_state", "debug_attach_outcome"], "required observations drifted")
    _require(observer.get("minimum_quality_for_target_enablement") == "observed", "target enablement must require observed state")
    _require(observer.get("unknown_dimension_decision") == "deny", "unknown dimension must deny")
    _require(observer.get("stale_observation_decision") == "deny", "stale observation must deny")
    _require(observer.get("observation_cache_reuse_authorized") is False, "observer cache reuse unexpectedly enabled")
    for key in (
        "state_mutation_for_observation_authorized",
        "reset_for_observation_authorized",
        "option_byte_write_for_observation_authorized",
        "rdp_regression_for_observation_authorized",
        "mass_erase_for_observation_authorized",
    ):
        _require(observer.get(key) is False, f"{key}: unsafe observer behavior enabled")

    matrix = policy.get("debug_expectations")
    _require(isinstance(matrix, list) and len(matrix) == 7, "debug matrix cardinality drifted")
    by_state: dict[str, dict[str, Any]] = {}
    for row in matrix:
        sid = row.get("state_id") if isinstance(row, dict) else None
        _require(isinstance(sid, str) and sid in EXPECTED_STATES and sid not in by_state, f"invalid/duplicate debug state {sid}")
        _require(row.get("runtime_debug_attach_authorized") is False, f"{sid}: runtime debug attach prematurely enabled")
        by_state[sid] = row
    _require(set(by_state) == EXPECTED_STATES, "debug matrix state set drifted")
    for sid in ("TZ0_RDP2", "TZ1_RDP2"):
        _require(by_state[sid].get("expected_debug_class") == "none", f"{sid}: RDP2 debug must be none")
        _require(by_state[sid].get("terminal") is True, f"{sid}: RDP2 must be terminal")
    for sid in ("TZ1_RDP0_5", "TZ1_RDP1"):
        _require(by_state[sid].get("secure_execution_attach_expected") == "deny", f"{sid}: secure execution attach must deny")
        _require(by_state[sid].get("nonsecure_execution_attach_expected") == "potentially_available_requires_hil", f"{sid}: nonsecure attach must remain HIL-gated")

    boundary = policy.get("validation_boundary")
    _require(isinstance(boundary, dict), "validation boundary missing")
    _require(boundary.get("offline_contract_validation") is True, "offline contract validation missing")
    for key in (
        "hardware_observation_executed", "hil_debug_matrix_executed", "openocd_debug_behavior_validated",
        "stlink_debug_behavior_validated", "programming_algorithm_validated", "flash_geometry_validated",
        "security_mutation_validated",
    ):
        _require(boundary.get(key) is False, f"{key}: unsupported validation claim")

    result = policy.get("admission_result")
    _require(isinstance(result, dict), "admission result missing")
    for key in (
        "observer_contract_defined", "debug_expectation_matrix_complete", "unknown_and_stale_state_fail_closed",
        "security_mutation_for_observation_blocked",
    ):
        _require(result.get(key) is True, f"{key}: required result missing")
    for key in (
        "observer_hil_validated", "debug_attach_hil_validated", "backend_state_enforcement_integrated",
        "target_touching_operation_authorized", "production_manifest_admission_authorized",
        "runtime_programming_authorized", "hil_validated",
    ):
        _require(result.get(key) is False, f"{key}: unsafe claim enabled")
    _require(policy.get("next_research_gate") == "stm32l5-hil-observer-debug-matrix-readiness-gate", "next gate drifted")


def build_gate_result(path: Path = POLICY) -> dict[str, Any]:
    validate_upstream()
    policy = _read(path)
    validate_policy(policy)
    return {
        "schema_version": 1,
        "transaction": TRANSACTION,
        "authority": "research_only",
        "family": "STM32L5",
        "modeled_security_states": len(policy["debug_expectations"]),
        "observer_contract_defined": True,
        "debug_expectation_matrix_complete": True,
        "observer_hil_validated": False,
        "debug_attach_hil_validated": False,
        "target_touching_operation_authorized": False,
        "production_manifest_admission_authorized": False,
        "runtime_programming_authorized": False,
        "exact_icpn_count": 1862,
        "next_research_gate": policy["next_research_gate"],
    }


def negative_controls(policy: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []
    fail_open_unknown = copy.deepcopy(policy)
    fail_open_unknown["observer_contract"]["unknown_dimension_decision"] = "allow"
    cases.append(("unknown state fail-open", fail_open_unknown))

    cached = copy.deepcopy(policy)
    cached["observer_contract"]["observation_cache_reuse_authorized"] = True
    cases.append(("stale/cached observation reuse", cached))

    rdp2_debug = copy.deepcopy(policy)
    next(r for r in rdp2_debug["debug_expectations"] if r["state_id"] == "TZ1_RDP2")["runtime_debug_attach_authorized"] = True
    cases.append(("RDP2 debug enabled", rdp2_debug))

    secure_attach = copy.deepcopy(policy)
    next(r for r in secure_attach["debug_expectations"] if r["state_id"] == "TZ1_RDP1")["secure_execution_attach_expected"] = "allow"
    cases.append(("secure execution attach allowed at TZ1_RDP1", secure_attach))

    hil_claim = copy.deepcopy(policy)
    hil_claim["admission_result"]["observer_hil_validated"] = True
    cases.append(("premature HIL observer claim", hil_claim))
    return cases

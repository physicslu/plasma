#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from device_catalog_admission_framework import AdmissionError
from stm32u5_security_state_gate import build_gate_result as build_security_gate_result
from stm32u5_runtime_enforcement import build_gate_result as build_runtime_gate_result

HERE = Path(__file__).resolve().parent
POLICY = HERE / "stm32u5-security-state-observer-debug-policy.json"
TRANSACTION = "stm32u5-security-state-observer-and-debug-validation-gate"
NEXT_GATE = "stm32u5-hil-observer-debug-matrix-readiness-gate"
EXPECTED_STATES = {
    "TZ0_RDP0", "TZ0_RDP1", "TZ0_RDP2",
    "TZ1_RDP0", "TZ1_RDP0_5", "TZ1_RDP1", "TZ1_RDP2",
}
EXPECTED_DEBUG_OBSERVATIONS = [
    "tzen_state",
    "rdp_level",
    "cpu_security_execution_state",
    "debug_attach_outcome",
]
EXPECTED_PUBLIC_OEM_OBSERVATIONS = [
    "oem1_key_state",
    "oem1_lock_state",
    "oem2_key_state",
    "oem2_lock_state",
]
RDP2_STATES = {"TZ0_RDP2", "TZ1_RDP2"}
U5_CONDITIONED_STATES = {"TZ1_RDP0_5", "TZ1_RDP1"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def _read(path: Path = POLICY) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), "STM32U5 observer/debug policy root must be object")
    return value


def validate_upstream() -> None:
    security = build_security_gate_result()
    runtime = build_runtime_gate_result()

    _require(security.get("authority") == "research_only", "security-state authority escaped research-only")
    _require(security.get("canonical_active_identity_count") == 265, "upstream canonical Active identity count drifted")
    _require(security.get("quarantined_preview_identity_count") == 1, "upstream Preview quarantine count drifted")
    _require(security.get("production_exact_icpn_count") == 2017, "upstream Production ICPN count drifted")
    _require(security.get("security_state_admission_model_complete") is True, "security-state admission model incomplete")
    _require(security.get("rdp2_unconditionally_terminal") is False, "security RDP2 semantics regressed to terminal")
    _require(security.get("exact_rdp1_regression_semantics_left_unresolved") is True, "security gate hid U5 RDP1 uncertainty")
    _require(security.get("runtime_programming_authorized") is False, "security gate opened runtime programming")
    _require(security.get("next_research_gate") == "stm32u5-runtime-enforcement-admission-gate", "security gate continuity drifted")

    _require(runtime.get("authority") == "research_only", "runtime authority escaped research-only")
    _require(runtime.get("canonical_active_identity_count") == 265, "runtime canonical Active identity count drifted")
    _require(runtime.get("quarantined_preview_exact_icpns") == ["STM32U5G9ZJJ3Q"], "runtime Preview quarantine drifted")
    _require(runtime.get("production_exact_icpn_count") == 2017, "runtime Production ICPN count drifted")
    _require(runtime.get("default_deny_enforced") is True, "runtime default-deny missing")
    _require(runtime.get("target_plane_decisions") == 105, "runtime target decision matrix drifted")
    _require(runtime.get("target_plane_allow_count") == 0, "runtime target plane contains allow")
    _require(runtime.get("rdp2_unconditionally_terminal") is False, "runtime RDP2 semantics regressed to terminal")
    _require(runtime.get("rdp1_regression_semantics_resolved") is False, "runtime falsely resolved U5 RDP1 regression")
    _require(runtime.get("target_touching_operation_authorized") is False, "runtime gate opened target access")
    _require(runtime.get("production_manifest_admission_authorized") is False, "runtime gate opened Production")
    _require(runtime.get("runtime_programming_authorized") is False, "runtime gate opened programming")
    _require(runtime.get("oem_key_operation_authorized") is False, "runtime gate opened OEM operations")
    _require(runtime.get("next_research_gate") == TRANSACTION, "runtime next-gate continuity drifted")


def validate_policy(policy: dict[str, Any]) -> None:
    _require(policy.get("schema_version") == 1, "observer/debug schema drifted")
    _require(policy.get("transaction") == TRANSACTION, "observer/debug transaction drifted")
    _require(policy.get("authority") == "research_only", "observer/debug authority escaped research-only")
    _require(policy.get("family") == "STM32U5", "observer/debug family drifted")
    _require(policy.get("canonical_active_identity_count") == 265, "canonical Active identity count drifted")
    _require(policy.get("quarantined_preview_exact_icpns") == ["STM32U5G9ZJJ3Q"], "Preview quarantine drifted")
    _require(policy.get("production_exact_icpn_count") == 2017, "Production exact ICPN count drifted")
    _require(policy.get("upstream_security_state_model") == "stm32u5-security-state-model.json", "security-state binding drifted")
    _require(policy.get("upstream_runtime_policy") == "stm32u5-runtime-enforcement-policy.json", "runtime-policy binding drifted")

    sources = policy.get("manufacturer_sources")
    _require(isinstance(sources, list) and len(sources) >= 3, "manufacturer evidence missing")
    seen: set[str] = set()
    for src in sources:
        _require(isinstance(src, dict), "manufacturer source must be object")
        sid = src.get("id")
        url = src.get("url")
        _require(isinstance(sid, str) and sid and sid not in seen, "invalid/duplicate source id")
        _require(src.get("authority") == "STMicroelectronics", f"{sid}: non-ST authority")
        _require(isinstance(url, str) and url.startswith("https://"), f"{sid}: invalid source URL")
        _require(urlparse(url).hostname in {"st.com", "www.st.com", "wiki.st.com"}, f"{sid}: non-ST source host")
        _require(isinstance(src.get("observations"), list) and src["observations"], f"{sid}: observations missing")
        seen.add(sid)
    _require({"st-rm0456", "st-wiki-rdp"}.issubset(seen), "required STM32U5 security/debug authorities missing")

    observer = policy.get("observer_contract")
    _require(isinstance(observer, dict), "observer contract missing")
    _require(observer.get("mode") == "passive_fail_closed", "observer must remain passive/fail-closed")
    _require(observer.get("required_observations_for_debug_classification") == EXPECTED_DEBUG_OBSERVATIONS, "debug observation set drifted")
    _require(observer.get("minimum_quality_for_target_enablement") == "observed", "target enablement must require observed state")
    _require(observer.get("unknown_dimension_decision") == "deny", "unknown dimension must deny")
    _require(observer.get("stale_observation_decision") == "deny", "stale observation must deny")
    _require(observer.get("observation_cache_reuse_authorized") is False, "observer cache reuse unexpectedly enabled")
    for key in (
        "state_mutation_for_observation_authorized",
        "reset_for_observation_authorized",
        "option_byte_write_for_observation_authorized",
        "rdp_regression_for_observation_authorized",
        "oem_unlock_for_observation_authorized",
        "mass_erase_for_observation_authorized",
    ):
        _require(observer.get(key) is False, f"{key}: unsafe observer behavior enabled")

    oem = policy.get("oem_observer_contract")
    _require(isinstance(oem, dict), "OEM observer contract missing")
    _require(oem.get("mode") == "public_metadata_only_fail_closed", "OEM observer mode drifted")
    _require(oem.get("required_public_metadata_observations") == EXPECTED_PUBLIC_OEM_OBSERVATIONS, "public OEM observation set drifted")
    _require(oem.get("unknown_oem_state_decision") == "deny", "unknown OEM state must deny")
    for key in (
        "secret_key_material_read_authorized",
        "secret_key_material_input_authorized",
        "secret_key_material_persistence_authorized",
        "secret_key_material_logging_authorized",
        "observer_only_oem_transition_authorization",
        "public_metadata_is_sufficient_to_prove_authentication_success",
        "oem_unlock_execution_authorized",
    ):
        _require(oem.get(key) is False, f"OEM observer boundary fail-open: {key}")

    matrix = policy.get("debug_expectations")
    _require(isinstance(matrix, list) and len(matrix) == 7, "debug matrix cardinality drifted")
    by_state: dict[str, dict[str, Any]] = {}
    for row in matrix:
        sid = row.get("state_id") if isinstance(row, dict) else None
        _require(isinstance(sid, str) and sid in EXPECTED_STATES and sid not in by_state, f"invalid/duplicate debug state {sid}")
        _require(row.get("runtime_debug_attach_authorized") is False, f"{sid}: runtime debug attach prematurely enabled")
        by_state[sid] = row
    _require(set(by_state) == EXPECTED_STATES, "debug matrix state set drifted")

    _require(by_state["TZ0_RDP0"].get("expected_debug_class") == "open", "TZ0_RDP0 debug class drifted")
    _require(by_state["TZ0_RDP1"].get("expected_debug_class") == "requires_runtime_validation", "TZ0_RDP1 debug uncertainty was overstated")
    _require(by_state["TZ1_RDP0"].get("expected_debug_class") == "open_but_runtime_unvalidated", "TZ1_RDP0 debug class drifted")
    for sid in U5_CONDITIONED_STATES:
        _require(by_state[sid].get("expected_debug_class") == "execution_state_conditioned_requires_hil", f"{sid}: conditioned U5 debug boundary drifted")
        _require(by_state[sid].get("secure_execution_attach_expected") == "unknown_requires_hil", f"{sid}: secure attach was falsely resolved")
        _require(by_state[sid].get("nonsecure_execution_attach_expected") == "unknown_requires_hil", f"{sid}: nonsecure attach was falsely resolved")
    for sid in RDP2_STATES:
        _require(by_state[sid].get("expected_debug_class") == "none", f"{sid}: RDP2 normal debug must be none")
        _require(by_state[sid].get("unconditionally_terminal") is False, f"{sid}: U5 RDP2 must not be modeled unconditionally terminal")
        _require(by_state[sid].get("conditional_lifecycle_exit_requires_oem2") is True, f"{sid}: OEM2 conditional exit missing")

    unresolved = policy.get("u5_unresolved_debug_semantics")
    _require(isinstance(unresolved, list) and len(unresolved) >= 4, "U5 unresolved debug boundary missing")
    _require(any("RDP0.5" in item for item in unresolved), "U5 RDP0.5 uncertainty was hidden")
    _require(any("RDP1" in item for item in unresolved), "U5 RDP1 debug uncertainty was hidden")

    boundary = policy.get("validation_boundary")
    _require(isinstance(boundary, dict), "validation boundary missing")
    _require(boundary.get("offline_contract_validation") is True, "offline contract validation missing")
    for key in (
        "hardware_observation_executed",
        "hil_debug_matrix_executed",
        "oem_state_observation_hil_validated",
        "openocd_debug_behavior_validated",
        "stlink_debug_behavior_validated",
        "oem2_authentication_path_validated",
        "programming_algorithm_validated",
        "flash_geometry_validated",
        "security_mutation_validated",
    ):
        _require(boundary.get(key) is False, f"{key}: unsupported validation claim")

    result = policy.get("admission_result")
    _require(isinstance(result, dict), "admission result missing")
    for key in (
        "observer_contract_defined",
        "oem_observer_contract_defined",
        "debug_expectation_matrix_complete",
        "unknown_and_stale_state_fail_closed",
        "unknown_oem_state_fail_closed",
        "security_mutation_for_observation_blocked",
        "rdp2_normal_debug_closed_modeled",
        "u5_rdp0_5_debug_semantics_left_unresolved",
        "u5_rdp1_debug_semantics_left_unresolved",
        "preview_quarantine_remains_enforced",
    ):
        _require(result.get(key) is True, f"{key}: required result missing")
    for key in (
        "rdp2_unconditionally_terminal",
        "observer_hil_validated",
        "oem_state_observer_hil_validated",
        "debug_attach_hil_validated",
        "backend_state_enforcement_integrated",
        "target_touching_operation_authorized",
        "production_manifest_admission_authorized",
        "runtime_programming_authorized",
        "oem_key_operation_authorized",
        "hil_validated",
    ):
        _require(result.get(key) is False, f"{key}: unsafe/overstated claim enabled")
    _require(policy.get("next_research_gate") == NEXT_GATE, "next gate drifted")


def build_gate_result(path: Path = POLICY) -> dict[str, Any]:
    validate_upstream()
    policy = _read(path)
    validate_policy(policy)
    return {
        "schema_version": 1,
        "transaction": TRANSACTION,
        "authority": "research_only",
        "family": "STM32U5",
        "canonical_active_identity_count": 265,
        "quarantined_preview_exact_icpns": ["STM32U5G9ZJJ3Q"],
        "production_exact_icpn_count": 2017,
        "modeled_security_states": len(policy["debug_expectations"]),
        "debug_observations_required": len(EXPECTED_DEBUG_OBSERVATIONS),
        "public_oem_observations_modeled": len(EXPECTED_PUBLIC_OEM_OBSERVATIONS),
        "observer_contract_defined": True,
        "oem_observer_contract_defined": True,
        "debug_expectation_matrix_complete": True,
        "rdp2_unconditionally_terminal": False,
        "u5_rdp0_5_debug_semantics_resolved": False,
        "u5_rdp1_debug_semantics_resolved": False,
        "observer_hil_validated": False,
        "oem_state_observer_hil_validated": False,
        "debug_attach_hil_validated": False,
        "target_touching_operation_authorized": False,
        "production_manifest_admission_authorized": False,
        "runtime_programming_authorized": False,
        "oem_key_operation_authorized": False,
        "next_research_gate": policy["next_research_gate"],
    }


def negative_controls(policy: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []

    fail_open_unknown = copy.deepcopy(policy)
    fail_open_unknown["observer_contract"]["unknown_dimension_decision"] = "allow"
    cases.append(("unknown lifecycle state fail-open", fail_open_unknown))

    stale_cache = copy.deepcopy(policy)
    stale_cache["observer_contract"]["observation_cache_reuse_authorized"] = True
    cases.append(("stale observation cache reuse", stale_cache))

    rdp2_debug = copy.deepcopy(policy)
    next(r for r in rdp2_debug["debug_expectations"] if r["state_id"] == "TZ1_RDP2")["runtime_debug_attach_authorized"] = True
    cases.append(("RDP2 debug enabled", rdp2_debug))

    terminal_rdp2 = copy.deepcopy(policy)
    next(r for r in terminal_rdp2["debug_expectations"] if r["state_id"] == "TZ0_RDP2")["unconditionally_terminal"] = True
    cases.append(("RDP2 falsely made terminal", terminal_rdp2))

    rdp05_resolved = copy.deepcopy(policy)
    next(r for r in rdp05_resolved["debug_expectations"] if r["state_id"] == "TZ1_RDP0_5")["nonsecure_execution_attach_expected"] = "allow"
    cases.append(("RDP0.5 debug semantics falsely resolved", rdp05_resolved))

    rdp1_resolved = copy.deepcopy(policy)
    next(r for r in rdp1_resolved["debug_expectations"] if r["state_id"] == "TZ1_RDP1")["secure_execution_attach_expected"] = "deny"
    cases.append(("RDP1 debug semantics falsely resolved", rdp1_resolved))

    oem_unknown_open = copy.deepcopy(policy)
    oem_unknown_open["oem_observer_contract"]["unknown_oem_state_decision"] = "allow"
    cases.append(("unknown OEM state fail-open", oem_unknown_open))

    key_read = copy.deepcopy(policy)
    key_read["oem_observer_contract"]["secret_key_material_read_authorized"] = True
    cases.append(("OEM secret key read enabled", key_read))

    observer_authorizes_oem = copy.deepcopy(policy)
    observer_authorizes_oem["oem_observer_contract"]["observer_only_oem_transition_authorization"] = True
    cases.append(("observer-only OEM transition authorization", observer_authorizes_oem))

    hil_claim = copy.deepcopy(policy)
    hil_claim["admission_result"]["observer_hil_validated"] = True
    cases.append(("premature HIL observer claim", hil_claim))

    preview = copy.deepcopy(policy)
    preview["quarantined_preview_exact_icpns"] = []
    cases.append(("Preview quarantine removed", preview))

    admitted = copy.deepcopy(policy)
    admitted["admission_result"]["production_manifest_admission_authorized"] = True
    cases.append(("premature Production admission", admitted))

    return cases


if __name__ == "__main__":
    print(json.dumps(build_gate_result(), sort_keys=True))

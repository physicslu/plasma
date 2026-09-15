#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError
from stm32l5_hil_fixture_inventory_binding import build_gate_result as build_inventory_gate_result

HERE = Path(__file__).resolve().parent
PLAN = HERE / "stm32l5-hil-fixture-acquisition-provenance.json"
COMMERCIAL = HERE / "stm32l5-commercial-identity-discovery.csv"
TRANSACTION = "stm32l5-hil-fixture-acquisition-and-provenance-gate"
DEVICE_LINES = {"STM32L552", "STM32L562"}
EXPECTED_STATES = {
    "TZ0_RDP0", "TZ0_RDP1", "TZ0_RDP2",
    "TZ1_RDP0", "TZ1_RDP0_5", "TZ1_RDP1", "TZ1_RDP2",
}
RDP2_STATES = {"TZ0_RDP2", "TZ1_RDP2"}
REQUIRED_ACQUISITION_FIELDS = {
    "fixture_identifier", "physical_asset_record_ref", "acquisition_or_transfer_record_ref",
    "commercial_icpn", "device_line", "physical_marking_evidence_ref", "custodian_or_lab_identity",
    "custody_record_ref", "received_at_utc", "source_or_supplier_identity", "availability_status",
}
REQUIRED_STATE_FIELDS = {
    "preprovisioned_security_state", "fixture_class", "security_state_provenance_ref",
    "security_state_evidence_digest", "security_state_verified_at_utc",
}
ALLOWED_AVAILABILITY = {"available", "reserved", "unavailable"}
ALLOWED_CLASSES = {
    "preprovisioned_recoverable_test_device",
    "preprovisioned_terminal_sacrificial_device",
}
PLACEHOLDER_TOKENS = {"todo", "tbd", "unknown", "placeholder", "example", "dummy", "fake", "n/a"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def _read(path: Path = PLAN) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    _require(isinstance(value, dict), f"{path.name}: root must be object")
    return value


def _commercial_identities() -> dict[str, str]:
    rows: dict[str, str] = {}
    with COMMERCIAL.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            icpn = row.get("icpn", "")
            _require(icpn and icpn not in rows, f"commercial identity duplicate/empty: {icpn}")
            if icpn.startswith("STM32L552"):
                line = "STM32L552"
            elif icpn.startswith("STM32L562"):
                line = "STM32L562"
            else:
                raise AdmissionError(f"commercial identity escaped STM32L5 line scope: {icpn}")
            rows[icpn] = line
    _require(len(rows) == 49, "STM32L5 commercial ICPN count drifted")
    return rows


def validate_upstream() -> None:
    upstream = build_inventory_gate_result()
    _require(upstream.get("authority") == "research_only", "upstream inventory gate escaped research-only")
    _require(upstream.get("verified_fixture_count") == 0, "upstream unexpectedly has verified fixtures")
    _require(upstream.get("fixture_inventory_bound") is False, "upstream unexpectedly claims fixture binding")
    _require(upstream.get("hil_execution_ready") is False, "upstream unexpectedly claims HIL readiness")
    _require(upstream.get("hil_executed") is False, "upstream unexpectedly claims HIL execution")
    _require(upstream.get("production_manifest_admission_authorized") is False, "upstream Production fence opened")
    _require(upstream.get("runtime_programming_authorized") is False, "upstream runtime programming fence opened")
    _require(upstream.get("exact_icpn_count") == 1862, "Production exact ICPN count drifted")
    _require(upstream.get("stm32l5_commercial_icpn_count") == 49, "STM32L5 commercial identity scope drifted")
    _require(upstream.get("next_research_gate") == TRANSACTION, "upstream next-gate continuity drifted")


def _non_placeholder(value: Any, field: str) -> None:
    _require(isinstance(value, str) and value.strip(), f"{field}: missing value")
    _require(value.strip().lower() not in PLACEHOLDER_TOKENS, f"{field}: placeholder value forbidden")


def validate_acquisition_record(entry: dict[str, Any], identities: dict[str, str]) -> None:
    _require(set(entry) >= REQUIRED_ACQUISITION_FIELDS | REQUIRED_STATE_FIELDS, "acquisition record missing required fields")
    for field in REQUIRED_ACQUISITION_FIELDS | REQUIRED_STATE_FIELDS:
        _non_placeholder(entry.get(field), field)
    fixture_id = entry["fixture_identifier"]
    icpn = entry["commercial_icpn"]
    line = entry["device_line"]
    state = entry["preprovisioned_security_state"]
    fixture_class = entry["fixture_class"]
    _require(icpn in identities, f"{fixture_id}: ICPN not in retained 49-part manufacturer set")
    _require(line in DEVICE_LINES and identities[icpn] == line, f"{fixture_id}: device-line/ICPN mismatch")
    _require(state in EXPECTED_STATES, f"{fixture_id}: invalid preprovisioned security state")
    _require(fixture_class in ALLOWED_CLASSES, f"{fixture_id}: invalid fixture class")
    _require(entry["availability_status"] in ALLOWED_AVAILABILITY, f"{fixture_id}: invalid availability status")
    if state in RDP2_STATES:
        _require(fixture_class == "preprovisioned_terminal_sacrificial_device", f"{fixture_id}: RDP2 fixture must be terminal/sacrificial")
    else:
        _require(fixture_class == "preprovisioned_recoverable_test_device", f"{fixture_id}: non-RDP2 fixture must be recoverable-class")


def validate_plan(plan: dict[str, Any]) -> None:
    validate_upstream()
    identities = _commercial_identities()
    _require(plan.get("schema_version") == 1, "acquisition schema drifted")
    _require(plan.get("transaction") == TRANSACTION, "acquisition transaction drifted")
    _require(plan.get("authority") == "research_only", "acquisition gate escaped research-only")
    _require(plan.get("family") == "STM32L5", "family drifted")
    _require(set(plan.get("device_lines", [])) == DEVICE_LINES, "device-line scope drifted")
    _require(plan.get("upstream_fixture_inventory") == "stm32l5-hil-fixture-inventory.json", "upstream fixture inventory binding drifted")
    _require(plan.get("commercial_identity_source") == COMMERCIAL.name, "commercial identity source drifted")
    _require(plan.get("exact_icpn_count") == 1862, "exact ICPN count drifted")
    _require(plan.get("stm32l5_commercial_icpn_count") == len(identities), "STM32L5 commercial identity count drifted")

    boundary = plan.get("acquisition_boundary")
    _require(isinstance(boundary, dict), "acquisition boundary missing")
    for key in (
        "external_physical_asset_required", "exact_commercial_icpn_required", "unique_fixture_identifier_required",
        "physical_asset_record_required", "custody_provenance_required",
        "security_state_provenance_required_before_hil_binding", "security_state_evidence_digest_required",
        "rdp2_fixture_must_be_preprovisioned_terminal_sacrificial",
    ):
        _require(boundary.get(key) is True, f"{key}: required acquisition invariant missing")
    for key in (
        "procurement_intent_is_fixture_evidence", "commercial_listing_is_fixture_evidence",
        "board_model_without_unique_asset_identity_is_fixture_evidence", "self_attestation_without_external_record_allowed",
        "security_state_creation_by_plasma_authorized", "security_mutation_by_acquisition_gate_authorized",
        "hil_execution_authorized", "runtime_debug_attach_authorized", "runtime_programming_authorized",
        "production_manifest_admission_authorized",
    ):
        _require(boundary.get(key) is False, f"{key}: unsafe acquisition authorization")

    acquisition_fields = plan.get("required_acquisition_fields")
    _require(isinstance(acquisition_fields, list) and set(acquisition_fields) == REQUIRED_ACQUISITION_FIELDS and len(acquisition_fields) == len(REQUIRED_ACQUISITION_FIELDS), "acquisition field schema drifted")
    state_fields = plan.get("required_state_provenance_fields_before_hil_binding")
    _require(isinstance(state_fields, list) and set(state_fields) == REQUIRED_STATE_FIELDS and len(state_fields) == len(REQUIRED_STATE_FIELDS), "state provenance field schema drifted")
    _require(set(plan.get("allowed_availability_status", [])) == ALLOWED_AVAILABILITY, "availability status set drifted")
    _require(set(plan.get("allowed_fixture_classes", [])) == ALLOWED_CLASSES, "fixture class set drifted")

    allocation = plan.get("full_matrix_reference_allocation")
    _require(isinstance(allocation, dict), "full matrix reference allocation missing")
    _require(allocation.get("security_state_slots_per_device_line") == 7, "state slots per device line drifted")
    _require(allocation.get("device_line_count") == 2, "device line count drifted")
    _require(allocation.get("state_specific_fixture_slots") == 14, "state-specific fixture slot count drifted")
    _require(allocation.get("hil_test_cells") == 20, "HIL test-cell count drifted")
    _require(allocation.get("context_split_cells_may_reuse_same_preprovisioned_state_fixture") is True, "context-split reuse rule drifted")
    _require(allocation.get("fixture_state_mutation_during_hil_allowed") is False, "fixture state mutation during HIL must remain blocked")
    _non_placeholder(allocation.get("note"), "full_matrix_reference_allocation.note")

    records = plan.get("acquisition_records")
    _require(isinstance(records, list), "acquisition records must be a list")
    seen: set[str] = set()
    for entry in records:
        _require(isinstance(entry, dict), "acquisition record must be object")
        validate_acquisition_record(entry, identities)
        fixture_id = entry["fixture_identifier"]
        _require(fixture_id not in seen, f"duplicate fixture identifier: {fixture_id}")
        seen.add(fixture_id)
    _require(len(records) == 0, "this gate snapshot may not invent or self-register acquired hardware")

    coverage = plan.get("provenance_coverage")
    _require(isinstance(coverage, dict), "provenance coverage missing")
    expected = {
        "verified_acquired_fixture_count": 0,
        "device_lines_with_verified_acquisition": 0,
        "security_state_slots_with_verified_provenance": 0,
        "rdp2_terminal_fixture_count": 0,
        "full_matrix_state_slots_required": 14,
        "hil_test_cells_total": 20,
    }
    _require(coverage == expected, "zero-acquisition provenance snapshot drifted")

    result = plan.get("admission_result")
    _require(isinstance(result, dict), "admission result missing")
    for key in (
        "acquisition_schema_defined", "identity_scope_validated", "provenance_requirements_defined",
        "full_matrix_reference_allocation_defined",
    ):
        _require(result.get(key) is True, f"{key}: required acquisition result missing")
    for key in (
        "verified_physical_acquisition_present", "verified_security_state_provenance_present",
        "fixture_inventory_bound", "hil_execution_ready", "hil_executed", "observer_hil_validated",
        "debug_attach_hil_validated", "production_manifest_admission_authorized", "runtime_programming_authorized",
    ):
        _require(result.get(key) is False, f"{key}: unsupported acquisition/HIL/Production claim")

    blocker = plan.get("blocker")
    _require(isinstance(blocker, dict), "external hardware acquisition blocker missing")
    _require(blocker.get("type") == "external_hardware_acquisition_required", "blocker type drifted")
    _non_placeholder(blocker.get("description"), "blocker.description")
    _non_placeholder(blocker.get("resolution"), "blocker.resolution")
    _require(plan.get("next_action") == "external_stm32l5_fixture_acquisition_and_provenance_submission", "next action drifted")
    _require(plan.get("next_research_gate") is None, "software-only gate chain must stop at external hardware blocker")


def build_gate_result(path: Path = PLAN) -> dict[str, Any]:
    plan = _read(path)
    validate_plan(plan)
    return {
        "schema_version": 1,
        "transaction": TRANSACTION,
        "authority": "research_only",
        "family": "STM32L5",
        "stm32l5_commercial_icpn_count": 49,
        "full_matrix_state_specific_fixture_slots": 14,
        "verified_acquired_fixture_count": 0,
        "verified_security_state_slots": 0,
        "fixture_inventory_bound": False,
        "hil_execution_ready": False,
        "hil_executed": False,
        "production_manifest_admission_authorized": False,
        "runtime_programming_authorized": False,
        "exact_icpn_count": 1862,
        "blocker": "external_hardware_acquisition_required",
        "next_action": plan["next_action"],
        "next_research_gate": None,
    }


def negative_controls(plan: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []

    intent = copy.deepcopy(plan)
    intent["acquisition_boundary"]["procurement_intent_is_fixture_evidence"] = True
    cases.append(("procurement intent treated as physical evidence", intent))

    listing = copy.deepcopy(plan)
    listing["acquisition_boundary"]["commercial_listing_is_fixture_evidence"] = True
    cases.append(("commercial listing treated as physical evidence", listing))

    no_asset_id = copy.deepcopy(plan)
    no_asset_id["acquisition_boundary"]["board_model_without_unique_asset_identity_is_fixture_evidence"] = True
    cases.append(("board model accepted without unique asset identity", no_asset_id))

    ready = copy.deepcopy(plan)
    ready["admission_result"]["hil_execution_ready"] = True
    cases.append(("HIL execution claimed ready with zero acquisitions", ready))

    production = copy.deepcopy(plan)
    production["admission_result"]["production_manifest_admission_authorized"] = True
    cases.append(("Production admission opened by acquisition gate", production))

    mutation = copy.deepcopy(plan)
    mutation["acquisition_boundary"]["security_state_creation_by_plasma_authorized"] = True
    cases.append(("Plasma allowed to create security state", mutation))

    count = copy.deepcopy(plan)
    count["exact_icpn_count"] = 1911
    cases.append(("Production ICPN count drift", count))
    return cases

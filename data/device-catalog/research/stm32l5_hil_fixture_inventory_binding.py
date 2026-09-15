#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import json
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError
from stm32l5_hil_observer_debug_readiness import build_gate_result as build_readiness_gate_result

HERE = Path(__file__).resolve().parent
INVENTORY = HERE / "stm32l5-hil-fixture-inventory.json"
COMMERCIAL = HERE / "stm32l5-commercial-identity-discovery.csv"
TRANSACTION = "stm32l5-hil-fixture-inventory-binding-gate"
DEVICE_LINES = {"STM32L552", "STM32L562"}
EXPECTED_STATES = {
    "TZ0_RDP0", "TZ0_RDP1", "TZ0_RDP2",
    "TZ1_RDP0", "TZ1_RDP0_5", "TZ1_RDP1", "TZ1_RDP2",
}
RDP2_STATES = {"TZ0_RDP2", "TZ1_RDP2"}
REQUIRED_FIELDS = {
    "fixture_identifier", "physical_asset_record_ref", "commercial_icpn", "device_line",
    "fixture_class", "preprovisioned_security_state", "security_state_provenance_ref",
    "security_state_evidence_digest", "custodian_or_lab_identity", "availability_status",
    "last_inventory_verified_at_utc",
}
ALLOWED_CLASSES = {
    "preprovisioned_recoverable_test_device",
    "preprovisioned_terminal_sacrificial_device",
}
ALLOWED_AVAILABILITY = {"available", "reserved", "unavailable"}
PLACEHOLDER_TOKENS = {"todo", "tbd", "unknown", "placeholder", "example", "dummy", "fake", "n/a"}


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AdmissionError(message)


def _read_json(path: Path = INVENTORY) -> dict[str, Any]:
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
    upstream = build_readiness_gate_result()
    _require(upstream.get("authority") == "research_only", "upstream readiness escaped research-only")
    _require(upstream.get("hil_test_cells") == 20, "upstream HIL matrix size drifted")
    _require(upstream.get("fixture_inventory_bound") is False, "upstream unexpectedly claims fixture binding")
    _require(upstream.get("hil_execution_ready") is False, "upstream unexpectedly claims HIL readiness")
    _require(upstream.get("hil_executed") is False, "upstream unexpectedly claims HIL execution")
    _require(upstream.get("production_manifest_admission_authorized") is False, "upstream Production fence opened")
    _require(upstream.get("runtime_programming_authorized") is False, "upstream runtime programming fence opened")
    _require(upstream.get("exact_icpn_count") == 1862, "Production exact ICPN count drifted")
    _require(upstream.get("next_research_gate") == TRANSACTION, "upstream next-gate continuity drifted")


def _non_placeholder(value: Any, field: str) -> None:
    _require(isinstance(value, str) and value.strip(), f"{field}: missing value")
    _require(value.strip().lower() not in PLACEHOLDER_TOKENS, f"{field}: placeholder value forbidden")


def validate_fixture_entry(entry: dict[str, Any], identities: dict[str, str]) -> None:
    _require(set(entry) >= REQUIRED_FIELDS, "fixture entry missing required fields")
    for field in REQUIRED_FIELDS:
        _non_placeholder(entry.get(field), field)
    fixture_id = entry["fixture_identifier"]
    icpn = entry["commercial_icpn"]
    line = entry["device_line"]
    state = entry["preprovisioned_security_state"]
    fixture_class = entry["fixture_class"]
    _require(icpn in identities, f"{fixture_id}: ICPN not in retained 49-part manufacturer set")
    _require(line in DEVICE_LINES and identities[icpn] == line, f"{fixture_id}: device-line/ICPN mismatch")
    _require(state in EXPECTED_STATES, f"{fixture_id}: invalid security state")
    _require(fixture_class in ALLOWED_CLASSES, f"{fixture_id}: invalid fixture class")
    _require(entry["availability_status"] in ALLOWED_AVAILABILITY, f"{fixture_id}: invalid availability status")
    if state in RDP2_STATES:
        _require(fixture_class == "preprovisioned_terminal_sacrificial_device", f"{fixture_id}: RDP2 fixture must be terminal/sacrificial")
    else:
        _require(fixture_class == "preprovisioned_recoverable_test_device", f"{fixture_id}: non-RDP2 fixture must use recoverable class")


def validate_inventory(inventory: dict[str, Any]) -> None:
    validate_upstream()
    identities = _commercial_identities()
    _require(inventory.get("schema_version") == 1, "fixture inventory schema drifted")
    _require(inventory.get("transaction") == TRANSACTION, "fixture inventory transaction drifted")
    _require(inventory.get("authority") == "research_only", "fixture inventory escaped research-only")
    _require(inventory.get("family") == "STM32L5", "fixture inventory family drifted")
    _require(set(inventory.get("device_lines", [])) == DEVICE_LINES, "fixture inventory device-line scope drifted")
    _require(inventory.get("upstream_readiness_plan") == "stm32l5-hil-observer-debug-readiness.json", "upstream readiness binding drifted")
    _require(inventory.get("commercial_identity_source") == COMMERCIAL.name, "commercial identity source drifted")
    _require(inventory.get("exact_icpn_count") == 1862, "exact ICPN count drifted")
    _require(inventory.get("stm32l5_commercial_icpn_count") == len(identities), "STM32L5 commercial identity count drifted")

    boundary = inventory.get("inventory_binding_boundary")
    _require(isinstance(boundary, dict), "inventory binding boundary missing")
    for key in (
        "verified_physical_inventory_required", "exact_commercial_icpn_required",
        "unique_fixture_identifier_required", "preprovisioned_security_state_required",
        "rdp2_fixture_must_be_terminal_sacrificial",
    ):
        _require(boundary.get(key) is True, f"{key}: required binding invariant missing")
    for key in (
        "placeholder_or_synthetic_fixture_allowed", "self_attested_fixture_without_evidence_allowed",
        "security_state_creation_by_plasma_authorized", "security_mutation_by_binding_gate_authorized",
        "hil_execution_authorized", "runtime_debug_attach_authorized", "runtime_programming_authorized",
        "production_manifest_admission_authorized",
    ):
        _require(boundary.get(key) is False, f"{key}: unsafe binding authorization")

    fields = inventory.get("required_fixture_fields")
    _require(isinstance(fields, list) and len(fields) == len(REQUIRED_FIELDS) and set(fields) == REQUIRED_FIELDS, "required fixture field schema drifted")
    _require(set(inventory.get("allowed_fixture_classes", [])) == ALLOWED_CLASSES, "fixture class set drifted")
    _require(set(inventory.get("allowed_availability_status", [])) == ALLOWED_AVAILABILITY, "availability status set drifted")

    assessment = inventory.get("repository_inventory_assessment")
    _require(isinstance(assessment, dict), "repository inventory assessment missing")
    _require(assessment.get("repository_search_completed") is True, "repository inventory search not recorded")
    _require(assessment.get("verified_stm32l5_fixture_records_found") == 0, "unsupported verified fixture record count")
    _require(assessment.get("external_inventory_supplied") is False, "external inventory supplied without evidence")
    _require(assessment.get("physical_fixture_claim_permitted_without_evidence") is False, "unevidenced physical fixture claims permitted")
    _require(assessment.get("assessment_result") == "no_verified_physical_inventory_available", "inventory assessment result drifted")

    fixtures = inventory.get("fixtures")
    _require(isinstance(fixtures, list), "fixtures must be a list")
    seen: set[str] = set()
    for entry in fixtures:
        _require(isinstance(entry, dict), "fixture entry must be object")
        validate_fixture_entry(entry, identities)
        fixture_id = entry["fixture_identifier"]
        _require(fixture_id not in seen, f"duplicate fixture identifier: {fixture_id}")
        seen.add(fixture_id)
    _require(len(fixtures) == 0, "this binding snapshot may not invent or self-register physical fixtures")

    coverage = inventory.get("coverage")
    _require(isinstance(coverage, dict), "fixture coverage missing")
    expected_coverage = {
        "verified_fixture_count": 0,
        "device_lines_with_verified_fixture": 0,
        "security_states_with_verified_fixture": 0,
        "rdp2_terminal_fixture_count": 0,
        "hil_test_cells_bound": 0,
        "hil_test_cells_total": 20,
    }
    _require(coverage == expected_coverage, "zero-inventory coverage snapshot drifted")

    result = inventory.get("binding_result")
    _require(isinstance(result, dict), "fixture binding result missing")
    for key in ("fixture_inventory_schema_defined", "commercial_identity_scope_validated", "repository_inventory_assessment_complete"):
        _require(result.get(key) is True, f"{key}: required binding result missing")
    for key in (
        "verified_fixture_inventory_present", "fixture_inventory_bound", "hil_execution_ready", "hil_executed",
        "observer_hil_validated", "debug_attach_hil_validated", "production_manifest_admission_authorized",
        "runtime_programming_authorized",
    ):
        _require(result.get(key) is False, f"{key}: unsupported fixture/HIL/Production claim")

    blocker = inventory.get("blocker")
    _require(isinstance(blocker, dict), "external physical asset blocker missing")
    _require(blocker.get("type") == "external_physical_asset_dependency", "blocker type drifted")
    _non_placeholder(blocker.get("description"), "blocker.description")
    _non_placeholder(blocker.get("resolution"), "blocker.resolution")
    _require(inventory.get("next_research_gate") == "stm32l5-hil-fixture-acquisition-and-provenance-gate", "next gate drifted")


def build_gate_result(path: Path = INVENTORY) -> dict[str, Any]:
    inventory = _read_json(path)
    validate_inventory(inventory)
    return {
        "schema_version": 1,
        "transaction": TRANSACTION,
        "authority": "research_only",
        "family": "STM32L5",
        "stm32l5_commercial_icpn_count": 49,
        "verified_fixture_count": 0,
        "hil_test_cells_bound": 0,
        "fixture_inventory_bound": False,
        "hil_execution_ready": False,
        "hil_executed": False,
        "production_manifest_admission_authorized": False,
        "runtime_programming_authorized": False,
        "exact_icpn_count": 1862,
        "blocker": "external_physical_asset_dependency",
        "next_research_gate": inventory["next_research_gate"],
    }


def negative_controls(inventory: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    cases: list[tuple[str, dict[str, Any]]] = []

    fake = copy.deepcopy(inventory)
    fake["fixtures"] = [{
        "fixture_identifier": "dummy",
        "physical_asset_record_ref": "placeholder",
        "commercial_icpn": "STM32L552ZET6",
        "device_line": "STM32L552",
        "fixture_class": "preprovisioned_recoverable_test_device",
        "preprovisioned_security_state": "TZ0_RDP0",
        "security_state_provenance_ref": "placeholder",
        "security_state_evidence_digest": "placeholder",
        "custodian_or_lab_identity": "placeholder",
        "availability_status": "available",
        "last_inventory_verified_at_utc": "placeholder"
    }]
    cases.append(("placeholder fixture injected", fake))

    bound = copy.deepcopy(inventory)
    bound["binding_result"]["fixture_inventory_bound"] = True
    cases.append(("fixture inventory claimed bound with zero fixtures", bound))

    ready = copy.deepcopy(inventory)
    ready["binding_result"]["hil_execution_ready"] = True
    cases.append(("HIL execution claimed ready without fixtures", ready))

    execute = copy.deepcopy(inventory)
    execute["inventory_binding_boundary"]["hil_execution_authorized"] = True
    cases.append(("HIL execution authorized by inventory gate", execute))

    production = copy.deepcopy(inventory)
    production["binding_result"]["production_manifest_admission_authorized"] = True
    cases.append(("Production admission opened by inventory gate", production))

    count = copy.deepcopy(inventory)
    count["exact_icpn_count"] = 1911
    cases.append(("Production ICPN count drift", count))
    return cases

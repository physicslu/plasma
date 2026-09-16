#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError, CandidateManualReview
from stm32u5_metadata_policy import (
    ACTIVE_STATUS,
    EXPECTED_SUBFAMILIES,
    FAMILY,
    MANUFACTURER,
    PREVIEW_STATUS,
    build_candidate_inputs,
    build_metadata_row,
    load_security_fence,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CATALOG = HERE / "openocd-parts-canonical.csv"
METADATA_BASELINE = HERE / "stm32u5-metadata-policy-baseline.json"
DELTA_RESOLUTION = HERE / "stm32u5-metadata-authority-delta-resolution.json"
BRIDGE = HERE / "stm32u5-cmsis-route-bridge.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

TARGET_CONFIG = "tcl/target/stm32u5x.cfg"
EXPECTED_RETAINED_COUNT = 266
EXPECTED_ACTIVE_COUNT = 265
QUARANTINED_PREVIEW = "STM32U5G9ZJJ3Q"
BRIDGE_ICPN = "STM32U5A5QII3Q"
BRIDGE_IDENTIFIER = "STM32U5A5xx"
BRIDGE_KIND = "cmsis_exact_membership_bridge"
EXPECTED_ROUTE_ROWS = 162
EXPECTED_ROUTE_KIND_COUNTS = {"ordering_pattern": 63, "cmsis_device_name": 99}
EXPECTED_ROUTE_EVIDENCE_SHA256 = "01b9b9b36423752199bab34b8a3a4ba7adb3445d2d884a46c0501c09701f099d"
EXPECTED_U5A5_ROUTE_ROWS = 11
EXPECTED_U5A5_ROUTE_EVIDENCE_SHA256 = "6c284e6452ddcf28df2adcaa60068120477e2ea9fadda5a807c2a6e523815220"
EXPECTED_ASSIGNMENT_KIND_COUNTS = {"ordering_pattern": 117, "cmsis_device_name": 147, BRIDGE_KIND: 1}
EXPECTED_ROUTE_BINDING_SHA256 = "0aa91868a0fd8dc66f0aded52748f7c95bc58b5fb01d11629ec22fcd0c3f9907"
PRODUCTION_EXACT_COUNT = 2017
CANONICAL_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "marketing_status_observed",
    "package", "pin_count", "flash_size", "temperature_grade", "dedicated_pinout", "packing",
    "option_suffix", "cmsis_device_name", "existing_identifier", "existing_identifier_kind",
    "mapping_status", "openocd_target_config", "source_type", "source_reference",
    "source_authority", "verification_status",
)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"{path.name}: root must be object")
    return value


def commercial_core(icpn: str) -> str:
    return icpn[:-2] if icpn.endswith("TR") else icpn


def pattern_matches(pattern: str, value: str) -> bool:
    expression = "".join("[A-Z0-9]" if char.lower() == "x" else re.escape(char) for char in pattern)
    return re.fullmatch(expression, value) is not None


def route_evidence_sha(rows: list[dict[str, str]]) -> str:
    lines = [
        "|".join((
            row["subfamily"], row["part_number"], row["identifier_kind"], row["target_config"],
            row["openocd_distribution"], row["mapping_status"], row["validation_status"], row["catalog_origin"],
        ))
        for row in rows
    ]
    return hashlib.sha256(("\n".join(sorted(lines)) + "\n").encode()).hexdigest()


def route_binding_sha(assignments: list[dict[str, str]]) -> str:
    lines = [
        "|".join((row["icpn"], row["identifier_kind"], row["identifier"], row["target_config"]))
        for row in assignments
    ]
    return hashlib.sha256(("\n".join(sorted(lines)) + "\n").encode()).hexdigest()


def validate_bridge_payload(payload: dict[str, Any]) -> None:
    expected_cmsis = {
        "repository": "STMicroelectronics/cmsis-device-u5",
        "commit": "624374fa1e21ca195d6f2102ac0caaa50d0ea4c8",
        "header_path": "Include/stm32u5xx.h",
        "header_blob_sha": "62e93f884c6ecf22a606412ddb69670d9aa68706",
        "cmsis_device_group": BRIDGE_IDENTIFIER,
        "group_header": "stm32u5a5xx.h",
        "exact_part_listed_under_group": True,
        "release_notes_path": "Release_Notes.md",
        "release_notes_blob_sha": "6a37ab4f18204d2339dbd4c7daff586791fd9dbe",
        "release_note_version": "V1.3.1 / 20-October-2023",
        "release_note_records_exact_part_addition": True,
    }
    expected_surface = {
        "source": CATALOG.name,
        "route_evidence_rows": EXPECTED_ROUTE_ROWS,
        "route_evidence_sha256": EXPECTED_ROUTE_EVIDENCE_SHA256,
        "stm32u5a5_route_rows": EXPECTED_U5A5_ROUTE_ROWS,
        "stm32u5a5_route_evidence_sha256": EXPECTED_U5A5_ROUTE_EVIDENCE_SHA256,
        "stm32u5a5_target_config_unanimous": True,
        "target_config": TARGET_CONFIG,
    }
    expected_binding = {
        "identifier_kind": BRIDGE_KIND,
        "identifier": BRIDGE_IDENTIFIER,
        "mapping_status": "deterministic_cmsis_exact_membership_bridge",
        "validation_status": "not_verified",
        "target_config": TARGET_CONFIG,
        "semantics": "Exact ST CMSIS device-group membership plus the existing unanimous Plasma STM32U5A5 target-config surface; mapping candidate only, not programming equivalence.",
    }
    if (
        payload.get("schema_version") != 1
        or payload.get("transaction") != "stm32u5-cmsis-route-bridge"
        or payload.get("authority") != "research_only"
        or payload.get("manufacturer") != MANUFACTURER
        or payload.get("family") != FAMILY
        or payload.get("exact_icpn") != BRIDGE_ICPN
        or payload.get("base_device") != "STM32U5A5QI"
        or payload.get("series") != "STM32U5A5"
        or payload.get("manufacturer_cmsis_authority") != expected_cmsis
        or payload.get("plasma_route_surface") != expected_surface
        or payload.get("bridge_binding") != expected_binding
    ):
        raise AdmissionError("STM32U5 CMSIS route bridge drifted")
    claims = payload.get("claims")
    if not isinstance(claims, dict) or not claims or set(claims.values()) != {False}:
        raise AdmissionError("STM32U5 CMSIS bridge escaped fail-closed claims")


def load_bridge(path: Path = BRIDGE) -> dict[str, Any]:
    payload = _read_json(path)
    validate_bridge_payload(payload)
    return payload


def read_route_rows(path: Path = CATALOG) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row.get("vendor") == MANUFACTURER and row.get("plasma_series") == FAMILY
        ]
    if len(rows) != EXPECTED_ROUTE_ROWS:
        raise AdmissionError(f"STM32U5 route surface count drifted: {len(rows)}")
    kinds = Counter(row.get("identifier_kind", "") for row in rows)
    if dict(kinds) != EXPECTED_ROUTE_KIND_COUNTS:
        raise AdmissionError(f"STM32U5 route kind counts drifted: {dict(kinds)}")
    if {row.get("subfamily", "") for row in rows} != EXPECTED_SUBFAMILIES:
        raise AdmissionError("STM32U5 route subfamily set drifted")
    for row in rows:
        part = row.get("part_number", "")
        if (
            row.get("target_config") != TARGET_CONFIG
            or row.get("openocd_distribution") != "upstream-openocd"
            or row.get("mapping_status") != "mapping_candidate"
            or row.get("validation_status") != "not_verified"
            or row.get("catalog_origin") != "plasma_openocd_parts_top5_mapped.csv"
            or row.get("identifier_kind") not in EXPECTED_ROUTE_KIND_COUNTS
            or not part.startswith(row.get("subfamily", ""))
        ):
            raise AdmissionError(f"invalid STM32U5 route evidence: {part}")
    if route_evidence_sha(rows) != EXPECTED_ROUTE_EVIDENCE_SHA256:
        raise AdmissionError("STM32U5 route evidence digest drifted")
    u5a5 = [row for row in rows if row["subfamily"] == "STM32U5A5"]
    if len(u5a5) != EXPECTED_U5A5_ROUTE_ROWS or route_evidence_sha(u5a5) != EXPECTED_U5A5_ROUTE_EVIDENCE_SHA256:
        raise AdmissionError("STM32U5A5 route evidence drifted")
    if {row["target_config"] for row in u5a5} != {TARGET_CONFIG}:
        raise AdmissionError("STM32U5A5 target-config evidence is not unanimous")
    return rows


def resolve_route(icpn: str, rows: list[dict[str, str]], bridge: dict[str, Any]) -> dict[str, str]:
    core = commercial_core(icpn)
    matches = [row for row in rows if pattern_matches(row["part_number"], core)]
    if len(matches) == 1:
        row = matches[0]
        return {"identifier": row["part_number"], "identifier_kind": row["identifier_kind"], "target_config": row["target_config"]}
    if len(matches) > 1:
        raise CandidateManualReview(f"{icpn}: STM32U5 OpenOCD route is ambiguous ({len(matches)} matches)")
    if icpn != bridge["exact_icpn"]:
        raise CandidateManualReview(f"{icpn}: STM32U5 OpenOCD route is unmapped")
    binding = bridge["bridge_binding"]
    return {"identifier": binding["identifier"], "identifier_kind": binding["identifier_kind"], "target_config": binding["target_config"]}


def build_canonical_row(candidate: dict[str, Any], routes: list[dict[str, str]], bridge: dict[str, Any]) -> dict[str, str]:
    metadata = build_metadata_row(candidate)
    route = resolve_route(metadata["icpn"], routes, bridge)
    kind, identifier = route["identifier_kind"], route["identifier"]
    mapping_status = "deterministic_cmsis_exact_membership_bridge" if kind == BRIDGE_KIND else "deterministic_openocd_mapping_candidate"
    values = {
        **metadata,
        "cmsis_device_name": identifier if kind in {"cmsis_device_name", BRIDGE_KIND} else "",
        "existing_identifier": identifier,
        "existing_identifier_kind": kind,
        "mapping_status": mapping_status,
        "openocd_target_config": route["target_config"],
    }
    return {field: values[field] for field in CANONICAL_FIELDS}


def _candidate_partition() -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    candidates = build_candidate_inputs()
    active = [item for item in candidates if item["marketing_status"] == ACTIVE_STATUS]
    preview = [item for item in candidates if item["marketing_status"] == PREVIEW_STATUS]
    if len(candidates) != EXPECTED_RETAINED_COUNT or len(active) != EXPECTED_ACTIVE_COUNT:
        raise AdmissionError("STM32U5 admission candidate cardinality drifted")
    if len(preview) != 1 or preview[0]["icpn"] != QUARANTINED_PREVIEW:
        raise AdmissionError("STM32U5 quarantined Preview identity drifted")
    try:
        build_metadata_row(preview[0])
    except CandidateManualReview:
        pass
    else:
        raise AdmissionError("STM32U5 quarantined Preview unexpectedly became metadata-ready")
    return active, preview


def build_canonical_rows() -> list[dict[str, str]]:
    routes = read_route_rows()
    bridge = load_bridge()
    active, _ = _candidate_partition()
    rows = [build_canonical_row(candidate, routes, bridge) for candidate in active]
    if len(rows) != EXPECTED_ACTIVE_COUNT or len({row["icpn"] for row in rows}) != EXPECTED_ACTIVE_COUNT:
        raise AdmissionError("STM32U5 planned canonical identities are not unique")
    if any(row["icpn"] == QUARANTINED_PREVIEW for row in rows):
        raise AdmissionError("STM32U5 quarantined Preview entered canonical plan")
    assigned = Counter(row["existing_identifier_kind"] for row in rows)
    if dict(assigned) != EXPECTED_ASSIGNMENT_KIND_COUNTS:
        raise AdmissionError(f"STM32U5 route assignment counts drifted: {dict(assigned)}")
    bridge_rows = [row for row in rows if row["existing_identifier_kind"] == BRIDGE_KIND]
    if len(bridge_rows) != 1 or bridge_rows[0]["icpn"] != BRIDGE_ICPN:
        raise AdmissionError("STM32U5 CMSIS bridge assignment drifted")
    assignments = [
        {"icpn": row["icpn"], "identifier_kind": row["existing_identifier_kind"], "identifier": row["existing_identifier"], "target_config": row["openocd_target_config"]}
        for row in rows
    ]
    if route_binding_sha(assignments) != EXPECTED_ROUTE_BINDING_SHA256:
        raise AdmissionError("STM32U5 exact-to-route binding digest drifted")
    return rows


def _validate_upstream_boundaries() -> None:
    security = load_security_fence()
    partition = security["research_partition"]
    if partition.get("catalog_admission_governed_separately") is not True:
        raise AdmissionError("STM32U5 catalog-admission governance fence drifted")
    for key in (
        "security_semantics_supported", "option_byte_writes_allowed", "oem_key_provisioning_allowed",
        "oem_unlock_execution_allowed", "rdp_regression_allowed", "mass_erase_allowed",
        "flash_geometry_validated", "programming_algorithm_equivalence", "runtime_programming_supported",
        "debug_attach_supported", "hil_validated",
    ):
        if partition.get(key) is not False:
            raise AdmissionError(f"STM32U5 security fence unexpectedly open: {key}")

    baseline = _read_json(METADATA_BASELINE)
    expected_result = {
        "metadata_ready_exact_icpns": 265,
        "manual_review_required": 1,
        "rejected_retained_identities": 0,
        "scope_expansion": 0,
        "active_identity_metadata_ready": 265,
        "preview_identity_metadata_ready": 0,
    }
    if (
        baseline.get("transaction") != "stm32u5-metadata-policy"
        or baseline.get("authority") != "research_only"
        or baseline.get("family") != FAMILY
        or baseline.get("production_exact_icpn_count") != PRODUCTION_EXACT_COUNT
        or baseline.get("result") != expected_result
    ):
        raise AdmissionError("STM32U5 metadata baseline is not clean")

    delta = _read_json(DELTA_RESOLUTION)
    scope = delta.get("next_admission_scope")
    resolution = delta.get("resolution")
    if (
        delta.get("transaction") != "stm32u5-metadata-authority-delta-resolution"
        or delta.get("authority") != "research_only"
        or delta.get("production_exact_icpn_count") != PRODUCTION_EXACT_COUNT
        or scope != {"metadata_ready_active_exact_icpns": 265, "quarantined_exact_icpns": [QUARANTINED_PREVIEW], "preview_identity_admission_authorized": False}
        or not isinstance(resolution, dict)
        or resolution.get("quarantine_required") is not True
        or resolution.get("metadata_ready") is not False
        or delta.get("next_research_gate") != "stm32u5-canonical-admission-plan-under-security-fence"
    ):
        raise AdmissionError("STM32U5 metadata delta-resolution boundary drifted")

    production = _read_json(PRODUCTION)
    sources = production.get("sources")
    if not isinstance(sources, list) or sum(int(item["row_count"]) for item in sources) != PRODUCTION_EXACT_COUNT:
        raise AdmissionError("Production exact ICPN count drifted")
    if any(item.get("family") == FAMILY for item in sources):
        raise AdmissionError("STM32U5 unexpectedly present in Production before publication gate")


def build_plan() -> dict[str, Any]:
    _validate_upstream_boundaries()
    rows = build_canonical_rows()
    statuses = Counter(row["marketing_status_observed"] for row in rows)
    if dict(statuses) != {ACTIVE_STATUS: EXPECTED_ACTIVE_COUNT}:
        raise AdmissionError("STM32U5 planned status preservation drifted")
    security = load_security_fence()["research_partition"]
    return {
        "schema_version": 1,
        "transaction": "stm32u5-canonical-admission-plan-under-security-fence",
        "authority": "research_only",
        "family": FAMILY,
        "manufacturer": MANUFACTURER,
        "production_exact_icpn_count": PRODUCTION_EXACT_COUNT,
        "retained_exact_icpns": EXPECTED_RETAINED_COUNT,
        "metadata_ready_active_exact_icpns": EXPECTED_ACTIVE_COUNT,
        "quarantined_preview_exact_icpns": [QUARANTINED_PREVIEW],
        "route_evidence_rows": EXPECTED_ROUTE_ROWS,
        "route_evidence_kind_counts": EXPECTED_ROUTE_KIND_COUNTS,
        "route_evidence_sha256": EXPECTED_ROUTE_EVIDENCE_SHA256,
        "supplemental_cmsis_bridges": 1,
        "cmsis_bridge_evidence": BRIDGE.name,
        "standard_route_assignments": 264,
        "unique_route_assignments": EXPECTED_ACTIVE_COUNT,
        "route_assignment_kind_counts": EXPECTED_ASSIGNMENT_KIND_COUNTS,
        "route_binding_sha256": EXPECTED_ROUTE_BINDING_SHA256,
        "planned_canonical_rows": EXPECTED_ACTIVE_COUNT,
        "marketing_status_counts": dict(statuses),
        "required_target_config": TARGET_CONFIG,
        "route_evidence_semantics": "OpenOCD/CMSIS mapping candidate plus one pinned ST CMSIS exact-membership bridge; not programming equivalence",
        "catalog_admission_governed_separately": security["catalog_admission_governed_separately"],
        "security_fence": {
            key: security[key]
            for key in (
                "security_semantics_supported", "option_byte_writes_allowed", "oem_key_provisioning_allowed",
                "oem_unlock_execution_allowed", "rdp_regression_allowed", "mass_erase_allowed",
                "flash_geometry_validated", "programming_algorithm_equivalence", "runtime_programming_supported",
                "debug_attach_supported", "hil_validated",
            )
        },
        "claims": {
            "production_write_authorized": False,
            "production_admission_authorized": False,
            "preview_identity_admission_authorized": False,
            "security_semantics_supported": False,
            "option_byte_semantics_supported": False,
            "oem_key_semantics_supported": False,
            "flash_geometry_validated": False,
            "programming_algorithm_equivalence": False,
            "runtime_programming_supported": False,
            "debug_attach_supported": False,
            "physical_validation_claimed": False,
            "hil_validated": False,
        },
        "next_research_gate": "stm32u5-security-state-admission-gate",
    }


def plan_is_clean(plan: dict[str, Any]) -> bool:
    return (
        plan.get("authority") == "research_only"
        and plan.get("family") == FAMILY
        and plan.get("production_exact_icpn_count") == PRODUCTION_EXACT_COUNT
        and plan.get("metadata_ready_active_exact_icpns") == EXPECTED_ACTIVE_COUNT
        and plan.get("quarantined_preview_exact_icpns") == [QUARANTINED_PREVIEW]
        and plan.get("unique_route_assignments") == EXPECTED_ACTIVE_COUNT
        and plan.get("planned_canonical_rows") == EXPECTED_ACTIVE_COUNT
        and plan.get("route_evidence_sha256") == EXPECTED_ROUTE_EVIDENCE_SHA256
        and plan.get("route_binding_sha256") == EXPECTED_ROUTE_BINDING_SHA256
        and plan.get("route_assignment_kind_counts") == EXPECTED_ASSIGNMENT_KIND_COUNTS
        and plan.get("supplemental_cmsis_bridges") == 1
        and plan.get("required_target_config") == TARGET_CONFIG
        and plan.get("catalog_admission_governed_separately") is True
        and isinstance(plan.get("claims"), dict)
        and set(plan["claims"].values()) == {False}
        and isinstance(plan.get("security_fence"), dict)
        and set(plan["security_fence"].values()) == {False}
        and plan.get("next_research_gate") == "stm32u5-security-state-admission-gate"
    )


if __name__ == "__main__":
    print(json.dumps(build_plan(), sort_keys=True))

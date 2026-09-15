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
from stm32u3_metadata_policy import (
    EXPECTED_EXACT_COUNT,
    FAMILY,
    MANUFACTURER,
    build_candidate_inputs,
    build_metadata_row,
    load_security_fence,
)

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "openocd-parts-canonical.csv"
METADATA_BASELINE = HERE / "stm32u3-metadata-policy-baseline.json"
TARGET_CONFIG = "tcl/target/stm32u3x.cfg"
EXPECTED_ROUTE_ROWS = 171
EXPECTED_ROUTE_KIND_COUNTS = {"ordering_pattern": 75, "cmsis_device_name": 96}
EXPECTED_ASSIGNMENT_KIND_COUNTS = {"ordering_pattern": 49, "cmsis_device_name": 57}
EXPECTED_ROUTE_EVIDENCE_SHA256 = "c08a8a6ab303619012be96eb9197a2f10956b13ecc380cd682ed8d6c8d9cc459"
EXPECTED_ROUTE_BINDING_SHA256 = "bb48d4cf660bc151d53f20f399b8ed3a8438796a5592b6f2570b5cf8119da328"
EXPECTED_SUBFAMILIES = {
    "STM32U335", "STM32U345", "STM32U356", "STM32U366",
    "STM32U375", "STM32U385", "STM32U3B5", "STM32U3C5",
}
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


def read_route_rows(path: Path = CATALOG) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row.get("vendor") == MANUFACTURER and row.get("plasma_series") == FAMILY
        ]
    if len(rows) != EXPECTED_ROUTE_ROWS:
        raise AdmissionError(f"STM32U3 route surface count drifted: {len(rows)}")
    kinds = Counter(row.get("identifier_kind", "") for row in rows)
    if dict(kinds) != EXPECTED_ROUTE_KIND_COUNTS:
        raise AdmissionError(f"STM32U3 route kind counts drifted: {dict(kinds)}")
    if {row.get("subfamily", "") for row in rows} != EXPECTED_SUBFAMILIES:
        raise AdmissionError("STM32U3 route subfamily set drifted")
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
            raise AdmissionError(f"invalid STM32U3 route evidence: {part}")
    if route_evidence_sha(rows) != EXPECTED_ROUTE_EVIDENCE_SHA256:
        raise AdmissionError("STM32U3 route evidence digest drifted")
    return rows


def resolve_route(icpn: str, rows: list[dict[str, str]]) -> dict[str, str]:
    core = commercial_core(icpn)
    matches = [row for row in rows if pattern_matches(row["part_number"], core)]
    if len(matches) != 1:
        status = "unmapped" if not matches else "ambiguous"
        raise CandidateManualReview(f"{icpn}: STM32U3 OpenOCD route is {status} ({len(matches)} matches)")
    row = matches[0]
    return {
        "identifier": row["part_number"],
        "identifier_kind": row["identifier_kind"],
        "target_config": row["target_config"],
    }


def route_binding_sha(assignments: list[dict[str, str]]) -> str:
    lines = [
        "|".join((row["icpn"], row["identifier_kind"], row["identifier"], row["target_config"]))
        for row in assignments
    ]
    return hashlib.sha256(("\n".join(sorted(lines)) + "\n").encode()).hexdigest()


def route_evidence_sha(rows: list[dict[str, str]]) -> str:
    lines = [
        "|".join((
            row["subfamily"], row["part_number"], row["identifier_kind"], row["target_config"],
            row["openocd_distribution"], row["mapping_status"], row["validation_status"],
            row["catalog_origin"],
        ))
        for row in rows
    ]
    return hashlib.sha256(("\n".join(sorted(lines)) + "\n").encode()).hexdigest()


def build_canonical_row(candidate: dict[str, Any], routes: list[dict[str, str]]) -> dict[str, str]:
    metadata = build_metadata_row(candidate)
    route = resolve_route(metadata["icpn"], routes)
    identifier = route["identifier"]
    kind = route["identifier_kind"]
    values = {
        **metadata,
        "cmsis_device_name": identifier if kind == "cmsis_device_name" else "",
        "existing_identifier": identifier,
        "existing_identifier_kind": kind,
        "mapping_status": "deterministic_openocd_mapping_candidate",
        "openocd_target_config": route["target_config"],
    }
    return {field: values[field] for field in CANONICAL_FIELDS}


def build_canonical_rows() -> list[dict[str, str]]:
    routes = read_route_rows()
    candidates = build_candidate_inputs()
    if len(candidates) != EXPECTED_EXACT_COUNT:
        raise AdmissionError("STM32U3 retained identity cardinality drifted")
    rows = [build_canonical_row(candidate, routes) for candidate in candidates]
    if len({row["icpn"] for row in rows}) != EXPECTED_EXACT_COUNT:
        raise AdmissionError("STM32U3 planned canonical identities are not unique")
    assigned = Counter(row["existing_identifier_kind"] for row in rows)
    if dict(assigned) != EXPECTED_ASSIGNMENT_KIND_COUNTS:
        raise AdmissionError(f"STM32U3 route assignment counts drifted: {dict(assigned)}")
    assignments = [
        {
            "icpn": row["icpn"],
            "identifier_kind": row["existing_identifier_kind"],
            "identifier": row["existing_identifier"],
            "target_config": row["openocd_target_config"],
        }
        for row in rows
    ]
    if route_binding_sha(assignments) != EXPECTED_ROUTE_BINDING_SHA256:
        raise AdmissionError("STM32U3 exact-to-route binding digest drifted")
    return rows


def build_plan() -> dict[str, Any]:
    security = load_security_fence()
    partition = security["research_partition"]
    if partition.get("production_admission_allowed") is not False:
        raise AdmissionError("STM32U3 Production admission fence unexpectedly open")

    baseline = _read_json(METADATA_BASELINE)
    expected_result = {
        "metadata_ready_exact_icpns": 106,
        "manual_review_required": 0,
        "rejected_retained_identities": 0,
        "scope_expansion": 0,
        "active_identity_metadata_ready": 100,
        "evaluation_identity_metadata_ready": 6,
    }
    if (
        baseline.get("transaction") != "stm32u3-metadata-policy"
        or baseline.get("authority") != "research_only"
        or baseline.get("family") != FAMILY
        or baseline.get("production_exact_icpn_count") != 1862
        or baseline.get("result") != expected_result
    ):
        raise AdmissionError("STM32U3 metadata baseline is not clean")

    rows = build_canonical_rows()
    statuses = Counter(row["marketing_status_observed"] for row in rows)
    if dict(statuses) != {"Active": 100, "Evaluation": 6}:
        raise AdmissionError("STM32U3 planned status preservation drifted")

    return {
        "schema_version": 1,
        "transaction": "stm32u3-canonical-admission-plan-under-security-fence",
        "authority": "research_only",
        "family": FAMILY,
        "manufacturer": MANUFACTURER,
        "production_exact_icpn_count": 1862,
        "metadata_ready_exact_icpns": 106,
        "route_evidence_rows": EXPECTED_ROUTE_ROWS,
        "route_evidence_kind_counts": EXPECTED_ROUTE_KIND_COUNTS,
        "route_evidence_sha256": EXPECTED_ROUTE_EVIDENCE_SHA256,
        "unique_route_assignments": 106,
        "route_assignment_kind_counts": EXPECTED_ASSIGNMENT_KIND_COUNTS,
        "route_binding_sha256": EXPECTED_ROUTE_BINDING_SHA256,
        "planned_canonical_rows": 106,
        "marketing_status_counts": dict(statuses),
        "required_target_config": TARGET_CONFIG,
        "route_evidence_semantics": "upstream OpenOCD mapping candidate only; not programming equivalence",
        "security_fence": {
            key: partition[key]
            for key in (
                "production_admission_allowed", "security_semantics_supported", "option_byte_writes_allowed",
                "oem_key_provisioning_allowed", "oem_unlock_execution_allowed", "rdp_regression_allowed",
                "mass_erase_allowed", "flash_geometry_validated", "programming_algorithm_equivalence",
                "runtime_programming_supported", "debug_attach_supported", "hil_validated",
            )
        },
        "claims": {
            "production_write_authorized": False,
            "production_admission_authorized": False,
            "evaluation_status_implies_production_admission": False,
            "security_semantics_supported": False,
            "option_byte_semantics_supported": False,
            "oem_key_semantics_supported": False,
            "flash_geometry_validated": False,
            "programming_algorithm_equivalence": False,
            "runtime_programming_supported": False,
            "debug_attach_supported": False,
            "hil_validated": False,
        },
        "next_research_gate": "stm32u3-security-state-admission-gate",
    }


def plan_is_clean(plan: dict[str, Any]) -> bool:
    return (
        plan.get("authority") == "research_only"
        and plan.get("family") == FAMILY
        and plan.get("production_exact_icpn_count") == 1862
        and plan.get("metadata_ready_exact_icpns") == EXPECTED_EXACT_COUNT
        and plan.get("unique_route_assignments") == EXPECTED_EXACT_COUNT
        and plan.get("planned_canonical_rows") == EXPECTED_EXACT_COUNT
        and plan.get("route_evidence_sha256") == EXPECTED_ROUTE_EVIDENCE_SHA256
        and plan.get("route_binding_sha256") == EXPECTED_ROUTE_BINDING_SHA256
        and plan.get("route_assignment_kind_counts") == EXPECTED_ASSIGNMENT_KIND_COUNTS
        and plan.get("required_target_config") == TARGET_CONFIG
        and isinstance(plan.get("claims"), dict)
        and set(plan["claims"].values()) == {False}
        and isinstance(plan.get("security_fence"), dict)
        and set(plan["security_fence"].values()) == {False}
        and plan.get("next_research_gate") == "stm32u3-security-state-admission-gate"
    )


if __name__ == "__main__":
    print(json.dumps(build_plan(), sort_keys=True))

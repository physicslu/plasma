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
from stm32l5_metadata_policy import (
    EXPECTED_EXACT_COUNT,
    FAMILY,
    MANUFACTURER,
    build_candidate_inputs,
    build_metadata_row,
    load_security_fence,
)

HERE = Path(__file__).resolve().parent
ROUTES = HERE / "stm32l5-admission-route-evidence.csv"
METADATA_BASELINE = HERE / "stm32l5-metadata-policy-baseline.json"
TARGET_CONFIG = "tcl/target/stm32l5x.cfg"
EXPECTED_ROUTE_ROWS = 38
EXPECTED_ROUTE_KIND_COUNTS = {"ordering_pattern": 15, "cmsis_device_name": 23}
EXPECTED_ASSIGNED_KIND_COUNTS = {"ordering_pattern": 27, "cmsis_device_name": 22}
EXPECTED_ROUTE_BINDING_SHA256 = "c54c0eb049c4d60808540cb5608047b6c2b74a451d8fad2e3a41f56ea1e4d46c"
CANONICAL_FIELDS = (
    "manufacturer", "icpn", "family", "series", "base_device", "package",
    "pin_count", "flash_size", "temperature_grade", "option_suffix",
    "cmsis_device_name", "existing_identifier", "existing_identifier_kind",
    "mapping_status", "openocd_target_config", "source_type", "source_reference",
    "source_authority", "verification_status",
)
ROUTE_COLUMNS = [
    "part_number", "identifier_kind", "target_config", "openocd_distribution",
    "mapping_status", "validation_status", "catalog_origin",
]


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AdmissionError(f"{path.name}: root must be object")
    return value


def commercial_core(icpn: str) -> str:
    for suffix in ("TR", "TT"):
        if icpn.endswith(suffix):
            return icpn[:-len(suffix)]
    return icpn


def _pattern_matches(pattern: str, core: str) -> bool:
    if pattern.count("x") != 1:
        return False
    regex = "^" + re.escape(pattern).replace("x", "[A-Z0-9]") + "$"
    return re.fullmatch(regex, core) is not None


def read_route_rows(path: Path = ROUTES) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != ROUTE_COLUMNS:
            raise AdmissionError("STM32L5 admission route schema drifted")
        rows = list(reader)
    validate_route_rows(rows)
    return rows


def validate_route_rows(rows: list[dict[str, str]]) -> None:
    if len(rows) != EXPECTED_ROUTE_ROWS:
        raise AdmissionError("STM32L5 frozen route row count drifted")
    identifiers = [row.get("part_number", "") for row in rows]
    if len(identifiers) != len(set(identifiers)):
        raise AdmissionError("duplicate STM32L5 frozen route identifier")
    kinds = Counter(row.get("identifier_kind", "") for row in rows)
    if dict(kinds) != EXPECTED_ROUTE_KIND_COUNTS:
        raise AdmissionError(f"STM32L5 route kind counts drifted: {dict(kinds)}")
    for row in rows:
        identifier = row["part_number"]
        if (
            row["identifier_kind"] not in EXPECTED_ROUTE_KIND_COUNTS
            or row["target_config"] != TARGET_CONFIG
            or row["openocd_distribution"] != "upstream-openocd"
            or row["mapping_status"] != "mapping_candidate"
            or row["validation_status"] != "not_verified"
            or row["catalog_origin"] != "plasma_openocd_parts_top5_mapped.csv"
            or identifier.count("x") != 1
            or not identifier.startswith(("STM32L552", "STM32L562"))
        ):
            raise AdmissionError(f"invalid STM32L5 frozen route evidence: {identifier}")


def resolve_route(icpn: str, rows: list[dict[str, str]]) -> dict[str, str]:
    core = commercial_core(icpn)
    matches = [row for row in rows if _pattern_matches(row["part_number"], core)]
    if len(matches) != 1:
        status = "unmapped" if not matches else "ambiguous"
        raise CandidateManualReview(f"{icpn}: STM32L5 OpenOCD route is {status} ({len(matches)} matches)")
    row = matches[0]
    return {
        "identifier": row["part_number"],
        "identifier_kind": row["identifier_kind"],
        "target_config": row["target_config"],
        "mapping_status": row["mapping_status"],
        "validation_status": row["validation_status"],
    }


def build_canonical_row(candidate: dict[str, Any], routes: list[dict[str, str]] | None = None) -> dict[str, str]:
    routes = read_route_rows() if routes is None else routes
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


def _binding_sha(rows: list[dict[str, str]]) -> str:
    lines = [
        "|".join((
            row["icpn"], row["existing_identifier_kind"], row["existing_identifier"],
            row["openocd_target_config"],
        ))
        for row in rows
    ]
    return hashlib.sha256(("\n".join(sorted(lines)) + "\n").encode()).hexdigest()


def build_plan() -> dict[str, Any]:
    security = load_security_fence()
    partition = security["research_partition"]
    if partition.get("production_admission_allowed") is not False:
        raise AdmissionError("STM32L5 security fence no longer blocks Production admission")

    baseline = _read_json(METADATA_BASELINE)
    if (
        baseline.get("transaction") != "stm32l5-metadata-policy"
        or baseline.get("authority") != "research_only"
        or baseline.get("family") != FAMILY
        or baseline.get("result") != {
            "metadata_ready_exact_icpns": 49,
            "manual_review_required": 0,
            "rejected_retained_identities": 0,
            "scope_expansion": 0,
        }
    ):
        raise AdmissionError("STM32L5 metadata baseline is not clean")

    routes = read_route_rows()
    candidates = build_candidate_inputs()
    if len(candidates) != EXPECTED_EXACT_COUNT:
        raise AdmissionError("STM32L5 candidate cardinality drifted")

    canonical_rows = [build_canonical_row(candidate, routes) for candidate in candidates]
    if len({row["icpn"] for row in canonical_rows}) != EXPECTED_EXACT_COUNT:
        raise AdmissionError("STM32L5 planned canonical identities are not unique")
    assigned = Counter(row["existing_identifier_kind"] for row in canonical_rows)
    if dict(assigned) != EXPECTED_ASSIGNED_KIND_COUNTS:
        raise AdmissionError(f"STM32L5 assigned route-kind counts drifted: {dict(assigned)}")
    binding_sha = _binding_sha(canonical_rows)
    if binding_sha != EXPECTED_ROUTE_BINDING_SHA256:
        raise AdmissionError("STM32L5 exact-to-route binding digest drifted")

    return {
        "schema_version": 1,
        "transaction": "stm32l5-canonical-admission-plan-under-security-fence",
        "authority": "research_only",
        "family": FAMILY,
        "manufacturer": MANUFACTURER,
        "metadata_ready_exact_icpns": EXPECTED_EXACT_COUNT,
        "route_evidence_rows": EXPECTED_ROUTE_ROWS,
        "route_evidence_kind_counts": EXPECTED_ROUTE_KIND_COUNTS,
        "unique_route_assignments": EXPECTED_EXACT_COUNT,
        "route_assignment_kind_counts": EXPECTED_ASSIGNED_KIND_COUNTS,
        "route_binding_sha256": binding_sha,
        "planned_canonical_rows": EXPECTED_EXACT_COUNT,
        "required_target_config": TARGET_CONFIG,
        "route_evidence_semantics": "upstream OpenOCD mapping candidate only; not programming equivalence",
        "security_fence": {
            "production_admission_allowed": partition["production_admission_allowed"],
            "security_semantics_supported": partition["security_semantics_supported"],
            "option_byte_writes_allowed": partition["option_byte_writes_allowed"],
            "rdp_regression_allowed": partition["rdp_regression_allowed"],
            "mass_erase_allowed": partition["mass_erase_allowed"],
            "flash_geometry_validated": partition["flash_geometry_validated"],
            "programming_algorithm_equivalence": partition["programming_algorithm_equivalence"],
            "runtime_programming_supported": partition["runtime_programming_supported"],
            "hil_validated": partition["hil_validated"],
        },
        "claims": {
            "production_write_authorized": False,
            "production_admission_authorized": False,
            "security_semantics_supported": False,
            "option_byte_semantics_supported": False,
            "flash_geometry_validated": False,
            "programming_algorithm_equivalence": False,
            "runtime_programming_supported": False,
            "hil_validated": False,
        },
        "next_research_gate": "stm32l5-security-state-admission-gate",
    }


def plan_is_clean(plan: dict[str, Any]) -> bool:
    return (
        plan.get("authority") == "research_only"
        and plan.get("family") == FAMILY
        and plan.get("metadata_ready_exact_icpns") == EXPECTED_EXACT_COUNT
        and plan.get("unique_route_assignments") == EXPECTED_EXACT_COUNT
        and plan.get("planned_canonical_rows") == EXPECTED_EXACT_COUNT
        and plan.get("route_binding_sha256") == EXPECTED_ROUTE_BINDING_SHA256
        and plan.get("required_target_config") == TARGET_CONFIG
        and isinstance(plan.get("claims"), dict)
        and set(plan["claims"].values()) == {False}
        and plan.get("security_fence", {}).get("production_admission_allowed") is False
        and plan.get("next_research_gate") == "stm32l5-security-state-admission-gate"
    )

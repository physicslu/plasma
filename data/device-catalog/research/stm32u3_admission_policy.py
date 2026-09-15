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
TARGET_CONFIG = "tcl/target/stm32u3x.cfg"
EXPECTED_ROUTE_ROWS = 171
EXPECTED_ROUTE_KIND_COUNTS = {"ordering_pattern": 75, "cmsis_device_name": 96}
EXPECTED_SUBFAMILIES = {
    "STM32U335", "STM32U345", "STM32U356", "STM32U366",
    "STM32U375", "STM32U385", "STM32U3B5", "STM32U3C5",
}


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
    return rows


def resolve_route(icpn: str, rows: list[dict[str, str]]) -> dict[str, Any]:
    core = commercial_core(icpn)
    matches = [row for row in rows if pattern_matches(row["part_number"], core)]
    if len(matches) != 1:
        return {
            "status": "unmapped" if not matches else "ambiguous",
            "match_count": len(matches),
            "identifiers": sorted(row["part_number"] for row in matches),
        }
    row = matches[0]
    return {
        "status": "unique",
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


def diagnostic_report() -> dict[str, Any]:
    security = load_security_fence()
    if security["research_partition"].get("production_admission_allowed") is not False:
        raise AdmissionError("STM32U3 Production admission fence unexpectedly open")
    routes = read_route_rows()
    candidates = build_candidate_inputs()
    if len(candidates) != EXPECTED_EXACT_COUNT:
        raise AdmissionError("STM32U3 retained identity cardinality drifted")

    assignments: list[dict[str, str]] = []
    unresolved: list[dict[str, Any]] = []
    for candidate in candidates:
        build_metadata_row(candidate)
        route = resolve_route(candidate["icpn"], routes)
        if route["status"] != "unique":
            unresolved.append({"icpn": candidate["icpn"], **route})
            continue
        assignments.append({
            "icpn": candidate["icpn"],
            "identifier_kind": route["identifier_kind"],
            "identifier": route["identifier"],
            "target_config": route["target_config"],
        })

    return {
        "route_rows": len(routes),
        "route_kind_counts": dict(Counter(row["identifier_kind"] for row in routes)),
        "subfamily_counts": dict(sorted(Counter(row["subfamily"] for row in routes).items())),
        "route_evidence_sha256": route_evidence_sha(routes),
        "unique_assignments": len(assignments),
        "assignment_kind_counts": dict(Counter(row["identifier_kind"] for row in assignments)),
        "route_binding_sha256": route_binding_sha(assignments) if assignments else None,
        "unresolved": unresolved,
    }


if __name__ == "__main__":
    print(json.dumps(diagnostic_report(), sort_keys=True))

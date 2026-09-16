#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

from device_catalog_admission_framework import CandidateManualReview
from stm32u5_metadata_policy import (
    ACTIVE_STATUS,
    EXPECTED_SUBFAMILIES,
    MANUFACTURER,
    PREVIEW_STATUS,
    build_candidate_inputs,
    build_metadata_row,
    load_security_fence,
)

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "openocd-parts-canonical.csv"
FAMILY = "STM32U5"
TARGET_CONFIG = "tcl/target/stm32u5x.cfg"
EXPECTED_ROUTE_ROWS = 162
EXPECTED_ROUTE_KIND_COUNTS = {"ordering_pattern": 63, "cmsis_device_name": 99}


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


def read_routes() -> list[dict[str, str]]:
    with CATALOG.open(newline="", encoding="utf-8") as handle:
        rows = [
            row for row in csv.DictReader(handle)
            if row.get("vendor") == MANUFACTURER and row.get("plasma_series") == FAMILY
        ]
    if len(rows) != EXPECTED_ROUTE_ROWS:
        raise SystemExit(f"STM32U5 route row drift: {len(rows)}")
    kinds = Counter(row.get("identifier_kind", "") for row in rows)
    if dict(kinds) != EXPECTED_ROUTE_KIND_COUNTS:
        raise SystemExit(f"STM32U5 route kind drift: {dict(kinds)}")
    if {row.get("subfamily", "") for row in rows} != EXPECTED_SUBFAMILIES:
        raise SystemExit("STM32U5 route subfamily set drift")
    for row in rows:
        if (
            row.get("target_config") != TARGET_CONFIG
            or row.get("openocd_distribution") != "upstream-openocd"
            or row.get("mapping_status") != "mapping_candidate"
            or row.get("validation_status") != "not_verified"
            or row.get("catalog_origin") != "plasma_openocd_parts_top5_mapped.csv"
            or row.get("identifier_kind") not in EXPECTED_ROUTE_KIND_COUNTS
            or not row.get("part_number", "").startswith(row.get("subfamily", ""))
        ):
            raise SystemExit(f"invalid STM32U5 route evidence: {row.get('part_number')}")
    return rows


def main() -> int:
    security = load_security_fence()
    partition = security["research_partition"]
    if partition.get("catalog_admission_governed_separately") is not True:
        raise SystemExit("STM32U5 catalog admission governance fence drifted")
    for key in (
        "security_semantics_supported", "option_byte_writes_allowed", "oem_key_provisioning_allowed",
        "oem_unlock_execution_allowed", "rdp_regression_allowed", "mass_erase_allowed",
        "flash_geometry_validated", "programming_algorithm_equivalence", "runtime_programming_supported",
        "debug_attach_supported", "hil_validated",
    ):
        if partition.get(key) is not False:
            raise SystemExit(f"STM32U5 security fence unexpectedly open: {key}")

    candidates = build_candidate_inputs()
    active = [candidate for candidate in candidates if candidate["marketing_status"] == ACTIVE_STATUS]
    preview = [candidate for candidate in candidates if candidate["marketing_status"] == PREVIEW_STATUS]
    if len(candidates) != 266 or len(active) != 265 or len(preview) != 1 or preview[0]["icpn"] != "STM32U5G9ZJJ3Q":
        raise SystemExit("STM32U5 admission candidate partition drifted")

    for candidate in active:
        build_metadata_row(candidate)
    try:
        build_metadata_row(preview[0])
    except CandidateManualReview:
        pass
    else:
        raise SystemExit("quarantined Preview identity unexpectedly became metadata-ready")

    routes = read_routes()
    assignments: list[dict[str, str]] = []
    unresolved: list[dict[str, object]] = []
    for candidate in active:
        icpn = candidate["icpn"]
        core = commercial_core(icpn)
        matches = [row for row in routes if pattern_matches(row["part_number"], core)]
        if len(matches) != 1:
            unresolved.append({
                "icpn": icpn,
                "match_count": len(matches),
                "matches": [row["part_number"] for row in matches],
            })
            continue
        row = matches[0]
        assignments.append({
            "icpn": icpn,
            "identifier_kind": row["identifier_kind"],
            "identifier": row["part_number"],
            "target_config": row["target_config"],
        })

    u5a5_routes = [
        {"part_number": row["part_number"], "identifier_kind": row["identifier_kind"]}
        for row in routes if row["subfamily"] == "STM32U5A5"
    ]
    result = {
        "transaction": "stm32u5-canonical-admission-plan-under-security-fence-probe",
        "retained_exact_icpns": 266,
        "active_metadata_ready_exact_icpns": len(active),
        "quarantined_preview_exact_icpns": len(preview),
        "route_evidence_rows": len(routes),
        "route_evidence_kind_counts": dict(Counter(row["identifier_kind"] for row in routes)),
        "route_evidence_sha256": route_evidence_sha(routes),
        "unique_route_assignments": len(assignments),
        "route_assignment_kind_counts": dict(Counter(row["identifier_kind"] for row in assignments)),
        "route_binding_sha256": route_binding_sha(assignments),
        "unresolved_count": len(unresolved),
        "unresolved": unresolved,
        "u5a5_route_rows": u5a5_routes,
        "required_target_config": TARGET_CONFIG,
        "production_exact_icpn_count": 2017,
        "production_write_authorized": False,
        "runtime_programming_supported": False,
        "hil_validated": False,
    }
    print(json.dumps(result, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

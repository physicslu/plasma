#!/usr/bin/env python3
"""Fail-closed STM32G4 Phase 4.9A source-surface foundation.

The OpenOCD-derived STM32G4 source mixes commercial ordering patterns with a
small CMSIS device-name alias surface. Only ordering patterns participate in
deterministic Base Device selection. CMSIS aliases remain routing metadata and
are never treated as manufacturer commercial identity evidence.

No function here asserts exact commercial ICPNs, authorizes canonical or
Production writes, or claims programming/runtime support.
"""

from __future__ import annotations

import csv
import re
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_bounded_discovery import deterministic_first_unadmitted_targets
from st_product_page_acquisition import AcquisitionError

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
PHASE = "4.9A"
MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32G4"
TARGET_CONFIG = "tcl/target/stm32g4x.cfg"
EXPECTED_ROW_COUNT = 183
EXPECTED_ORDERING_COUNT = 177
EXPECTED_CMSIS_COUNT = 6
EXPECTED_SUBFAMILY_COUNTS = {
    "STM32G411": 22,
    "STM32G414": 10,
    "STM32G431": 27,
    "STM32G441": 9,
    "STM32G471": 17,
    "STM32G473": 27,
    "STM32G474": 25,
    "STM32G483": 9,
    "STM32G484": 9,
    "STM32G491": 19,
    "STM32G4A1": 9,
}
EXPECTED_ORDERING_BY_SUBFAMILY = {
    "STM32G411": 22,
    "STM32G414": 10,
    "STM32G431": 25,
    "STM32G441": 9,
    "STM32G471": 17,
    "STM32G473": 25,
    "STM32G474": 25,
    "STM32G483": 9,
    "STM32G484": 9,
    "STM32G491": 17,
    "STM32G4A1": 9,
}
EXPECTED_CMSIS_BY_SUBFAMILY = {
    "STM32G411": 0,
    "STM32G414": 0,
    "STM32G431": 2,
    "STM32G441": 0,
    "STM32G471": 0,
    "STM32G473": 2,
    "STM32G474": 0,
    "STM32G483": 0,
    "STM32G484": 0,
    "STM32G491": 2,
    "STM32G4A1": 0,
}
EXPECTED_SUBFAMILIES = tuple(EXPECTED_SUBFAMILY_COUNTS)
PATTERN_RE = re.compile(r"^(STM32G4[A-Z0-9]+)([A-Z])x$")
ROUTING_VALUE_RE = re.compile(r"^STM32G4[A-Z0-9]+$")


def read_catalog(path: Path = DEFAULT_CATALOG) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def guarded_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = [
        row
        for row in catalog_rows
        if row.get("vendor") == MANUFACTURER and row.get("plasma_series") == FAMILY
    ]
    if len(rows) != EXPECTED_ROW_COUNT:
        raise AcquisitionError(
            f"{PHASE} requires guarded {EXPECTED_ROW_COUNT}-row STM32G4 surface, got {len(rows)}"
        )
    if dict(sorted(Counter(row.get("subfamily", "") for row in rows).items())) != EXPECTED_SUBFAMILY_COUNTS:
        raise AcquisitionError(f"{PHASE} STM32G4 subfamily surface drifted")

    kinds = Counter(row.get("identifier_kind", "") for row in rows)
    if kinds != Counter({"ordering_pattern": EXPECTED_ORDERING_COUNT, "cmsis_device_name": EXPECTED_CMSIS_COUNT}):
        raise AcquisitionError(f"{PHASE} STM32G4 identifier-kind surface drifted: {dict(kinds)}")

    for row in rows:
        part = row.get("part_number", "")
        if row.get("target_config") != TARGET_CONFIG:
            raise AcquisitionError(f"{part}: unexpected OpenOCD target config")
        if row.get("openocd_distribution") != "upstream-openocd":
            raise AcquisitionError(f"{part}: unexpected OpenOCD distribution")
        if row.get("mapping_status") != "mapping_candidate":
            raise AcquisitionError(f"{part}: unexpected mapping status")
        if row.get("validation_status") != "not_verified":
            raise AcquisitionError(f"{part}: unexpected validation status")
        if row.get("identifier_kind") == "ordering_pattern":
            match = PATTERN_RE.fullmatch(part)
            if match is None:
                raise AcquisitionError(f"unsupported STM32G4 ordering pattern: {part!r}")
            base = match.group(1)
            subfamily = row.get("subfamily", "")
            if not base.startswith(subfamily) or len(base) != len(subfamily) + 2:
                raise AcquisitionError(f"{part}: invalid concrete STM32G4 Base Device {base!r}")
        elif row.get("identifier_kind") == "cmsis_device_name":
            if not part.startswith(row.get("subfamily", "")):
                raise AcquisitionError(f"{part}: CMSIS alias escaped its source subfamily")
        else:
            raise AcquisitionError(f"{part}: unsupported identifier kind")

    ordering_by_subfamily = Counter(
        row["subfamily"] for row in rows if row["identifier_kind"] == "ordering_pattern"
    )
    cmsis_by_subfamily = Counter(
        row["subfamily"] for row in rows if row["identifier_kind"] == "cmsis_device_name"
    )
    if {sub: ordering_by_subfamily[sub] for sub in EXPECTED_SUBFAMILIES} != EXPECTED_ORDERING_BY_SUBFAMILY:
        raise AcquisitionError(f"{PHASE} STM32G4 ordering-pattern distribution drifted")
    if {sub: cmsis_by_subfamily[sub] for sub in EXPECTED_SUBFAMILIES} != EXPECTED_CMSIS_BY_SUBFAMILY:
        raise AcquisitionError(f"{PHASE} STM32G4 CMSIS-alias distribution drifted")
    return rows


def commercial_ordering_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in guarded_rows(catalog_rows) if row["identifier_kind"] == "ordering_pattern"]


def cmsis_alias_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in guarded_rows(catalog_rows) if row["identifier_kind"] == "cmsis_device_name"]


def base_from_row(row: dict[str, str]) -> str:
    match = PATTERN_RE.fullmatch(row.get("part_number", ""))
    if match is None:
        raise AcquisitionError(f"unsupported STM32G4 ordering pattern: {row.get('part_number')!r}")
    return match.group(1)


def deterministic_initial_targets(catalog_rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    return deterministic_first_unadmitted_targets(
        family_rows=commercial_ordering_rows(catalog_rows),
        production_bases=set(),
        expected_subfamilies=EXPECTED_SUBFAMILIES,
        base_from_row=base_from_row,
        subfamily_from_row=lambda row: row["subfamily"],
        phase=PHASE,
        error_type=AcquisitionError,
    )


def pattern_matches(pattern: str, value: str) -> bool:
    expression = "".join("[A-Z0-9]" if char.lower() == "x" else re.escape(char) for char in pattern)
    return re.fullmatch(expression, value) is not None


def resolve_ordering_pattern_mapping(routing_value: str, catalog_rows: list[dict[str, str]]) -> dict[str, Any]:
    if ROUTING_VALUE_RE.fullmatch(routing_value) is None:
        return {"status": "unmapped", "match_count": 0, "target_configs": []}
    matches = [
        row for row in commercial_ordering_rows(catalog_rows)
        if pattern_matches(row["part_number"], routing_value)
    ]
    configs = sorted({row["target_config"] for row in matches})
    identifiers = sorted({row["part_number"] for row in matches})
    if len(matches) == 1 and configs == [TARGET_CONFIG]:
        return {
            "status": "unique",
            "match_count": 1,
            "identifier_kind": "ordering_pattern",
            "existing_identifier": identifiers[0],
            "target_configs": configs,
        }
    return {
        "status": "ambiguous" if matches else "unmapped",
        "match_count": len(matches),
        "existing_identifiers": identifiers,
        "target_configs": configs,
    }


def build_foundation_report(catalog_rows: list[dict[str, str]]) -> dict[str, object]:
    rows = guarded_rows(catalog_rows)
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "source_row_count": len(rows),
        "commercial_ordering_row_count": len(commercial_ordering_rows(catalog_rows)),
        "cmsis_alias_row_count": len(cmsis_alias_rows(catalog_rows)),
        "subfamily_counts": EXPECTED_SUBFAMILY_COUNTS,
        "ordering_pattern_counts": EXPECTED_ORDERING_BY_SUBFAMILY,
        "cmsis_alias_counts": EXPECTED_CMSIS_BY_SUBFAMILY,
        "target_config": TARGET_CONFIG,
        "initial_targets": [
            {"subfamily": subfamily, "base_device": base}
            for subfamily, base in deterministic_initial_targets(catalog_rows)
        ],
        "claims": {
            "cmsis_alias_is_commercial_identity": False,
            "manufacturer_evidence_retained": False,
            "exact_commercial_icpn_asserted": False,
            "canonical_dataset_admission": False,
            "production_write_authorized": False,
            "programming_policy_defined": False,
            "runtime_support_claimed": False,
        },
    }

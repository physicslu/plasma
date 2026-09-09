#!/usr/bin/env python3
"""Fail-closed STM32F7 source-surface foundation for bounded discovery.

This module deliberately stops before manufacturer evidence acquisition. It
qualifies the current OpenOCD-derived STM32F7 surface, extracts concrete Base
Devices from ordering patterns, selects one deterministic initial target per
source subfamily, and resolves synthetic routing examples to stm32f7x.cfg.

No function in this module asserts an exact commercial ICPN, authorizes
canonical admission, or claims runtime/programming support.
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
PHASE = "4.6A"
MANUFACTURER = "STMicroelectronics"
FAMILY = "STM32F7"
TARGET_CONFIG = "tcl/target/stm32f7x.cfg"
EXPECTED_ROW_COUNT = 123
EXPECTED_SUBFAMILY_COUNTS = {
    "STM32F722": 10,
    "STM32F723": 12,
    "STM32F730": 4,
    "STM32F732": 5,
    "STM32F733": 6,
    "STM32F745": 10,
    "STM32F746": 16,
    "STM32F750": 3,
    "STM32F756": 8,
    "STM32F765": 14,
    "STM32F767": 14,
    "STM32F768": 1,
    "STM32F769": 8,
    "STM32F777": 7,
    "STM32F778": 1,
    "STM32F779": 4,
}
EXPECTED_SUBFAMILIES = tuple(EXPECTED_SUBFAMILY_COUNTS)
BASE_RE = re.compile(r"^STM32F7[0-9]{2}[A-Z][A-Z0-9]$")
PATTERN_RE = re.compile(r"^(STM32F7[0-9]{2}[A-Z][A-Z0-9])([A-Z])x$")
ROUTING_VALUE_RE = re.compile(r"^STM32F7[0-9A-Z]+$")


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
            f"{PHASE} requires the guarded {EXPECTED_ROW_COUNT}-row STM32F7 surface, got {len(rows)}"
        )

    subfamilies = Counter(row.get("subfamily", "") for row in rows)
    if dict(sorted(subfamilies.items())) != EXPECTED_SUBFAMILY_COUNTS:
        raise AcquisitionError(
            f"{PHASE} STM32F7 subfamily surface drifted: {dict(sorted(subfamilies.items()))}"
        )

    for row in rows:
        pattern = row.get("part_number", "")
        match = PATTERN_RE.fullmatch(pattern)
        if match is None:
            raise AcquisitionError(f"unsupported STM32F7 ordering pattern: {pattern!r}")
        if BASE_RE.fullmatch(match.group(1)) is None:
            raise AcquisitionError(f"invalid concrete STM32F7 Base Device: {match.group(1)!r}")
        if row.get("identifier_kind") != "ordering_pattern":
            raise AcquisitionError(f"{pattern}: identifier kind is not ordering_pattern")
        if row.get("target_config") != TARGET_CONFIG:
            raise AcquisitionError(f"{pattern}: unexpected OpenOCD target config")
        if row.get("openocd_distribution") != "upstream-openocd":
            raise AcquisitionError(f"{pattern}: unexpected OpenOCD distribution")
        if row.get("mapping_status") != "mapping_candidate":
            raise AcquisitionError(f"{pattern}: unexpected mapping status")
        if row.get("validation_status") != "not_verified":
            raise AcquisitionError(f"{pattern}: unexpected validation status")
    return rows


def base_from_row(row: dict[str, str]) -> str:
    match = PATTERN_RE.fullmatch(row.get("part_number", ""))
    if match is None:
        raise AcquisitionError(f"unsupported STM32F7 ordering pattern: {row.get('part_number')!r}")
    return match.group(1)


def deterministic_initial_targets(
    catalog_rows: list[dict[str, str]],
) -> list[tuple[str, str]]:
    """Select the first concrete Base Device in each guarded source subfamily."""

    return deterministic_first_unadmitted_targets(
        family_rows=guarded_rows(catalog_rows),
        production_bases=set(),
        expected_subfamilies=EXPECTED_SUBFAMILIES,
        base_from_row=base_from_row,
        subfamily_from_row=lambda row: row["subfamily"],
        phase=PHASE,
        error_type=AcquisitionError,
    )


def pattern_matches(pattern: str, value: str) -> bool:
    expression = "".join(
        "[A-Z0-9]" if char.lower() == "x" else re.escape(char)
        for char in pattern
    )
    return re.fullmatch(expression, value) is not None


def resolve_ordering_pattern_mapping(
    routing_value: str,
    catalog_rows: list[dict[str, str]],
) -> dict[str, Any]:
    """Resolve a routing value only; this does not assert commercial identity."""

    if ROUTING_VALUE_RE.fullmatch(routing_value) is None:
        return {"status": "unmapped", "match_count": 0, "target_configs": []}
    matches = [
        row
        for row in guarded_rows(catalog_rows)
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


def build_foundation_report(
    catalog_rows: list[dict[str, str]],
) -> dict[str, object]:
    rows = guarded_rows(catalog_rows)
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "source_row_count": len(rows),
        "subfamily_counts": EXPECTED_SUBFAMILY_COUNTS,
        "target_config": TARGET_CONFIG,
        "initial_targets": [
            {"subfamily": subfamily, "base_device": base}
            for subfamily, base in deterministic_initial_targets(catalog_rows)
        ],
        "claims": {
            "manufacturer_evidence_retained": False,
            "exact_commercial_icpn_asserted": False,
            "canonical_dataset_admission": False,
            "production_write_authorized": False,
            "programming_policy_defined": False,
            "runtime_support_claimed": False,
        },
    }

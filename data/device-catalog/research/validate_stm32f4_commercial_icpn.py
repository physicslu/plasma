#!/usr/bin/env python3
"""Validate the Phase 3.1 STM32F4 canonical commercial ICPN dataset offline."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path

from evaluate_stm32f4_pilot import read_baseline
from stm32f4_admission_policy import (
    FAMILY,
    MANUFACTURER,
    TARGET_CONFIG,
    resolve_ordering_pattern_mapping,
)

HERE = Path(__file__).resolve().parent
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
BASELINE = HERE / "stm32f4-phase3.1-pilot-baseline.json"
CATALOG = HERE / "openocd-parts-canonical.csv"
EXPECTED_ROWS = 18
EXPECTED_FIELDS = [
    "manufacturer",
    "icpn",
    "family",
    "series",
    "base_device",
    "package",
    "pin_count",
    "flash_size",
    "temperature_grade",
    "option_suffix",
    "cmsis_device_name",
    "existing_identifier",
    "existing_identifier_kind",
    "mapping_status",
    "openocd_target_config",
    "source_type",
    "source_reference",
    "source_authority",
    "verification_status",
]


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def validate() -> dict[str, object]:
    fields, rows = read_csv(CANONICAL)
    _, catalog_rows = read_csv(CATALOG)
    baseline = read_baseline(BASELINE)
    expected = {
        icpn
        for target in baseline["targets"]
        for icpn in target["exact_icpns"]
    }
    errors: list[str] = []

    if fields != EXPECTED_FIELDS:
        errors.append("canonical schema/order mismatch")
    if len(rows) != EXPECTED_ROWS:
        errors.append(f"canonical row count must be {EXPECTED_ROWS}")
    values = [row.get("icpn", "") for row in rows]
    if len(values) != len(set(values)):
        errors.append("duplicate ICPN rows")
    if set(values) != expected:
        errors.append("canonical ICPN set does not match Phase 3.1 baseline")

    for row in rows:
        icpn = row.get("icpn", "")
        if row.get("manufacturer") != MANUFACTURER:
            errors.append(f"{icpn}: manufacturer mismatch")
        if row.get("family") != FAMILY:
            errors.append(f"{icpn}: family mismatch")
        if row.get("existing_identifier_kind") != "ordering_pattern":
            errors.append(f"{icpn}: identifier kind mismatch")
        if row.get("mapping_status") != "deterministic_ordering_pattern":
            errors.append(f"{icpn}: mapping status mismatch")
        if row.get("openocd_target_config") != TARGET_CONFIG:
            errors.append(f"{icpn}: target config mismatch")
        if row.get("cmsis_device_name") != "":
            errors.append(f"{icpn}: CMSIS name must remain unclaimed")
        if row.get("source_authority") != "STMicroelectronics official":
            errors.append(f"{icpn}: source authority mismatch")
        if row.get("verification_status") != "verified_direct_st_retained_browser_exact_icpn":
            errors.append(f"{icpn}: verification status mismatch")
        if "plasma-evidence=stm32f4-phase3.1-bounded-pilot-2026-08-30-retained-20260830T023035Z-b42d460" not in row.get("source_reference", ""):
            errors.append(f"{icpn}: retained evidence binding mismatch")

        mapping = resolve_ordering_pattern_mapping(icpn, catalog_rows)
        if mapping.get("status") != "unique":
            errors.append(f"{icpn}: current OpenOCD ordering-pattern mapping is not unique")
        elif mapping.get("existing_identifier") != row.get("existing_identifier"):
            errors.append(f"{icpn}: current ordering pattern differs from canonical")
        elif mapping.get("target_configs") != [TARGET_CONFIG]:
            errors.append(f"{icpn}: current target config differs from canonical")

    return {
        "rows": len(rows),
        "unique_icpns": len(set(values)),
        "expected_icpns": len(expected),
        "target_config": TARGET_CONFIG,
        "errors": errors,
    }


def main() -> int:
    report = validate()
    print(json.dumps(report, indent=2, sort_keys=True))
    if report["errors"]:
        return 1
    print("STM32F4 commercial ICPN catalog: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

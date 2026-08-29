#!/usr/bin/env python3
"""Validate the evidence-backed STM32F1 commercial ICPN vertical slice."""

from __future__ import annotations

import csv
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "stm32f1-commercial-icpn.csv"
CATALOG = ROOT / "openocd-parts-canonical.csv"
REQUIRED_COLUMNS = {
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
}
ALLOWED_MAPPING_STATUS = {"exact", "deterministic_pattern", "ambiguous", "unmapped"}
WILDCARD_RE = re.compile(r"[xX*?\[\]]")
EXACT_ICPN_RE = re.compile(r"^STM32F1[0-9A-Z]+$")


def read_csv(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        return list(reader.fieldnames or []), list(reader)


def fail(errors: list[str], message: str) -> None:
    errors.append(message)


def main() -> int:
    fields, rows = read_csv(DATASET)
    _, catalog_rows = read_csv(CATALOG)
    errors: list[str] = []

    missing_columns = REQUIRED_COLUMNS - set(fields)
    if missing_columns:
        fail(errors, f"missing required columns: {sorted(missing_columns)}")

    catalog_by_identifier: dict[str, list[dict[str, str]]] = defaultdict(list)
    for row in catalog_rows:
        catalog_by_identifier[row["part_number"]].append(row)

    icpn_counts = Counter(row.get("icpn", "") for row in rows)
    duplicates = sorted(icpn for icpn, count in icpn_counts.items() if count > 1)
    wildcard_icpns: list[str] = []
    missing_provenance: list[str] = []
    ambiguous: list[str] = []
    unmapped: list[str] = []
    cmsis_mapped = 0
    plasma_mapped = 0
    openocd_mapped = 0

    for line_number, row in enumerate(rows, start=2):
        icpn = row.get("icpn", "").strip()
        if not icpn or not EXACT_ICPN_RE.fullmatch(icpn) or WILDCARD_RE.search(icpn):
            wildcard_icpns.append(icpn or f"<blank at line {line_number}>")
        if row.get("manufacturer") != "STMicroelectronics":
            fail(errors, f"line {line_number}: manufacturer is not STMicroelectronics")
        if "st.com/" not in row.get("source_reference", ""):
            missing_provenance.append(icpn)
        if row.get("source_authority") != "STMicroelectronics official":
            missing_provenance.append(icpn)
        if not row.get("verification_status", "").startswith("verified_direct_st"):
            missing_provenance.append(icpn)
        if row.get("mapping_status") not in ALLOWED_MAPPING_STATUS:
            fail(errors, f"line {line_number}: unsupported mapping_status")
        if row.get("mapping_status") == "ambiguous":
            ambiguous.append(icpn)
        if row.get("mapping_status") == "unmapped":
            unmapped.append(icpn)
        if row.get("mapping_status") == "deterministic_pattern" and not (
            row.get("base_device")
            == row.get("cmsis_device_name")
            == row.get("existing_identifier")
        ):
            fail(errors, f"line {line_number}: deterministic identity chain is inconsistent")

        cmsis = row.get("cmsis_device_name", "")
        if cmsis:
            cmsis_mapped += 1
        matches = catalog_by_identifier.get(row.get("existing_identifier", ""), [])
        exact_matches = [
            match
            for match in matches
            if match["identifier_kind"] == row.get("existing_identifier_kind")
            and match["target_config"] == row.get("openocd_target_config")
        ]
        if len(exact_matches) == 1:
            plasma_mapped += 1
            if row.get("openocd_target_config"):
                openocd_mapped += 1
        elif len(exact_matches) > 1:
            fail(errors, f"line {line_number}: asserted Plasma mapping is not unique")
        elif row.get("mapping_status") not in {"ambiguous", "unmapped"}:
            fail(errors, f"line {line_number}: asserted Plasma mapping is not in canonical catalog")

        if row.get("openocd_target_config") == icpn:
            fail(errors, f"line {line_number}: commercial identity conflated with OpenOCD capability")
        if not row.get("source_type", "").startswith("official_st_"):
            fail(errors, f"line {line_number}: non-ST source used as commercial identity authority")

    if duplicates:
        fail(errors, f"duplicate ICPNs: {duplicates}")
    if wildcard_icpns:
        fail(errors, f"invalid or wildcard ICPNs: {wildcard_icpns}")
    if missing_provenance:
        fail(errors, f"ICPNs lacking authoritative ST provenance: {sorted(set(missing_provenance))}")

    stats = {
        "total_exact_icpns": len(rows),
        "unique_icpns": len(icpn_counts),
        "duplicate_icpns": len(duplicates),
        "wildcard_icpns": len(wildcard_icpns),
        "icpns_lacking_authoritative_provenance": len(set(missing_provenance)),
        "direct_st_evidence": sum(
            row.get("verification_status", "").startswith("verified_direct_st") for row in rows
        ),
        "base_device_distribution": dict(sorted(Counter(row["base_device"] for row in rows).items())),
        "package_distribution": dict(sorted(Counter(row["package"] or "<unknown>" for row in rows).items())),
        "cmsis_mapping": {"mapped": cmsis_mapped, "total": len(rows)},
        "plasma_catalog_mapping": {"mapped": plasma_mapped, "total": len(rows)},
        "openocd_cfg_mapping": {"mapped": openocd_mapped, "total": len(rows)},
        "ambiguous_mappings": ambiguous,
        "unmapped_icpns": unmapped,
        "errors": errors,
    }
    print(json.dumps(stats, indent=2, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())

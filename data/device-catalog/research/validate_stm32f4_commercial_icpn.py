#!/usr/bin/env python3
"""Validate the current STM32F4 canonical commercial ICPN dataset offline."""

from __future__ import annotations

import csv
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_evidence_framework import (
    EvidenceFrameworkError,
    read_json,
    validate_core_provenance,
    validate_manifest,
)
from stm32f4_admission_policy import (
    FAMILY,
    MANUFACTURER,
    TARGET_CONFIG,
    build_candidate_inputs,
    build_canonical_row,
    resolve_ordering_pattern_mapping,
)

HERE = Path(__file__).resolve().parent
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
CATALOG = HERE / "openocd-parts-canonical.csv"
EVIDENCE_ROOT = HERE / "evidence"
FINAL_TAIL_AUTHORITY = HERE / "st-final-active-tail-gap-metadata-authority-v6.0.json"
EXPECTED_EVIDENCE_FILES = {
    "control-summary.json",
    "pilot-summary.json",
    "evaluation.json",
    "provenance.json",
    "README.md",
}
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


def _evidence_id_from_reference(reference: str) -> str | None:
    marker = "#plasma-evidence="
    if reference.count(marker) != 1:
        return None
    evidence_id = reference.split(marker, 1)[1]
    return evidence_id if evidence_id and "#" not in evidence_id else None


def _discover_retained_rows(
    catalog_rows: list[dict[str, str]],
) -> tuple[dict[tuple[str, str], dict[str, str]], dict[str, dict[str, Any]], list[str]]:
    """Rebuild every STM32F4 retained candidate row keyed by evidence ID + ICPN."""

    rows_by_binding: dict[tuple[str, str], dict[str, str]] = {}
    packages: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    if not EVIDENCE_ROOT.is_dir():
        return rows_by_binding, packages, ["STM32F4 retained evidence root is missing"]

    for evidence_dir in sorted(EVIDENCE_ROOT.iterdir()):
        if not evidence_dir.is_dir() or not evidence_dir.name.startswith("stm32f4-"):
            continue
        manifest_path = evidence_dir / "manifest.json"
        pilot_path = evidence_dir / "pilot-summary.json"
        provenance_path = evidence_dir / "provenance.json"
        if not (manifest_path.is_file() and pilot_path.is_file() and provenance_path.is_file()):
            continue
        try:
            manifest = validate_manifest(evidence_dir, expected_files=EXPECTED_EVIDENCE_FILES)
            provenance = read_json(provenance_path)
            core = validate_core_provenance(
                provenance,
                evidence_id=manifest["evidence_id"],
                expected_repository="physicslu/plasma",
                expected_manufacturer=MANUFACTURER,
            )
            pilot = read_json(pilot_path)
            evidence_id = manifest["evidence_id"]
            candidates = build_candidate_inputs(
                summary=pilot,
                evidence_id=evidence_id,
                catalog_rows=catalog_rows,
            )
        except (OSError, json.JSONDecodeError, EvidenceFrameworkError, RuntimeError) as exc:
            errors.append(f"{evidence_dir.name}: invalid retained evidence package: {exc}")
            continue

        if evidence_id in packages:
            errors.append(f"duplicate retained evidence ID: {evidence_id}")
            continue
        packages[evidence_id] = {
            "directory": evidence_dir.name,
            "candidate_count": len(candidates),
            "executed_git_sha": core.get("executed_git_sha"),
        }
        for candidate in candidates:
            icpn = candidate.get("icpn")
            if not isinstance(icpn, str) or not icpn:
                errors.append(f"{evidence_dir.name}: retained candidate lacks ICPN")
                continue
            key = (evidence_id, icpn)
            if key in rows_by_binding:
                errors.append(f"{evidence_id}/{icpn}: duplicate retained candidate binding")
                continue
            try:
                rows_by_binding[key] = build_canonical_row(candidate, EXPECTED_FIELDS)
            except RuntimeError as exc:
                errors.append(f"{evidence_id}/{icpn}: canonical row reconstruction failed: {exc}")

    if not packages:
        errors.append("no STM32F4 retained evidence packages discovered")
    return rows_by_binding, packages, errors


def validate() -> dict[str, object]:
    fields, rows = read_csv(CANONICAL)
    _, catalog_rows = read_csv(CATALOG)
    retained_rows, packages, errors = _discover_retained_rows(catalog_rows)

    if fields != EXPECTED_FIELDS:
        errors.append("canonical schema/order mismatch")
    if not rows:
        errors.append("canonical dataset must not be empty")
    values = [row.get("icpn", "") for row in rows]
    if len(values) != len(set(values)):
        errors.append("duplicate ICPN rows")

    evidence_usage: dict[str, int] = {evidence_id: 0 for evidence_id in packages}

    tail_payload = read_json(FINAL_TAIL_AUTHORITY)
    tail_records = {
        item["icpn"]: item
        for item in tail_payload.get("records", [])
        if isinstance(item, dict) and item.get("family") == FAMILY
    }
    expected_tail_ids = {
        "STM32F405OGY6VTR",
        "STM32F405OGY6WTR",
        "STM32F437VIT6WTR",
    }
    if set(tail_records) != expected_tail_ids:
        errors.append("final STM32F4 tail authority exact set drifted")

    observed_tail_ids: set[str] = set()
    for row in rows:
        icpn = row.get("icpn", "")
        if row.get("manufacturer") != MANUFACTURER:
            errors.append(f"{icpn}: manufacturer mismatch")
        if row.get("family") != FAMILY:
            errors.append(f"{icpn}: family mismatch")
        tail = tail_records.get(icpn)
        if tail is not None:
            observed_tail_ids.add(icpn)
            expected_meta = {
                "series": tail["series"],
                "base_device": tail["base_device"],
                "package": tail["package"],
                "pin_count": str(tail["pin_count"]),
                "flash_size": tail["flash_size"],
                "temperature_grade": tail["temperature_grade"],
                "option_suffix": tail["option_suffix"],
            }
            for key, expected in expected_meta.items():
                if row.get(key) != expected:
                    errors.append(f"{icpn}: final-tail {key} mismatch")
            if row.get("cmsis_device_name") != "":
                errors.append(f"{icpn}: final-tail CMSIS name must remain unclaimed")
            if row.get("existing_identifier") != "" or row.get("existing_identifier_kind") != "":
                errors.append(f"{icpn}: final-tail backend identifier must remain unbound")
            if row.get("mapping_status") != "no_mapping":
                errors.append(f"{icpn}: final-tail mapping status must remain no_mapping")
            if row.get("openocd_target_config") != "":
                errors.append(f"{icpn}: final-tail target config must remain unbound")
            if row.get("source_type") != "official_st_exact_product_authority_plus_locked_active_lifecycle":
                errors.append(f"{icpn}: final-tail source type mismatch")
            if row.get("source_reference") != tail["metadata_source_url"]:
                errors.append(f"{icpn}: final-tail source reference mismatch")
            if row.get("source_authority") != "STMicroelectronics official":
                errors.append(f"{icpn}: final-tail source authority mismatch")
            if row.get("verification_status") != "verified_official_exact_product_identity_metadata_plus_locked_active_lifecycle":
                errors.append(f"{icpn}: final-tail verification status mismatch")
            continue

        if row.get("existing_identifier_kind") != "ordering_pattern":
            errors.append(f"{icpn}: identifier kind mismatch")
        if row.get("mapping_status") != "deterministic_ordering_pattern":
            errors.append(f"{icpn}: mapping status mismatch")
        if row.get("openocd_target_config") != TARGET_CONFIG:
            errors.append(f"{icpn}: target config mismatch")
        if row.get("cmsis_device_name") != "":
            errors.append(f"{icpn}: CMSIS name must remain unclaimed")
        if row.get("source_type") != "official_st_product_page_retained_browser_evidence":
            errors.append(f"{icpn}: source type mismatch")
        if row.get("source_authority") != "STMicroelectronics official":
            errors.append(f"{icpn}: source authority mismatch")
        if row.get("verification_status") != "verified_direct_st_retained_browser_exact_icpn":
            errors.append(f"{icpn}: verification status mismatch")

        evidence_id = _evidence_id_from_reference(row.get("source_reference", ""))
        if evidence_id is None:
            errors.append(f"{icpn}: malformed retained evidence binding")
        else:
            expected_row = retained_rows.get((evidence_id, icpn))
            if expected_row is None:
                errors.append(f"{icpn}: retained evidence binding is not backed by an immutable candidate")
            elif row != expected_row:
                errors.append(f"{icpn}: canonical row differs from retained evidence/policy reconstruction")
            if evidence_id in evidence_usage:
                evidence_usage[evidence_id] += 1

        mapping = resolve_ordering_pattern_mapping(icpn, catalog_rows)
        if mapping.get("status") != "unique":
            errors.append(f"{icpn}: current OpenOCD ordering-pattern mapping is not unique")
        elif mapping.get("existing_identifier") != row.get("existing_identifier"):
            errors.append(f"{icpn}: current ordering pattern differs from canonical")
        elif mapping.get("target_configs") != [TARGET_CONFIG]:
            errors.append(f"{icpn}: current target config differs from canonical")

    if observed_tail_ids != expected_tail_ids:
        errors.append(
            "final STM32F4 tail identities missing from canonical: "
            + ",".join(sorted(expected_tail_ids - observed_tail_ids))
        )

    return {
        "rows": len(rows),
        "final_tail_no_mapping_rows": len(observed_tail_ids),
        "unique_icpns": len(set(values)),
        "retained_evidence_packages": len(packages),
        "retained_candidate_bindings": len(retained_rows),
        "evidence_usage": evidence_usage,
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

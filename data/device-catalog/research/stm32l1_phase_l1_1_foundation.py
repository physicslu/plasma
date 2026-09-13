#!/usr/bin/env python3
"""Fail-closed STM32L1 Phase L1.1 bounded research foundation.

L1.1 freezes the STM32L1 OpenOCD-derived research surface and binds one
deterministic representative Base Device per guarded subfamily to the retained
manufacturer-authoritative lifecycle requalification and Ordering Information
artifacts from H024.

This is research foundation only. The retained exact ICPNs are representative
evidence and are not a complete STM32L1 commercial inventory. Nothing here
authorizes canonical admission, Production writes, programming policy,
Flash/security qualification, HIL, electrical/socket, or runtime support.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from st_product_page_acquisition import AcquisitionError
from stm32_post_u0_evidence_probe import base_from_ordering_pattern
from stm32l1_requalification import (
    DEFAULT_ORDERING,
    DEFAULT_OUTPUT,
    DEFAULT_SUMMARY,
    DEFAULT_TARGETS,
    EXPECTED_ACTIVE,
    EXPECTED_EXCLUDED,
    FROZEN_PRODUCTION_PRESTATE,
    build_requalification_result,
)

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_BASELINE = HERE / "stm32l1-phase-l1.1-foundation-baseline.json"

PHASE = "L1.1"
FAMILY = "STM32L1"
MANUFACTURER = "STMicroelectronics"
TARGET_CONFIG = "tcl/target/stm32l1.cfg"

EXPECTED_ROW_COUNT = 132
EXPECTED_ORDERING_COUNT = 87
EXPECTED_CMSIS_COUNT = 45
EXPECTED_REPRESENTATIVE_EXACT_ICPNS = 9
EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS = 8
EXPECTED_ORDERING_SOURCE_COUNT = 3
EXPECTED_SUBFAMILIES = ("STM32L100", "STM32L151", "STM32L152", "STM32L162")
EXPECTED_TARGETS = (
    ("STM32L100", "STM32L100C6"),
    ("STM32L151", "STM32L151C6"),
    ("STM32L152", "STM32L152C6"),
    ("STM32L162", "STM32L162QC"),
)

EXPECTED_OPENOCD_CATALOG_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_REQUALIFICATION_RESULT_BLOB = "2c90037444efddc85e200b45631ec6ec762eb901"
EXPECTED_TARGET_MANIFEST_BLOB = "b8499df773d6b850565646670dd2fc780cc63596"
EXPECTED_RETAINED_SUMMARY_BLOB = "51aa041be6749e7f094870a79cea6994b23a4057"
EXPECTED_ORDERING_AUTHORITY_BLOB = "72e14cf7ae86ffb30282986712c9bbbbdf0650bc"
EXPECTED_PRODUCTION_PRESTATE_BLOB = "477f0fa4f507e01e420df47a49384d3db7928ba7"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _git_blob_sha(path: Path) -> str:
    data = path.read_bytes()
    return hashlib.sha1(f"blob {len(data)}\0".encode() + data, usedforsecurity=False).hexdigest()


def _require_blob(path: Path, expected: str, label: str) -> None:
    observed = _git_blob_sha(path)
    if observed != expected:
        raise AcquisitionError(f"{label} Git blob drifted: {observed}")


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AcquisitionError(f"{path.name}: expected JSON object")
    return payload


def _all_false(value: Any, label: str) -> None:
    if not isinstance(value, dict) or not value:
        raise AcquisitionError(f"{label}: missing fail-closed claim map")
    escaped = {key: state for key, state in value.items() if state is not False}
    if escaped:
        raise AcquisitionError(f"{label}: escaped fail-closed state: {escaped}")


def read_catalog(path: Path = DEFAULT_CATALOG) -> list[dict[str, str]]:
    observed = _sha256(path)
    if observed != EXPECTED_OPENOCD_CATALOG_SHA256:
        raise AcquisitionError(f"OpenOCD canonical catalog SHA-256 drifted: {observed}")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def guarded_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = [
        row for row in catalog_rows
        if row.get("vendor") == MANUFACTURER and row.get("plasma_series") == FAMILY
    ]
    if len(rows) != EXPECTED_ROW_COUNT:
        raise AcquisitionError(f"{PHASE} requires {EXPECTED_ROW_COUNT} STM32L1 rows, got {len(rows)}")
    kinds = Counter(row.get("identifier_kind", "") for row in rows)
    wanted = Counter({"ordering_pattern": EXPECTED_ORDERING_COUNT, "cmsis_device_name": EXPECTED_CMSIS_COUNT})
    if kinds != wanted:
        raise AcquisitionError(f"{PHASE} identifier-kind surface drifted: {dict(kinds)}")
    subfamilies = tuple(sorted({row.get("subfamily", "") for row in rows if row.get("subfamily")}))
    if subfamilies != tuple(sorted(EXPECTED_SUBFAMILIES)):
        raise AcquisitionError(f"{PHASE} subfamily surface drifted: {subfamilies}")
    ordering_subfamilies: set[str] = set()
    for row in rows:
        part = row.get("part_number", "")
        if row.get("target_config") != TARGET_CONFIG:
            raise AcquisitionError(f"{part}: unexpected OpenOCD target config")
        if row.get("openocd_distribution") != "upstream-openocd":
            raise AcquisitionError(f"{part}: unexpected OpenOCD distribution")
        if row.get("mapping_status") != "mapping_candidate" or row.get("validation_status") != "not_verified":
            raise AcquisitionError(f"{part}: source status escaped research-only state")
        kind = row.get("identifier_kind")
        subfamily = row.get("subfamily", "")
        if kind == "ordering_pattern":
            base = base_from_ordering_pattern(row)
            if not base.startswith(subfamily):
                raise AcquisitionError(f"{part}: ordering Base Device escaped {subfamily}")
            ordering_subfamilies.add(subfamily)
        elif kind == "cmsis_device_name":
            if not part.startswith(subfamily):
                raise AcquisitionError(f"{part}: CMSIS alias escaped subfamily")
        else:
            raise AcquisitionError(f"{part}: unsupported identifier kind")
    if ordering_subfamilies != set(EXPECTED_SUBFAMILIES):
        raise AcquisitionError(f"{PHASE} ordering-pattern subfamily coverage drifted")
    return rows


def commercial_ordering_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in guarded_rows(catalog_rows) if row["identifier_kind"] == "ordering_pattern"]


def cmsis_alias_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [row for row in guarded_rows(catalog_rows) if row["identifier_kind"] == "cmsis_device_name"]


def deterministic_initial_targets(catalog_rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    by_subfamily: dict[str, set[str]] = defaultdict(set)
    for row in commercial_ordering_rows(catalog_rows):
        by_subfamily[row["subfamily"]].add(base_from_ordering_pattern(row))
    targets = [(subfamily, min(by_subfamily[subfamily])) for subfamily in EXPECTED_SUBFAMILIES]
    if tuple(targets) != EXPECTED_TARGETS:
        raise AcquisitionError(f"{PHASE} deterministic targets drifted: {targets}")
    return targets


def validate_requalification_result(path: Path = DEFAULT_OUTPUT) -> dict[str, Any]:
    _require_blob(path, EXPECTED_REQUALIFICATION_RESULT_BLOB, "STM32L1 requalification result")
    frozen = _read_json(path)
    generated = build_requalification_result()
    if generated != frozen:
        raise AcquisitionError("STM32L1 requalification result no longer replays")
    if frozen.get("status") != "eligible_for_next_research_gate":
        raise AcquisitionError("STM32L1 is no longer eligible for the next research gate")
    if frozen.get("active_subfamilies") != list(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("STM32L1 requalified subfamily set drifted")
    if frozen.get("active_exact_icpn_evidence_count") != EXPECTED_REPRESENTATIVE_EXACT_ICPNS:
        raise AcquisitionError("STM32L1 Active exact evidence aggregate drifted")
    if frozen.get("non_active_exact_icpn_evidence_count") != EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS:
        raise AcquisitionError("STM32L1 non-Active evidence aggregate drifted")
    if frozen.get("selected_next_research_family") is not None:
        raise AcquisitionError("requalification unexpectedly selected a next family")
    _all_false(frozen.get("claims"), "requalification claims")
    return frozen


def validate_target_manifest(path: Path = DEFAULT_TARGETS) -> dict[str, list[str]]:
    _require_blob(path, EXPECTED_TARGET_MANIFEST_BLOB, "STM32L1 requalification target manifest")
    payload = _read_json(path)
    _all_false(payload.get("claims"), "target manifest claims")
    if payload.get("target_count") != 7:
        raise AcquisitionError("STM32L1 target surface drifted")
    rows = payload.get("targets")
    if not isinstance(rows, list):
        raise AcquisitionError("STM32L1 target manifest rows missing")
    by_base: dict[str, list[str]] = defaultdict(list)
    expected_bases = {base for _, base in EXPECTED_TARGETS}
    for row in rows:
        if not isinstance(row, dict):
            raise AcquisitionError("STM32L1 target row must be an object")
        base = row.get("base_device")
        role = row.get("role")
        if base not in expected_bases or not isinstance(role, str):
            raise AcquisitionError(f"unexpected STM32L1 target row: {row}")
        by_base[base].append(role)
    for subfamily, base in EXPECTED_TARGETS:
        roles = sorted(by_base.get(base, []))
        required = ["historical_representative"]
        if subfamily in {"STM32L100", "STM32L151", "STM32L152"}:
            required.append("generation_companion")
        if roles != sorted(required):
            raise AcquisitionError(f"{base}: generation-aware target roles drifted: {roles}")
    return dict(by_base)


def validate_retained_identity(path: Path = DEFAULT_SUMMARY) -> dict[str, dict[str, list[str]]]:
    _require_blob(path, EXPECTED_RETAINED_SUMMARY_BLOB, "STM32L1 retained requalification summary")
    payload = _read_json(path)
    _all_false(payload.get("claims"), "retained evidence claims")
    if payload.get("requalification_status") != "eligible_for_next_research_gate":
        raise AcquisitionError("retained STM32L1 lifecycle status drifted")
    by_subfamily = payload.get("by_subfamily")
    if not isinstance(by_subfamily, dict):
        raise AcquisitionError("retained STM32L1 by-subfamily evidence missing")
    observed: dict[str, dict[str, list[str]]] = {}
    total_active = 0
    total_excluded = 0
    for subfamily, base in EXPECTED_TARGETS:
        item = by_subfamily.get(subfamily)
        if not isinstance(item, dict):
            raise AcquisitionError(f"{subfamily}: retained lifecycle evidence missing")
        active = item.get("active_exact_icpns")
        excluded = item.get("excluded_non_active_icpns")
        if active != EXPECTED_ACTIVE[subfamily] or excluded != EXPECTED_EXCLUDED[subfamily]:
            raise AcquisitionError(f"{subfamily}: exact lifecycle evidence drifted")
        if any(not icpn.startswith(base) for icpn in active + excluded):
            raise AcquisitionError(f"{subfamily}: exact identity escaped representative Base Device")
        observed[subfamily] = {"active": active, "excluded": excluded}
        total_active += len(active)
        total_excluded += len(excluded)
    if total_active != EXPECTED_REPRESENTATIVE_EXACT_ICPNS or total_excluded != EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS:
        raise AcquisitionError("STM32L1 retained exact lifecycle aggregates drifted")
    return observed


def validate_ordering_authority(path: Path = DEFAULT_ORDERING) -> dict[str, Any]:
    _require_blob(path, EXPECTED_ORDERING_AUTHORITY_BLOB, "STM32L1 Ordering Information authority")
    payload = _read_json(path)
    _all_false(payload.get("claims"), "Ordering Information claims")
    if payload.get("authority") != "official_st_datasheet_ordering_information":
        raise AcquisitionError("STM32L1 Ordering Information authority drifted")
    coverage = payload.get("coverage")
    if not isinstance(coverage, dict):
        raise AcquisitionError("STM32L1 Ordering Information coverage missing")
    expected = list(EXPECTED_SUBFAMILIES)
    if coverage.get("required_subfamilies") != expected or coverage.get("covered_subfamilies") != expected:
        raise AcquisitionError("STM32L1 Ordering Information subfamily coverage drifted")
    if coverage.get("coverage_complete") is not True:
        raise AcquisitionError("STM32L1 Ordering Information coverage incomplete")
    sources = payload.get("ordering_sources")
    if not isinstance(sources, list) or len(sources) != EXPECTED_ORDERING_SOURCE_COUNT:
        raise AcquisitionError("STM32L1 Ordering Information source count drifted")
    covered: set[str] = set()
    for source in sources:
        if not isinstance(source, dict) or source.get("ordering_information_present") is not True:
            raise AcquisitionError("STM32L1 Ordering Information source is incomplete")
        url = source.get("source_url")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/"):
            raise AcquisitionError("STM32L1 Ordering Information source is not official ST")
        for subfamily in source.get("subfamilies", []):
            if not isinstance(subfamily, str):
                raise AcquisitionError("malformed STM32L1 Ordering Information coverage")
            covered.add(subfamily)
    if covered != set(EXPECTED_SUBFAMILIES):
        raise AcquisitionError("STM32L1 Ordering Information source coverage drifted")
    migration = payload.get("migration_authority")
    if not isinstance(migration, dict) or migration.get("document") != "TN1176":
        raise AcquisitionError("STM32L1 generation migration authority drifted")
    if not str(migration.get("source_url", "")).startswith("https://www.st.com/"):
        raise AcquisitionError("STM32L1 migration authority is not official ST")
    return payload


def validate_production_prestate(path: Path = FROZEN_PRODUCTION_PRESTATE) -> dict[str, Any]:
    _require_blob(path, EXPECTED_PRODUCTION_PRESTATE_BLOB, "post-L4 Production prestate")
    payload = _read_json(path)
    if payload.get("status") != "production":
        raise AcquisitionError("post-L4 prestate is not Production")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise AcquisitionError("post-L4 Production sources missing")
    counts = {item.get("family"): item.get("row_count") for item in sources if isinstance(item, dict)}
    if len(counts) != 12 or sum(value for value in counts.values() if isinstance(value, int)) != 1718:
        raise AcquisitionError("post-L4 Production aggregate drifted")
    if counts.get("STM32L4") != 446:
        raise AcquisitionError("post-L4 STM32L4 Production count drifted")
    if FAMILY in counts:
        raise AcquisitionError("STM32L1 unexpectedly exists in frozen Production prestate")
    return payload


def build_foundation_report(catalog_rows: list[dict[str, str]] | None = None) -> dict[str, Any]:
    rows = read_catalog() if catalog_rows is None else catalog_rows
    guarded_rows(rows)
    requalification = validate_requalification_result()
    validate_target_manifest()
    validate_retained_identity()
    validate_ordering_authority()
    validate_production_prestate()
    targets = deterministic_initial_targets(rows)
    production = requalification["production"]
    if production != {"exact_icpn_count": 1718, "base_device_count": 530, "family_count": 12, "stm32l1_exact_icpn_count": 0}:
        raise AcquisitionError("STM32L1 L1.1 Production boundary drifted")
    return {
        "claims": {
            "canonical_admission_authorized": False,
            "complete_family_inventory_claimed": False,
            "exact_icpn_publication_authorized": False,
            "flash_geometry_qualified": False,
            "manufacturer_evidence_is_admission": False,
            "option_security_semantics_qualified": False,
            "physical_hil_qualified": False,
            "production_write_authorized": False,
            "programming_algorithm_equivalence": False,
            "programming_policy_defined": False,
            "runtime_programming_support_claimed": False,
        },
        "evidence_foundation": {
            "active_exact_icpns_observed": EXPECTED_REPRESENTATIVE_EXACT_ICPNS,
            "excluded_non_active_part_numbers_observed": EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS,
            "generation_migration_authority": "TN1176",
            "openocd_catalog_sha256": EXPECTED_OPENOCD_CATALOG_SHA256,
            "ordering_authority_git_blob": EXPECTED_ORDERING_AUTHORITY_BLOB,
            "ordering_source_count": EXPECTED_ORDERING_SOURCE_COUNT,
            "production_manifest_prestate_git_blob": EXPECTED_PRODUCTION_PRESTATE_BLOB,
            "representative_count": len(EXPECTED_TARGETS),
            "requalification_result_git_blob": EXPECTED_REQUALIFICATION_RESULT_BLOB,
            "retained_probe_summary_git_blob": EXPECTED_RETAINED_SUMMARY_BLOB,
            "scope": "representative_evidence_only_not_complete_family_inventory",
            "target_manifest_git_blob": EXPECTED_TARGET_MANIFEST_BLOB,
        },
        "family": FAMILY,
        "identifier_kind_counts": {
            "cmsis_device_name": EXPECTED_CMSIS_COUNT,
            "ordering_pattern": EXPECTED_ORDERING_COUNT,
        },
        "initial_targets": [
            {"base_device": base, "subfamily": subfamily}
            for subfamily, base in targets
        ],
        "phase": PHASE,
        "schema_version": 1,
        "scope": "bounded_research_foundation_only",
        "source_row_count": EXPECTED_ROW_COUNT,
        "subfamilies": list(EXPECTED_SUBFAMILIES),
        "target_config": TARGET_CONFIG,
    }


def validate_baseline(path: Path = DEFAULT_BASELINE) -> dict[str, Any]:
    baseline = _read_json(path)
    observed = build_foundation_report()
    if observed != baseline:
        raise AcquisitionError("STM32L1 L1.1 baseline no longer matches deterministic replay")
    return baseline


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    report = build_foundation_report()
    if args.check:
        baseline = _read_json(DEFAULT_BASELINE)
        if report != baseline:
            raise AcquisitionError("STM32L1 L1.1 deterministic replay differs from frozen baseline")
        print("STM32L1 L1.1 deterministic baseline replay: PASS")
        return 0
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

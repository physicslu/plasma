#!/usr/bin/env python3
"""Fail-closed STM32L4 Phase L4.1 bounded research foundation.

L4.1 freezes the selected STM32L4 OpenOCD-derived research surface and binds
the 24 deterministic representatives to retained official-ST identity/lifecycle
and Ordering Information evidence.

This is research foundation only. Representative exact ICPNs are evidence for
sampled Base Devices and are not a complete STM32L4 commercial inventory.
Nothing here authorizes canonical admission, Production writes, programming
policy, Flash/security qualification, HIL, electrical/socket, or runtime
support.
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

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_SELECTION = HERE / "stm32-post-l0-next-family-selection.json"
DEFAULT_TARGET_MANIFEST = HERE / "evidence" / "stm32-l1-l0-l4-post-c0-live-2026-09-12" / "targets.json"
DEFAULT_RETAINED_SUMMARY = HERE / "evidence" / "stm32-l1-l0-l4-post-c0-live-2026-09-12" / "probe-summary.json"
DEFAULT_ORDERING_REVIEW = HERE / "stm32-l0-l4-post-c0-ordering-authority-review.json"
DEFAULT_PRODUCTION_PRESTATE = HERE / "stm32-post-l0-production-manifest-prestate.json"
DEFAULT_BASELINE = HERE / "stm32l4-phase-l4.1-foundation-baseline.json"

PHASE = "L4.1"
FAMILY = "STM32L4"
MANUFACTURER = "STMicroelectronics"
TARGET_CONFIG = "tcl/target/stm32l4x.cfg"

EXPECTED_ROW_COUNT = 255
EXPECTED_ORDERING_COUNT = 207
EXPECTED_CMSIS_COUNT = 48
EXPECTED_REPRESENTATIVE_EXACT_ICPNS = 60
EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS = 3
EXPECTED_UNIQUE_OFFICIAL_DATASHEETS = 20

EXPECTED_SUBFAMILIES = (
    "STM32L412", "STM32L422", "STM32L431", "STM32L432",
    "STM32L433", "STM32L442", "STM32L443", "STM32L451",
    "STM32L452", "STM32L462", "STM32L471", "STM32L475",
    "STM32L476", "STM32L486", "STM32L496", "STM32L4A6",
    "STM32L4P5", "STM32L4Q5", "STM32L4R5", "STM32L4R7",
    "STM32L4R9", "STM32L4S5", "STM32L4S7", "STM32L4S9",
)
EXPECTED_TARGETS = (
    ("STM32L412", "STM32L412C8"),
    ("STM32L422", "STM32L422CB"),
    ("STM32L431", "STM32L431CB"),
    ("STM32L432", "STM32L432KB"),
    ("STM32L433", "STM32L433CB"),
    ("STM32L442", "STM32L442KC"),
    ("STM32L443", "STM32L443CC"),
    ("STM32L451", "STM32L451CC"),
    ("STM32L452", "STM32L452CC"),
    ("STM32L462", "STM32L462CE"),
    ("STM32L471", "STM32L471QE"),
    ("STM32L475", "STM32L475RC"),
    ("STM32L476", "STM32L476JE"),
    ("STM32L486", "STM32L486JG"),
    ("STM32L496", "STM32L496AE"),
    ("STM32L4A6", "STM32L4A6AG"),
    ("STM32L4P5", "STM32L4P5AE"),
    ("STM32L4Q5", "STM32L4Q5AG"),
    ("STM32L4R5", "STM32L4R5AG"),
    ("STM32L4R7", "STM32L4R7AI"),
    ("STM32L4R9", "STM32L4R9AG"),
    ("STM32L4S5", "STM32L4S5AI"),
    ("STM32L4S7", "STM32L4S7AI"),
    ("STM32L4S9", "STM32L4S9AI"),
)

EXPECTED_OPENOCD_CATALOG_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_SELECTION_SHA256 = "70dd86816606e94380fe6a0b0474a88771542607fc7db2aaa3a8be65e1e2e7b8"
EXPECTED_TARGET_MANIFEST_SHA256 = "767ad681a7d8e839cbf68b507babb2c417905a2f40a380566e773fa987ab9434"
EXPECTED_RETAINED_SUMMARY_SHA256 = "45c3020462601e6cb36e726cc1acc4203abc36a96063a5223ab5c7511bcff02c"
EXPECTED_ORDERING_REVIEW_SHA256 = "d16e71cb322c7da754ed12cc1bd0e984015888cbf8bdb07685e1d87966ad8612"
EXPECTED_PRODUCTION_PRESTATE_SHA256 = "c435551f65cede76356ba45fa8523259d6201c2cc673c05ccf214a888beeefec"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _require_sha256(path: Path, expected: str, label: str) -> None:
    observed = _sha256(path)
    if observed != expected:
        raise AcquisitionError(f"{label} SHA-256 drifted: {observed}")


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
    _require_sha256(path, EXPECTED_OPENOCD_CATALOG_SHA256, "OpenOCD canonical catalog")
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def guarded_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = [
        row for row in catalog_rows
        if row.get("vendor") == MANUFACTURER and row.get("plasma_series") == FAMILY
    ]
    if len(rows) != EXPECTED_ROW_COUNT:
        raise AcquisitionError(f"{PHASE} requires {EXPECTED_ROW_COUNT} STM32L4 rows, got {len(rows)}")
    kinds = Counter(row.get("identifier_kind", "") for row in rows)
    wanted = Counter({
        "ordering_pattern": EXPECTED_ORDERING_COUNT,
        "cmsis_device_name": EXPECTED_CMSIS_COUNT,
    })
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


def validate_selection(path: Path = DEFAULT_SELECTION) -> dict[str, Any]:
    _require_sha256(path, EXPECTED_SELECTION_SHA256, "post-L0 next-family selection")
    payload = _read_json(path)
    if payload.get("selection_id") != "stm32-post-l0-next-family-selection-v1":
        raise AcquisitionError("unexpected post-L0 selection artifact")
    if payload.get("selected_next_research_family") != FAMILY:
        raise AcquisitionError("STM32L4 is no longer the frozen selected family")
    if payload.get("scope") != "next_family_research_only":
        raise AcquisitionError("selection scope escaped research-only boundary")
    _all_false(payload.get("authority_boundaries"), "selection authority boundaries")
    l4 = (payload.get("candidate_evidence") or {}).get(FAMILY)
    expected = {
        "representative_targets": 24,
        "verified_identity_targets": 24,
        "active_candidate_targets": 24,
        "lifecycle_excluded_targets": 0,
        "source_unavailable_404": 0,
        "manual_review": 0,
        "active_exact_icpns_observed": 60,
        "excluded_non_active_part_numbers": 3,
        "commercial_identity_access_clean": True,
        "rejected_for_future_support": False,
    }
    if not isinstance(l4, dict) or any(l4.get(key) != value for key, value in expected.items()):
        raise AcquisitionError("frozen STM32L4 selection evidence drifted")
    return payload


def validate_target_manifest(path: Path = DEFAULT_TARGET_MANIFEST) -> dict[str, str]:
    _require_sha256(path, EXPECTED_TARGET_MANIFEST_SHA256, "post-C0 target manifest")
    payload = _read_json(path)
    _all_false(payload.get("claims"), "target manifest claims")
    if payload.get("target_count") != 44:
        raise AcquisitionError("post-C0 target manifest count drifted")
    targets = payload.get("targets")
    if not isinstance(targets, list):
        raise AcquisitionError("target manifest targets must be a list")
    observed = {
        item.get("subfamily"): item.get("base_device")
        for item in targets
        if isinstance(item, dict) and item.get("series") == FAMILY
    }
    expected = {subfamily: base for subfamily, base in EXPECTED_TARGETS}
    if observed != expected:
        raise AcquisitionError(f"STM32L4 target manifest drifted: {observed}")
    return observed


def validate_retained_identity(path: Path = DEFAULT_RETAINED_SUMMARY) -> dict[str, dict[str, Any]]:
    _require_sha256(path, EXPECTED_RETAINED_SUMMARY_SHA256, "retained post-C0 evidence")
    payload = _read_json(path)
    _all_false(payload.get("claims"), "retained evidence claims")
    by_series = payload.get("by_series")
    if not isinstance(by_series, dict) or not isinstance(by_series.get(FAMILY), dict):
        raise AcquisitionError("retained evidence missing STM32L4 summary")
    l4 = by_series[FAMILY]
    expected = {
        "attempted_targets": 24,
        "verified_identity_targets": 24,
        "active_candidate_targets": 24,
        "lifecycle_excluded_targets": 0,
        "source_unavailable_404": 0,
        "manual_review": 0,
        "active_exact_icpns": 60,
        "excluded_non_active_part_numbers": 3,
        "commercial_identity_access_clean": True,
    }
    if any(l4.get(key) != value for key, value in expected.items()):
        raise AcquisitionError("retained STM32L4 evidence summary drifted")
    results = payload.get("results")
    if not isinstance(results, list):
        raise AcquisitionError("retained evidence results must be a list")
    expected_bases = {base for _, base in EXPECTED_TARGETS}
    observed: dict[str, dict[str, Any]] = {}
    total_exact = 0
    total_excluded = 0
    for result in results:
        if not isinstance(result, dict) or result.get("series") != FAMILY:
            continue
        base = result.get("base_device")
        if not isinstance(base, str) or base not in expected_bases or base in observed:
            raise AcquisitionError(f"unexpected/duplicate retained STM32L4 target: {base}")
        if result.get("acquisition_status") != "success":
            raise AcquisitionError(f"{base}: acquisition status drifted")
        if result.get("commercial_identity_status") != "verified_active" or result.get("disposition") != "active_candidates":
            raise AcquisitionError(f"{base}: retained identity/lifecycle drifted")
        source = result.get("source_url")
        if not isinstance(source, str) or not source.startswith("https://www.st.com/en/microcontrollers-microprocessors/"):
            raise AcquisitionError(f"{base}: non-official source URL")
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise AcquisitionError(f"{base}: nested evidence missing")
        if evidence.get("evidence_surface") != "quality_and_reliability_identity_plus_sample_and_buy_lifecycle":
            raise AcquisitionError(f"{base}: commercial evidence surface drifted")
        exact = evidence.get("exact_icpns")
        excluded = evidence.get("excluded_non_active_part_numbers")
        records = evidence.get("part_number_records")
        if not isinstance(exact, list) or not exact or not isinstance(excluded, list):
            raise AcquisitionError(f"{base}: exact lifecycle disposition drifted")
        if any(not isinstance(icpn, str) or not icpn.startswith(base) for icpn in exact):
            raise AcquisitionError(f"{base}: retained exact ICPN escaped Base Device")
        excluded_ids: list[str] = []
        for item in excluded:
            if not isinstance(item, dict):
                raise AcquisitionError(f"{base}: lifecycle exclusion must be an object")
            icpn = item.get("icpn")
            status = item.get("marketing_status")
            if not isinstance(icpn, str) or not icpn.startswith(base):
                raise AcquisitionError(f"{base}: invalid lifecycle-excluded ICPN")
            if not isinstance(status, str) or not status.strip():
                raise AcquisitionError(f"{base}: lifecycle exclusion lacks Marketing Status")
            excluded_ids.append(icpn)
        if not isinstance(records, list):
            raise AcquisitionError(f"{base}: exact identity records missing")
        record_ids = [row.get("icpn") for row in records if isinstance(row, dict)]
        if len(record_ids) != len(set(record_ids)):
            raise AcquisitionError(f"{base}: duplicate exact identity records")
        if set(record_ids) != set(exact) | set(excluded_ids):
            raise AcquisitionError(f"{base}: exact identity/lifecycle join drifted")
        observed[base] = result
        total_exact += len(exact)
        total_excluded += len(excluded_ids)
    if set(observed) != expected_bases:
        raise AcquisitionError("retained STM32L4 representative set drifted")
    if total_exact != EXPECTED_REPRESENTATIVE_EXACT_ICPNS:
        raise AcquisitionError("retained STM32L4 active exact ICPN aggregate drifted")
    if total_excluded != EXPECTED_EXCLUDED_NON_ACTIVE_ICPNS:
        raise AcquisitionError("retained STM32L4 excluded exact ICPN aggregate drifted")
    return observed


def validate_ordering_authority(path: Path = DEFAULT_ORDERING_REVIEW) -> dict[str, dict[str, Any]]:
    _require_sha256(path, EXPECTED_ORDERING_REVIEW_SHA256, "post-C0 L0/L4 Ordering review")
    payload = _read_json(path)
    _all_false(payload.get("claims"), "Ordering review claims")
    method = payload.get("method")
    if not isinstance(method, dict) or method.get("authority") != "official_st_datasheet":
        raise AcquisitionError("STM32L4 Ordering authority is no longer official ST")
    summary = (payload.get("by_series") or {}).get(FAMILY)
    expected_summary = {
        "representative_targets": 24,
        "unique_official_datasheets": 20,
        "ordering_authority_covered_targets": 24,
        "required_schema_complete_targets": 24,
        "blocking_evidence_issues": 0,
        "ordering_evidence_quality": "complete",
        "revision_drift": False,
    }
    if not isinstance(summary, dict) or any(summary.get(key) != value for key, value in expected_summary.items()):
        raise AcquisitionError("STM32L4 Ordering Information summary drifted")
    authorities = payload.get("l4_authorities")
    if not isinstance(authorities, list):
        raise AcquisitionError("STM32L4 Ordering authorities missing")
    expected_bases = {base for _, base in EXPECTED_TARGETS}
    by_target: dict[str, dict[str, Any]] = {}
    datasheets: set[str] = set()
    for authority in authorities:
        if not isinstance(authority, dict):
            raise AcquisitionError("STM32L4 Ordering authority row must be an object")
        datasheet = authority.get("datasheet_id")
        url = authority.get("url")
        covered = authority.get("covered_targets")
        if not isinstance(datasheet, str) or not datasheet.startswith("DS"):
            raise AcquisitionError("STM32L4 Ordering authority lacks datasheet ID")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/resource/en/datasheet/"):
            raise AcquisitionError(f"{datasheet}: non-official Ordering authority URL")
        if authority.get("required_fields_complete") is not True:
            raise AcquisitionError(f"{datasheet}: Ordering schema incomplete")
        if not isinstance(covered, list) or not covered:
            raise AcquisitionError(f"{datasheet}: no covered targets")
        datasheets.add(datasheet)
        for base in covered:
            if not isinstance(base, str) or base not in expected_bases or base in by_target:
                raise AcquisitionError(f"{datasheet}: unexpected/duplicate covered target {base}")
            by_target[base] = authority
    if set(by_target) != expected_bases:
        raise AcquisitionError("STM32L4 Ordering target coverage drifted")
    if len(datasheets) != EXPECTED_UNIQUE_OFFICIAL_DATASHEETS:
        raise AcquisitionError("STM32L4 unique official datasheet count drifted")
    l462_semantics = by_target["STM32L462CE"].get("special_semantics")
    if not isinstance(l462_semantics, list) or not any("lifecycle" in item.lower() for item in l462_semantics if isinstance(item, str)):
        raise AcquisitionError("STM32L462 lifecycle semantics disappeared")
    return by_target


def validate_production_prestate(path: Path = DEFAULT_PRODUCTION_PRESTATE) -> dict[str, Any]:
    _require_sha256(path, EXPECTED_PRODUCTION_PRESTATE_SHA256, "post-L0 Production prestate")
    payload = _read_json(path)
    if payload.get("status") != "production":
        raise AcquisitionError("post-L0 prestate is not Production")
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise AcquisitionError("post-L0 Production prestate sources missing")
    counts: dict[str, int] = {}
    for item in sources:
        if not isinstance(item, dict):
            raise AcquisitionError("post-L0 Production source row malformed")
        family = item.get("family")
        count = item.get("row_count")
        if not isinstance(family, str) or not isinstance(count, int):
            raise AcquisitionError("post-L0 Production source family/count malformed")
        counts[family] = count
    if sum(counts.values()) != 1272 or len(counts) != 11:
        raise AcquisitionError("post-L0 Production aggregate drifted")
    if counts.get("STM32L0") != 360:
        raise AcquisitionError("post-L0 STM32L0 Production count drifted")
    if FAMILY in counts:
        raise AcquisitionError("STM32L4 unexpectedly exists in frozen Production prestate")
    return payload


def build_foundation_report(catalog_rows: list[dict[str, str]] | None = None) -> dict[str, Any]:
    rows = read_catalog() if catalog_rows is None else catalog_rows
    guarded_rows(rows)
    validate_selection()
    validate_target_manifest()
    validate_retained_identity()
    validate_ordering_authority()
    validate_production_prestate()
    targets = deterministic_initial_targets(rows)
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
            "openocd_catalog_sha256": EXPECTED_OPENOCD_CATALOG_SHA256,
            "ordering_review_sha256": EXPECTED_ORDERING_REVIEW_SHA256,
            "production_manifest_prestate_sha256": EXPECTED_PRODUCTION_PRESTATE_SHA256,
            "representative_count": len(EXPECTED_TARGETS),
            "retained_probe_summary_sha256": EXPECTED_RETAINED_SUMMARY_SHA256,
            "scope": "representative_evidence_only_not_complete_family_inventory",
            "selection_sha256": EXPECTED_SELECTION_SHA256,
            "target_manifest_sha256": EXPECTED_TARGET_MANIFEST_SHA256,
            "unique_official_datasheets": EXPECTED_UNIQUE_OFFICIAL_DATASHEETS,
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
        raise AcquisitionError("STM32L4 L4.1 baseline no longer matches deterministic replay")
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
            raise AcquisitionError("STM32L4 L4.1 deterministic replay differs from frozen baseline")
        print("STM32L4 L4.1 deterministic baseline replay: PASS")
        return 0
    payload = json.dumps(report, indent=2) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

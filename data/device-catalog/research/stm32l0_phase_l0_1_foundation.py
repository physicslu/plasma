#!/usr/bin/env python3
"""Fail-closed STM32L0 Phase L0.1 bounded research foundation.

L0.1 freezes the already-selected STM32L0 OpenOCD-derived research surface and
binds the 16 deterministic representatives to retained official-ST
identity/lifecycle and Ordering Information evidence.

This is research foundation only. Representative exact ICPNs are evidence for
the 16 sampled Base Devices and are not a complete STM32L0 commercial
inventory. Nothing here authorizes canonical admission, Production writes,
programming-policy equivalence, Flash/security qualification, HIL, electrical
or runtime support.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from st_product_page_acquisition import AcquisitionError

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_SELECTION = HERE / "stm32-post-c0-next-family-selection.json"
DEFAULT_TARGET_MANIFEST = HERE / "evidence" / "stm32-l1-l0-l4-post-c0-live-2026-09-12" / "targets.json"
DEFAULT_RETAINED_SUMMARY = HERE / "evidence" / "stm32-l1-l0-l4-post-c0-live-2026-09-12" / "probe-summary.json"
DEFAULT_ORDERING_COMPARISON = HERE / "stm32-l0-l4-post-c0-ordering-authority-review.json"
DEFAULT_L0_ORDERING_REVIEW = HERE / "stm32-c0-l0-post-u0-ordering-authority-review.json"
DEFAULT_PRODUCTION_PRESTATE = HERE / "stm32-post-c0-production-manifest-prestate.json"
DEFAULT_BASELINE = HERE / "stm32l0-phase-l0.1-foundation-baseline.json"

PHASE = "L0.1"
FAMILY = "STM32L0"
MANUFACTURER = "STMicroelectronics"
TARGET_CONFIG = "tcl/target/stm32l0.cfg"
EXPECTED_ROW_COUNT = 166
EXPECTED_ORDERING_COUNT = 164
EXPECTED_CMSIS_COUNT = 2
EXPECTED_REPRESENTATIVE_EXACT_ICPNS = 44
EXPECTED_SUBFAMILIES = (
    "STM32L010", "STM32L011", "STM32L021", "STM32L031",
    "STM32L041", "STM32L051", "STM32L052", "STM32L053",
    "STM32L062", "STM32L063", "STM32L071", "STM32L072",
    "STM32L073", "STM32L081", "STM32L082", "STM32L083",
)
EXPECTED_TARGETS = (
    ("STM32L010", "STM32L010C6"), ("STM32L011", "STM32L011D3"),
    ("STM32L021", "STM32L021D4"), ("STM32L031", "STM32L031C4"),
    ("STM32L041", "STM32L041C6"), ("STM32L051", "STM32L051C6"),
    ("STM32L052", "STM32L052C6"), ("STM32L053", "STM32L053C6"),
    ("STM32L062", "STM32L062C8"), ("STM32L063", "STM32L063C8"),
    ("STM32L071", "STM32L071C8"), ("STM32L072", "STM32L072CB"),
    ("STM32L073", "STM32L073CB"), ("STM32L081", "STM32L081CB"),
    ("STM32L082", "STM32L082CZ"), ("STM32L083", "STM32L083CB"),
)

EXPECTED_OPENOCD_CATALOG_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_SELECTION_SHA256 = "a46cef39516bf94901b979ccfc446b5720b2c6855b46ede1765232f6082df134"
EXPECTED_TARGET_MANIFEST_SHA256 = "767ad681a7d8e839cbf68b507babb2c417905a2f40a380566e773fa987ab9434"
EXPECTED_RETAINED_SUMMARY_SHA256 = "45c3020462601e6cb36e726cc1acc4203abc36a96063a5223ab5c7511bcff02c"
EXPECTED_ORDERING_COMPARISON_SHA256 = "d16e71cb322c7da754ed12cc1bd0e984015888cbf8bdb07685e1d87966ad8612"
EXPECTED_L0_ORDERING_REVIEW_SHA256 = "9f4bde47508100025d3d6e92813f244431a18d95cf3fc73a45de93849dddd38d"
EXPECTED_PRODUCTION_PRESTATE_SHA256 = "15f9c9a9be8640bc0664b562c667f676d0084e4c157e01f582c87a10886c5420"
EXPECTED_L0_ORDERING_REVIEW_GIT_BLOB = "ecf16ec5fa414fb82f7c4e4d28b10a26edf95cd9"
ORDERING_PATTERN_RE = re.compile(r"^(STM32L0[A-Z0-9]+)([A-Z])x$")


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


def base_from_row(row: dict[str, str]) -> str:
    if row.get("identifier_kind") != "ordering_pattern":
        raise AcquisitionError("commercial research selection requires ordering_pattern rows")
    part = row.get("part_number", "")
    match = ORDERING_PATTERN_RE.fullmatch(part)
    if match is None:
        raise AcquisitionError(f"unsupported STM32L0 ordering pattern: {part!r}")
    base = match.group(1)
    subfamily = row.get("subfamily", "")
    if not base.startswith(subfamily) or len(base) != len(subfamily) + 2:
        raise AcquisitionError(f"{part}: invalid concrete STM32L0 Base Device {base!r}")
    return base


def guarded_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = [row for row in catalog_rows if row.get("vendor") == MANUFACTURER and row.get("plasma_series") == FAMILY]
    if len(rows) != EXPECTED_ROW_COUNT:
        raise AcquisitionError(f"{PHASE} requires {EXPECTED_ROW_COUNT} STM32L0 rows, got {len(rows)}")
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
            base_from_row(row)
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
        by_subfamily[row["subfamily"]].add(base_from_row(row))
    targets = [(subfamily, min(by_subfamily[subfamily])) for subfamily in EXPECTED_SUBFAMILIES]
    if tuple(targets) != EXPECTED_TARGETS:
        raise AcquisitionError(f"{PHASE} deterministic targets drifted: {targets}")
    return targets


def validate_selection(path: Path = DEFAULT_SELECTION) -> dict[str, Any]:
    _require_sha256(path, EXPECTED_SELECTION_SHA256, "post-C0 next-family selection")
    payload = _read_json(path)
    if payload.get("selection_id") != "stm32-post-c0-next-family-selection-v1":
        raise AcquisitionError("unexpected post-C0 selection artifact")
    if payload.get("selected_next_research_family") != FAMILY:
        raise AcquisitionError("STM32L0 is no longer the frozen selected family")
    if payload.get("scope") != "next_family_research_only":
        raise AcquisitionError("selection scope escaped research-only boundary")
    _all_false(payload.get("authority_boundaries"), "selection authority boundaries")
    l0 = (payload.get("candidate_evidence") or {}).get(FAMILY)
    expected = {
        "representative_targets": 16, "verified_identity_targets": 16,
        "active_candidate_targets": 16, "lifecycle_excluded_targets": 0,
        "manual_review": 0, "active_exact_icpns_observed": 44,
        "commercial_identity_access_clean": True,
    }
    if not isinstance(l0, dict) or any(l0.get(key) != value for key, value in expected.items()):
        raise AcquisitionError("frozen STM32L0 selection evidence drifted")
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
    observed = {item.get("subfamily"): item.get("base_device") for item in targets if isinstance(item, dict) and item.get("series") == FAMILY}
    expected = {subfamily: base for subfamily, base in EXPECTED_TARGETS}
    if observed != expected:
        raise AcquisitionError(f"STM32L0 target manifest drifted: {observed}")
    return observed


def validate_retained_identity(path: Path = DEFAULT_RETAINED_SUMMARY) -> dict[str, dict[str, Any]]:
    _require_sha256(path, EXPECTED_RETAINED_SUMMARY_SHA256, "retained post-C0 evidence")
    payload = _read_json(path)
    _all_false(payload.get("claims"), "retained evidence claims")
    by_series = payload.get("by_series")
    if not isinstance(by_series, dict) or not isinstance(by_series.get(FAMILY), dict):
        raise AcquisitionError("retained evidence missing STM32L0 summary")
    l0 = by_series[FAMILY]
    expected = {
        "attempted_targets": 16, "verified_identity_targets": 16,
        "active_candidate_targets": 16, "lifecycle_excluded_targets": 0,
        "source_unavailable_404": 0, "manual_review": 0,
        "active_exact_icpns": 44, "commercial_identity_access_clean": True,
    }
    if any(l0.get(key) != value for key, value in expected.items()):
        raise AcquisitionError("retained STM32L0 evidence summary drifted")
    results = payload.get("results")
    if not isinstance(results, list):
        raise AcquisitionError("retained evidence results must be a list")
    expected_bases = {base for _, base in EXPECTED_TARGETS}
    observed: dict[str, dict[str, Any]] = {}
    total_exact = 0
    for result in results:
        if not isinstance(result, dict) or result.get("series") != FAMILY:
            continue
        base = result.get("base_device")
        if not isinstance(base, str) or base not in expected_bases or base in observed:
            raise AcquisitionError(f"unexpected/duplicate retained STM32L0 target: {base}")
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
        if not isinstance(exact, list) or not exact or not isinstance(excluded, list) or excluded:
            raise AcquisitionError(f"{base}: STM32L0 exact lifecycle disposition drifted")
        if any(not isinstance(icpn, str) or not icpn.startswith(base) for icpn in exact):
            raise AcquisitionError(f"{base}: retained exact ICPN escaped Base Device")
        if not isinstance(records, list):
            raise AcquisitionError(f"{base}: exact identity records missing")
        record_ids = [row.get("icpn") for row in records if isinstance(row, dict)]
        if len(record_ids) != len(set(record_ids)) or set(record_ids) != set(exact):
            raise AcquisitionError(f"{base}: exact identity/lifecycle join drifted")
        observed[base] = result
        total_exact += len(exact)
    if set(observed) != expected_bases or total_exact != EXPECTED_REPRESENTATIVE_EXACT_ICPNS:
        raise AcquisitionError("retained STM32L0 representative set/aggregate drifted")
    return observed


def validate_ordering_authority(comparison_path: Path = DEFAULT_ORDERING_COMPARISON, detail_path: Path = DEFAULT_L0_ORDERING_REVIEW) -> dict[str, dict[str, Any]]:
    _require_sha256(comparison_path, EXPECTED_ORDERING_COMPARISON_SHA256, "post-C0 Ordering comparison")
    comparison = _read_json(comparison_path)
    _all_false(comparison.get("claims"), "post-C0 Ordering comparison claims")
    method = comparison.get("method")
    if not isinstance(method, dict) or method.get("authority") != "official_st_datasheet":
        raise AcquisitionError("Ordering Information authority is no longer official ST")
    l0_summary = (comparison.get("by_series") or {}).get(FAMILY)
    expected_summary = {
        "representative_targets": 16, "unique_official_datasheets": 16,
        "ordering_authority_covered_targets": 16, "required_schema_complete_targets": 16,
        "blocking_evidence_issues": 0, "ordering_evidence_quality": "complete",
        "revision_drift": False,
    }
    if not isinstance(l0_summary, dict) or any(l0_summary.get(key) != value for key, value in expected_summary.items()):
        raise AcquisitionError("post-C0 STM32L0 Ordering Information continuity drifted")
    if l0_summary.get("prior_review") != DEFAULT_L0_ORDERING_REVIEW.name:
        raise AcquisitionError("post-C0 STM32L0 prior Ordering authority changed")
    if l0_summary.get("prior_review_git_blob_sha") != EXPECTED_L0_ORDERING_REVIEW_GIT_BLOB:
        raise AcquisitionError("post-C0 STM32L0 prior Ordering blob drifted")
    _require_sha256(detail_path, EXPECTED_L0_ORDERING_REVIEW_SHA256, "STM32L0 detailed Ordering review")
    detail = _read_json(detail_path)
    _all_false(detail.get("claims"), "STM32L0 detailed Ordering review claims")
    detail_method = detail.get("method")
    if not isinstance(detail_method, dict) or detail_method.get("authority") != "official_st_datasheet":
        raise AcquisitionError("detailed STM32L0 Ordering authority is no longer official ST")
    detail_summary = (detail.get("by_series") or {}).get(FAMILY)
    if not isinstance(detail_summary, dict) or any(detail_summary.get(key) != value for key, value in expected_summary.items()):
        raise AcquisitionError("detailed STM32L0 Ordering summary drifted")
    entries = detail.get("l0_targets")
    if not isinstance(entries, list) or len(entries) != 16:
        raise AcquisitionError("STM32L0 Ordering authority target count drifted")
    expected = {base: subfamily for subfamily, base in EXPECTED_TARGETS}
    observed: dict[str, dict[str, Any]] = {}
    for item in entries:
        if not isinstance(item, dict):
            raise AcquisitionError("STM32L0 Ordering authority row must be an object")
        base = item.get("base_device")
        if not isinstance(base, str) or base not in expected or base in observed:
            raise AcquisitionError(f"unexpected/duplicate STM32L0 Ordering target: {base}")
        if item.get("subfamily") != expected[base] or item.get("required_fields_complete") is not True:
            raise AcquisitionError(f"{base}: Ordering authority semantics drifted")
        url = item.get("datasheet_url")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/resource/en/datasheet/"):
            raise AcquisitionError(f"{base}: Ordering authority URL is not official ST")
        if not isinstance(item.get("datasheet_id"), str) or not isinstance(item.get("revision"), int) or not isinstance(item.get("ordering_pdf_page"), int):
            raise AcquisitionError(f"{base}: incomplete Ordering authority locator")
        observed[base] = item
    if set(observed) != set(expected):
        raise AcquisitionError("STM32L0 Ordering authority coverage drifted")
    if not any("narrow grammar" in text for text in observed["STM32L010C6"].get("special_semantics", [])):
        raise AcquisitionError("STM32L010 narrow Ordering grammar semantic drifted")
    if not any("UFQFPN28" in text and "one-power-pair" in text for text in observed["STM32L031C4"].get("special_semantics", [])):
        raise AcquisitionError("STM32L031 S-option semantic drifted")
    return observed


def validate_production_prestate(path: Path = DEFAULT_PRODUCTION_PRESTATE) -> dict[str, Any]:
    _require_sha256(path, EXPECTED_PRODUCTION_PRESTATE_SHA256, "immutable post-C0 Production prestate")
    payload = _read_json(path)
    if payload.get("status") != "production" or payload.get("selection_policy") != "admitted_exact_manufacturer_part_number_only":
        raise AcquisitionError("immutable Production prestate contract drifted")
    sources = payload.get("sources")
    if not isinstance(sources, list) or len(sources) != 10:
        raise AcquisitionError("immutable Production family count drifted")
    counts = {item.get("family"): item.get("row_count") for item in sources if isinstance(item, dict)}
    if sum(value for value in counts.values() if isinstance(value, int)) != 912:
        raise AcquisitionError("immutable Production exact ICPN count drifted")
    if counts.get("STM32C0") != 209 or FAMILY in counts:
        raise AcquisitionError("immutable post-C0 Production boundary drifted")
    return payload


def build_foundation_report(catalog_rows: list[dict[str, str]]) -> dict[str, Any]:
    surface = guarded_rows(catalog_rows)
    validate_selection()
    validate_target_manifest()
    validate_retained_identity()
    validate_ordering_authority()
    validate_production_prestate()
    targets = deterministic_initial_targets(catalog_rows)
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "scope": "bounded_research_foundation_only",
        "target_config": TARGET_CONFIG,
        "source_row_count": len(surface),
        "identifier_kind_counts": dict(sorted(Counter(row["identifier_kind"] for row in surface).items())),
        "subfamilies": list(EXPECTED_SUBFAMILIES),
        "initial_targets": [{"subfamily": subfamily, "base_device": base} for subfamily, base in targets],
        "evidence_foundation": {
            "scope": "representative_evidence_only_not_complete_family_inventory",
            "representative_count": 16,
            "active_exact_icpns_observed": EXPECTED_REPRESENTATIVE_EXACT_ICPNS,
            "unique_official_datasheets": 16,
            "openocd_catalog_sha256": EXPECTED_OPENOCD_CATALOG_SHA256,
            "selection_sha256": EXPECTED_SELECTION_SHA256,
            "target_manifest_sha256": EXPECTED_TARGET_MANIFEST_SHA256,
            "retained_probe_summary_sha256": EXPECTED_RETAINED_SUMMARY_SHA256,
            "ordering_comparison_review_sha256": EXPECTED_ORDERING_COMPARISON_SHA256,
            "l0_ordering_authority_review_sha256": EXPECTED_L0_ORDERING_REVIEW_SHA256,
            "production_manifest_prestate_sha256": EXPECTED_PRODUCTION_PRESTATE_SHA256,
        },
        "claims": {
            "canonical_admission_authorized": False,
            "complete_family_inventory_claimed": False,
            "flash_geometry_qualified": False,
            "manufacturer_evidence_is_admission": False,
            "option_security_semantics_qualified": False,
            "physical_hil_qualified": False,
            "production_write_authorized": False,
            "programming_algorithm_equivalence": False,
            "programming_policy_defined": False,
            "runtime_programming_support_claimed": False,
        },
    }


def write_baseline(path: Path = DEFAULT_BASELINE) -> None:
    path.write_text(json.dumps(build_foundation_report(read_catalog()), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_baseline(path: Path = DEFAULT_BASELINE) -> None:
    if build_foundation_report(read_catalog()) != _read_json(path):
        raise AcquisitionError("STM32L0 L0.1 foundation baseline drifted")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--write-baseline", action="store_true")
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.write_baseline:
        write_baseline()
    if args.check:
        check_baseline()
    if not args.write_baseline and not args.check:
        print(json.dumps(build_foundation_report(read_catalog()), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

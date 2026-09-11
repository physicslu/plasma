#!/usr/bin/env python3
"""Fail-closed STM32C0 Phase C0.1 research foundation.

C0.1 freezes the selected STM32C0 OpenOCD research surface and binds six
deterministic representatives to retained official-ST commercial evidence and
Ordering Information. The 21 exact ICPNs are representative evidence only,
not complete-family inventory. No admission, Production, programming, HIL, or
runtime authority is created here.
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
DEFAULT_SELECTION = HERE / "stm32-post-u0-next-family-selection.json"
DEFAULT_RETAINED_SUMMARY = HERE / "evidence/stm32-c0-l1-l0-post-u0-live-2026-09-11/probe-summary.json"
DEFAULT_ORDERING_REVIEW = HERE / "stm32-c0-l0-post-u0-ordering-authority-review.json"
DEFAULT_BASELINE = HERE / "stm32c0-phase-c0.1-foundation-baseline.json"
PHASE = "C0.1"
FAMILY = "STM32C0"
MANUFACTURER = "STMicroelectronics"
TARGET_CONFIG = "tcl/target/stm32c0x.cfg"
EXPECTED_ROW_COUNT = 95
EXPECTED_ORDERING_COUNT = 73
EXPECTED_CMSIS_COUNT = 22
EXPECTED_SUBFAMILIES = ("STM32C011", "STM32C031", "STM32C051", "STM32C071", "STM32C091", "STM32C092")
EXPECTED_TARGETS = (
    ("STM32C011", "STM32C011F4"), ("STM32C031", "STM32C031C4"),
    ("STM32C051", "STM32C051C6"), ("STM32C071", "STM32C071C8"),
    ("STM32C091", "STM32C091CB"), ("STM32C092", "STM32C092CB"),
)
EXPECTED_ORDERING_AUTHORITIES = {
    "STM32C011F4": ("DS13866", 5, 93), "STM32C031C4": ("DS13867", 4, 100),
    "STM32C051C6": ("DS14721", 2, 107), "STM32C071C8": ("DS14693", 2, 128),
    "STM32C091CB": ("DS14720", 3, 121), "STM32C092CB": ("DS14720", 3, 121),
}
EXPECTED_SELECTION_SHA256 = "f2bc4d955952cc8c25362ca5568e944470f7a1b43bf41dee2fcca9516e9c8773"
EXPECTED_RETAINED_SUMMARY_SHA256 = "1bfa9da6e6b3d020c3f643eb5d6c72ee7ee5c8aa995c66de21fa7576b79a9228"
EXPECTED_ORDERING_REVIEW_SHA256 = "9f4bde47508100025d3d6e92813f244431a18d95cf3fc73a45de93849dddd38d"
EXPECTED_REPRESENTATIVE_EXACT_ICPNS = 21
ORDERING_PATTERN_RE = re.compile(r"^(STM32C0[A-Z0-9]+)([A-Z])x$")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcquisitionError(f"{path.name}: expected JSON object")
    return value


def _bound(path: Path, digest: str, label: str) -> dict[str, Any]:
    observed = _sha256(path)
    if observed != digest:
        raise AcquisitionError(f"{label} SHA-256 drifted: {observed}")
    return _json(path)


def _all_false(value: Any, label: str) -> None:
    if not isinstance(value, dict) or not value:
        raise AcquisitionError(f"{label}: missing fail-closed claim map")
    escaped = {k: v for k, v in value.items() if v is not False}
    if escaped:
        raise AcquisitionError(f"{label}: escaped fail-closed state: {escaped}")


def read_catalog(path: Path = DEFAULT_CATALOG) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def base_from_row(row: dict[str, str]) -> str:
    if row.get("identifier_kind") != "ordering_pattern":
        raise AcquisitionError("commercial selection requires ordering_pattern")
    match = ORDERING_PATTERN_RE.fullmatch(row.get("part_number", ""))
    if match is None:
        raise AcquisitionError(f"unsupported STM32C0 ordering pattern: {row.get('part_number')!r}")
    return match.group(1)


def guarded_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = [r for r in catalog_rows if r.get("vendor") == MANUFACTURER and r.get("plasma_series") == FAMILY]
    if len(rows) != EXPECTED_ROW_COUNT:
        raise AcquisitionError(f"{PHASE}: expected {EXPECTED_ROW_COUNT} source rows, got {len(rows)}")
    kinds = Counter(r.get("identifier_kind", "") for r in rows)
    if kinds != Counter({"ordering_pattern": 73, "cmsis_device_name": 22}):
        raise AcquisitionError(f"{PHASE}: identifier-kind surface drifted: {dict(kinds)}")
    if tuple(sorted({r.get("subfamily", "") for r in rows})) != tuple(sorted(EXPECTED_SUBFAMILIES)):
        raise AcquisitionError(f"{PHASE}: subfamily surface drifted")
    ordering_subfamilies: set[str] = set()
    for row in rows:
        part = row.get("part_number", "")
        if row.get("target_config") != TARGET_CONFIG or row.get("openocd_distribution") != "upstream-openocd":
            raise AcquisitionError(f"{part}: routing surface drifted")
        if row.get("mapping_status") != "mapping_candidate" or row.get("validation_status") != "not_verified":
            raise AcquisitionError(f"{part}: source status escaped research-only state")
        if row.get("identifier_kind") == "ordering_pattern":
            if not base_from_row(row).startswith(row.get("subfamily", "")):
                raise AcquisitionError(f"{part}: ordering pattern escaped subfamily")
            ordering_subfamilies.add(row["subfamily"])
        elif row.get("identifier_kind") == "cmsis_device_name":
            if not part.startswith(row.get("subfamily", "")):
                raise AcquisitionError(f"{part}: CMSIS alias escaped subfamily")
        else:
            raise AcquisitionError(f"{part}: unsupported identifier kind")
    if ordering_subfamilies != set(EXPECTED_SUBFAMILIES):
        raise AcquisitionError(f"{PHASE}: ordering-pattern subfamily coverage drifted")
    return rows


def commercial_ordering_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [r for r in guarded_rows(rows) if r["identifier_kind"] == "ordering_pattern"]


def cmsis_alias_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    return [r for r in guarded_rows(rows) if r["identifier_kind"] == "cmsis_device_name"]


def deterministic_initial_targets(rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    by_subfamily: dict[str, set[str]] = defaultdict(set)
    for row in commercial_ordering_rows(rows):
        by_subfamily[row["subfamily"]].add(base_from_row(row))
    targets = [(sf, min(by_subfamily[sf])) for sf in EXPECTED_SUBFAMILIES]
    if tuple(targets) != EXPECTED_TARGETS:
        raise AcquisitionError(f"{PHASE}: deterministic targets drifted: {targets}")
    return targets


def validate_selection(path: Path = DEFAULT_SELECTION) -> dict[str, Any]:
    payload = _bound(path, EXPECTED_SELECTION_SHA256, "post-U0 selection")
    if payload.get("selection_id") != "stm32-post-u0-next-family-selection-v1" or payload.get("selected_next_research_family") != FAMILY:
        raise AcquisitionError("STM32C0 is no longer the frozen selected family")
    if payload.get("scope") != "next_family_research_only":
        raise AcquisitionError("selection scope escaped research-only boundary")
    _all_false(payload.get("authority_boundaries"), "selection authority boundaries")
    c0 = (payload.get("candidate_evidence") or {}).get(FAMILY)
    if not isinstance(c0, dict) or c0.get("representative_targets") != 6 or c0.get("active_exact_icpns_observed") != 21:
        raise AcquisitionError("selection C0 evidence summary drifted")
    return payload


def validate_retained_identity(path: Path = DEFAULT_RETAINED_SUMMARY) -> dict[str, dict[str, Any]]:
    payload = _bound(path, EXPECTED_RETAINED_SUMMARY_SHA256, "retained post-U0 evidence")
    _all_false(payload.get("claims"), "retained evidence claims")
    c0 = (payload.get("by_series") or {}).get(FAMILY)
    expected = {
        "attempted_targets": 6, "verified_identity_targets": 6, "active_candidate_targets": 6,
        "lifecycle_excluded_targets": 0, "source_unavailable_404": 0, "manual_review": 0,
        "active_exact_icpns": 21, "excluded_non_active_part_numbers": 0,
        "commercial_identity_access_clean": True,
    }
    if not isinstance(c0, dict) or any(c0.get(k) != v for k, v in expected.items()):
        raise AcquisitionError("retained STM32C0 summary drifted")
    expected_bases = {b for _, b in EXPECTED_TARGETS}
    results = payload.get("results")
    if not isinstance(results, list):
        raise AcquisitionError("retained evidence results must be a list")
    observed: dict[str, dict[str, Any]] = {}
    for result in results:
        if not isinstance(result, dict) or result.get("series") != FAMILY:
            continue
        base = result.get("base_device")
        if base in observed or base not in expected_bases:
            raise AcquisitionError(f"unexpected/duplicate retained C0 target: {base}")
        if result.get("commercial_identity_status") != "verified_active" or result.get("disposition") != "active_candidates":
            raise AcquisitionError(f"{base}: retained identity/lifecycle drifted")
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise AcquisitionError(f"{base}: nested evidence missing")
        exact = evidence.get("exact_icpns")
        if not isinstance(exact, list) or not exact or any(not isinstance(pn, str) or not pn.startswith(base) for pn in exact):
            raise AcquisitionError(f"{base}: invalid retained exact ICPNs")
        if evidence.get("evidence_surface") != "quality_and_reliability_identity_plus_sample_and_buy_lifecycle":
            raise AcquisitionError(f"{base}: evidence authority surface drifted")
        url = result.get("source_url")
        if not isinstance(url, str) or not url.startswith("https://www.st.com/en/microcontrollers-microprocessors/"):
            raise AcquisitionError(f"{base}: non-official source URL")
        observed[base] = {**result, "exact_icpns": list(exact)}
    if set(observed) != expected_bases or sum(len(x["exact_icpns"]) for x in observed.values()) != 21:
        raise AcquisitionError("retained C0 representative set/aggregate drifted")
    return observed


def validate_ordering_authority(path: Path = DEFAULT_ORDERING_REVIEW) -> dict[str, tuple[str, int, int]]:
    payload = _bound(path, EXPECTED_ORDERING_REVIEW_SHA256, "post-U0 Ordering Information review")
    _all_false(payload.get("claims"), "ordering review claims")
    method = payload.get("method")
    if not isinstance(method, dict) or method.get("authority") != "official_st_datasheet" or method.get("transport_diagnostics_are_selection_evidence") is not False:
        raise AcquisitionError("Ordering Information authority boundary drifted")
    c0 = (payload.get("by_series") or {}).get(FAMILY)
    expected = {
        "representative_targets": 6, "unique_official_datasheets": 5,
        "ordering_authority_covered_targets": 6, "required_schema_complete_targets": 6,
        "blocking_evidence_issues": 0, "ordering_evidence_quality": "complete", "revision_drift": False,
    }
    if not isinstance(c0, dict) or any(c0.get(k) != v for k, v in expected.items()):
        raise AcquisitionError("STM32C0 Ordering Information summary drifted")
    observed = {(x.get("datasheet_id"), x.get("revision"), x.get("ordering_pdf_page")) for x in c0.get("authorities", []) if isinstance(x, dict)}
    if observed != set(EXPECTED_ORDERING_AUTHORITIES.values()):
        raise AcquisitionError("STM32C0 Ordering Information authorities drifted")
    return dict(EXPECTED_ORDERING_AUTHORITIES)


def build_foundation_report(rows: list[dict[str, str]]) -> dict[str, Any]:
    surface = guarded_rows(rows)
    validate_selection()
    retained = validate_retained_identity()
    authorities = validate_ordering_authority()
    targets = deterministic_initial_targets(rows)
    reps: list[dict[str, Any]] = []
    for subfamily, base in targets:
        ds, rev, page = authorities[base]
        reps.append({
            "subfamily": subfamily, "base_device": base, "commercial_identity_status": "verified_active",
            "exact_icpns": list(retained[base]["exact_icpns"]), "datasheet_id": ds,
            "datasheet_revision": rev, "ordering_pdf_page": page,
        })
    return {
        "schema_version": 1, "phase": PHASE, "family": FAMILY, "target_config": TARGET_CONFIG,
        "source_row_count": len(surface),
        "identifier_kind_counts": dict(sorted(Counter(r["identifier_kind"] for r in surface).items())),
        "initial_targets": [{"subfamily": sf, "base_device": b} for sf, b in targets],
        "evidence_foundation": {
            "scope": "representative_evidence_only_not_complete_family_inventory",
            "representative_count": 6, "active_exact_icpns_observed": sum(len(r["exact_icpns"]) for r in reps),
            "selection_sha256": EXPECTED_SELECTION_SHA256,
            "retained_probe_summary_sha256": EXPECTED_RETAINED_SUMMARY_SHA256,
            "ordering_information_review_sha256": EXPECTED_ORDERING_REVIEW_SHA256,
            "representatives": reps,
        },
        "claims": {
            "canonical_admission_authorized": False, "complete_family_inventory_claimed": False,
            "flash_geometry_qualified": False, "manufacturer_evidence_is_admission": False,
            "option_security_semantics_qualified": False, "physical_hil_qualified": False,
            "production_write_authorized": False, "programming_algorithm_equivalence": False,
            "programming_policy_defined": False, "runtime_programming_support_claimed": False,
        },
    }


def write_baseline(path: Path = DEFAULT_BASELINE) -> None:
    path.write_text(json.dumps(build_foundation_report(read_catalog()), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_baseline(path: Path = DEFAULT_BASELINE) -> None:
    if build_foundation_report(read_catalog()) != _json(path):
        raise AcquisitionError("STM32C0 C0.1 foundation baseline drifted")


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

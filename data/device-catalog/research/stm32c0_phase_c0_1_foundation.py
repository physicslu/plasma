#!/usr/bin/env python3
"""Fail-closed STM32C0 Phase C0.1 research foundation.

C0.1 freezes the already-selected STM32C0 OpenOCD-derived research surface and
binds its deterministic representatives to retained official-ST commercial
identity/lifecycle evidence plus official Ordering Information authority.

This is research foundation only. It does not authorize canonical admission,
Production publication, programming-policy equivalence, Flash/security
qualification, physical/HIL qualification, or runtime programming support.
The 21 exact ICPNs observed here are representative evidence only and are not a
claim of complete STM32C0 commercial inventory.
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
DEFAULT_RETAINED_SUMMARY = (
    HERE
    / "evidence"
    / "stm32-c0-l1-l0-post-u0-live-2026-09-11"
    / "probe-summary.json"
)
DEFAULT_ORDERING_REVIEW = HERE / "stm32-c0-l0-post-u0-ordering-authority-review.json"
DEFAULT_BASELINE = HERE / "stm32c0-phase-c0.1-foundation-baseline.json"

PHASE = "C0.1"
FAMILY = "STM32C0"
MANUFACTURER = "STMicroelectronics"
TARGET_CONFIG = "tcl/target/stm32c0x.cfg"
EXPECTED_ROW_COUNT = 95
EXPECTED_ORDERING_COUNT = 73
EXPECTED_CMSIS_COUNT = 22
EXPECTED_SUBFAMILIES = (
    "STM32C011",
    "STM32C031",
    "STM32C051",
    "STM32C071",
    "STM32C091",
    "STM32C092",
)
EXPECTED_TARGETS = (
    ("STM32C011", "STM32C011F4"),
    ("STM32C031", "STM32C031C4"),
    ("STM32C051", "STM32C051C6"),
    ("STM32C071", "STM32C071C8"),
    ("STM32C091", "STM32C091CB"),
    ("STM32C092", "STM32C092CB"),
)
EXPECTED_ORDERING_AUTHORITIES = {
    "STM32C011F4": ("DS13866", 5, 93),
    "STM32C031C4": ("DS13867", 4, 100),
    "STM32C051C6": ("DS14721", 2, 107),
    "STM32C071C8": ("DS14693", 2, 128),
    "STM32C091CB": ("DS14720", 3, 121),
    "STM32C092CB": ("DS14720", 3, 121),
}

EXPECTED_SELECTION_SHA256 = "f2bc4d955952cc8c25362ca5568e944470f7a1b43bf41dee2fcca9516e9c8773"
EXPECTED_RETAINED_SUMMARY_SHA256 = "1bfa9da6e6b3d020c3f643eb5d6c72ee7ee5c8aa995c66de21fa7576b79a9228"
EXPECTED_ORDERING_REVIEW_SHA256 = "9f4bde47508100025d3d6e92813f244431a18d95cf3fc73a45de93849dddd38d"
EXPECTED_REPRESENTATIVE_EXACT_ICPNS = 21

ORDERING_PATTERN_RE = re.compile(r"^(STM32C0[A-Z0-9]+)([A-Z])x$")


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


def _require_all_false(payload: Any, label: str) -> None:
    if not isinstance(payload, dict) or not payload:
        raise AcquisitionError(f"{label}: expected non-empty fail-closed claim map")
    escaped = {key: value for key, value in payload.items() if value is not False}
    if escaped:
        raise AcquisitionError(f"{label}: authority boundary escaped fail-closed state: {escaped}")


def read_catalog(path: Path = DEFAULT_CATALOG) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def base_from_row(row: dict[str, str]) -> str:
    if row.get("identifier_kind") != "ordering_pattern":
        raise AcquisitionError("commercial research selection requires ordering_pattern rows")
    part = row.get("part_number", "")
    match = ORDERING_PATTERN_RE.fullmatch(part)
    if match is None:
        raise AcquisitionError(f"unsupported STM32C0 ordering pattern: {part!r}")
    return match.group(1)


def guarded_rows(catalog_rows: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = [
        row
        for row in catalog_rows
        if row.get("vendor") == MANUFACTURER and row.get("plasma_series") == FAMILY
    ]
    if len(rows) != EXPECTED_ROW_COUNT:
        raise AcquisitionError(
            f"{PHASE} requires guarded {EXPECTED_ROW_COUNT}-row STM32C0 surface, got {len(rows)}"
        )

    kinds = Counter(row.get("identifier_kind", "") for row in rows)
    expected_kinds = Counter(
        {"ordering_pattern": EXPECTED_ORDERING_COUNT, "cmsis_device_name": EXPECTED_CMSIS_COUNT}
    )
    if kinds != expected_kinds:
        raise AcquisitionError(f"{PHASE} STM32C0 identifier-kind surface drifted: {dict(kinds)}")

    subfamilies = tuple(sorted({row.get("subfamily", "") for row in rows if row.get("subfamily")}))
    if subfamilies != tuple(sorted(EXPECTED_SUBFAMILIES)):
        raise AcquisitionError(f"{PHASE} STM32C0 subfamily surface drifted: {subfamilies}")

    ordering_subfamilies: set[str] = set()
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

        kind = row.get("identifier_kind")
        subfamily = row.get("subfamily", "")
        if kind == "ordering_pattern":
            base = base_from_row(row)
            if not base.startswith(subfamily):
                raise AcquisitionError(f"{part}: ordering pattern escaped source subfamily")
            ordering_subfamilies.add(subfamily)
        elif kind == "cmsis_device_name":
            if not part.startswith(subfamily):
                raise AcquisitionError(f"{part}: CMSIS alias escaped source subfamily")
        else:
            raise AcquisitionError(f"{part}: unsupported identifier kind")

    if ordering_subfamilies != set(EXPECTED_SUBFAMILIES):
        raise AcquisitionError(
            f"{PHASE} ordering-pattern coverage drifted: {sorted(ordering_subfamilies)}"
        )
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
    _require_sha256(path, EXPECTED_SELECTION_SHA256, "post-U0 next-family selection")
    payload = _read_json(path)
    if payload.get("selection_id") != "stm32-post-u0-next-family-selection-v1":
        raise AcquisitionError("unexpected post-U0 selection artifact")
    if payload.get("selected_next_research_family") != FAMILY:
        raise AcquisitionError("STM32C0 is no longer the frozen next research family")
    if payload.get("scope") != "next_family_research_only":
        raise AcquisitionError("selection scope escaped research-only boundary")
    _require_all_false(payload.get("authority_boundaries"), "selection authority boundaries")
    evidence = payload.get("candidate_evidence")
    c0 = evidence.get(FAMILY) if isinstance(evidence, dict) else None
    if not isinstance(c0, dict):
        raise AcquisitionError("selection artifact is missing STM32C0 evidence")
    if c0.get("active_exact_icpns_observed") != EXPECTED_REPRESENTATIVE_EXACT_ICPNS:
        raise AcquisitionError("selection STM32C0 representative exact ICPN count drifted")
    if c0.get("representative_targets") != len(EXPECTED_TARGETS):
        raise AcquisitionError("selection STM32C0 representative count drifted")
    return payload


def validate_retained_identity(path: Path = DEFAULT_RETAINED_SUMMARY) -> dict[str, dict[str, Any]]:
    _require_sha256(path, EXPECTED_RETAINED_SUMMARY_SHA256, "retained post-U0 evidence summary")
    payload = _read_json(path)
    _require_all_false(payload.get("claims"), "retained evidence claims")

    by_series = payload.get("by_series")
    c0 = by_series.get(FAMILY) if isinstance(by_series, dict) else None
    if not isinstance(c0, dict):
        raise AcquisitionError("retained evidence is missing STM32C0 summary")
    expected_summary = {
        "attempted_targets": 6,
        "verified_identity_targets": 6,
        "active_candidate_targets": 6,
        "lifecycle_excluded_targets": 0,
        "source_unavailable_404": 0,
        "manual_review": 0,
        "active_exact_icpns": EXPECTED_REPRESENTATIVE_EXACT_ICPNS,
        "excluded_non_active_part_numbers": 0,
        "commercial_identity_access_clean": True,
    }
    for key, expected in expected_summary.items():
        if c0.get(key) != expected:
            raise AcquisitionError(f"retained STM32C0 evidence summary drifted at {key}")

    targets = payload.get("targets")
    if not isinstance(targets, list):
        raise AcquisitionError("retained evidence targets must be a list")
    expected_bases = {base for _, base in EXPECTED_TARGETS}
    observed: dict[str, dict[str, Any]] = {}
    for target in targets:
        if not isinstance(target, dict) or target.get("series") != FAMILY:
            continue
        base = target.get("base_device")
        if base in observed:
            raise AcquisitionError(f"duplicate retained STM32C0 target: {base}")
        if base not in expected_bases:
            raise AcquisitionError(f"unexpected retained STM32C0 target: {base}")
        if target.get("commercial_identity_status") != "verified_active":
            raise AcquisitionError(f"{base}: retained identity is no longer verified active")
        if target.get("disposition") != "active_candidates":
            raise AcquisitionError(f"{base}: retained disposition drifted")
        exact = target.get("exact_icpns")
        if not isinstance(exact, list) or not exact or any(not isinstance(icpn, str) for icpn in exact):
            raise AcquisitionError(f"{base}: retained exact ICPNs are invalid")
        if any(not icpn.startswith(base) for icpn in exact):
            raise AcquisitionError(f"{base}: retained exact ICPN escaped representative Base Device")
        source_url = target.get("source_url")
        if not isinstance(source_url, str) or not source_url.startswith(
            "https://www.st.com/en/microcontrollers-microprocessors/"
        ):
            raise AcquisitionError(f"{base}: retained identity authority is not official ST")
        observed[base] = target

    if set(observed) != expected_bases:
        raise AcquisitionError(f"retained STM32C0 representative set drifted: {sorted(observed)}")
    if sum(len(target["exact_icpns"]) for target in observed.values()) != EXPECTED_REPRESENTATIVE_EXACT_ICPNS:
        raise AcquisitionError("retained STM32C0 representative exact ICPN aggregate drifted")
    return observed


def validate_ordering_authority(path: Path = DEFAULT_ORDERING_REVIEW) -> dict[str, tuple[str, int, int]]:
    _require_sha256(path, EXPECTED_ORDERING_REVIEW_SHA256, "post-U0 Ordering Information review")
    payload = _read_json(path)
    _require_all_false(payload.get("claims"), "ordering review claims")
    method = payload.get("method")
    if not isinstance(method, dict) or method.get("authority") != "official_st_datasheet":
        raise AcquisitionError("Ordering Information authority is no longer official ST datasheet")
    if method.get("transport_diagnostics_are_selection_evidence") is not False:
        raise AcquisitionError("transport diagnostics must remain excluded from ordering evidence")

    by_series = payload.get("by_series")
    c0 = by_series.get(FAMILY) if isinstance(by_series, dict) else None
    if not isinstance(c0, dict):
        raise AcquisitionError("ordering review is missing STM32C0 summary")
    expected = {
        "representative_targets": 6,
        "unique_official_datasheets": 5,
        "ordering_authority_covered_targets": 6,
        "required_schema_complete_targets": 6,
        "blocking_evidence_issues": 0,
        "ordering_evidence_quality": "complete",
        "revision_drift": False,
    }
    for key, value in expected.items():
        if c0.get(key) != value:
            raise AcquisitionError(f"STM32C0 Ordering Information evidence drifted at {key}")

    authorities = c0.get("authorities")
    if not isinstance(authorities, list):
        raise AcquisitionError("STM32C0 ordering authorities must be a list")
    observed = {
        (entry.get("datasheet_id"), entry.get("revision"), entry.get("ordering_pdf_page"))
        for entry in authorities
        if isinstance(entry, dict)
    }
    required = set(EXPECTED_ORDERING_AUTHORITIES.values())
    if observed != required:
        raise AcquisitionError(f"STM32C0 Ordering Information authorities drifted: {observed}")
    return dict(EXPECTED_ORDERING_AUTHORITIES)


def build_foundation_report(catalog_rows: list[dict[str, str]]) -> dict[str, Any]:
    rows = guarded_rows(catalog_rows)
    validate_selection()
    retained = validate_retained_identity()
    authorities = validate_ordering_authority()
    targets = deterministic_initial_targets(catalog_rows)

    subfamily_counts = dict(sorted(Counter(row["subfamily"] for row in rows).items()))
    kind_counts = dict(sorted(Counter(row["identifier_kind"] for row in rows).items()))
    representative_rows: list[dict[str, Any]] = []
    for subfamily, base in targets:
        target = retained[base]
        datasheet_id, revision, ordering_page = authorities[base]
        representative_rows.append(
            {
                "subfamily": subfamily,
                "base_device": base,
                "commercial_identity_status": "verified_active",
                "exact_icpns": list(target["exact_icpns"]),
                "datasheet_id": datasheet_id,
                "datasheet_revision": revision,
                "ordering_pdf_page": ordering_page,
            }
        )

    claims = {
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
    }
    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "target_config": TARGET_CONFIG,
        "source_row_count": len(rows),
        "identifier_kind_counts": kind_counts,
        "subfamily_counts": subfamily_counts,
        "initial_targets": [
            {"subfamily": subfamily, "base_device": base} for subfamily, base in targets
        ],
        "evidence_foundation": {
            "scope": "representative_evidence_only_not_complete_family_inventory",
            "representative_count": len(representative_rows),
            "active_exact_icpns_observed": sum(len(item["exact_icpns"]) for item in representative_rows),
            "selection_sha256": EXPECTED_SELECTION_SHA256,
            "retained_probe_summary_sha256": EXPECTED_RETAINED_SUMMARY_SHA256,
            "ordering_information_review_sha256": EXPECTED_ORDERING_REVIEW_SHA256,
            "representatives": representative_rows,
        },
        "claims": claims,
    }


def write_baseline(path: Path = DEFAULT_BASELINE) -> None:
    payload = build_foundation_report(read_catalog())
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_baseline(path: Path = DEFAULT_BASELINE) -> None:
    expected = _read_json(path)
    observed = build_foundation_report(read_catalog())
    if observed != expected:
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

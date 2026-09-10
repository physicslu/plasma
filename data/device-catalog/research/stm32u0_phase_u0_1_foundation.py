#!/usr/bin/env python3
"""Fail-closed STM32U0 Phase U0.1 bounded-surface and evidence foundation.

This transaction freezes the already-selected STM32U0 research surface and binds
it to retained official-ST commercial identity/lifecycle and Ordering
Information evidence from H006.

OpenOCD/CMSIS data bounds research only. It is not commercial identity authority.
Retained manufacturer evidence is evidence, not canonical admission. Nothing in
this module authorizes Production writes, programming-policy equivalence,
Flash/security qualification, HIL, or runtime support.
"""

from __future__ import annotations

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
DEFAULT_SELECTION = HERE / "stm32-next-family-selection.json"
DEFAULT_RETAINED_SUMMARY = (
    HERE
    / "evidence"
    / "stm32-u0-c0-l1-evidence-accessibility-probe-live-2026-09-10"
    / "probe-summary.json"
)
DEFAULT_ORDERING_REVIEW = HERE / "stm32-u0-c0-ordering-authority-review.json"

PHASE = "U0.1"
FAMILY = "STM32U0"
MANUFACTURER = "STMicroelectronics"
TARGET_CONFIG = "tcl/target/stm32u0x.cfg"
EXPECTED_ROW_COUNT = 48
EXPECTED_ORDERING_COUNT = 42
EXPECTED_CMSIS_COUNT = 6
EXPECTED_SUBFAMILY_COUNTS = {
    "STM32U031": 16,
    "STM32U073": 24,
    "STM32U083": 8,
}
EXPECTED_SUBFAMILIES = tuple(EXPECTED_SUBFAMILY_COUNTS)
EXPECTED_TARGETS = (
    ("STM32U031", "STM32U031C6"),
    ("STM32U073", "STM32U073C8"),
    ("STM32U083", "STM32U083CC"),
)
EXPECTED_EXACT_ICPNS = {
    "STM32U031C6": (
        "STM32U031C6T6",
        "STM32U031C6U6",
    ),
    "STM32U073C8": (
        "STM32U073C8T6",
        "STM32U073C8U6",
    ),
    "STM32U083CC": (
        "STM32U083CCT6",
        "STM32U083CCT6TR",
        "STM32U083CCU6",
        "STM32U083CCU6TR",
    ),
}
EXPECTED_ORDERING_AUTHORITIES = {
    "STM32U031C6": ("DS14581", 2, 124),
    "STM32U073C8": ("DS14548", 2, 135),
    "STM32U083CC": ("DS14463", 2, 135),
}

EXPECTED_SELECTION_SHA256 = "2c81a6c3495a75a6f4115252293af6e99b727f3d12d67f31853922279a96d017"
EXPECTED_RETAINED_SUMMARY_SHA256 = "d4339d85a7565f4be731de863ee7db0c1301a335bb5b2777e84a1089aae2769d"
EXPECTED_ORDERING_REVIEW_SHA256 = "3fe019d420cbe43c732b9d403acaa2f1b0bf0dc583b38073eb25528217f5efe9"

ORDERING_PATTERN_RE = re.compile(r"^(STM32U0[A-Z0-9]+)([A-Z])x$")
ROUTING_VALUE_RE = re.compile(r"^STM32U0[A-Z0-9]+$")


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
    non_false = {key: value for key, value in payload.items() if value is not False}
    if non_false:
        raise AcquisitionError(f"{label}: authority boundary escaped fail-closed state: {non_false}")


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
            f"{PHASE} requires guarded {EXPECTED_ROW_COUNT}-row STM32U0 surface, got {len(rows)}"
        )

    subfamilies = dict(sorted(Counter(row.get("subfamily", "") for row in rows).items()))
    if subfamilies != EXPECTED_SUBFAMILY_COUNTS:
        raise AcquisitionError(f"{PHASE} STM32U0 subfamily surface drifted: {subfamilies}")

    kinds = Counter(row.get("identifier_kind", "") for row in rows)
    expected_kinds = Counter(
        {
            "ordering_pattern": EXPECTED_ORDERING_COUNT,
            "cmsis_device_name": EXPECTED_CMSIS_COUNT,
        }
    )
    if kinds != expected_kinds:
        raise AcquisitionError(f"{PHASE} STM32U0 identifier-kind surface drifted: {dict(kinds)}")

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
            if not base.startswith(subfamily) or len(base) != len(subfamily) + 2:
                raise AcquisitionError(f"{part}: invalid concrete STM32U0 Base Device {base!r}")
            ordering_subfamilies.add(subfamily)
        elif kind == "cmsis_device_name":
            if not part.startswith(subfamily):
                raise AcquisitionError(f"{part}: CMSIS alias escaped its source subfamily")
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


def base_from_row(row: dict[str, str]) -> str:
    if row.get("identifier_kind") != "ordering_pattern":
        raise AcquisitionError("commercial research selection requires ordering_pattern rows")
    part = row.get("part_number", "")
    match = ORDERING_PATTERN_RE.fullmatch(part)
    if match is None:
        raise AcquisitionError(f"unsupported STM32U0 ordering pattern: {part!r}")
    return match.group(1)


def deterministic_initial_targets(catalog_rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    by_subfamily: dict[str, set[str]] = defaultdict(set)
    for row in commercial_ordering_rows(catalog_rows):
        by_subfamily[row["subfamily"]].add(base_from_row(row))

    observed_subfamilies = tuple(sorted(by_subfamily))
    if observed_subfamilies != tuple(sorted(EXPECTED_SUBFAMILIES)):
        raise AcquisitionError(f"{PHASE} deterministic target subfamilies drifted")

    targets = [(subfamily, min(by_subfamily[subfamily])) for subfamily in EXPECTED_SUBFAMILIES]
    if tuple(targets) != EXPECTED_TARGETS:
        raise AcquisitionError(f"{PHASE} deterministic targets drifted: {targets}")
    return targets


def pattern_matches(pattern: str, value: str) -> bool:
    expression = "".join("[A-Z0-9]" if char.lower() == "x" else re.escape(char) for char in pattern)
    return re.fullmatch(expression, value) is not None


def resolve_ordering_pattern_mapping(
    routing_value: str,
    catalog_rows: list[dict[str, str]],
) -> dict[str, Any]:
    if ROUTING_VALUE_RE.fullmatch(routing_value) is None:
        return {"status": "unmapped", "match_count": 0, "target_configs": []}
    matches = [
        row
        for row in commercial_ordering_rows(catalog_rows)
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


def validate_selection(path: Path = DEFAULT_SELECTION) -> None:
    _require_sha256(path, EXPECTED_SELECTION_SHA256, "STM32 next-family selection")
    payload = _read_json(path)
    if payload.get("selection_id") != "stm32-next-family-evidence-quality-selection-v1":
        raise AcquisitionError("unexpected STM32 next-family selection artifact")
    decision = payload.get("decision")
    if not isinstance(decision, dict):
        raise AcquisitionError("selection decision must be an object")
    if decision.get("selected_next_research_family") != FAMILY:
        raise AcquisitionError("STM32U0 is no longer the frozen next research family")
    if decision.get("selection_scope") != "next_family_research_only":
        raise AcquisitionError("selection scope escaped research-only boundary")
    _require_all_false(payload.get("authority_boundaries"), "selection authority boundaries")


def validate_retained_identity(
    path: Path = DEFAULT_RETAINED_SUMMARY,
) -> dict[str, dict[str, Any]]:
    _require_sha256(path, EXPECTED_RETAINED_SUMMARY_SHA256, "retained STM32 evidence summary")
    payload = _read_json(path)
    _require_all_false(payload.get("claims"), "retained evidence claims")

    by_series = payload.get("by_series")
    if not isinstance(by_series, dict) or not isinstance(by_series.get(FAMILY), dict):
        raise AcquisitionError("retained evidence is missing STM32U0 series summary")
    u0_summary = by_series[FAMILY]
    expected_summary = {
        "active_candidate_targets": 3,
        "active_exact_icpns": 8,
        "attempted_targets": 3,
        "commercial_identity_access_clean": True,
        "lifecycle_excluded_targets": 0,
        "manual_review": 0,
        "source_unavailable_404": 0,
        "verified_identity_targets": 3,
    }
    for key, expected in expected_summary.items():
        if u0_summary.get(key) != expected:
            raise AcquisitionError(f"retained STM32U0 evidence summary drifted at {key}")

    targets = payload.get("targets")
    if not isinstance(targets, list):
        raise AcquisitionError("retained evidence targets must be a list")
    observed: dict[str, dict[str, Any]] = {}
    for target in targets:
        if not isinstance(target, dict) or target.get("series") != FAMILY:
            continue
        base = target.get("base_device")
        if base in observed:
            raise AcquisitionError(f"duplicate retained STM32U0 target: {base}")
        if base not in EXPECTED_EXACT_ICPNS:
            raise AcquisitionError(f"unexpected retained STM32U0 target: {base}")
        if target.get("commercial_identity_status") != "verified_active":
            raise AcquisitionError(f"{base}: retained identity is no longer verified active")
        if target.get("disposition") != "active_candidates":
            raise AcquisitionError(f"{base}: retained disposition drifted")
        if tuple(target.get("exact_icpns", [])) != EXPECTED_EXACT_ICPNS[base]:
            raise AcquisitionError(f"{base}: retained exact ICPNs drifted")
        source_url = target.get("source_url")
        if not isinstance(source_url, str) or not source_url.startswith(
            "https://www.st.com/en/microcontrollers-microprocessors/"
        ):
            raise AcquisitionError(f"{base}: retained identity authority is not official ST")
        observed[base] = target

    expected_bases = {base for _, base in EXPECTED_TARGETS}
    if set(observed) != expected_bases:
        raise AcquisitionError(f"retained STM32U0 representative set drifted: {sorted(observed)}")
    return observed


def validate_ordering_authority(
    path: Path = DEFAULT_ORDERING_REVIEW,
) -> dict[str, dict[str, Any]]:
    _require_sha256(path, EXPECTED_ORDERING_REVIEW_SHA256, "STM32U0/C0 Ordering Information review")
    payload = _read_json(path)
    _require_all_false(payload.get("claims"), "ordering review claims")

    method = payload.get("method")
    if not isinstance(method, dict) or method.get("authority") != "official_st_datasheet":
        raise AcquisitionError("Ordering Information authority is no longer official ST datasheet")
    if method.get("transport_diagnostics_are_selection_evidence") is not False:
        raise AcquisitionError("transport diagnostics must remain excluded from selection evidence")

    by_series = payload.get("by_series")
    if not isinstance(by_series, dict) or not isinstance(by_series.get(FAMILY), dict):
        raise AcquisitionError("ordering review is missing STM32U0 summary")
    u0_summary = by_series[FAMILY]
    if (
        u0_summary.get("blocking_evidence_issues") != 0
        or u0_summary.get("ordering_authority_covered_targets") != 3
        or u0_summary.get("required_schema_complete_targets") != 3
        or u0_summary.get("ordering_evidence_quality") != "complete"
    ):
        raise AcquisitionError("STM32U0 Ordering Information evidence quality drifted")

    targets = payload.get("targets")
    if not isinstance(targets, list):
        raise AcquisitionError("ordering review targets must be a list")
    observed: dict[str, dict[str, Any]] = {}
    for target in targets:
        if not isinstance(target, dict) or target.get("series") != FAMILY:
            continue
        base = target.get("base_device")
        if base in observed:
            raise AcquisitionError(f"duplicate STM32U0 ordering authority: {base}")
        if base not in EXPECTED_ORDERING_AUTHORITIES:
            raise AcquisitionError(f"unexpected STM32U0 ordering authority target: {base}")
        ds, revision, page = EXPECTED_ORDERING_AUTHORITIES[base]
        if (
            target.get("datasheet_id") != ds
            or target.get("revision") != revision
            or target.get("ordering_pdf_page") != page
            or target.get("required_fields_complete") is not True
            or target.get("structured_text_review") != "verified"
        ):
            raise AcquisitionError(f"{base}: official Ordering Information authority drifted")
        datasheet_url = target.get("datasheet_url")
        if not isinstance(datasheet_url, str) or not datasheet_url.startswith(
            "https://www.st.com/resource/en/datasheet/"
        ):
            raise AcquisitionError(f"{base}: datasheet authority is not official ST")
        observed[base] = target

    expected_bases = {base for _, base in EXPECTED_TARGETS}
    if set(observed) != expected_bases:
        raise AcquisitionError(f"STM32U0 ordering representative set drifted: {sorted(observed)}")
    return observed


def build_foundation_report(
    catalog_rows: list[dict[str, str]],
    selection_path: Path = DEFAULT_SELECTION,
    retained_summary_path: Path = DEFAULT_RETAINED_SUMMARY,
    ordering_review_path: Path = DEFAULT_ORDERING_REVIEW,
) -> dict[str, object]:
    rows = guarded_rows(catalog_rows)
    targets = deterministic_initial_targets(catalog_rows)
    validate_selection(selection_path)
    retained = validate_retained_identity(retained_summary_path)
    ordering = validate_ordering_authority(ordering_review_path)

    representatives: list[dict[str, object]] = []
    for subfamily, base in targets:
        retained_target = retained[base]
        ordering_target = ordering[base]
        if retained_target.get("subfamily") != subfamily or ordering_target.get("subfamily") != subfamily:
            raise AcquisitionError(f"{base}: evidence subfamily disagrees with bounded surface")
        representatives.append(
            {
                "base_device": base,
                "commercial_identity_status": retained_target["commercial_identity_status"],
                "datasheet_id": ordering_target["datasheet_id"],
                "datasheet_revision": ordering_target["revision"],
                "exact_icpns": list(retained_target["exact_icpns"]),
                "ordering_pdf_page": ordering_target["ordering_pdf_page"],
                "subfamily": subfamily,
            }
        )

    return {
        "schema_version": 1,
        "phase": PHASE,
        "family": FAMILY,
        "source_row_count": len(rows),
        "identifier_kind_counts": {
            "cmsis_device_name": len(cmsis_alias_rows(catalog_rows)),
            "ordering_pattern": len(commercial_ordering_rows(catalog_rows)),
        },
        "subfamily_counts": EXPECTED_SUBFAMILY_COUNTS,
        "target_config": TARGET_CONFIG,
        "initial_targets": [
            {"base_device": base, "subfamily": subfamily}
            for subfamily, base in targets
        ],
        "evidence_foundation": {
            "active_exact_icpns_observed": sum(len(EXPECTED_EXACT_ICPNS[base]) for _, base in targets),
            "ordering_information_review_sha256": EXPECTED_ORDERING_REVIEW_SHA256,
            "representative_count": len(targets),
            "representatives": representatives,
            "retained_probe_summary_sha256": EXPECTED_RETAINED_SUMMARY_SHA256,
            "selection_sha256": EXPECTED_SELECTION_SHA256,
        },
        "claims": {
            "canonical_admission_authorized": False,
            "cmsis_alias_is_commercial_identity": False,
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

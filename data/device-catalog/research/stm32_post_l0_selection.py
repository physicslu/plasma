#!/usr/bin/env python3
"""Post-L0 STM32 next-family research selection.

This transaction is deliberately read-only. It replays the frozen post-L0
Production state, the retained official-ST commercial identity/lifecycle
evidence from the post-C0 probe, and the retained official-ST Ordering
Information review. It may select only the next research family.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from st_product_page_acquisition import AcquisitionError
from stm32_cross_family_prioritization import build_prioritization
from stm32_post_c0_selection import validate_authoritative_summary, validate_ordering_review

HERE = Path(__file__).resolve().parent
FROZEN_PRODUCTION = HERE / "stm32-post-l0-production-manifest-prestate.json"
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_EVIDENCE = HERE / "evidence" / "stm32-l1-l0-l4-post-c0-live-2026-09-12" / "probe-summary.json"
DEFAULT_ORDERING_REVIEW = HERE / "stm32-l0-l4-post-c0-ordering-authority-review.json"
CURRENT_SHORTLIST = ("STM32L1", "STM32L4")
SELECTION_ID = "stm32-post-l0-next-family-selection-v1"
COMMERCIAL_IDENTITY_AUTHORITY = (
    "official_st_quality_and_reliability_exact_identity_plus_"
    "sample_and_buy_marketing_status_exact_set_join"
)


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AcquisitionError(f"{path}: JSON object required")
    return payload


def _all_false(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def build_post_l0_prioritization() -> dict[str, Any]:
    report = build_prioritization(catalog_path=DEFAULT_CATALOG, manifest_path=FROZEN_PRODUCTION)
    production = report.get("production_invariants", {})
    if production.get("exact_icpn_count") != 1272:
        raise AcquisitionError("post-L0 Production exact ICPN prestate drifted")
    if production.get("base_device_count") != 392:
        raise AcquisitionError("post-L0 Production Base Device prestate drifted")
    counts = production.get("family_exact_icpn_counts", {})
    if not isinstance(counts, dict) or len(counts) != 11 or counts.get("STM32L0") != 360:
        raise AcquisitionError("post-L0 Production family prestate drifted")
    shortlist = tuple(item.get("plasma_series") for item in report.get("research_shortlist", []))
    if shortlist != CURRENT_SHORTLIST:
        raise AcquisitionError(f"post-L0 shortlist drifted: {shortlist}")
    if report.get("selected_next_research_family") is not None or not _all_false(report.get("claims")):
        raise AcquisitionError("cross-family prioritization escaped read-only pre-selection state")
    return report


def classify_current_candidates(summary: dict[str, Any]) -> dict[str, str]:
    validate_authoritative_summary(summary)
    by_series = summary.get("by_series", {})
    dispositions: dict[str, str] = {}
    for series in CURRENT_SHORTLIST:
        row = by_series.get(series)
        if not isinstance(row, dict) or row.get("commercial_identity_access_clean") is not True:
            dispositions[series] = "evidence_incomplete"
            continue
        attempted = int(row.get("attempted_targets", 0))
        if int(row.get("lifecycle_excluded_targets", 0)) > 0:
            dispositions[series] = "deprioritized_for_next_family_research_due_to_lifecycle"
        elif attempted > 0 and int(row.get("active_candidate_targets", 0)) == attempted:
            dispositions[series] = "ordering_review_candidate"
        else:
            dispositions[series] = "evidence_incomplete"
    return dispositions


def build_selection(
    summary: dict[str, Any] | None = None,
    ordering_review: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prioritization = build_post_l0_prioritization()
    summary = _read_json(DEFAULT_EVIDENCE) if summary is None else summary
    ordering_review = _read_json(DEFAULT_ORDERING_REVIEW) if ordering_review is None else ordering_review
    dispositions = classify_current_candidates(summary)

    if any(value == "evidence_incomplete" for value in dispositions.values()):
        eligible: list[str] = []
        selected = None
        status = "blocked_incomplete_manufacturer_evidence"
        ordering_result = None
    else:
        eligible = [series for series in CURRENT_SHORTLIST if dispositions[series] == "ordering_review_candidate"]
        if not eligible:
            selected = None
            status = "blocked_no_active_clean_candidate"
            ordering_result = None
        elif len(eligible) > 1:
            selected = None
            status = "blocked_multiple_active_candidates_require_new_comparison"
            ordering_result = "new_current_ordering_comparison_required"
        else:
            validate_ordering_review(ordering_review, eligible)
            selected = eligible[0]
            status = "selected_only_remaining_active_clean_candidate_after_lifecycle_and_ordering_evidence"
            ordering_result = "complete_for_only_remaining_active_clean_candidate"

    candidate_evidence: dict[str, Any] = {}
    for series in CURRENT_SHORTLIST:
        row = summary["by_series"][series]
        candidate_evidence[series] = {
            "representative_targets": row["attempted_targets"],
            "verified_identity_targets": row["verified_identity_targets"],
            "active_candidate_targets": row["active_candidate_targets"],
            "lifecycle_excluded_targets": row["lifecycle_excluded_targets"],
            "active_exact_icpns_observed": row["active_exact_icpns"],
            "excluded_non_active_part_numbers": row["excluded_non_active_part_numbers"],
            "manual_review": row["manual_review"],
            "source_unavailable_404": row["source_unavailable_404"],
            "commercial_identity_access_clean": row["commercial_identity_access_clean"],
            "disposition": dispositions[series],
            "rejected_for_future_support": False,
        }

    production = prioritization["production_invariants"]
    return {
        "schema_version": 1,
        "selection_id": SELECTION_ID,
        "selection_date": "2026-09-12",
        "scope": "next_family_research_only",
        "production_prestate": {
            "exact_icpns": production["exact_icpn_count"],
            "base_devices": production["base_device_count"],
            "stm32_families": len(production["family_exact_icpn_counts"]),
            "stm32l0_exact_icpns": production["family_exact_icpn_counts"]["STM32L0"],
        },
        "current_shortlist": list(CURRENT_SHORTLIST),
        "commercial_identity_authority": COMMERCIAL_IDENTITY_AUTHORITY,
        "retained_evidence_origin": "stm32-post-c0-official-st-evidence-accessibility-probe-v1",
        "candidate_evidence": candidate_evidence,
        "ordering_review_candidates": eligible,
        "ordering_evidence_result": ordering_result,
        "selection_status": status,
        "selected_next_research_family": selected,
        "selection_reason": (
            "STM32L1 remains lifecycle-deprioritized by retained official-ST exact-variant evidence; "
            "STM32L4 is the only current shortlist family with all representative targets Active and complete official-ST Ordering Information evidence."
            if selected == "STM32L4" else None
        ),
        "authority_boundaries": {
            "canonical_admission_authorized": False,
            "exact_icpn_publication_authorized": False,
            "flash_geometry_qualified": False,
            "option_security_semantics_qualified": False,
            "physical_hil_qualified": False,
            "production_write_authorized": False,
            "programming_algorithm_equivalence": False,
            "programming_policy_defined": False,
            "runtime_programming_support_claimed": False,
            "socket_physical_validation_claimed": False,
            "ppu_physical_validation_claimed": False,
        },
    }


def selection_is_clean(selection: dict[str, Any]) -> bool:
    candidates = selection.get("candidate_evidence", {})
    return (
        selection.get("current_shortlist") == ["STM32L1", "STM32L4"]
        and selection.get("selected_next_research_family") == "STM32L4"
        and selection.get("ordering_review_candidates") == ["STM32L4"]
        and selection.get("ordering_evidence_result") == "complete_for_only_remaining_active_clean_candidate"
        and selection.get("selection_status") == "selected_only_remaining_active_clean_candidate_after_lifecycle_and_ordering_evidence"
        and candidates.get("STM32L1", {}).get("lifecycle_excluded_targets") == 3
        and candidates.get("STM32L1", {}).get("active_candidate_targets") == 1
        and candidates.get("STM32L4", {}).get("lifecycle_excluded_targets") == 0
        and candidates.get("STM32L4", {}).get("active_candidate_targets") == 24
        and selection.get("production_prestate") == {
            "exact_icpns": 1272,
            "base_devices": 392,
            "stm32_families": 11,
            "stm32l0_exact_icpns": 360,
        }
        and _all_false(selection.get("authority_boundaries"))
    )


def main() -> int:
    result = build_selection()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if selection_is_clean(result) else 1


if __name__ == "__main__":
    raise SystemExit(main())

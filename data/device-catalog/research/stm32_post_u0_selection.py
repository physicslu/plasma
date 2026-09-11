#!/usr/bin/env python3
"""Post-U0 STM32 next-family research selection policy.

This policy consumes retained authoritative ST Quality & Reliability evidence and
an independent official-ST Ordering Information review. It may select the next
research family only; it never admits devices or claims programming/runtime
support.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from st_product_page_acquisition import AcquisitionError
from stm32_post_u0_evidence_probe import EXPECTED_SHORTLIST, EXPECTED_SURFACES, EXPECTED_TARGET_COUNT

HERE = Path(__file__).resolve().parent
DEFAULT_EVIDENCE = HERE / "evidence" / "stm32-c0-l1-l0-post-u0-live-2026-09-11" / "probe-summary.json"
DEFAULT_ORDERING_REVIEW = HERE / "stm32-c0-l0-post-u0-ordering-authority-review.json"
AUTHORITY_SURFACE = "quality_and_reliability_part_number"
SELECTION_ID = "stm32-post-u0-next-family-selection-v1"


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise AcquisitionError(f"{path}: JSON object required")
    return payload


def _all_false(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def validate_authoritative_summary(summary: dict[str, Any]) -> None:
    if summary.get("schema_version") != 1 or summary.get("phase") != "C0.0":
        raise AcquisitionError("unsupported post-U0 evidence summary")
    if tuple(summary.get("candidate_series", [])) != EXPECTED_SHORTLIST:
        raise AcquisitionError("post-U0 evidence candidate order drifted")
    if summary.get("attempted_targets") != EXPECTED_TARGET_COUNT:
        raise AcquisitionError("post-U0 evidence target count drifted")
    if summary.get("selected_next_research_family") is not None:
        raise AcquisitionError("evidence probe must remain pre-selection")
    if not _all_false(summary.get("claims")):
        raise AcquisitionError("evidence probe claims escaped fail-closed state")

    expected_counts = {series: len(EXPECTED_SURFACES[series]["subfamilies"]) for series in EXPECTED_SHORTLIST}
    by_series = summary.get("by_series")
    if not isinstance(by_series, dict):
        raise AcquisitionError("evidence summary lacks by_series")
    for series, attempted in expected_counts.items():
        row = by_series.get(series)
        if not isinstance(row, dict) or row.get("attempted_targets") != attempted:
            raise AcquisitionError(f"{series}: evidence target partition drifted")

    results = summary.get("results")
    if not isinstance(results, list) or len(results) != EXPECTED_TARGET_COUNT:
        raise AcquisitionError("authoritative evidence result count drifted")
    for result in results:
        if not isinstance(result, dict):
            raise AcquisitionError("authoritative evidence result must be object")
        if result.get("acquisition_status") != "success":
            continue
        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            raise AcquisitionError("successful evidence result lacks evidence object")
        if evidence.get("evidence_surface") != AUTHORITY_SURFACE:
            raise AcquisitionError(
                f"{result.get('base_device')}: non-authoritative identity surface "
                f"{evidence.get('evidence_surface')!r}"
            )


def classify_series(summary: dict[str, Any]) -> dict[str, str]:
    validate_authoritative_summary(summary)
    out: dict[str, str] = {}
    by_series = summary["by_series"]
    for series in EXPECTED_SHORTLIST:
        row = by_series[series]
        attempted = int(row["attempted_targets"])
        if (
            row.get("commercial_identity_access_clean") is not True
            or int(row.get("manual_review", 0)) != 0
            or int(row.get("source_unavailable_404", 0)) != 0
            or int(row.get("verified_identity_targets", 0)) != attempted
        ):
            out[series] = "evidence_incomplete"
        elif int(row.get("lifecycle_excluded_targets", 0)) > 0:
            out[series] = "deprioritized_for_next_family_research_due_to_lifecycle"
        elif int(row.get("active_candidate_targets", 0)) == attempted:
            out[series] = "ordering_review_candidate"
        else:
            out[series] = "evidence_incomplete"
    return out


def validate_ordering_review(review: dict[str, Any], required_series: list[str]) -> None:
    if review.get("schema_version") != 1:
        raise AcquisitionError("unsupported Ordering Information review")
    method = review.get("method")
    if not isinstance(method, dict) or method.get("authority") != "official_st_datasheet":
        raise AcquisitionError("Ordering Information authority is not official ST datasheet")
    if method.get("transport_diagnostics_are_selection_evidence") is not False:
        raise AcquisitionError("transport diagnostics cannot score Ordering Information quality")
    if method.get("visual_screenshot_review_is_selection_gate") is not False:
        raise AcquisitionError("visual screenshot cache cannot gate selection")
    if not _all_false(review.get("claims")):
        raise AcquisitionError("Ordering Information review claims escaped fail-closed state")

    by_series = review.get("by_series")
    if not isinstance(by_series, dict):
        raise AcquisitionError("Ordering Information review lacks by_series")
    for series in required_series:
        row = by_series.get(series)
        if not isinstance(row, dict):
            raise AcquisitionError(f"{series}: Ordering Information review missing")
        if (
            row.get("blocking_evidence_issues") != 0
            or row.get("ordering_evidence_quality") != "complete"
            or row.get("ordering_authority_covered_targets") != row.get("representative_targets")
            or row.get("required_schema_complete_targets") != row.get("representative_targets")
            or row.get("revision_drift") is not False
        ):
            raise AcquisitionError(f"{series}: Ordering Information evidence is not complete/current")


def build_selection(
    summary: dict[str, Any],
    ordering_review: dict[str, Any],
) -> dict[str, Any]:
    dispositions = classify_series(summary)
    eligible = [series for series in EXPECTED_SHORTLIST if dispositions[series] == "ordering_review_candidate"]

    selected: str | None = None
    selection_status: str
    if not eligible:
        selection_status = "blocked_no_active_clean_candidate"
    elif any(dispositions[series] == "evidence_incomplete" for series in EXPECTED_SHORTLIST):
        selection_status = "blocked_incomplete_manufacturer_evidence"
    else:
        validate_ordering_review(ordering_review, eligible)
        comparison = ordering_review.get("comparison")
        if not isinstance(comparison, dict):
            raise AcquisitionError("Ordering Information comparison missing")
        reviewed = comparison.get("eligible_for_current_priority_tiebreak")
        if reviewed != eligible:
            raise AcquisitionError(
                f"Ordering Information comparison set drifted: expected {eligible}, got {reviewed}"
            )
        if comparison.get("result") != "equivalent_required_ordering_evidence_quality":
            selection_status = "blocked_unequal_or_unresolved_ordering_evidence"
        else:
            selected = eligible[0]
            selection_status = "selected_by_current_shortlist_order_after_equivalent_evidence"

    candidate_evidence: dict[str, Any] = {}
    for series in EXPECTED_SHORTLIST:
        row = summary["by_series"][series]
        candidate_evidence[series] = {
            "representative_targets": row["attempted_targets"],
            "verified_identity_targets": row["verified_identity_targets"],
            "active_candidate_targets": row["active_candidate_targets"],
            "lifecycle_excluded_targets": row["lifecycle_excluded_targets"],
            "source_unavailable_404": row["source_unavailable_404"],
            "manual_review": row["manual_review"],
            "active_exact_icpns_observed": row["active_exact_icpns"],
            "commercial_identity_access_clean": row["commercial_identity_access_clean"],
            "disposition": dispositions[series],
            "rejected_for_future_support": False,
        }

    return {
        "schema_version": 1,
        "selection_id": SELECTION_ID,
        "selection_date": "2026-09-11",
        "scope": "next_family_research_only",
        "current_shortlist": list(EXPECTED_SHORTLIST),
        "commercial_identity_authority": "official_st_quality_and_reliability_exact_part_number_marketing_status",
        "sample_buy_is_identity_gate": False,
        "candidate_evidence": candidate_evidence,
        "ordering_review_candidates": eligible,
        "ordering_evidence_result": (
            ordering_review.get("comparison", {}).get("result") if eligible else None
        ),
        "selection_status": selection_status,
        "selected_next_research_family": selected,
        "tie_break_policy": "current_post_u0_cross_family_prioritization_order_after_equivalent_required_evidence",
        "authority_boundaries": {
            "canonical_admission_authorized": False,
            "flash_geometry_qualified": False,
            "option_security_semantics_qualified": False,
            "physical_hil_qualified": False,
            "production_write_authorized": False,
            "programming_algorithm_equivalence": False,
            "programming_policy_defined": False,
            "runtime_programming_support_claimed": False,
        },
    }


def main() -> int:
    summary = _read_json(DEFAULT_EVIDENCE)
    review = _read_json(DEFAULT_ORDERING_REVIEW)
    result = build_selection(summary, review)
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if result["selected_next_research_family"] else 1


if __name__ == "__main__":
    raise SystemExit(main())

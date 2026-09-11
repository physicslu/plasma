#!/usr/bin/env python3
"""Negative controls for post-U0 STM32 next-family research selection."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32_post_u0_selection import (
    AUTHORITY_SURFACE,
    DEFAULT_ORDERING_REVIEW,
    build_selection,
    validate_authoritative_summary,
)

HERE = Path(__file__).resolve().parent
DIAGNOSTIC = HERE / "evidence" / "stm32-c0-l1-l0-post-u0-live-2026-09-11" / "probe-summary.json"


def readj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def as_authoritative(summary: dict) -> dict:
    """Convert retained diagnostic facts into a Q&R-shaped policy fixture only."""
    out = copy.deepcopy(summary)
    out["commercial_identity_authority"] = "official_st_quality_and_reliability_exact_part_number_marketing_status"
    out["sample_buy_is_identity_gate"] = False
    for result in out["results"]:
        if result.get("acquisition_status") == "success":
            result["evidence"]["evidence_surface"] = AUTHORITY_SURFACE
            result["evidence"]["commercial_identity_authority"] = out["commercial_identity_authority"]
            result["evidence"]["sample_buy_is_identity_gate"] = False
    return out


class PostU0SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.diagnostic = readj(DIAGNOSTIC)
        self.summary = as_authoritative(self.diagnostic)
        self.review = readj(DEFAULT_ORDERING_REVIEW)

    def test_dual_surface_diagnostic_is_not_authoritative_selection_evidence(self) -> None:
        with self.assertRaises(AcquisitionError):
            validate_authoritative_summary(self.diagnostic)

    def test_equivalent_c0_l0_evidence_selects_current_priority_leader_c0(self) -> None:
        result = build_selection(self.summary, self.review)
        self.assertEqual(result["ordering_review_candidates"], ["STM32C0", "STM32L0"])
        self.assertEqual(result["selected_next_research_family"], "STM32C0")
        self.assertEqual(
            result["selection_status"],
            "selected_by_current_shortlist_order_after_equivalent_evidence",
        )
        self.assertEqual(
            result["candidate_evidence"]["STM32L1"]["disposition"],
            "deprioritized_for_next_family_research_due_to_lifecycle",
        )
        self.assertFalse(result["candidate_evidence"]["STM32L1"]["rejected_for_future_support"])
        self.assertTrue(all(value is False for value in result["authority_boundaries"].values()))

    def test_manual_review_blocks_selection(self) -> None:
        summary = copy.deepcopy(self.summary)
        summary["by_series"]["STM32L0"]["manual_review"] = 1
        summary["by_series"]["STM32L0"]["commercial_identity_access_clean"] = False
        result = build_selection(summary, self.review)
        self.assertIsNone(result["selected_next_research_family"])
        self.assertEqual(result["selection_status"], "blocked_incomplete_manufacturer_evidence")

    def test_source_unavailable_blocks_selection(self) -> None:
        summary = copy.deepcopy(self.summary)
        summary["by_series"]["STM32L0"]["source_unavailable_404"] = 1
        summary["by_series"]["STM32L0"]["commercial_identity_access_clean"] = False
        result = build_selection(summary, self.review)
        self.assertIsNone(result["selected_next_research_family"])
        self.assertEqual(result["selection_status"], "blocked_incomplete_manufacturer_evidence")

    def test_c0_lifecycle_exclusion_removes_c0_from_ordering_tiebreak(self) -> None:
        summary = copy.deepcopy(self.summary)
        summary["by_series"]["STM32C0"]["lifecycle_excluded_targets"] = 1
        summary["by_series"]["STM32C0"]["active_candidate_targets"] = 5
        review = copy.deepcopy(self.review)
        review["comparison"]["eligible_for_current_priority_tiebreak"] = ["STM32L0"]
        result = build_selection(summary, review)
        self.assertEqual(result["ordering_review_candidates"], ["STM32L0"])
        self.assertEqual(result["selected_next_research_family"], "STM32L0")

    def test_ordering_revision_drift_fails_closed(self) -> None:
        review = copy.deepcopy(self.review)
        review["by_series"]["STM32L0"]["revision_drift"] = True
        with self.assertRaises(AcquisitionError):
            build_selection(self.summary, review)

    def test_ordering_eligible_set_mismatch_fails_closed(self) -> None:
        review = copy.deepcopy(self.review)
        review["comparison"]["eligible_for_current_priority_tiebreak"] = ["STM32C0"]
        with self.assertRaises(AcquisitionError):
            build_selection(self.summary, review)

    def test_ordering_review_cannot_authorize_support_claims(self) -> None:
        review = copy.deepcopy(self.review)
        review["claims"]["programming_policy_defined"] = True
        with self.assertRaises(AcquisitionError):
            build_selection(self.summary, review)


if __name__ == "__main__":
    unittest.main()

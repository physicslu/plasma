#!/usr/bin/env python3
"""Negative controls for post-U0 STM32 next-family research selection."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32_post_u0_selection import (
    DEFAULT_EVIDENCE,
    DEFAULT_ORDERING_REVIEW,
    DEFAULT_QR_DIAGNOSTIC,
    build_selection,
    validate_authoritative_summary,
    validate_qr_only_method_diagnostic,
)


def readj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class PostU0SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = readj(DEFAULT_EVIDENCE)
        self.qr_diagnostic = readj(DEFAULT_QR_DIAGNOSTIC)
        self.review = readj(DEFAULT_ORDERING_REVIEW)

    def test_retained_dual_surface_exact_set_evidence_is_authoritative(self) -> None:
        validate_authoritative_summary(self.summary)
        self.assertEqual(self.summary["attempted_targets"], 26)
        self.assertEqual(self.summary["manual_review_targets"], 0)
        self.assertTrue(self.summary["bounded_probe_complete"])

    def test_qr_only_run_is_method_diagnostic_not_family_failure(self) -> None:
        validate_qr_only_method_diagnostic(self.qr_diagnostic)
        self.assertEqual(self.qr_diagnostic["by_series"]["STM32C0"]["manual_review"], 6)
        with self.assertRaises(AcquisitionError):
            validate_authoritative_summary(self.qr_diagnostic)

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

    def test_manual_review_cannot_enter_selection(self) -> None:
        summary = copy.deepcopy(self.summary)
        summary["manual_review_targets"] = 1
        summary["bounded_probe_complete"] = False
        with self.assertRaises(AcquisitionError):
            build_selection(summary, self.review)

    def test_undispositioned_target_cannot_enter_selection(self) -> None:
        summary = copy.deepcopy(self.summary)
        summary["dispositioned_targets"] = 25
        summary["bounded_probe_complete"] = False
        with self.assertRaises(AcquisitionError):
            build_selection(summary, self.review)

    def test_non_st_source_fails_closed(self) -> None:
        summary = copy.deepcopy(self.summary)
        summary["results"][0]["source_url"] = "https://example.invalid/part"
        with self.assertRaises(AcquisitionError):
            build_selection(summary, self.review)

    def test_joined_exact_identity_set_mismatch_fails_closed(self) -> None:
        summary = copy.deepcopy(self.summary)
        evidence = summary["results"][0]["evidence"]
        evidence["exact_icpns"] = evidence["exact_icpns"][:-1]
        with self.assertRaises(AcquisitionError):
            build_selection(summary, self.review)

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

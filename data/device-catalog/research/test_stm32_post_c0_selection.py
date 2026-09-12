#!/usr/bin/env python3
"""Negative controls for post-C0 STM32 next-family research selection."""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32_post_c0_selection import (
    DEFAULT_EVIDENCE,
    DEFAULT_ORDERING_REVIEW,
    build_selection,
    validate_authoritative_summary,
)


def readj(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


class PostC0SelectionTests(unittest.TestCase):
    def setUp(self) -> None:
        self.summary = readj(DEFAULT_EVIDENCE)
        self.review = readj(DEFAULT_ORDERING_REVIEW)

    def test_retained_dual_surface_exact_set_evidence_is_authoritative(self) -> None:
        validate_authoritative_summary(self.summary)
        self.assertEqual(self.summary["attempted_targets"], 44)
        self.assertEqual(self.summary["dispositioned_targets"], 44)
        self.assertEqual(self.summary["manual_review_targets"], 0)
        self.assertTrue(self.summary["bounded_probe_complete"])

    def test_equivalent_l0_l4_evidence_selects_current_priority_leader_l0(self) -> None:
        result = build_selection(self.summary, self.review)
        self.assertEqual(result["ordering_review_candidates"], ["STM32L0", "STM32L4"])
        self.assertEqual(result["selected_next_research_family"], "STM32L0")
        self.assertEqual(
            result["selection_status"],
            "selected_by_current_shortlist_order_after_equivalent_evidence",
        )
        self.assertEqual(
            result["candidate_evidence"]["STM32L1"]["disposition"],
            "deprioritized_for_next_family_research_due_to_lifecycle",
        )
        self.assertFalse(result["candidate_evidence"]["STM32L1"]["rejected_for_future_support"])
        self.assertEqual(
            result["candidate_evidence"]["STM32L4"]["disposition"],
            "ordering_review_candidate",
        )
        self.assertTrue(all(value is False for value in result["authority_boundaries"].values()))

    def test_l4_non_active_variants_do_not_become_family_lifecycle_exclusion(self) -> None:
        row = self.summary["by_series"]["STM32L4"]
        self.assertEqual(row["active_candidate_targets"], 24)
        self.assertEqual(row["lifecycle_excluded_targets"], 0)
        self.assertEqual(row["excluded_non_active_part_numbers"], 3)
        result = build_selection(self.summary, self.review)
        self.assertIn("STM32L4", result["ordering_review_candidates"])

    def test_manual_review_cannot_enter_selection(self) -> None:
        summary = copy.deepcopy(self.summary)
        summary["manual_review_targets"] = 1
        summary["bounded_probe_complete"] = False
        with self.assertRaises(AcquisitionError):
            build_selection(summary, self.review)

    def test_undispositioned_target_cannot_enter_selection(self) -> None:
        summary = copy.deepcopy(self.summary)
        summary["dispositioned_targets"] = 43
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
        evidence = summary["results"][20]["evidence"]
        evidence["exact_icpns"] = evidence["exact_icpns"][:-1]
        with self.assertRaises(AcquisitionError):
            build_selection(summary, self.review)

    def test_ordering_revision_drift_fails_closed(self) -> None:
        review = copy.deepcopy(self.review)
        review["by_series"]["STM32L4"]["revision_drift"] = True
        with self.assertRaises(AcquisitionError):
            build_selection(self.summary, review)

    def test_ordering_eligible_set_mismatch_fails_closed(self) -> None:
        review = copy.deepcopy(self.review)
        review["comparison"]["eligible_for_current_priority_tiebreak"] = ["STM32L0"]
        with self.assertRaises(AcquisitionError):
            build_selection(self.summary, review)

    def test_ordering_review_cannot_authorize_support_claims(self) -> None:
        review = copy.deepcopy(self.review)
        review["claims"]["programming_policy_defined"] = True
        with self.assertRaises(AcquisitionError):
            build_selection(self.summary, review)


if __name__ == "__main__":
    unittest.main()

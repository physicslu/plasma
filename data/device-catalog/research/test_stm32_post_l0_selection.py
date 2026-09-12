#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import unittest

from st_product_page_acquisition import AcquisitionError
from stm32_post_l0_selection import (
    CURRENT_SHORTLIST,
    DEFAULT_EVIDENCE,
    DEFAULT_ORDERING_REVIEW,
    build_post_l0_prioritization,
    build_selection,
    selection_is_clean,
)


class STM32PostL0SelectionTests(unittest.TestCase):
    @staticmethod
    def _read(path):
        return json.loads(path.read_text(encoding="utf-8"))

    def test_post_l0_production_and_shortlist_are_frozen(self) -> None:
        report = build_post_l0_prioritization()
        production = report["production_invariants"]
        self.assertEqual(production["exact_icpn_count"], 1272)
        self.assertEqual(production["base_device_count"], 392)
        self.assertEqual(len(production["family_exact_icpn_counts"]), 11)
        self.assertEqual(production["family_exact_icpn_counts"]["STM32L0"], 360)
        self.assertEqual(
            [item["plasma_series"] for item in report["research_shortlist"]],
            list(CURRENT_SHORTLIST),
        )
        self.assertIsNone(report["selected_next_research_family"])
        self.assertTrue(all(value is False for value in report["claims"].values()))

    def test_retained_authority_selects_l4(self) -> None:
        selection = build_selection()
        self.assertTrue(selection_is_clean(selection))
        self.assertEqual(selection["selected_next_research_family"], "STM32L4")
        self.assertEqual(selection["ordering_review_candidates"], ["STM32L4"])
        self.assertEqual(
            selection["selection_status"],
            "selected_only_remaining_active_clean_candidate_after_lifecycle_and_ordering_evidence",
        )

    def test_l1_is_deprioritized_not_rejected(self) -> None:
        selection = build_selection()
        l1 = selection["candidate_evidence"]["STM32L1"]
        self.assertEqual(l1["representative_targets"], 4)
        self.assertEqual(l1["active_candidate_targets"], 1)
        self.assertEqual(l1["lifecycle_excluded_targets"], 3)
        self.assertEqual(l1["excluded_non_active_part_numbers"], 8)
        self.assertEqual(l1["disposition"], "deprioritized_for_next_family_research_due_to_lifecycle")
        self.assertFalse(l1["rejected_for_future_support"])

    def test_l4_ordering_authority_is_complete_and_current(self) -> None:
        selection = build_selection()
        l4 = selection["candidate_evidence"]["STM32L4"]
        self.assertEqual(l4["representative_targets"], 24)
        self.assertEqual(l4["active_candidate_targets"], 24)
        self.assertEqual(l4["lifecycle_excluded_targets"], 0)
        self.assertEqual(l4["active_exact_icpns_observed"], 60)

        review = self._read(DEFAULT_ORDERING_REVIEW)
        row = review["by_series"]["STM32L4"]
        self.assertEqual(row["representative_targets"], 24)
        self.assertEqual(row["ordering_authority_covered_targets"], 24)
        self.assertEqual(row["required_schema_complete_targets"], 24)
        self.assertEqual(row["blocking_evidence_issues"], 0)
        self.assertEqual(row["ordering_evidence_quality"], "complete")
        self.assertFalse(row["revision_drift"])

    def test_two_active_candidates_do_not_reuse_stale_tiebreak(self) -> None:
        summary = self._read(DEFAULT_EVIDENCE)
        mutated = copy.deepcopy(summary)
        l1 = mutated["by_series"]["STM32L1"]
        l1["active_candidate_targets"] = l1["attempted_targets"]
        l1["lifecycle_excluded_targets"] = 0
        selection = build_selection(summary=mutated)
        self.assertIsNone(selection["selected_next_research_family"])
        self.assertEqual(
            selection["selection_status"],
            "blocked_multiple_active_candidates_require_new_comparison",
        )

    def test_ordering_revision_drift_fails_closed(self) -> None:
        review = self._read(DEFAULT_ORDERING_REVIEW)
        mutated = copy.deepcopy(review)
        mutated["by_series"]["STM32L4"]["revision_drift"] = True
        with self.assertRaises(AcquisitionError):
            build_selection(ordering_review=mutated)

    def test_no_support_or_publication_authority_escapes(self) -> None:
        selection = build_selection()
        self.assertEqual(set(selection["authority_boundaries"].values()), {False})


if __name__ == "__main__":
    unittest.main()

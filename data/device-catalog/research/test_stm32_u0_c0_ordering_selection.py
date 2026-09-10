#!/usr/bin/env python3
"""Negative controls for STM32 U0/C0 next-family research selection."""
from __future__ import annotations
import copy, json, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
REVIEW = json.loads((HERE/"stm32-u0-c0-ordering-authority-review.json").read_text())
SELECTION = json.loads((HERE/"stm32-next-family-selection.json").read_text())

def allowed(review: dict, selection: dict) -> bool:
    if review.get("comparison",{}).get("result") != "equivalent_required_evidence_quality":
        return False
    for family in ("STM32U0","STM32C0"):
        s = review.get("by_series",{}).get(family,{})
        if s.get("blocking_evidence_issues") != 0 or s.get("ordering_evidence_quality") != "complete":
            return False
        if s.get("ordering_authority_covered_targets") != s.get("representative_targets"):
            return False
        if s.get("required_schema_complete_targets") != s.get("representative_targets"):
            return False
    d = selection.get("decision",{})
    return (
        d.get("tie_break_policy") == "frozen_cross_family_prioritization_order"
        and d.get("frozen_shortlist") == ["STM32U0","STM32C0","STM32L1"]
        and d.get("selected_next_research_family") == "STM32U0"
        and d.get("selection_scope") == "next_family_research_only"
    )

class NegativeControls(unittest.TestCase):
    def test_authoritative_state_allows_selection(self):
        self.assertTrue(allowed(REVIEW, SELECTION))
    def test_incomplete_u0_coverage_fails_closed(self):
        r = copy.deepcopy(REVIEW); r["by_series"]["STM32U0"]["ordering_authority_covered_targets"] = 2
        self.assertFalse(allowed(r, SELECTION))
    def test_c0_blocker_fails_closed(self):
        r = copy.deepcopy(REVIEW); r["by_series"]["STM32C0"]["blocking_evidence_issues"] = 1
        self.assertFalse(allowed(r, SELECTION))
    def test_non_tie_cannot_use_tiebreak(self):
        r = copy.deepcopy(REVIEW); r["comparison"]["result"] = "STM32C0_higher_evidence_quality"
        self.assertFalse(allowed(r, SELECTION))
    def test_shortlist_reorder_cannot_silently_keep_u0(self):
        s = copy.deepcopy(SELECTION); s["decision"]["frozen_shortlist"] = ["STM32C0","STM32U0","STM32L1"]
        self.assertFalse(allowed(REVIEW, s))
    def test_no_admission_or_programming_authority(self):
        self.assertEqual(set(SELECTION["authority_boundaries"].values()), {False})

if __name__ == "__main__":
    unittest.main()

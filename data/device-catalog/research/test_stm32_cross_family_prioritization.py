#!/usr/bin/env python3
"""Regression and negative-control tests for STM32 cross-family prioritization."""
from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from stm32_cross_family_prioritization import (
    DEFAULT_CATALOG,
    DEFAULT_MANIFEST,
    build_prioritization,
)

CURRENT_SHORTLIST = ["STM32L1", "STM32L0", "STM32L4"]


class STM32CrossFamilyPrioritizationTests(unittest.TestCase):
    def _current(self):
        return build_prioritization(catalog_path=DEFAULT_CATALOG, manifest_path=DEFAULT_MANIFEST)

    def test_current_post_u0_inventory_and_shortlist_are_deterministic(self) -> None:
        report = self._current()
        self.assertEqual(report["policy_id"], "stm32-cross-family-prioritization-v1")
        self.assertEqual(report["production_invariants"]["exact_icpn_count"], 912)
        self.assertEqual(report["production_invariants"]["base_device_count"], 293)
        self.assertEqual(report["production_invariants"]["production_series"], [
            "STM32C0", "STM32F0", "STM32F1", "STM32F2", "STM32F3",
            "STM32F4", "STM32F7", "STM32G0", "STM32G4", "STM32U0",
        ])
        self.assertEqual(report["production_invariants"]["family_exact_icpn_counts"]["STM32U0"], 68)
        self.assertEqual(report["inventory"]["candidate_series_count"], 13)
        self.assertEqual(report["inventory"]["candidate_source_row_count"], 1226)
        self.assertEqual(report["inventory"]["candidate_ordering_pattern_rows"], 855)
        self.assertEqual(report["inventory"]["shortlist_eligible_series_count"], 3)
        self.assertEqual(report["inventory"]["cohort_counts"], {
            "high_complexity_requires_partitioned_scope": 1,
            "standard_nonwireless_research": 3,
            "trustzone_requires_security_scope": 3,
            "wireless_requires_dedicated_scope": 6,
        })
        self.assertEqual(
            [item["plasma_series"] for item in report["research_shortlist"]],
            CURRENT_SHORTLIST,
        )
        self.assertNotIn("STM32U0", {item["plasma_series"] for item in report["candidates"]})
        self.assertNotIn("STM32C0", {item["plasma_series"] for item in report["candidates"]})
        self.assertEqual(report["production_invariants"]["family_exact_icpn_counts"]["STM32C0"], 209)
        self.assertIsNone(report["selected_next_research_family"])
        self.assertTrue(all(value is False for value in report["claims"].values()))

    def test_risk_cohorts_are_explicit_and_do_not_leak_into_shortlist(self) -> None:
        report = self._current()
        candidates = {item["plasma_series"]: item for item in report["candidates"]}
        shortlist = {item["plasma_series"] for item in report["research_shortlist"]}
        for series in ("STM32W108", "STM32WLX", "STM32WBX", "STM32WBA2X", "STM32WBA5X", "STM32WBA6X"):
            self.assertEqual(candidates[series]["cohort"], "wireless_requires_dedicated_scope")
            self.assertFalse(candidates[series]["shortlist_eligible"])
            self.assertNotIn(series, shortlist)
        for series in ("STM32L5", "STM32U3", "STM32U5"):
            self.assertEqual(candidates[series]["cohort"], "trustzone_requires_security_scope")
            self.assertFalse(candidates[series]["shortlist_eligible"])
            self.assertNotIn(series, shortlist)
        self.assertEqual(candidates["STM32H7"]["cohort"], "high_complexity_requires_partitioned_scope")
        self.assertEqual(len(candidates["STM32H7"]["target_configs"]), 2)
        self.assertFalse(candidates["STM32H7"]["shortlist_eligible"])
        self.assertNotIn("STM32H7", shortlist)

    def test_mixed_identifier_kinds_are_not_automatically_rejected(self) -> None:
        report = self._current()
        candidates = {item["plasma_series"]: item for item in report["candidates"]}
        # Current shortlist families are deliberately allowed because the next gate
        # can operate on their bounded ordering-pattern sub-surface. CMSIS names
        # are not promoted to commercial identities.
        for series in CURRENT_SHORTLIST:
            self.assertGreater(candidates[series]["ordering_pattern_rows"], 0)
            self.assertGreater(candidates[series]["cmsis_device_name_rows"], 0)
            self.assertTrue(candidates[series]["structural_gate_pass"])
            self.assertTrue(candidates[series]["shortlist_eligible"])

    def test_single_target_is_a_fail_closed_structural_gate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "catalog.csv"
            with DEFAULT_CATALOG.open(newline="", encoding="utf-8") as src:
                reader = csv.DictReader(src)
                rows = list(reader)
                fields = reader.fieldnames
            self.assertIsNotNone(fields)
            mutated = False
            for row in rows:
                if row.get("plasma_series") == "STM32L1" and row.get("identifier_kind") == "ordering_pattern":
                    row["target_config"] = "tcl/target/artificial-second-l1.cfg"
                    mutated = True
                    break
            self.assertTrue(mutated)
            with path.open("w", newline="", encoding="utf-8") as dst:
                writer = csv.DictWriter(dst, fieldnames=fields, lineterminator="\n")
                writer.writeheader()
                writer.writerows(rows)
            report = build_prioritization(catalog_path=path, manifest_path=DEFAULT_MANIFEST)
            candidates = {item["plasma_series"]: item for item in report["candidates"]}
            self.assertFalse(candidates["STM32L1"]["structural_gate_pass"])
            self.assertFalse(candidates["STM32L1"]["shortlist_eligible"])
            self.assertNotIn("STM32L1", {item["plasma_series"] for item in report["research_shortlist"]})

    def test_shortlist_never_becomes_selection_or_programming_claim(self) -> None:
        report = self._current()
        self.assertEqual(len(report["research_shortlist"]), 3)
        self.assertEqual(
            [item["plasma_series"] for item in report["research_shortlist"]],
            CURRENT_SHORTLIST,
        )
        self.assertIsNone(report["selected_next_research_family"])
        for item in report["research_shortlist"]:
            self.assertEqual(
                item["next_required_gate"],
                "bounded_official_manufacturer_evidence_accessibility_probe",
            )
        for claim in (
            "production_write_authorized",
            "exact_icpn_claimed_from_openocd",
            "marketing_lifecycle_claimed_from_openocd",
            "programming_policy_defined",
            "programming_algorithm_equivalence_claimed",
            "selected_next_research_family",
            "shortlist_is_admission_ready",
            "runtime_programming_support_claimed",
        ):
            self.assertFalse(report["claims"][claim], claim)


if __name__ == "__main__":
    unittest.main()

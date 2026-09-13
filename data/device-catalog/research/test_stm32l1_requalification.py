#!/usr/bin/env python3
"""Regression and negative-control tests for STM32L1 lifecycle requalification."""
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path

from st_product_page_acquisition import AcquisitionError
from stm32l1_requalification import (
    DEFAULT_ORDERING,
    DEFAULT_PROVENANCE,
    DEFAULT_SUMMARY,
    DEFAULT_TARGETS,
    EXPECTED_ACTIVE,
    EXPECTED_EXCLUDED,
    build_requalification_result,
)


class STM32L1RequalificationTests(unittest.TestCase):
    def test_current_result_is_bounded_and_fail_closed(self) -> None:
        result = build_requalification_result()
        self.assertEqual(result["status"], "eligible_for_next_research_gate")
        self.assertEqual(result["active_subfamily_count"], 4)
        self.assertEqual(result["active_exact_icpn_evidence_count"], 9)
        self.assertEqual(result["non_active_exact_icpn_evidence_count"], 8)
        self.assertEqual(
            result["historical_single_page_false_negative_subfamilies"],
            ["STM32L100", "STM32L151", "STM32L152"],
        )
        self.assertTrue(result["ordering_information_coverage_complete"])
        self.assertIsNone(result["selected_next_research_family"])
        self.assertTrue(all(value is False for value in result["claims"].values()))

    def test_production_is_unchanged_and_l1_is_not_published(self) -> None:
        production = build_requalification_result()["production"]
        self.assertEqual(production, {
            "exact_icpn_count": 1718,
            "base_device_count": 530,
            "family_count": 12,
            "stm32l1_exact_icpn_count": 0,
        })

    def test_generation_companions_reverse_single_page_false_negative(self) -> None:
        summary = json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8"))
        by_subfamily = summary["by_subfamily"]
        for subfamily in ("STM32L100", "STM32L151", "STM32L152"):
            item = by_subfamily[subfamily]
            self.assertFalse(item["historical_representative_active"])
            self.assertTrue(item["generation_companion_active"])
            self.assertEqual(item["active_exact_icpns"], EXPECTED_ACTIVE[subfamily])
            self.assertEqual(item["excluded_non_active_icpns"], EXPECTED_EXCLUDED[subfamily])
        self.assertTrue(by_subfamily["STM32L162"]["historical_representative_active"])

    def test_ordering_authority_covers_all_active_subfamilies(self) -> None:
        ordering = json.loads(DEFAULT_ORDERING.read_text(encoding="utf-8"))
        self.assertEqual(ordering["coverage"]["required_subfamilies"], [
            "STM32L100", "STM32L151", "STM32L152", "STM32L162"
        ])
        self.assertEqual(ordering["coverage"]["covered_subfamilies"], [
            "STM32L100", "STM32L151", "STM32L152", "STM32L162"
        ])
        self.assertTrue(ordering["coverage"]["coverage_complete"])
        self.assertEqual(ordering["migration_authority"]["document"], "TN1176")

    def test_live_provenance_is_exactly_bound(self) -> None:
        provenance = json.loads(DEFAULT_PROVENANCE.read_text(encoding="utf-8"))
        self.assertEqual(provenance["workflow_run_id"], 34749400091)
        self.assertEqual(provenance["workflow_run_attempt"], 1)
        self.assertEqual(
            provenance["artifact_digest"],
            "sha256:b20ffce5cf4ab540fbed1458719c544ba06cfceb8f0ba10829034b76c0dbcf5f",
        )
        self.assertEqual(provenance["browser"]["playwright_version"], "1.62.0")
        self.assertEqual(provenance["browser"]["browser_version"], "151.0.7922.34")

    def test_missing_generation_companion_fails_closed(self) -> None:
        payload = json.loads(DEFAULT_TARGETS.read_text(encoding="utf-8"))
        payload["targets"] = [row for row in payload["targets"] if row["target_id"] != "STM32L151C6-generation-a"]
        payload["target_count"] = len(payload["targets"])
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "targets.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(AcquisitionError):
                build_requalification_result(targets_path=path)

    def test_false_negative_set_cannot_be_silently_rewritten(self) -> None:
        payload = copy.deepcopy(json.loads(DEFAULT_SUMMARY.read_text(encoding="utf-8")))
        payload["historical_single_page_false_negative_subfamilies"] = ["STM32L100"]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "summary.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(AcquisitionError):
                build_requalification_result(summary_path=path)


if __name__ == "__main__":
    unittest.main()

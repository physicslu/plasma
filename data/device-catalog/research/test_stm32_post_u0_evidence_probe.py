#!/usr/bin/env python3
"""Negative controls for the post-U0 STM32 C0.0 evidence-selection probe."""
from __future__ import annotations

import copy
import unittest

from st_product_page_acquisition import AcquisitionError
from stm32_post_u0_evidence_probe import (
    EXPECTED_SHORTLIST,
    EXPECTED_TARGET_COUNT,
    RateLimitedFetcher,
    current_prioritization,
    deterministic_targets,
    read_catalog,
    source_url_for_base,
)


class PostU0EvidenceProbeTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = read_catalog()

    def test_current_boundary_is_post_u0_and_unselected(self) -> None:
        report = current_prioritization()
        self.assertEqual(report["production_invariants"]["exact_icpn_count"], 703)
        self.assertEqual(report["production_invariants"]["base_device_count"], 243)
        self.assertEqual(report["production_invariants"]["family_exact_icpn_counts"]["STM32U0"], 68)
        self.assertEqual(
            tuple(item["plasma_series"] for item in report["research_shortlist"]),
            EXPECTED_SHORTLIST,
        )
        self.assertIsNone(report["selected_next_research_family"])
        self.assertTrue(all(value is False for value in report["claims"].values()))

    def test_deterministic_target_count_and_series_partition(self) -> None:
        targets = deterministic_targets(self.rows)
        self.assertEqual(len(targets), EXPECTED_TARGET_COUNT)
        counts = {series: sum(t.series == series for t in targets) for series in EXPECTED_SHORTLIST}
        self.assertEqual(counts, {"STM32C0": 6, "STM32L1": 4, "STM32L0": 16})
        self.assertEqual(len({(t.series, t.subfamily) for t in targets}), EXPECTED_TARGET_COUNT)

    def test_targets_are_lexical_min_ordering_bases_not_cmsis_aliases(self) -> None:
        targets = deterministic_targets(self.rows)
        for target in targets:
            ordering = []
            for row in self.rows:
                if (
                    row.get("plasma_series") == target.series
                    and row.get("subfamily") == target.subfamily
                    and row.get("identifier_kind") == "ordering_pattern"
                ):
                    part = row["part_number"]
                    ordering.append(part[:-2])
            self.assertTrue(ordering)
            self.assertEqual(target.base_device, min(ordering))

    def test_source_urls_are_official_st_and_slug_bound(self) -> None:
        for target in deterministic_targets(self.rows):
            self.assertEqual(target.source_url, source_url_for_base(target.base_device))
            self.assertTrue(target.source_url.startswith("https://www.st.com/en/microcontrollers-microprocessors/"))

    def test_surface_target_config_drift_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        mutated = False
        for row in rows:
            if row.get("plasma_series") == "STM32C0":
                row["target_config"] = "tcl/target/artificial-c0.cfg"
                mutated = True
                break
        self.assertTrue(mutated)
        with self.assertRaises(AcquisitionError):
            deterministic_targets(rows)

    def test_surface_identifier_kind_drift_fails_closed(self) -> None:
        rows = copy.deepcopy(self.rows)
        mutated = False
        for row in rows:
            if row.get("plasma_series") == "STM32L0" and row.get("identifier_kind") == "ordering_pattern":
                row["identifier_kind"] = "cmsis_device_name"
                mutated = True
                break
        self.assertTrue(mutated)
        with self.assertRaises(AcquisitionError):
            deterministic_targets(rows)

    def test_rate_limit_cannot_be_weakened_below_one_second(self) -> None:
        with self.assertRaises(AcquisitionError):
            RateLimitedFetcher(delay_seconds=0.5, fetcher=lambda *_: (b"", "", None, None))


if __name__ == "__main__":
    unittest.main()

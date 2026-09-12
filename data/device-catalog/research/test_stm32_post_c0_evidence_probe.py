#!/usr/bin/env python3
"""Boundary tests for the post-C0 STM32L1/L0/L4 evidence probe."""
from __future__ import annotations

import unittest

from st_product_page_acquisition import AcquisitionError
from stm32_post_c0_evidence_probe import (
    EXPECTED_SHORTLIST,
    EXPECTED_SURFACES,
    EXPECTED_TARGET_COUNT,
    current_prioritization,
    deterministic_targets,
    read_catalog,
    run_probe,
)


class STM32PostC0EvidenceProbeTests(unittest.TestCase):
    def test_current_post_c0_boundary_is_locked(self) -> None:
        report = current_prioritization()
        self.assertEqual(
            tuple(item["plasma_series"] for item in report["research_shortlist"]),
            EXPECTED_SHORTLIST,
        )
        self.assertEqual(report["production_invariants"]["exact_icpn_count"], 912)
        self.assertEqual(report["production_invariants"]["base_device_count"], 293)
        self.assertEqual(report["production_invariants"]["family_exact_icpn_counts"]["STM32C0"], 209)
        self.assertIsNone(report["selected_next_research_family"])

    def test_deterministic_targets_cover_every_guarded_subfamily_once(self) -> None:
        targets = deterministic_targets(read_catalog())
        self.assertEqual(len(targets), EXPECTED_TARGET_COUNT)
        self.assertEqual(EXPECTED_TARGET_COUNT, 44)
        observed = {(target.series, target.subfamily) for target in targets}
        expected = {
            (series, subfamily)
            for series in EXPECTED_SHORTLIST
            for subfamily in EXPECTED_SURFACES[series]["subfamilies"]
        }
        self.assertEqual(observed, expected)
        self.assertEqual(len(observed), EXPECTED_TARGET_COUNT)
        for target in targets:
            self.assertTrue(target.base_device.startswith(target.subfamily))
            self.assertTrue(target.source_url.startswith("https://www.st.com/"))

    def test_target_partition_is_4_16_24(self) -> None:
        targets = deterministic_targets(read_catalog())
        counts = {series: 0 for series in EXPECTED_SHORTLIST}
        for target in targets:
            counts[target.series] += 1
        self.assertEqual(counts, {"STM32L1": 4, "STM32L0": 16, "STM32L4": 24})

    def test_probe_never_selects_or_authorizes_production(self) -> None:
        targets = deterministic_targets(read_catalog())

        def fake_fetcher(source_url: str, timeout_seconds: float):
            return b"fixture", source_url, None, None

        def fake_builder(**kwargs):
            base = kwargs["base_device"]
            return {
                "exact_icpns": [base + "T6"],
                "excluded_non_active_part_numbers": [],
                "part_number_records": [{"icpn": base + "T6", "marketing_status": "Active"}],
            }

        summary = run_probe(targets=targets, fetcher=fake_fetcher, evidence_builder=fake_builder)
        self.assertTrue(summary["bounded_probe_complete"])
        self.assertIsNone(summary["selected_next_research_family"])
        self.assertTrue(all(value is False for value in summary["claims"].values()))

    def test_foreign_identity_fails_closed(self) -> None:
        targets = deterministic_targets(read_catalog())

        def fake_fetcher(source_url: str, timeout_seconds: float):
            return b"fixture", source_url, None, None

        def fake_builder(**kwargs):
            return {
                "exact_icpns": ["STM32FOREIGN"],
                "excluded_non_active_part_numbers": [],
            }

        summary = run_probe(targets=targets, fetcher=fake_fetcher, evidence_builder=fake_builder)
        self.assertFalse(summary["bounded_probe_complete"])
        self.assertGreater(summary["manual_review_targets"], 0)


if __name__ == "__main__":
    unittest.main()

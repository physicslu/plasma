#!/usr/bin/env python3
"""Hard-lock replay for the post-STM32G4 cross-family prioritization snapshot."""
from __future__ import annotations

import hashlib
import json
import unittest
from pathlib import Path

from stm32_cross_family_prioritization import (
    DEFAULT_CATALOG,
    DEFAULT_MANIFEST,
    build_prioritization,
)

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32-cross-family-prioritization-baseline.json"
FROZEN_MANIFEST = HERE / "stm32-cross-family-prioritization-production-manifest-prestate.json"
EXPECTED_BASELINE_SHA256 = "9a99865865f048e6a7636efd82cb17958fdc593240a329e18e3b68d8b0f862f9"
EXPECTED_PRESTATE_SHA256 = "93c2a4541daeb1d4aa1dcc57edef54042862eb6d9da03e3a6b401e4b8481b11d"
EXPECTED_SHORTLIST = ["STM32U0", "STM32C0", "STM32L1"]
EXPECTED_PRODUCTION_SERIES = {
    "STM32F0", "STM32F1", "STM32F2", "STM32F3",
    "STM32F4", "STM32F7", "STM32G0", "STM32G4",
}


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def canonical_bytes(report: dict) -> bytes:
    return (json.dumps(report, indent=2, sort_keys=True) + "\n").encode("utf-8")


class STM32CrossFamilyPrioritizationReplayTests(unittest.TestCase):
    def test_immutable_byte_anchors(self) -> None:
        self.assertEqual(sha256(BASELINE), EXPECTED_BASELINE_SHA256)
        self.assertEqual(sha256(FROZEN_MANIFEST), EXPECTED_PRESTATE_SHA256)

    def test_frozen_prestate_rebuild_is_byte_identical(self) -> None:
        replay = build_prioritization(
            catalog_path=DEFAULT_CATALOG,
            manifest_path=FROZEN_MANIFEST,
        )
        self.assertEqual(canonical_bytes(replay), BASELINE.read_bytes())

    def test_relative_and_absolute_manifest_forms_replay_identically(self) -> None:
        absolute = build_prioritization(
            catalog_path=DEFAULT_CATALOG.resolve(),
            manifest_path=FROZEN_MANIFEST.resolve(),
        )
        relative = build_prioritization(
            catalog_path=Path("data/device-catalog/research/openocd-parts-canonical.csv"),
            manifest_path=Path(
                "data/device-catalog/research/"
                "stm32-cross-family-prioritization-production-manifest-prestate.json"
            ),
        )
        self.assertEqual(relative, absolute)

    def test_historical_inventory_and_shortlist_are_locked(self) -> None:
        report = json.loads(BASELINE.read_text(encoding="utf-8"))
        self.assertEqual(report["policy_id"], "stm32-cross-family-prioritization-v1")
        self.assertEqual(
            report["inputs"]["production_manifest"],
            "data/device-catalog/research/"
            "stm32-cross-family-prioritization-production-manifest-prestate.json",
        )
        self.assertEqual(report["production_invariants"]["exact_icpn_count"], 635)
        self.assertEqual(report["production_invariants"]["base_device_count"], 217)
        self.assertEqual(
            set(report["production_invariants"]["production_series"]),
            EXPECTED_PRODUCTION_SERIES,
        )
        self.assertEqual(report["inventory"]["candidate_series_count"], 15)
        self.assertEqual(report["inventory"]["candidate_source_row_count"], 1369)
        self.assertEqual(report["inventory"]["candidate_ordering_pattern_rows"], 970)
        self.assertEqual(report["inventory"]["shortlist_eligible_series_count"], 5)
        self.assertEqual(
            report["inventory"]["cohort_counts"],
            {
                "high_complexity_requires_partitioned_scope": 1,
                "standard_nonwireless_research": 5,
                "trustzone_requires_security_scope": 3,
                "wireless_requires_dedicated_scope": 6,
            },
        )
        self.assertEqual(
            [item["plasma_series"] for item in report["research_shortlist"]],
            EXPECTED_SHORTLIST,
        )
        self.assertIsNone(report["selected_next_research_family"])
        self.assertTrue(all(value is False for value in report["claims"].values()))

    def test_current_production_may_grow_without_rewriting_history(self) -> None:
        frozen = json.loads(BASELINE.read_text(encoding="utf-8"))["production_invariants"]
        current = build_prioritization(
            catalog_path=DEFAULT_CATALOG,
            manifest_path=DEFAULT_MANIFEST,
        )["production_invariants"]
        self.assertGreaterEqual(current["exact_icpn_count"], frozen["exact_icpn_count"])
        self.assertGreaterEqual(current["base_device_count"], frozen["base_device_count"])
        self.assertTrue(set(frozen["production_series"]).issubset(current["production_series"]))

    def test_snapshot_never_claims_selection_or_programming_support(self) -> None:
        report = json.loads(BASELINE.read_text(encoding="utf-8"))
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

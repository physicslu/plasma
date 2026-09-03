#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from stm32f4_admission_policy import _package_and_pins  # noqa: E402
from stm32f4_coverage_gap_inventory import build_inventory  # noqa: E402
from validate_stm32f4_phase4_1_rt_policy_evidence import (  # noqa: E402
    EXPECTED_BASE_DEVICES,
    validate_policy_evidence,
)

EVIDENCE = HERE / "evidence" / "stm32f4-phase4.1-rt-policy-2026-09-01"
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
PRODUCTION_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
F446_BASELINE = HERE / "stm32f4-phase4.0-f446-batch1-baseline.json"
EXPECTED_CANONICAL_SHA256 = "6a3150e356511dfed679b747515d1ae1380d3da101b11edd3322f27cd936c948"
PREVIEW_AUDIT_ONLY_ICPN = "STM32F401CCF6TR"
PHASE41_KNOWN_BLOCKER_CLASSES = {
    "unsupported flash-size code 8",
    "unsupported flash-size code H",
    "unsupported STM32F4 package code: I",
    "unsupported STM32F4 pin/package combination: A/H",
    "unsupported STM32F4 pin/package combination: A/Y",
    "unsupported STM32F4 pin/package combination: B/T",
    "unsupported STM32F4 pin/package combination: M/Y",
    "unsupported STM32F4 pin/package combination: N/H",
    "unsupported STM32F4 pin/package combination: T/Y",
}


class STM32F4Phase41RTPolicyTests(unittest.TestCase):
    def test_policy_evidence_is_offline_valid_and_denies_admission(self) -> None:
        report = validate_policy_evidence(EVIDENCE)
        self.assertEqual(report["source_documents"], 7)
        self.assertEqual(report["covered_base_devices"], 11)
        self.assertFalse(report["canonical_dataset_admission"])
        self.assertFalse(report["algorithm_equivalence_claimed"])

    def test_rt_pair_maps_only_catalog_semantics(self) -> None:
        self.assertEqual(_package_and_pins("R", "T"), ("LQFP", "64"))

    def test_rt_policy_remains_effective_after_catalog_growth(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertFalse(inventory["algorithm_equivalence_claimed"])
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(
            inventory["gap"]["base_device_count"],
            149 - inventory["production"]["base_device_count"],
        )
        self.assertEqual(
            inventory["gap"]["base_device_count"],
            inventory["gap"]["policy_ready_count"] + inventory["gap"]["policy_blocked_count"],
        )
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            production_bases = {row["base_device"] for row in csv.DictReader(handle)}
        ready_bases = {item["base_device"] for item in inventory["gap"]["policy_ready"]}
        blocked_bases = {item["base_device"] for item in inventory["gap"]["policy_blocked"]}
        self.assertEqual(EXPECTED_BASE_DEVICES - production_bases, EXPECTED_BASE_DEVICES & ready_bases)
        self.assertTrue(EXPECTED_BASE_DEVICES.isdisjoint(blocked_bases))

    def test_later_policy_growth_does_not_introduce_unknown_phase41_blocker_classes(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        blockers = {
            blocker
            for item in inventory["gap"]["policy_blocked"]
            for blocker in item["policy_blockers"]
        }
        # Phase 4.1 owns the historical blocker vocabulary it observed. Later
        # phases may legitimately remove blocker classes as policy expands, but
        # they must not silently introduce a blocker class outside that reviewed
        # vocabulary. Current exact blocker counts belong to the current phase.
        self.assertTrue(blockers.issubset(PHASE41_KNOWN_BLOCKER_CLASSES))

    def test_policy_history_and_preview_audit_survive_later_growth(self) -> None:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertIn(PREVIEW_AUDIT_ONLY_ICPN, rows)

        baseline = json.loads(F446_BASELINE.read_text(encoding="utf-8"))
        preview = next(
            item
            for item in baseline["excluded_non_active_observations"]
            if item["icpn"] == PREVIEW_AUDIT_ONLY_ICPN
        )
        self.assertEqual(preview["marketing_status"], "Preview")
        self.assertFalse(preview["admission"])

        payload = CANONICAL.read_bytes()
        current_sha = hashlib.sha256(payload).hexdigest()
        current_blob = hashlib.sha1(f"blob {len(payload)}".encode() + bytes([0]) + payload).hexdigest()
        manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
        sources = {source["family"]: source for source in manifest["sources"]}
        self.assertEqual(sources["STM32F4"]["row_count"], len(rows))
        self.assertEqual(sources["STM32F4"]["sha256"], current_sha)
        self.assertEqual(sources["STM32F4"]["git_blob_sha"], current_blob)
        self.assertEqual(sum(source["row_count"] for source in sources.values()), 75 + len(rows))


if __name__ == "__main__":
    unittest.main()

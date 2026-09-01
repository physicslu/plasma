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
EXPECTED_REMAINING_BLOCKERS = {
    "unsupported flash-size code 8",
    "unsupported flash-size code H",
    "unsupported STM32F4 package code: I",
    "unsupported STM32F4 pin/package combination: A/H",
    "unsupported STM32F4 pin/package combination: A/Y",
    "unsupported STM32F4 pin/package combination: B/T",
    "unsupported STM32F4 pin/package combination: C/T",
    "unsupported STM32F4 pin/package combination: I/H",
    "unsupported STM32F4 pin/package combination: I/T",
    "unsupported STM32F4 pin/package combination: M/Y",
    "unsupported STM32F4 pin/package combination: N/H",
    "unsupported STM32F4 pin/package combination: O/Y",
    "unsupported STM32F4 pin/package combination: R/Y",
    "unsupported STM32F4 pin/package combination: T/Y",
    "unsupported STM32F4 pin/package combination: V/H",
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

    def test_inventory_delta_is_exactly_eleven_ready_and_eighty_two_blocked(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertFalse(inventory["algorithm_equivalence_claimed"])
        self.assertEqual(inventory["production"]["exact_icpn_rows"], 158)
        self.assertEqual(inventory["production"]["base_device_count"], 56)
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(inventory["gap"]["base_device_count"], 93)
        self.assertEqual(inventory["gap"]["policy_ready_count"], 11)
        self.assertEqual(inventory["gap"]["policy_blocked_count"], 82)
        self.assertEqual(
            {item["base_device"] for item in inventory["gap"]["policy_ready"]},
            EXPECTED_BASE_DEVICES,
        )

    def test_all_unapproved_policy_classes_remain_fail_closed(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        blockers = {
            blocker
            for item in inventory["gap"]["policy_blocked"]
            for blocker in item["policy_blockers"]
        }
        self.assertEqual(blockers, EXPECTED_REMAINING_BLOCKERS)

    def test_policy_only_change_preserves_production_catalog_and_preview_audit(self) -> None:
        self.assertEqual(hashlib.sha256(CANONICAL.read_bytes()).hexdigest(), EXPECTED_CANONICAL_SHA256)
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertEqual(len(rows), 158)
        self.assertIn(PREVIEW_AUDIT_ONLY_ICPN, rows)

        baseline = json.loads(F446_BASELINE.read_text(encoding="utf-8"))
        preview = next(
            item
            for item in baseline["excluded_non_active_observations"]
            if item["icpn"] == PREVIEW_AUDIT_ONLY_ICPN
        )
        self.assertEqual(preview["marketing_status"], "Preview")
        self.assertFalse(preview["admission"])

        manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
        sources = {source["family"]: source for source in manifest["sources"]}
        self.assertEqual(sources["STM32F4"]["row_count"], 158)
        self.assertEqual(sources["STM32F4"]["sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(sum(source["row_count"] for source in sources.values()), 233)


if __name__ == "__main__":
    unittest.main()

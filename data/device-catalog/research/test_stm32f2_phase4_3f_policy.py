#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from device_catalog_admission_framework import CandidateManualReview, CandidateReject  # noqa: E402
from stm32f2_phase4_3f_policy import (  # noqa: E402
    DEFAULT_POLICY_BASELINE,
    EXPECTED_COUNT,
    SUPPORTED_BASE_DEVICES,
    _row_builder,
    build_policy_plan,
    policy_plan_is_clean,
    policy_summary,
)


class STM32F2Phase43FPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = build_policy_plan()
        cls.candidates = {item["icpn"]: item for item in cls.plan["candidates"]}

    def _candidate(self, icpn: str = "STM32F215RGT6") -> dict:
        item = self.candidates[icpn]
        return {
            "manufacturer": item["manufacturer"],
            "base_device": item["base_device"],
            "icpn": item["icpn"],
            "authoritative_evidence": copy.deepcopy(item["authoritative_evidence"]),
            "base_mapping": copy.deepcopy(item["base_mapping"]),
        }

    def test_policy_matches_checked_in_baseline(self) -> None:
        baseline = json.loads(DEFAULT_POLICY_BASELINE.read_text(encoding="utf-8"))
        self.assertTrue(policy_plan_is_clean(self.plan))
        self.assertEqual(policy_summary(self.plan), baseline)
        self.assertEqual(self.plan["candidate_count"], EXPECTED_COUNT)
        self.assertEqual({item["base_device"] for item in self.plan["candidates"]}, SUPPORTED_BASE_DEVICES)

    def test_exact_metadata_contract(self) -> None:
        rows = {icpn: item["proposed_canonical_row"] for icpn, item in self.candidates.items()}
        self.assertEqual(rows["STM32F205RCT7TR"]["flash_size"], "256 KiB")
        self.assertEqual(rows["STM32F205RCT7TR"]["temperature_grade"], "-40 to 105 C")
        self.assertEqual(rows["STM32F205RCT7TR"]["option_suffix"], "TR")
        self.assertEqual((rows["STM32F207IEH6"]["package"], rows["STM32F207IEH6"]["pin_count"]), ("UFBGA", "176"))
        self.assertEqual(rows["STM32F207IET6"]["package"], "LQFP")
        self.assertEqual(rows["STM32F215RGT6"]["flash_size"], "1024 KiB")
        self.assertEqual(rows["STM32F217IGH6TR"]["flash_size"], "1024 KiB")
        self.assertTrue(all(row["openocd_target_config"] == "tcl/target/stm32f2x.cfg" for row in rows.values()))

    def test_unapproved_base_fails_closed(self) -> None:
        candidate = self._candidate()
        candidate["base_device"] = "STM32F215RE"
        candidate["icpn"] = "STM32F215RET6"
        with self.assertRaisesRegex(CandidateReject, "outside bounded"):
            _row_builder(candidate, list(self.plan["candidates"][0]["proposed_canonical_row"]))

    def test_unknown_flash_code_requires_manual_review(self) -> None:
        candidate = self._candidate()
        candidate["base_device"] = "STM32F215RZ"
        candidate["icpn"] = "STM32F215RZT6"
        with self.assertRaisesRegex(CandidateManualReview, "flash-size code"):
            _row_builder(candidate, list(self.plan["candidates"][0]["proposed_canonical_row"]))

    def test_wrong_mapping_requires_manual_review(self) -> None:
        candidate = self._candidate()
        candidate["base_mapping"]["target_configs"] = ["tcl/target/stm32f4x.cfg"]
        with self.assertRaisesRegex(CandidateManualReview, "target mapping"):
            _row_builder(candidate, list(self.plan["candidates"][0]["proposed_canonical_row"]))

    def test_production_snapshot_is_pre_batch2(self) -> None:
        self.assertEqual(
            self.plan["production_snapshot"],
            {
                "exact_icpn_count": 468,
                "base_device_count": 161,
                "family_exact_icpn_counts": {"STM32F1": 75, "STM32F2": 9, "STM32F4": 384},
                "stm32f2_exact_icpn_count": 9,
            },
        )


if __name__ == "__main__":
    unittest.main()

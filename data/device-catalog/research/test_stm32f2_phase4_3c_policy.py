#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import json
import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from device_catalog_admission_framework import CandidateManualReview, CandidateReject  # noqa: E402
from stm32f2_admission_policy import (  # noqa: E402
    CANONICAL_FIELDS,
    TARGET_CONFIG,
    build_canonical_row,
)
from stm32f2_phase4_3c_policy import (  # noqa: E402
    DEFAULT_POLICY_BASELINE,
    DEFAULT_PRODUCTION_MANIFEST,
    build_policy_plan,
    policy_plan_is_clean,
    policy_summary,
)

F4_CANONICAL = HERE / "stm32f4-commercial-icpn.csv"


class STM32F2Phase43CPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = build_policy_plan()
        cls.candidates = {
            item["icpn"]: item for item in cls.plan["candidates"]
        }

    def _candidate(self, icpn: str = "STM32F205RBT6") -> dict:
        item = self.candidates[icpn]
        return {
            "manufacturer": item["manufacturer"],
            "base_device": item["base_device"],
            "icpn": item["icpn"],
            "authoritative_evidence": copy.deepcopy(item["authoritative_evidence"]),
            "base_mapping": copy.deepcopy(item["base_mapping"]),
        }

    def test_policy_plan_matches_checked_in_baseline(self) -> None:
        baseline = json.loads(DEFAULT_POLICY_BASELINE.read_text(encoding="utf-8"))
        self.assertTrue(policy_plan_is_clean(self.plan))
        self.assertEqual(policy_summary(self.plan), baseline)
        self.assertEqual(
            self.plan["decision_counts"],
            {
                "admit": 9,
                "already_present": 0,
                "manual_review_required": 0,
                "reject": 0,
            },
        )
        self.assertEqual(self.plan["conflicts"], 0)
        self.assertEqual(self.plan["policy_ready_count"], 9)

    def test_canonical_schema_matches_existing_family_contract(self) -> None:
        with F4_CANONICAL.open(newline="", encoding="utf-8") as handle:
            fields = tuple(csv.DictReader(handle).fieldnames or [])
        self.assertEqual(fields, CANONICAL_FIELDS)

    def test_exact_candidate_metadata(self) -> None:
        rows = {
            icpn: item["proposed_canonical_row"]
            for icpn, item in self.candidates.items()
        }
        self.assertEqual(
            (rows["STM32F205RBT6"]["package"], rows["STM32F205RBT6"]["pin_count"]),
            ("LQFP", "64"),
        )
        self.assertEqual(rows["STM32F205RBT6"]["flash_size"], "128 KiB")
        self.assertEqual(rows["STM32F205RBT6"]["temperature_grade"], "-40 to 85 C")
        self.assertEqual(rows["STM32F205RBT6"]["option_suffix"], "")
        self.assertEqual(rows["STM32F205RBT6TR"]["option_suffix"], "TR")
        self.assertEqual(rows["STM32F205RBT7"]["temperature_grade"], "-40 to 105 C")
        self.assertEqual(
            (rows["STM32F207ICH6"]["package"], rows["STM32F207ICH6"]["pin_count"]),
            ("UFBGA", "176"),
        )
        self.assertEqual(rows["STM32F207ICH6"]["flash_size"], "256 KiB")
        self.assertEqual(rows["STM32F207ICT6"]["package"], "LQFP")
        self.assertEqual(rows["STM32F215RET6"]["flash_size"], "512 KiB")
        self.assertEqual(rows["STM32F217IEH6"]["flash_size"], "512 KiB")
        self.assertTrue(
            all(row["openocd_target_config"] == TARGET_CONFIG for row in rows.values())
        )

    def test_unsupported_package_code_is_rejected(self) -> None:
        candidate = self._candidate()
        candidate["icpn"] = "STM32F205RBU6"
        with self.assertRaisesRegex(CandidateReject, "package code"):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_unsupported_temperature_code_is_rejected(self) -> None:
        candidate = self._candidate()
        candidate["icpn"] = "STM32F205RBT3"
        with self.assertRaisesRegex(CandidateReject, "temperature code"):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_unsupported_flash_code_requires_manual_review(self) -> None:
        candidate = self._candidate()
        candidate["base_device"] = "STM32F205R8"
        candidate["icpn"] = "STM32F205R8T6"
        with self.assertRaisesRegex(CandidateManualReview, "flash-size code"):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_unsupported_option_suffix_is_rejected(self) -> None:
        candidate = self._candidate()
        candidate["icpn"] = "STM32F205RBT6M"
        with self.assertRaisesRegex(CandidateReject, "option suffix"):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_unapproved_base_device_is_rejected(self) -> None:
        candidate = self._candidate()
        candidate["base_device"] = "STM32F205RC"
        candidate["icpn"] = "STM32F205RCT6"
        with self.assertRaisesRegex(CandidateReject, "outside bounded"):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_ambiguous_mapping_requires_manual_review(self) -> None:
        candidate = self._candidate()
        candidate["base_mapping"]["status"] = "ambiguous"
        with self.assertRaisesRegex(CandidateManualReview, "one unique"):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_wrong_target_mapping_requires_manual_review(self) -> None:
        candidate = self._candidate()
        candidate["base_mapping"]["target_configs"] = ["tcl/target/stm32f4x.cfg"]
        with self.assertRaisesRegex(CandidateManualReview, "target mapping"):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_invalid_evidence_digest_is_rejected(self) -> None:
        candidate = self._candidate()
        candidate["authoritative_evidence"]["rendered_dom_sha256"] = "not-a-digest"
        with self.assertRaisesRegex(CandidateReject, "rendered DOM digest"):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_canonical_schema_drift_fails_closed(self) -> None:
        candidate = self._candidate()
        with self.assertRaisesRegex(Exception, "schema"):
            build_canonical_row(candidate, list(CANONICAL_FIELDS[:-1]))

    def test_historical_snapshot_ignores_later_family_growth(self) -> None:
        manifest = json.loads(DEFAULT_PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
        sources = {source["family"]: source for source in manifest["sources"]}
        self.assertTrue({"STM32F1", "STM32F4"}.issubset(sources))
        self.assertIn("STM32F2", sources)
        self.assertGreaterEqual(
            int(sources["STM32F2"]["row_count"]),
            self.plan["policy_ready_count"],
        )
        self.assertGreaterEqual(
            sum(int(source["row_count"]) for source in manifest["sources"]),
            self.plan["production_snapshot"]["exact_icpn_count"],
        )
        self.assertEqual(
            self.plan["production_snapshot"],
            {
                "exact_icpn_count": 459,
                "base_device_count": 157,
                "family_exact_icpn_counts": {"STM32F1": 75, "STM32F4": 384},
                "stm32f2_exact_icpn_count": 0,
            },
        )
        self.assertFalse(self.plan["production_write_applied"])
        self.assertTrue(self.plan["exact_icpn_admission_deferred"])


if __name__ == "__main__":
    unittest.main()

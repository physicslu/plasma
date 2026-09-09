#!/usr/bin/env python3
"""Regression tests for STM32F0 Phase 4.5D admission planning."""

from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import CandidateManualReview
from stm32f0_admission_policy import CANONICAL_FIELDS, build_canonical_row
from stm32f0_phase4_5d_admission import (
    EXPECTED_CANDIDATE_COUNT,
    EXPECTED_PRODUCTION_BASE_DEVICE_COUNT,
    EXPECTED_PRODUCTION_EXACT_COUNT,
    admission_plan_is_clean,
    build_admission_plan,
)


def valid_candidate() -> dict[str, object]:
    return {
        "manufacturer": "STMicroelectronics",
        "base_device": "STM32F078CB",
        "icpn": "STM32F078CBY6TR",
        "authoritative_evidence": {
            "evidence_id": "test-evidence",
            "source_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32f078cb.html",
            "rendered_dom_sha256": "a" * 64,
            "evidence_section_sha256": "b" * 64,
            "evidence_profile": "stm32f0_dual_surface_v1",
        },
        "base_mapping": {
            "status": "unique",
            "match_count": 1,
            "identifier_kind": "ordering_pattern",
            "existing_identifier": "STM32F078CBYx",
            "target_configs": ["tcl/target/stm32f0x.cfg"],
        },
    }


class STM32F0Phase45DAdmissionTests(unittest.TestCase):
    def test_canonical_row_combines_metadata_and_capability(self) -> None:
        row = build_canonical_row(valid_candidate(), list(CANONICAL_FIELDS))
        self.assertEqual(row["icpn"], "STM32F078CBY6TR")
        self.assertEqual(row["package"], "WLCSP")
        self.assertEqual(row["pin_count"], "49")
        self.assertEqual(row["flash_size"], "128 KiB")
        self.assertEqual(row["existing_identifier"], "STM32F078CBYx")
        self.assertEqual(row["existing_identifier_kind"], "ordering_pattern")
        self.assertEqual(row["mapping_status"], "deterministic_ordering_pattern")
        self.assertEqual(row["openocd_target_config"], "tcl/target/stm32f0x.cfg")

    def test_missing_mapping_blocks_admission_not_metadata(self) -> None:
        candidate = valid_candidate()
        candidate.pop("base_mapping")
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_ambiguous_mapping_requires_manual_review(self) -> None:
        candidate = copy.deepcopy(valid_candidate())
        candidate["base_mapping"]["status"] = "ambiguous"
        candidate["base_mapping"]["match_count"] = 2
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_wrong_target_config_requires_manual_review(self) -> None:
        candidate = copy.deepcopy(valid_candidate())
        candidate["base_mapping"]["target_configs"] = ["tcl/target/stm32f3x.cfg"]
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_non_ordering_pattern_mapping_requires_manual_review(self) -> None:
        candidate = copy.deepcopy(valid_candidate())
        candidate["base_mapping"]["identifier_kind"] = "cmsis_device_name"
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_current_catalog_builds_clean_42_candidate_plan(self) -> None:
        plan = build_admission_plan()
        self.assertTrue(admission_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], EXPECTED_CANDIDATE_COUNT)
        self.assertEqual(plan["decision_counts"], {
            "admit": 42,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        })
        self.assertEqual(plan["canonical_rows_before"], 0)
        self.assertTrue(plan["metadata_policy_clean"])
        self.assertTrue(plan["capability_mapping_gate_applied"])
        self.assertEqual(plan["required_target_config"], "tcl/target/stm32f0x.cfg")

        for item in plan["candidates"]:
            row = item["proposed_canonical_row"]
            self.assertEqual(item["decision"], "admit")
            self.assertIsNotNone(row)
            self.assertEqual(row["family"], "STM32F0")
            self.assertEqual(row["openocd_target_config"], "tcl/target/stm32f0x.cfg")
            self.assertEqual(row["existing_identifier_kind"], "ordering_pattern")
            self.assertEqual(row["mapping_status"], "deterministic_ordering_pattern")

    def test_admission_plan_remains_read_only(self) -> None:
        plan = build_admission_plan()
        self.assertEqual(plan["production_snapshot"]["exact_icpn_count"], EXPECTED_PRODUCTION_EXACT_COUNT)
        self.assertEqual(plan["production_snapshot"]["base_device_count"], EXPECTED_PRODUCTION_BASE_DEVICE_COUNT)
        self.assertEqual(plan["production_snapshot"]["stm32f0_exact_icpn_count"], 0)
        self.assertFalse(plan["canonical_write_applied"])
        self.assertFalse(plan["production_write_applied"])
        self.assertFalse(plan["programming_algorithm_equivalence_claimed"])
        self.assertFalse(plan["physical_target_qualification_claimed"])
        self.assertFalse(plan["runtime_programming_support_claimed"])
        self.assertFalse(plan["full_stm32f0_surface_covered"])
        self.assertTrue(plan["fail_closed"])

    def test_nonempty_canonical_prestate_is_refused(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stm32f0-commercial-icpn.csv"
            path.write_text(
                ",".join(CANONICAL_FIELDS) + "\n" + ",".join(["x"] * len(CANONICAL_FIELDS)) + "\n",
                encoding="utf-8",
            )
            with self.assertRaises(Exception):
                build_admission_plan(canonical_path=path)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Regression tests for STM32F3 Phase 4.4C metadata policy."""

from __future__ import annotations

import copy
import unittest

from device_catalog_admission_framework import CandidateManualReview, CandidateReject
from stm32f3_admission_policy import CANONICAL_FIELDS, build_canonical_row
from stm32f3_phase4_4c_policy import (
    EXPECTED_PRODUCTION_BASE_DEVICE_COUNT,
    EXPECTED_PRODUCTION_EXACT_COUNT,
    build_policy_plan,
    metadata_contract,
    policy_plan_is_clean,
    policy_summary,
)

EXPECTED_ROWS = {
    "STM32F301C6T6": ("STM32F301C6", "LQFP", "48", "32 KiB", "-40 to 85 C", ""),
    "STM32F301C6T6TR": ("STM32F301C6", "LQFP", "48", "32 KiB", "-40 to 85 C", "TR"),
    "STM32F301C6T7": ("STM32F301C6", "LQFP", "48", "32 KiB", "-40 to 105 C", ""),
    "STM32F302C6T6": ("STM32F302C6", "LQFP", "48", "32 KiB", "-40 to 85 C", ""),
    "STM32F303C6T6": ("STM32F303C6", "LQFP", "48", "32 KiB", "-40 to 85 C", ""),
    "STM32F373C8T6": ("STM32F373C8", "LQFP", "48", "64 KiB", "-40 to 85 C", ""),
    "STM32F373C8T6TR": ("STM32F373C8", "LQFP", "48", "64 KiB", "-40 to 85 C", "TR"),
    "STM32F334C4T6": ("STM32F334C4", "LQFP", "48", "16 KiB", "-40 to 85 C", ""),
    "STM32F318C8T6": ("STM32F318C8", "LQFP", "48", "64 KiB", "-40 to 85 C", ""),
    "STM32F318C8Y6TR": ("STM32F318C8", "WLCSP", "49", "64 KiB", "-40 to 85 C", "TR"),
}


def valid_candidate(icpn: str = "STM32F318C8Y6TR") -> dict[str, object]:
    base = "STM32F318C8"
    return {
        "manufacturer": "STMicroelectronics",
        "base_device": base,
        "icpn": icpn,
        "authoritative_evidence": {
            "evidence_id": "test-evidence",
            "source_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32f318c8.html",
            "rendered_dom_sha256": "a" * 64,
            "evidence_section_sha256": "b" * 64,
            "evidence_profile": "stm32f3_dual_surface_v1",
        },
        "base_mapping": {
            "status": "unique",
            "match_count": 1,
            "identifier_kind": "ordering_pattern",
            "existing_identifier": "STM32F318C8Yx",
            "target_configs": ["tcl/target/stm32f3x.cfg"],
        },
    }


class STM32F3Phase44CPolicyTests(unittest.TestCase):
    def test_metadata_contract_is_explicit_and_physical(self) -> None:
        contract = metadata_contract()
        self.assertEqual(contract["flash_by_code"], {"4": "16 KiB", "6": "32 KiB", "8": "64 KiB"})
        self.assertEqual(contract["pins_by_combination"], {"C/T": "48", "C/Y": "49"})
        self.assertEqual(contract["package_by_code"], {"T": "LQFP", "Y": "WLCSP"})
        self.assertEqual(contract["allowed_option_suffixes"], ["", "TR"])

    def test_wlcsp_uses_actual_49_ball_count(self) -> None:
        row = build_canonical_row(valid_candidate(), list(CANONICAL_FIELDS))
        self.assertEqual(row["package"], "WLCSP")
        self.assertEqual(row["pin_count"], "49")
        self.assertEqual(row["flash_size"], "64 KiB")
        self.assertEqual(row["option_suffix"], "TR")

    def test_policy_rejects_unknown_package(self) -> None:
        candidate = valid_candidate("STM32F318C8U6")
        with self.assertRaises(CandidateReject):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_policy_requires_unique_f3_mapping(self) -> None:
        candidate = valid_candidate()
        candidate = copy.deepcopy(candidate)
        candidate["base_mapping"]["target_configs"] = ["tcl/target/stm32f4x.cfg"]
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_policy_rejects_unapproved_option_suffix(self) -> None:
        candidate = valid_candidate("STM32F318C8Y6TT")
        with self.assertRaises(CandidateReject):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_retained_batch_builds_clean_ten_candidate_plan(self) -> None:
        plan = build_policy_plan()
        self.assertTrue(policy_plan_is_clean(plan))
        self.assertEqual(plan["canonical_rows_before"], 0)
        self.assertEqual(plan["decision_counts"], {
            "admit": 10,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        })
        self.assertEqual(plan["production_snapshot"]["exact_icpn_count"], EXPECTED_PRODUCTION_EXACT_COUNT)
        self.assertEqual(plan["production_snapshot"]["base_device_count"], EXPECTED_PRODUCTION_BASE_DEVICE_COUNT)
        self.assertEqual(plan["production_snapshot"]["stm32f3_exact_icpn_count"], 0)
        self.assertFalse(plan["production_write_applied"])
        self.assertTrue(plan["exact_icpn_admission_deferred"])

        observed = {}
        for candidate in plan["candidates"]:
            row = candidate["proposed_canonical_row"]
            observed[row["icpn"]] = (
                row["base_device"],
                row["package"],
                row["pin_count"],
                row["flash_size"],
                row["temperature_grade"],
                row["option_suffix"],
            )
            self.assertEqual(row["family"], "STM32F3")
            self.assertEqual(row["openocd_target_config"], "tcl/target/stm32f3x.cfg")
            self.assertEqual(row["existing_identifier_kind"], "ordering_pattern")
            self.assertEqual(row["mapping_status"], "deterministic_ordering_pattern")
        self.assertEqual(observed, EXPECTED_ROWS)

    def test_policy_summary_does_not_claim_admission_or_runtime(self) -> None:
        summary = policy_summary(build_policy_plan())
        self.assertEqual(summary["candidate_count"], 10)
        self.assertEqual(summary["decision_counts"]["admit"], 10)
        self.assertTrue(summary["exact_icpn_admission_deferred"])
        self.assertFalse(summary["production_write_applied"])
        self.assertFalse(summary["programming_algorithm_equivalence_claimed"])
        self.assertFalse(summary["runtime_support_claimed"])
        self.assertFalse(summary["full_stm32f3_surface_covered"])
        self.assertTrue(summary["fail_closed"])


if __name__ == "__main__":
    unittest.main()

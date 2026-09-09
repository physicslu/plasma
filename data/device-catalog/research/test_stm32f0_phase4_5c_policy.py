#!/usr/bin/env python3
"""Regression tests for STM32F0 Phase 4.5C metadata policy."""

from __future__ import annotations

import copy
import unittest

from device_catalog_admission_framework import CandidateReject
from stm32f0_metadata_policy import METADATA_FIELDS, build_metadata_row
from stm32f0_phase4_5c_policy import (
    EXPECTED_PRODUCTION_BASE_DEVICE_COUNT,
    EXPECTED_PRODUCTION_EXACT_COUNT,
    build_policy_plan,
    metadata_contract,
    policy_plan_is_clean,
    policy_summary,
    validate_policy,
)


def valid_candidate(icpn: str = "STM32F078CBY6TR") -> dict[str, object]:
    base = "STM32F078CB"
    return {
        "manufacturer": "STMicroelectronics",
        "base_device": base,
        "icpn": icpn,
        "authoritative_evidence": {
            "evidence_id": "test-evidence",
            "source_url": "https://www.st.com/en/microcontrollers-microprocessors/stm32f078cb.html",
            "rendered_dom_sha256": "a" * 64,
            "evidence_section_sha256": "b" * 64,
            "evidence_profile": "stm32f0_dual_surface_v1",
        },
    }


class STM32F0Phase45CPolicyTests(unittest.TestCase):
    def test_metadata_contract_is_explicit_and_keeps_capability_separate(self) -> None:
        contract = metadata_contract()
        self.assertEqual(
            contract["flash_by_code"],
            {
                "4": "16 KiB",
                "6": "32 KiB",
                "8": "64 KiB",
                "B": "128 KiB",
                "C": "256 KiB",
            },
        )
        self.assertEqual(
            contract["package_by_code"],
            {"T": "LQFP", "U": "UFQFPN", "Y": "WLCSP"},
        )
        self.assertEqual(
            contract["pins_by_combination"],
            {"C/T": "48", "C/U": "48", "C/Y": "49"},
        )
        self.assertEqual(contract["temperature_by_code"], {
            "6": "-40 to 85 C",
            "7": "-40 to 105 C",
        })
        self.assertEqual(contract["allowed_option_suffixes"], ["", "TR"])
        self.assertFalse(contract["openocd_routing_gates_metadata"])
        self.assertEqual(contract["capability_mapping_deferred_to"], "4.5D")

    def test_wlcsp_uses_actual_49_ball_count(self) -> None:
        row = build_metadata_row(valid_candidate(), list(METADATA_FIELDS))
        self.assertEqual(row["package"], "WLCSP")
        self.assertEqual(row["pin_count"], "49")
        self.assertEqual(row["flash_size"], "128 KiB")
        self.assertEqual(row["temperature_grade"], "-40 to 85 C")
        self.assertEqual(row["option_suffix"], "TR")

    def test_ufqfpn_uses_48_physical_pins(self) -> None:
        candidate = valid_candidate("STM32F078CBU6")
        row = build_metadata_row(candidate, list(METADATA_FIELDS))
        self.assertEqual(row["package"], "UFQFPN")
        self.assertEqual(row["pin_count"], "48")

    def test_flash_and_temperature_codes_cover_bounded_batch(self) -> None:
        cases = {
            "STM32F031C4T6": ("16 KiB", "-40 to 85 C"),
            "STM32F030C6T6": ("32 KiB", "-40 to 85 C"),
            "STM32F072C8T7": ("64 KiB", "-40 to 105 C"),
            "STM32F078CBT6": ("128 KiB", "-40 to 85 C"),
            "STM32F098CCT7": ("256 KiB", "-40 to 105 C"),
        }
        bases = {
            "STM32F031C4T6": "STM32F031C4",
            "STM32F030C6T6": "STM32F030C6",
            "STM32F072C8T7": "STM32F072C8",
            "STM32F078CBT6": "STM32F078CB",
            "STM32F098CCT7": "STM32F098CC",
        }
        for icpn, expected in cases.items():
            base = bases[icpn]
            candidate = valid_candidate()
            candidate["base_device"] = base
            candidate["icpn"] = icpn
            candidate["authoritative_evidence"]["source_url"] = (
                "https://www.st.com/en/microcontrollers-microprocessors/"
                f"{base.lower()}.html"
            )
            row = build_metadata_row(candidate, list(METADATA_FIELDS))
            self.assertEqual((row["flash_size"], row["temperature_grade"]), expected)

    def test_policy_rejects_unknown_package_code(self) -> None:
        candidate = valid_candidate("STM32F078CBQ6")
        with self.assertRaises(CandidateReject):
            build_metadata_row(candidate, list(METADATA_FIELDS))

    def test_policy_rejects_unknown_option_suffix(self) -> None:
        candidate = valid_candidate("STM32F078CBY6TT")
        with self.assertRaises(CandidateReject):
            build_metadata_row(candidate, list(METADATA_FIELDS))

    def test_openocd_mapping_is_not_a_metadata_input(self) -> None:
        clean = valid_candidate()
        expected = build_metadata_row(clean, list(METADATA_FIELDS))

        bogus = copy.deepcopy(clean)
        bogus["base_mapping"] = {
            "status": "ambiguous",
            "target_configs": ["tcl/target/not-stm32f0.cfg"],
            "identifier_kind": "wrong",
        }
        self.assertEqual(
            build_metadata_row(bogus, list(METADATA_FIELDS)),
            expected,
        )

        absent = copy.deepcopy(clean)
        absent.pop("base_mapping", None)
        self.assertEqual(
            build_metadata_row(absent, list(METADATA_FIELDS)),
            expected,
        )

    def test_retained_batch_builds_clean_42_candidate_metadata_plan(self) -> None:
        plan = build_policy_plan()
        self.assertTrue(policy_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 42)
        self.assertEqual(plan["decision_counts"], {
            "metadata_ready": 42,
            "manual_review_required": 0,
            "reject": 0,
        })
        self.assertEqual(plan["production_snapshot"]["exact_icpn_count"], EXPECTED_PRODUCTION_EXACT_COUNT)
        self.assertEqual(plan["production_snapshot"]["base_device_count"], EXPECTED_PRODUCTION_BASE_DEVICE_COUNT)
        self.assertEqual(plan["production_snapshot"]["stm32f0_exact_icpn_count"], 0)
        self.assertFalse(plan["openocd_routing_gate_applied"])
        self.assertTrue(plan["capability_mapping_deferred"])
        self.assertFalse(plan["production_write_applied"])
        self.assertTrue(plan["exact_icpn_admission_deferred"])

    def test_metadata_distribution_is_deterministic(self) -> None:
        plan = build_policy_plan()
        self.assertEqual(plan["metadata_distribution"], {
            "flash_size": {
                "128 KiB": 10,
                "16 KiB": 7,
                "256 KiB": 4,
                "32 KiB": 9,
                "64 KiB": 12,
            },
            "package": {"LQFP": 24, "UFQFPN": 17, "WLCSP": 1},
            "temperature_grade": {"-40 to 105 C": 8, "-40 to 85 C": 34},
            "option_suffix": {"": 26, "TR": 16},
        })

    def test_policy_summary_denies_admission_and_runtime_claims(self) -> None:
        summary = policy_summary(build_policy_plan())
        self.assertEqual(summary["candidate_count"], 42)
        self.assertEqual(summary["decision_counts"]["metadata_ready"], 42)
        self.assertTrue(summary["exact_icpn_admission_deferred"])
        self.assertFalse(summary["production_write_applied"])
        self.assertFalse(summary["openocd_routing_gate_applied"])
        self.assertTrue(summary["capability_mapping_deferred"])
        self.assertFalse(summary["programming_algorithm_equivalence_claimed"])
        self.assertFalse(summary["runtime_support_claimed"])
        self.assertFalse(summary["full_stm32f0_surface_covered"])
        self.assertTrue(summary["fail_closed"])

    def test_checked_in_policy_baseline_replays_exactly(self) -> None:
        plan, summary = validate_policy()
        self.assertTrue(policy_plan_is_clean(plan))
        self.assertEqual(summary, policy_summary(plan))


if __name__ == "__main__":
    unittest.main()

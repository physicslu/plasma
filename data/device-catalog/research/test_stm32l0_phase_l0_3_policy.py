#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest

from device_catalog_admission_framework import CandidateManualReview, CandidateReject
from stm32l0_metadata_policy import (
    EXPECTED_ACTIVE_CANDIDATE_COUNT,
    EXPECTED_SERIES,
    EXPECTED_TARGET_COUNT,
    METADATA_FIELDS,
    build_candidate_inputs,
    build_metadata_row,
    load_ordering_authority,
)
from stm32l0_phase_l0_3_policy import build_plan, plan_is_clean
from validate_stm32l0_phase_l0_2_retained_evidence import main as validate_retained


class STM32L0PhaseL03PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retained_status = validate_retained()
        cls.candidates = build_candidate_inputs()
        cls.plan = build_plan()

    def test_l02_retained_boundary_is_the_only_identity_input(self) -> None:
        self.assertEqual(self.retained_status, 0)
        self.assertEqual(len(self.candidates), EXPECTED_ACTIVE_CANDIDATE_COUNT)
        self.assertEqual(len({item["icpn"] for item in self.candidates}), 360)
        self.assertEqual(len({item["base_device"] for item in self.candidates}), EXPECTED_TARGET_COUNT)

    def test_ordering_authority_is_bounded_to_16_official_st_series_records(self) -> None:
        authority = load_ordering_authority()
        self.assertEqual(set(authority), EXPECTED_SERIES)
        self.assertEqual(len(authority), 16)
        for series, record in authority.items():
            self.assertTrue(record["datasheet_url"].startswith("https://www.st.com/resource/en/datasheet/"))
            self.assertTrue(record["datasheet_url"].endswith(".pdf"))
            self.assertEqual(record["ordering_section"], 8)
            self.assertGreater(record["revision"], 0)
            self.assertGreater(record["pdf_page"], 0)
            self.assertTrue(record["pin_codes"])
            self.assertTrue(record["flash"])
            self.assertTrue(record["package_codes"])
            self.assertTrue(record["temperature_codes"])
            self.assertTrue(record["option_suffixes"])
            self.assertTrue(series.startswith("STM32L0"))

    def test_special_ordering_semantics_remain_fail_closed(self) -> None:
        authority = load_ordering_authority()
        l010 = authority["STM32L010"]
        self.assertEqual(l010["coverage"], "explicit_base_only")
        self.assertEqual(l010["covered_base_devices"], ["STM32L010C6"])
        self.assertNotIn("D", l010["option_suffixes"])
        self.assertNotIn("DTR", l010["option_suffixes"])
        self.assertIn("S", authority["STM32L031"]["option_suffixes"])
        self.assertIn("S", authority["STM32L041"]["option_suffixes"])

    def test_all_360_candidates_are_deterministically_dispositioned_without_rejects(self) -> None:
        counts = self.plan["decision_counts"]
        self.assertEqual(sum(counts.values()), 360)
        self.assertEqual(counts["reject"], 0)
        self.assertEqual(counts["metadata_ready"] + counts["manual_review_required"], 360)
        self.assertEqual(self.plan["candidate_count"], 360)
        self.assertEqual(self.plan["base_device_count"], 99)

    def test_manual_review_is_limited_to_uncovered_l010_base_devices(self) -> None:
        manual_bases = set(self.plan["manual_review_base_devices"])
        self.assertTrue(manual_bases)
        self.assertTrue(all(base.startswith("STM32L010") for base in manual_bases))
        self.assertNotIn("STM32L010C6", manual_bases)
        self.assertTrue(all(base != "STM32L010C6" for base in manual_bases))

    def test_metadata_ready_rows_use_official_st_ordering_authority_only(self) -> None:
        ready = [item["metadata"] for item in self.plan["candidates"] if item["decision"] == "metadata_ready"]
        self.assertTrue(ready)
        for row in ready:
            self.assertIsNotNone(row)
            self.assertEqual(tuple(row), METADATA_FIELDS)
            self.assertEqual(row["manufacturer"], "STMicroelectronics")
            self.assertEqual(row["family"], "STM32L0")
            self.assertEqual(row["source_type"], "manufacturer_ordering_information")
            self.assertEqual(row["source_authority"], "STMicroelectronics official")
            self.assertIn("st.com/resource/en/datasheet/", row["source_reference"])
            self.assertNotIn("openocd", row["source_reference"].lower())
            self.assertNotIn("cmsis", row["source_reference"].lower())

    def test_uncovered_l010_base_fails_to_manual_review_instead_of_guessing_metadata(self) -> None:
        candidate = next(item for item in self.candidates if item["base_device"].startswith("STM32L010") and item["base_device"] != "STM32L010C6")
        with self.assertRaises(CandidateManualReview):
            build_metadata_row(candidate, list(METADATA_FIELDS))

    def test_legal_looking_but_unretained_exact_identity_is_rejected(self) -> None:
        candidate = copy.deepcopy(self.candidates[0])
        candidate["icpn"] = candidate["icpn"] + "X"
        with self.assertRaises(CandidateReject):
            build_metadata_row(candidate, list(METADATA_FIELDS))

    def test_planner_is_clean_without_authorizing_production_or_runtime_support(self) -> None:
        self.assertTrue(plan_is_clean(self.plan))
        production = self.plan["production_snapshot"]
        self.assertEqual(production["exact_icpn_count"], 912)
        self.assertEqual(production["base_device_count"], 293)
        self.assertEqual(production["stm32l0_exact_icpn_count"], 0)
        self.assertFalse(self.plan["production_write_applied"])
        self.assertEqual(self.plan["canonical_dataset_admission"], "deferred")
        self.assertFalse(self.plan["programming_algorithm_equivalence_claimed"])
        self.assertFalse(self.plan["physical_hil_qualified"])
        self.assertFalse(self.plan["runtime_support_claimed"])
        contract = self.plan["metadata_contract"]
        for key in (
            "canonical_admission_authorized",
            "production_write_authorized",
            "programming_policy_defined",
            "flash_geometry_qualified",
            "option_security_semantics_qualified",
            "physical_hil_qualified",
            "runtime_programming_support_claimed",
            "scope_expansion_authorized",
        ):
            self.assertIs(contract[key], False)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import unittest

from device_catalog_admission_framework import CandidateReject
from stm32l4_metadata_policy import (
    EXPECTED_SERIES,
    build_candidate_inputs,
    build_metadata_row,
    load_ordering_authority,
)
from stm32l4_phase_l4_3_policy import build_plan, production_snapshot
from validate_stm32l4_phase_l4_2_retained_evidence import main as validate_retained


class STM32L4L43MetadataPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.candidates = build_candidate_inputs()
        cls.by_icpn = {item["icpn"]: item for item in cls.candidates}

    def test_l42_retained_evidence_is_still_valid(self) -> None:
        self.assertEqual(validate_retained(), 0)

    def test_frozen_scope_is_exactly_446_over_138_bases(self) -> None:
        self.assertEqual(len(self.candidates), 446)
        self.assertEqual(len({item["base_device"] for item in self.candidates}), 138)

    def test_ordering_authority_is_24_series_20_documents(self) -> None:
        authority = load_ordering_authority()
        self.assertEqual(set(authority), EXPECTED_SERIES)
        self.assertEqual(len({item["document_id"] for item in authority.values()}), 20)

    def test_l412_external_smps_suffix_is_preserved(self) -> None:
        row = build_metadata_row(self.by_icpn["STM32L412CBT6P"])
        self.assertEqual(row["option_suffix"], "P")
        self.assertEqual(row["package"], "LQFP")

    def test_l433_temperature_and_packing_are_not_collapsed(self) -> None:
        row = build_metadata_row(self.by_icpn["STM32L433CBY6TR"])
        self.assertEqual(row["option_suffix"], "TR")
        self.assertEqual(row["temperature_grade"], "-40..85 C")

    def test_l496_power_option_is_preserved(self) -> None:
        row = build_metadata_row(self.by_icpn["STM32L496AGI6P"])
        self.assertEqual(row["option_suffix"], "P")

    def test_l4s_blank_option_remains_valid(self) -> None:
        row = build_metadata_row(self.by_icpn["STM32L4S5AII3"])
        self.assertEqual(row["option_suffix"], "")

    def test_excluded_non_active_identity_is_rejected(self) -> None:
        candidate = {"manufacturer":"STMicroelectronics","series":"STM32L452","base_device":"STM32L452CE","icpn":"STM32L452CET6P"}
        with self.assertRaises(CandidateReject):
            build_metadata_row(candidate)

    def test_syntactically_plausible_unretained_identity_is_rejected(self) -> None:
        candidate = {"manufacturer":"STMicroelectronics","series":"STM32L412","base_device":"STM32L412C8","icpn":"STM32L412C8T7"}
        with self.assertRaises(CandidateReject):
            build_metadata_row(candidate)

    def test_production_boundary_remains_1272_and_excludes_l4(self) -> None:
        snapshot = production_snapshot()
        self.assertEqual(snapshot["exact_icpn_count"], 1272)
        self.assertEqual(snapshot["base_device_count"], 392)
        self.assertEqual(snapshot["family_count"], 11)
        self.assertEqual(snapshot["stm32l4_exact_icpn_count"], 0)

    def test_plan_never_expands_scope(self) -> None:
        plan = build_plan()
        self.assertEqual(plan["candidate_count"], 446)
        self.assertEqual(plan["base_device_count"], 138)
        self.assertFalse(plan["production_write_applied"])
        self.assertEqual(plan["canonical_dataset_admission"], "deferred")


if __name__ == "__main__":
    unittest.main()

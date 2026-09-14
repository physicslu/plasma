#!/usr/bin/env python3
from __future__ import annotations

import unittest

from device_catalog_admission_framework import CandidateReject
from stm32l1_metadata_policy import (
    EXPECTED_SUBFAMILIES,
    build_candidate_inputs,
    build_metadata_row,
    load_exact_variant_exceptions,
    load_ordering_authority,
)
from stm32l1_phase_l1_3_policy import build_plan, plan_is_clean


class STM32L1PhaseL13MetadataPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.candidates = build_candidate_inputs()
        cls.by_icpn = {row["icpn"]: row for row in cls.candidates}

    def test_authority_coverage_is_complete_and_deterministic(self) -> None:
        records = load_ordering_authority()
        self.assertEqual(len(records), 10)
        self.assertEqual(len({row["document_id"] for row in records}), 10)
        self.assertEqual(
            {subfamily for row in records for subfamily in row["subfamilies"]},
            EXPECTED_SUBFAMILIES,
        )
        self.assertEqual(
            [row["authority_id"] for row in records],
            [
                "l100-gen-a",
                "l100-xc",
                "l15-gen-a",
                "l15-xc-low-pin",
                "l15-xc-high-pin",
                "l15-xd",
                "l15-xe",
                "l162-xc",
                "l162-xd",
                "l162-xe",
            ],
        )

    def test_retained_candidate_boundary_is_exact(self) -> None:
        self.assertEqual(len(self.candidates), 144)
        self.assertEqual(len({row["base_device"] for row in self.candidates}), 59)
        self.assertEqual(len(self.by_icpn), 144)

    def test_exact_variant_exception_whitelist_is_empty(self) -> None:
        self.assertEqual(load_exact_variant_exceptions(), {})

    def test_generation_a_identity_stays_distinct(self) -> None:
        generated = build_metadata_row(self.by_icpn["STM32L151C6T6A"])
        legacy = build_metadata_row(self.by_icpn["STM32L151CCT6"])
        self.assertEqual(generated["option_suffix"], "A")
        self.assertEqual(legacy["option_suffix"], "")
        self.assertNotEqual(generated["base_device"], legacy["base_device"])

    def test_low_and_high_pin_xc_authorities_do_not_overlap(self) -> None:
        low = build_metadata_row(self.by_icpn["STM32L151UCY6DTR"])
        high = build_metadata_row(self.by_icpn["STM32L151QCH6"])
        self.assertEqual(low["pin_count"], "63")
        self.assertEqual(low["package"], "WLCSP")
        self.assertEqual(low["option_suffix"], "DTR")
        self.assertIn("DocID022799", low["source_reference"])
        self.assertEqual(high["pin_count"], "132")
        self.assertEqual(high["package"], "BGA")
        self.assertIn("DS10262", high["source_reference"])

    def test_package_dependent_104_pin_resolution(self) -> None:
        row = build_metadata_row(self.by_icpn["STM32L162VEY6TR"])
        self.assertEqual(row["pin_count"], "104")
        self.assertEqual(row["package"], "WLCSP104")
        self.assertEqual(row["flash_size"], "512 KiB")

    def test_identity_outside_retained_scope_fails_closed(self) -> None:
        candidate = dict(self.by_icpn["STM32L151C6T6A"])
        candidate["icpn"] = "STM32L151C6T6ATR_FAKE"
        with self.assertRaises(CandidateReject):
            build_metadata_row(candidate)

    def test_full_plan_is_clean_and_production_is_unchanged(self) -> None:
        plan = build_plan()
        self.assertTrue(plan_is_clean(plan))
        self.assertEqual(
            plan["decision_counts"],
            {"metadata_ready": 144, "manual_review_required": 0, "reject": 0},
        )
        self.assertEqual(plan["exact_variant_exception_icpns"], [])
        self.assertEqual(plan["issues"], [])
        self.assertEqual(plan["manual_review_base_devices"], [])
        production = plan["production_snapshot"]
        self.assertEqual(production["exact_icpn_count"], 1718)
        self.assertEqual(production["base_device_count"], 530)
        self.assertEqual(production["family_count"], 12)
        self.assertEqual(production["stm32l1_exact_icpn_count"], 0)


if __name__ == "__main__":
    unittest.main()

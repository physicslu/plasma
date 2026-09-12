#!/usr/bin/env python3
from __future__ import annotations

import unittest

from stm32l0_admission_policy import TARGET_CONFIG
from stm32l0_phase_l0_2_discovery import commercial_core
from stm32l0_phase_l0_4_admission import admission_plan_is_clean, build_admission_plan


class STM32L0PhaseL04AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = build_admission_plan()

    def test_all_360_metadata_ready_identities_are_capability_dispositioned(self) -> None:
        self.assertEqual(self.plan["manufacturer_verified_identity_count"], 360)
        self.assertEqual(self.plan["metadata_ready_count"], 360)
        self.assertEqual(
            self.plan["capability_admittable_count"] + self.plan["capability_unresolved_count"],
            360,
        )
        replay = self.plan["current_mapping_replay"]
        self.assertEqual(replay["unique"] + replay["ambiguous"] + replay["unmapped"], 360)
        self.assertEqual(replay["unique"], self.plan["capability_admittable_count"])
        self.assertEqual(replay["ambiguous"] + replay["unmapped"], self.plan["capability_unresolved_count"])

    def test_admitted_candidates_have_one_l0_ordering_pattern_route(self) -> None:
        self.assertEqual(self.plan["candidate_count"], self.plan["capability_admittable_count"])
        for item in self.plan["candidates"]:
            mapping = item["base_mapping"]
            self.assertEqual(mapping["status"], "unique")
            self.assertEqual(mapping["target_config"], TARGET_CONFIG)
            pattern = mapping["ordering_pattern"]
            self.assertTrue(pattern.endswith("x"))
            self.assertTrue(commercial_core(item["icpn"]).startswith(pattern[:-1]))
            row = item["proposed_canonical_row"]
            self.assertEqual(row["icpn"], item["icpn"])
            self.assertEqual(row["openocd_target_config"], TARGET_CONFIG)
            self.assertEqual(row["existing_identifier_kind"], "ordering_pattern")
            self.assertEqual(row["mapping_status"], "deterministic_ordering_pattern")

    def test_capability_unresolved_is_not_identity_or_metadata_rejection(self) -> None:
        for item in self.plan["capability_unresolved"]:
            self.assertEqual(item["identity_status"], "manufacturer_verified_active")
            self.assertEqual(item["metadata_status"], "metadata_ready")
            self.assertEqual(item["capability_status"], "openocd_ordering_pattern_unresolved")
            self.assertIn(item["mapping"]["status"], {"ambiguous", "unmapped"})
        self.assertFalse(self.plan["capability_unresolved_is_identity_rejection"])

    def test_framework_plan_is_clean_for_capability_admittable_subset(self) -> None:
        counts = self.plan["decision_counts"]
        self.assertEqual(counts["admit"], self.plan["capability_admittable_count"])
        self.assertEqual(counts["already_present"], 0)
        self.assertEqual(counts["manual_review_required"], 0)
        self.assertEqual(counts["reject"], 0)
        self.assertEqual(self.plan["canonical_rows_before"], 0)
        self.assertEqual(self.plan["canonical_dataset_admission"], "planned")
        self.assertTrue(admission_plan_is_clean(self.plan))

    def test_packing_suffix_routing_does_not_change_exact_identity(self) -> None:
        items = [item for item in self.plan["candidates"] if item["icpn"].endswith("TR")]
        self.assertTrue(items)
        for item in items[:12]:
            self.assertEqual(item["proposed_canonical_row"]["icpn"], item["icpn"])
            self.assertNotEqual(commercial_core(item["icpn"]), item["icpn"])

    def test_production_and_runtime_claims_remain_unchanged(self) -> None:
        production = self.plan["production_snapshot"]
        self.assertEqual(production["exact_icpn_count"], 912)
        self.assertEqual(production["base_device_count"], 293)
        self.assertEqual(production["stm32l0_exact_icpn_count"], 0)
        self.assertFalse(self.plan["canonical_write_applied"])
        self.assertFalse(self.plan["production_write_applied"])
        self.assertFalse(self.plan["programming_algorithm_equivalence_claimed"])
        self.assertFalse(self.plan["flash_geometry_equivalence_claimed"])
        self.assertFalse(self.plan["option_security_semantics_claimed"])
        self.assertFalse(self.plan["physical_target_qualification_claimed"])
        self.assertFalse(self.plan["hil_qualification_claimed"])
        self.assertFalse(self.plan["runtime_programming_support_claimed"])


if __name__ == "__main__":
    unittest.main()

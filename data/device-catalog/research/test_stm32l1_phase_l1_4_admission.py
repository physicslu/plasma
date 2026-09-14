#!/usr/bin/env python3
from __future__ import annotations

import unittest

from device_catalog_admission_framework import CandidateManualReview
from stm32l1_admission_policy import CANONICAL_FIELDS, TARGET_CONFIG, build_canonical_row
from stm32l1_metadata_policy import build_candidate_inputs
from stm32l1_phase_l1_1_foundation import DEFAULT_CATALOG, read_catalog
from stm32l1_phase_l1_2_discovery import resolve_mapping
from stm32l1_phase_l1_4_admission import (
    _is_unique_mapping,
    admission_plan_is_clean,
    build_admission_plan,
)


class STM32L1L14AdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = build_admission_plan()

    def test_full_plan_is_clean(self) -> None:
        self.assertTrue(admission_plan_is_clean(self.plan))
        self.assertEqual(self.plan["manufacturer_verified_identity_count"], 144)
        self.assertEqual(self.plan["metadata_ready_count"], 144)
        self.assertEqual(self.plan["capability_admittable_count"], 144)
        self.assertEqual(self.plan["capability_unresolved_count"], 0)
        self.assertEqual(self.plan["current_mapping_replay"], {"unique": 144, "ambiguous": 0, "unmapped": 0})
        self.assertEqual(
            self.plan["decision_counts"],
            {"admit": 144, "already_present": 0, "manual_review_required": 0, "reject": 0},
        )

    def test_read_only_nonclaims(self) -> None:
        for key in (
            "canonical_write_applied", "production_write_applied",
            "programming_algorithm_equivalence_claimed", "flash_geometry_equivalence_claimed",
            "option_security_semantics_claimed", "physical_target_qualification_claimed",
            "hil_qualification_claimed", "runtime_programming_support_claimed",
        ):
            self.assertIs(self.plan[key], False)
        self.assertFalse(self.plan["full_stm32l1_surface_covered"])
        self.assertTrue(self.plan["fail_closed"])

    def test_production_boundary(self) -> None:
        snapshot = self.plan["production_snapshot"]
        self.assertEqual(snapshot["exact_icpn_count"], 1718)
        self.assertEqual(snapshot["base_device_count"], 530)
        self.assertEqual(snapshot["family_count"], 12)
        self.assertEqual(snapshot["stm32l1_exact_icpn_count"], 0)

    def test_exact_candidate_has_unique_route(self) -> None:
        candidate = dict(build_candidate_inputs()[0])
        mapping = resolve_mapping(candidate["icpn"], read_catalog(DEFAULT_CATALOG))
        self.assertTrue(_is_unique_mapping(mapping))
        candidate["base_mapping"] = mapping
        row = build_canonical_row(candidate, list(CANONICAL_FIELDS))
        self.assertEqual(tuple(row), CANONICAL_FIELDS)
        self.assertEqual(row["mapping_status"], "deterministic_ordering_pattern")
        self.assertEqual(row["openocd_target_config"], TARGET_CONFIG)

    def test_nonunique_route_fails_closed(self) -> None:
        candidate = dict(build_candidate_inputs()[0])
        candidate["base_mapping"] = {"status": "unmapped"}
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))
        self.assertFalse(_is_unique_mapping({"status": "unmapped"}))
        self.assertFalse(_is_unique_mapping({"status": "ambiguous", "ordering_patterns": ["A", "B"]}))

    def test_wrong_target_fails_closed(self) -> None:
        self.assertFalse(_is_unique_mapping({
            "status": "unique",
            "ordering_pattern": "STM32L151C6x",
            "target_config": "tcl/target/stm32l4x.cfg",
        }))


if __name__ == "__main__":
    unittest.main()

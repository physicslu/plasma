#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest

from st_product_page_acquisition import AcquisitionError
from stm32l1_phase_l1_2_discovery import (
    DiscoverySurface,
    DiscoveryTarget,
    EXPECTED_L1_1_REPRESENTATIVES,
    GENERATION_A_DENSITIES,
    GENERATION_A_SUBFAMILIES,
    _aggregate_surface_evidence,
    deterministic_targets,
    read_catalog,
    requires_generation_a_companion,
    target_manifest,
    validate_gate1_production_boundary,
    validate_l1_1_boundary,
    validate_targets,
)


class STM32L1PhaseL12DiscoveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.rows = read_catalog()
        cls.targets = deterministic_targets(cls.rows)

    def test_frozen_boundaries_are_valid(self) -> None:
        validate_l1_1_boundary()
        production = validate_gate1_production_boundary()
        self.assertEqual(sum(item["row_count"] for item in production["sources"]), 1718)
        self.assertFalse(any(item["family"] == "STM32L1" for item in production["sources"]))

    def test_deterministic_base_device_set_is_unique_and_bounded(self) -> None:
        bases = [target.base_device for target in self.targets]
        self.assertEqual(len(bases), len(set(bases)))
        self.assertLessEqual(len(bases), 87)
        self.assertTrue(EXPECTED_L1_1_REPRESENTATIVES.issubset(set(bases)))
        self.assertEqual({target.subfamily for target in self.targets}, {"STM32L100", "STM32L151", "STM32L152", "STM32L162"})

    def test_generation_a_policy_is_density_scoped_not_subfamily_wide(self) -> None:
        for target in self.targets:
            expected = target.subfamily in GENERATION_A_SUBFAMILIES and target.base_device[-1:] in GENERATION_A_DENSITIES
            self.assertEqual(requires_generation_a_companion(target.subfamily, target.base_device), expected)
            roles = [surface.role for surface in target.surfaces]
            self.assertEqual(roles[0], "canonical_or_legacy")
            self.assertEqual("generation_a_companion" in roles, expected)
            self.assertEqual(len(roles), 2 if expected else 1)

    def test_l1_1_representatives_preserve_generation_aware_semantics(self) -> None:
        by_base = {target.base_device: target for target in self.targets}
        for base in ("STM32L100C6", "STM32L151C6", "STM32L152C6"):
            self.assertEqual([surface.role for surface in by_base[base].surfaces], ["canonical_or_legacy", "generation_a_companion"])
        self.assertEqual([surface.role for surface in by_base["STM32L162QC"].surfaces], ["canonical_or_legacy"])

    def test_target_manifest_is_fail_closed_and_has_no_authority_escape(self) -> None:
        manifest = target_manifest(self.targets)
        self.assertEqual(manifest["base_device_count"], len(self.targets))
        self.assertGreater(manifest["evidence_surface_count"], 0)
        self.assertGreater(manifest["generation_pair_target_count"], 0)
        self.assertTrue(all(value is False for value in manifest["claims"].values()))

    def test_surface_policy_mutation_fails_closed(self) -> None:
        targets = list(self.targets)
        victim = next(target for target in targets if len(target.surfaces) == 2)
        index = targets.index(victim)
        targets[index] = DiscoveryTarget(
            subfamily=victim.subfamily,
            base_device=victim.base_device,
            surfaces=(victim.surfaces[0],),
            selection_reason=victim.selection_reason,
        )
        with self.assertRaises(AcquisitionError):
            validate_targets(targets)

    def test_cross_surface_lifecycle_conflict_fails_closed(self) -> None:
        target = DiscoveryTarget(
            subfamily="STM32L151",
            base_device="STM32L151C6",
            surfaces=(
                DiscoverySurface("canonical_or_legacy", "https://www.st.com/en/microcontrollers-microprocessors/stm32l151c6.html"),
                DiscoverySurface("generation_a_companion", "https://www.st.com/en/microcontrollers-microprocessors/stm32l151c6-a.html"),
            ),
            selection_reason="unit-test",
        )
        active_record = {"icpn": "STM32L151C6T6A", "marketing_status": "Active"}
        non_active_record = {"icpn": "STM32L151C6T6A", "marketing_status": "NRND"}
        acquired = [
            {
                "role": "canonical_or_legacy",
                "evidence": {
                    "exact_icpns": [],
                    "excluded_non_active_part_numbers": [non_active_record],
                    "part_number_records": [non_active_record],
                },
            },
            {
                "role": "generation_a_companion",
                "evidence": {
                    "exact_icpns": ["STM32L151C6T6A"],
                    "excluded_non_active_part_numbers": [],
                    "part_number_records": [active_record],
                },
            },
        ]
        with self.assertRaises(AcquisitionError):
            _aggregate_surface_evidence(target=target, acquired=acquired)

    def test_generation_aggregate_keeps_legacy_and_active_exact_sets_separate(self) -> None:
        target = DiscoveryTarget(
            subfamily="STM32L100",
            base_device="STM32L100C6",
            surfaces=(
                DiscoverySurface("canonical_or_legacy", "https://www.st.com/en/microcontrollers-microprocessors/stm32l100c6.html"),
                DiscoverySurface("generation_a_companion", "https://www.st.com/en/microcontrollers-microprocessors/stm32l100c6-a.html"),
            ),
            selection_reason="unit-test",
        )
        legacy = {"icpn": "STM32L100C6U6", "marketing_status": "NRND"}
        active = {"icpn": "STM32L100C6U6A", "marketing_status": "Active"}
        aggregate = _aggregate_surface_evidence(
            target=target,
            acquired=[
                {
                    "role": "canonical_or_legacy",
                    "evidence": {
                        "exact_icpns": [],
                        "excluded_non_active_part_numbers": [legacy],
                        "part_number_records": [legacy],
                    },
                },
                {
                    "role": "generation_a_companion",
                    "evidence": {
                        "exact_icpns": ["STM32L100C6U6A"],
                        "excluded_non_active_part_numbers": [],
                        "part_number_records": [active],
                    },
                },
            ],
        )
        self.assertEqual(aggregate["exact_icpns"], ["STM32L100C6U6A"])
        self.assertEqual([item["icpn"] for item in aggregate["excluded_non_active_part_numbers"]], ["STM32L100C6U6"])
        self.assertEqual(aggregate["surface_count"], 2)


if __name__ == "__main__":
    unittest.main()

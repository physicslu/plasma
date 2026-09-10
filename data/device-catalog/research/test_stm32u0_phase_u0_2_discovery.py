#!/usr/bin/env python3
"""Deterministic tests for STM32U0 Phase U0.2 commercial discovery."""

from __future__ import annotations

import unittest

from st_product_page_acquisition import AcquisitionError
from stm32u0_phase_u0_1_foundation import read_catalog
from stm32u0_phase_u0_2_discovery import (
    DEFAULT_MANIFEST,
    EXPECTED_BASE_COUNTS,
    MAX_TARGETS,
    DiscoveryTarget,
    deterministic_targets,
    discovery_is_clean,
    read_manifest,
    source_url_for_base,
)

EXPECTED_REPRESENTATIVES = {"STM32U031C6", "STM32U073C8", "STM32U083CC"}


class STM32U0U02DiscoveryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.catalog_rows = read_catalog()

    def test_frozen_ordering_surface_resolves_to_26_unique_base_devices(self) -> None:
        targets = deterministic_targets(self.catalog_rows)
        self.assertEqual(len(targets), MAX_TARGETS)
        self.assertEqual(len({base for _, base in targets}), MAX_TARGETS)
        counts = {subfamily: sum(1 for sub, _ in targets if sub == subfamily) for subfamily in EXPECTED_BASE_COUNTS}
        self.assertEqual(counts, EXPECTED_BASE_COUNTS)
        self.assertTrue(EXPECTED_REPRESENTATIVES.issubset({base for _, base in targets}))

    def test_manifest_is_exact_projection_of_frozen_u01_ordering_surface(self) -> None:
        pilot_id, targets = read_manifest(DEFAULT_MANIFEST, self.catalog_rows)
        self.assertEqual(pilot_id, "stm32u0-u0.2-official-st-commercial-discovery-2026-09-10")
        self.assertEqual(
            [(target.subfamily, target.base_device) for target in targets],
            deterministic_targets(self.catalog_rows),
        )
        for target in targets:
            self.assertEqual(target.source_url, source_url_for_base(target.base_device))

    def test_manifest_does_not_admit_cmsis_aliases(self) -> None:
        _, targets = read_manifest(DEFAULT_MANIFEST, self.catalog_rows)
        bases = {target.base_device for target in targets}
        for alias in (
            "STM32U031G6YxT", "STM32U031G8YxT", "STM32U073H8YxT",
            "STM32U073HBYxT", "STM32U073HCYxT", "STM32U083HCYxT",
        ):
            self.assertNotIn(alias, bases)

    def test_source_url_is_canonical_official_st_product_page(self) -> None:
        self.assertEqual(
            source_url_for_base("STM32U083RC"),
            "https://www.st.com/en/microcontrollers-microprocessors/stm32u083rc.html",
        )

    def test_clean_gate_accepts_dispositioned_404_but_not_manual_review(self) -> None:
        base = {
            "attempted": MAX_TARGETS,
            "dispositioned_targets": MAX_TARGETS,
            "acquisition_failure": 0,
            "bounded_discovery_clean": True,
            "identity_manual_intervention_required": 0,
            "active_exact_icpn_candidates": 1,
            "claims": {
                "canonical_admission_authorized": False,
                "production_write_authorized": False,
            },
        }
        self.assertTrue(discovery_is_clean(base))
        base["identity_manual_intervention_required"] = 1
        self.assertFalse(discovery_is_clean(base))

    def test_target_dataclass_is_research_only_data(self) -> None:
        target = DiscoveryTarget(
            "STM32U031", "STM32U031C6", source_url_for_base("STM32U031C6"), "test"
        )
        self.assertEqual(target.base_device, "STM32U031C6")
        with self.assertRaises(AcquisitionError):
            source_url_for_base("") if False else read_manifest(DEFAULT_MANIFEST.with_name("missing.json"), self.catalog_rows)


if __name__ == "__main__":
    unittest.main()

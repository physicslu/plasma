#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from stm32f4_admission_policy import _package_and_pins
from stm32f4_coverage_gap_inventory import build_inventory

CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"


class STM32F4Phase42DRYWLCSP64PolicyTests(unittest.TestCase):
    def test_ry_maps_to_wlcsp64(self) -> None:
        self.assertEqual(_package_and_pins("R", "Y"), ("WLCSP", "64"))

    def test_policy_mapping_remains_valid_after_admission(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertEqual(inventory["production"]["exact_icpn_rows"], 208)
        self.assertEqual(inventory["production"]["base_device_count"], 70)
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(inventory["gap"]["base_device_count"], 79)
        self.assertEqual(inventory["gap"]["policy_ready_count"], 0)
        self.assertEqual(inventory["gap"]["policy_blocked_count"], 79)

        gap_bases = {
            item["base_device"]
            for item in inventory["gap"]["policy_ready"] + inventory["gap"]["policy_blocked"]
        }
        self.assertNotIn("STM32F412RE", gap_bases)
        self.assertNotIn("STM32F412RG", gap_bases)

    def test_admitted_bases_are_now_in_production(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        production = set(inventory["production"]["base_devices"])
        self.assertIn("STM32F412RE", production)
        self.assertIn("STM32F412RG", production)


if __name__ == "__main__":
    unittest.main()

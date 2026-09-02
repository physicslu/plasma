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

    def test_policy_delta_unlocks_exactly_two_bases(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertEqual(inventory["production"]["exact_icpn_rows"], 199)
        self.assertEqual(inventory["production"]["base_device_count"], 68)
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(inventory["gap"]["base_device_count"], 81)
        self.assertEqual(inventory["gap"]["policy_ready_count"], 2)
        self.assertEqual(inventory["gap"]["policy_blocked_count"], 79)

        ready = {item["base_device"]: item for item in inventory["gap"]["policy_ready"]}
        self.assertEqual(set(ready), {"STM32F412RE", "STM32F412RG"})
        for base in ready:
            self.assertEqual(ready[base]["package_codes"], ["T", "Y"])
            self.assertEqual(ready[base]["policy_blockers"], [])

    def test_production_is_unchanged(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        production = set(inventory["production"]["base_devices"])
        self.assertNotIn("STM32F412RE", production)
        self.assertNotIn("STM32F412RG", production)


if __name__ == "__main__":
    unittest.main()

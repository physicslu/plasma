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
EXPECTED_READY = {"STM32F405OE", "STM32F405OG", "STM32F415OG"}


class STM32F4Phase42HOYWLCSP90PolicyTests(unittest.TestCase):
    def test_oy_maps_to_wlcsp90(self) -> None:
        self.assertEqual(_package_and_pins("O", "Y"), ("WLCSP", "90"))

    def test_policy_unlocks_exactly_three_bases(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertEqual(inventory["production"]["exact_icpn_rows"], 208)
        self.assertEqual(inventory["production"]["base_device_count"], 70)
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(inventory["gap"]["base_device_count"], 79)
        self.assertEqual(inventory["gap"]["policy_ready_count"], 3)
        self.assertEqual(inventory["gap"]["policy_blocked_count"], 76)

        ready = {item["base_device"] for item in inventory["gap"]["policy_ready"]}
        self.assertEqual(ready, EXPECTED_READY)

    def test_ready_bases_have_only_y_package_and_no_residual_blocker(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        ready = {item["base_device"]: item for item in inventory["gap"]["policy_ready"]}
        for base in EXPECTED_READY:
            self.assertEqual(ready[base]["package_codes"], ["Y"])
            self.assertEqual(ready[base]["policy_blockers"], [])

    def test_no_production_write_occurs_in_policy_transaction(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        production = set(inventory["production"]["base_devices"])
        self.assertTrue(EXPECTED_READY.isdisjoint(production))


if __name__ == "__main__":
    unittest.main()

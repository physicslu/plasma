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


class STM32F4Phase42STYWLCSP36PolicyTests(unittest.TestCase):
    def _inventory(self):
        return build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)

    def test_ty_maps_to_wlcsp36(self) -> None:
        self.assertEqual(_package_and_pins("T", "Y"), ("WLCSP", "36"))

    def test_stm32f410tb_is_ready_or_already_admitted(self) -> None:
        inventory = self._inventory()
        production = set(inventory["production"]["base_devices"])
        gaps = {
            item["base_device"]: item
            for item in inventory["gap"]["policy_ready"] + inventory["gap"]["policy_blocked"]
        }

        if "STM32F410TB" in production:
            self.assertNotIn("STM32F410TB", gaps)
            return

        self.assertIn("STM32F410TB", gaps)
        self.assertTrue(gaps["STM32F410TB"]["admission_policy_ready"])
        self.assertEqual(gaps["STM32F410TB"]["policy_blockers"], [])

    def test_stm32f410t8_stays_fail_closed_until_flash8_is_supported_or_admitted(self) -> None:
        inventory = self._inventory()
        production = set(inventory["production"]["base_devices"])
        gaps = {
            item["base_device"]: item
            for item in inventory["gap"]["policy_ready"] + inventory["gap"]["policy_blocked"]
        }

        if "STM32F410T8" in production:
            self.assertNotIn("STM32F410T8", gaps)
            return

        self.assertIn("STM32F410T8", gaps)
        self.assertFalse(gaps["STM32F410T8"]["admission_policy_ready"])
        self.assertEqual(
            gaps["STM32F410T8"]["policy_blockers"],
            ["unsupported flash-size code 8"],
        )


if __name__ == "__main__":
    unittest.main()

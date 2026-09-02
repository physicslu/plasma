#!/usr/bin/env python3
from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from stm32f4_admission_policy import _package_and_pins  # noqa: E402
from stm32f4_coverage_gap_inventory import build_inventory  # noqa: E402

CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"


class STM32F4Phase42ACTLQFP48PolicyTests(unittest.TestCase):
    def test_ct_maps_to_lqfp48(self) -> None:
        self.assertEqual(_package_and_pins("C", "T"), ("LQFP", "48"))

    def test_policy_remains_bounded_after_candidate_admission(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(
            inventory["gap"]["base_device_count"],
            149 - inventory["production"]["base_device_count"],
        )
        self.assertEqual(
            inventory["gap"]["base_device_count"],
            inventory["gap"]["policy_ready_count"] + inventory["gap"]["policy_blocked_count"],
        )

        ready = {item["base_device"]: item for item in inventory["gap"]["policy_ready"]}
        blocked = {item["base_device"]: item for item in inventory["gap"]["policy_blocked"]}
        production_bases = set(inventory["production"]["base_devices"])

        self.assertIn("STM32F410CB", production_bases)
        self.assertNotIn("STM32F410CB", ready)
        self.assertNotIn("STM32F410CB", blocked)

        self.assertIn("STM32F410C8", blocked)
        self.assertEqual(
            blocked["STM32F410C8"]["policy_blockers"],
            ["unsupported flash-size code 8"],
        )

    def test_policy_mapping_does_not_implicitly_admit_other_ct_devices(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        production_bases = set(inventory["production"]["base_devices"])
        self.assertNotIn("STM32F410C8", production_bases)


if __name__ == "__main__":
    unittest.main()

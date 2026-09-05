#!/usr/bin/env python3
from __future__ import annotations

import json
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
EVIDENCE = HERE / "stm32f4-phase4.2af-ah-ufbga169-policy-evidence.json"
EXPECTED_READY = {
    "STM32F427AG",
    "STM32F427AI",
    "STM32F429AG",
    "STM32F429AI",
    "STM32F437AI",
    "STM32F439AI",
}
EXPECTED_RESIDUAL_A_Y_BLOCKED = {
    "STM32F469AE",
    "STM32F469AG",
    "STM32F469AI",
    "STM32F479AG",
    "STM32F479AI",
}
EXPECTED_AFFECTED = EXPECTED_READY | EXPECTED_RESIDUAL_A_Y_BLOCKED


class STM32F4Phase42AFAHUFBGA169PolicyTests(unittest.TestCase):
    def _inventory(self):
        return build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)

    def test_ah_maps_to_ufbga169(self) -> None:
        self.assertEqual(_package_and_pins("A", "H"), ("UFBGA", "169"))

    def test_exact_six_base_devices_become_policy_ready(self) -> None:
        inventory = self._inventory()
        ready = {item["base_device"]: item for item in inventory["gap"]["policy_ready"]}
        blocked = {
            item["base_device"]: item for item in inventory["gap"]["policy_blocked"]
        }
        production = set(inventory["production"]["base_devices"])
        remaining_expected = EXPECTED_READY - production

        self.assertLessEqual(remaining_expected, set(ready))
        self.assertLessEqual(EXPECTED_READY - remaining_expected, production)
        self.assertTrue(EXPECTED_READY.isdisjoint(blocked))
        for base_device in remaining_expected:
            item = ready[base_device]
            self.assertTrue(item["admission_policy_ready"])
            self.assertEqual(item["package_codes"], ["H"])
            self.assertEqual(item["policy_blockers"], [])

        if remaining_expected == EXPECTED_READY:
            self.assertEqual(inventory["production"]["exact_icpn_rows"], 364)
            self.assertEqual(inventory["production"]["base_device_count"], 128)
            self.assertEqual(inventory["gap"]["base_device_count"], 21)
            self.assertEqual(inventory["gap"]["policy_ready_count"], 6)
            self.assertEqual(inventory["gap"]["policy_blocked_count"], 15)

    def test_f469_f479_a_y_surface_remains_fail_closed(self) -> None:
        inventory = self._inventory()
        blocked = {
            item["base_device"]: item for item in inventory["gap"]["policy_blocked"]
        }
        production = set(inventory["production"]["base_devices"])
        remaining_expected = EXPECTED_RESIDUAL_A_Y_BLOCKED - production

        self.assertLessEqual(remaining_expected, set(blocked))
        for base_device in remaining_expected:
            item = blocked[base_device]
            self.assertFalse(item["admission_policy_ready"])
            self.assertEqual(item["package_codes"], ["H", "Y"])
            self.assertEqual(
                item["policy_blockers"],
                ["unsupported STM32F4 pin/package combination: A/Y"],
            )

    def test_policy_evidence_is_bounded_and_denies_admission(self) -> None:
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        expected_delta = evidence["expected_immediate_delta_before_admission"]
        self.assertEqual(evidence["phase"], "4.2AF")
        self.assertEqual(set(evidence["affected_base_devices"]), EXPECTED_AFFECTED)
        self.assertEqual(set(expected_delta["policy_ready_base_devices"]), EXPECTED_READY)
        self.assertEqual(
            set(expected_delta["residual_a_y_blocked_base_devices"]),
            EXPECTED_RESIDUAL_A_Y_BLOCKED,
        )
        self.assertEqual(expected_delta["policy_ready_count"], 6)
        self.assertEqual(expected_delta["policy_blocked_count"], 15)
        self.assertFalse(evidence["production_write_applied"])
        self.assertTrue(evidence["exact_icpn_admission_deferred"])
        self.assertTrue(evidence["a_y_policy_deferred"])
        self.assertFalse(evidence["algorithm_equivalence_claimed"])
        self.assertTrue(evidence["fail_closed"])


if __name__ == "__main__":
    unittest.main()

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
EVIDENCE = HERE / "stm32f4-phase4.2y-nh-tfbga216-policy-evidence.json"
EXPECTED_READY = {
    "STM32F429NE",
    "STM32F429NG",
    "STM32F429NI",
    "STM32F439NG",
    "STM32F439NI",
    "STM32F469NE",
    "STM32F469NG",
    "STM32F469NI",
    "STM32F479NG",
    "STM32F479NI",
}


class STM32F4Phase42YNHTFBGA216PolicyTests(unittest.TestCase):
    def _inventory(self):
        return build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)

    def test_nh_maps_to_tfbga216(self) -> None:
        self.assertEqual(_package_and_pins("N", "H"), ("TFBGA", "216"))

    def test_exact_ten_base_devices_become_policy_ready(self) -> None:
        inventory = self._inventory()
        ready = {item["base_device"]: item for item in inventory["gap"]["policy_ready"]}
        blocked = {item["base_device"] for item in inventory["gap"]["policy_blocked"]}
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
        self.assertGreaterEqual(inventory["gap"]["policy_ready_count"], len(remaining_expected))

        if remaining_expected == EXPECTED_READY:
            self.assertEqual(inventory["production"]["exact_icpn_rows"], 338)
            self.assertEqual(inventory["production"]["base_device_count"], 114)
            self.assertEqual(inventory["gap"]["base_device_count"], 35)
            self.assertEqual(inventory["gap"]["policy_ready_count"], 10)
            self.assertEqual(inventory["gap"]["policy_blocked_count"], 25)

    def test_policy_evidence_is_bounded_and_denies_admission(self) -> None:
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        expected_delta = evidence["expected_immediate_delta_before_admission"]
        self.assertEqual(evidence["phase"], "4.2Y")
        self.assertEqual(set(evidence["affected_base_devices"]), EXPECTED_READY)
        self.assertEqual(set(expected_delta["policy_ready_base_devices"]), EXPECTED_READY)
        self.assertEqual(expected_delta["policy_ready_count"], 10)
        self.assertEqual(expected_delta["policy_blocked_count"], 25)
        self.assertFalse(evidence["production_write_applied"])
        self.assertTrue(evidence["exact_icpn_admission_deferred"])
        self.assertFalse(evidence["algorithm_equivalence_claimed"])
        self.assertTrue(evidence["fail_closed"])


if __name__ == "__main__":
    unittest.main()

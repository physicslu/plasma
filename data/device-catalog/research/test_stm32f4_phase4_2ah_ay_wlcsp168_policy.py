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
EVIDENCE = HERE / "stm32f4-phase4.2ah-ay-wlcsp168-policy-evidence.json"
EXPECTED_READY = {
    "STM32F469AE",
    "STM32F469AG",
    "STM32F469AI",
    "STM32F479AG",
    "STM32F479AI",
}
EXPECTED_B_T_BLOCKED = {
    "STM32F429BE",
    "STM32F429BG",
    "STM32F429BI",
    "STM32F439BG",
    "STM32F439BI",
    "STM32F469BE",
    "STM32F469BG",
    "STM32F469BI",
    "STM32F479BG",
    "STM32F479BI",
}
EXPECTED_VISIBLE_A_Y = {
    "STM32F469AGY6TR",
    "STM32F469AIY6TR",
    "STM32F479AIY6TR",
}


class STM32F4Phase42AHAYWLCSP168PolicyTests(unittest.TestCase):
    def _inventory(self):
        return build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)

    def test_a_y_maps_to_wlcsp168(self) -> None:
        self.assertEqual(_package_and_pins("A", "Y"), ("WLCSP", "168"))

    def test_exact_five_base_devices_become_policy_ready(self) -> None:
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
            self.assertEqual(item["package_codes"], ["H", "Y"])
            self.assertEqual(item["policy_blockers"], [])

        if remaining_expected == EXPECTED_READY:
            self.assertEqual(inventory["production"]["exact_icpn_rows"], 373)
            self.assertEqual(inventory["production"]["base_device_count"], 134)
            self.assertEqual(inventory["gap"]["base_device_count"], 15)
            self.assertEqual(inventory["gap"]["policy_ready_count"], 5)
            self.assertEqual(inventory["gap"]["policy_blocked_count"], 10)

    def test_b_t_surface_remains_fail_closed(self) -> None:
        inventory = self._inventory()
        blocked = {item["base_device"]: item for item in inventory["gap"]["policy_blocked"]}
        production = set(inventory["production"]["base_devices"])
        remaining_expected = EXPECTED_B_T_BLOCKED - production

        self.assertLessEqual(remaining_expected, set(blocked))
        for base_device in remaining_expected:
            item = blocked[base_device]
            self.assertFalse(item["admission_policy_ready"])
            self.assertEqual(item["package_codes"], ["T"])
            self.assertEqual(
                item["policy_blockers"],
                ["unsupported STM32F4 pin/package combination: B/T"],
            )

    def test_policy_evidence_is_bounded_and_denies_admission(self) -> None:
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        expected_delta = evidence["expected_immediate_delta_before_admission"]
        observed = evidence["official_evidence"]["observed_active_representative_exact_icpns"]
        self.assertEqual(evidence["phase"], "4.2AH")
        self.assertEqual(set(evidence["affected_base_devices"]), EXPECTED_READY)
        self.assertEqual(set(expected_delta["policy_ready_base_devices"]), EXPECTED_READY)
        self.assertEqual(set(expected_delta["residual_b_t_blocked_base_devices"]), EXPECTED_B_T_BLOCKED)
        self.assertEqual(set(observed), EXPECTED_VISIBLE_A_Y)
        self.assertEqual(expected_delta["policy_ready_count"], 5)
        self.assertEqual(expected_delta["policy_blocked_count"], 10)
        self.assertFalse(evidence["production_write_applied"])
        self.assertTrue(evidence["exact_icpn_admission_deferred"])
        self.assertTrue(evidence["b_t_policy_deferred"])
        self.assertTrue(evidence["live_y_exact_not_assumed_for_every_base"])
        self.assertFalse(evidence["algorithm_equivalence_claimed"])
        self.assertTrue(evidence["fail_closed"])


if __name__ == "__main__":
    unittest.main()

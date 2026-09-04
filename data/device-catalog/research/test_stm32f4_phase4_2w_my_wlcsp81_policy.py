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
EVIDENCE = HERE / "stm32f4-phase4.2w-my-wlcsp81-policy-evidence.json"
EXPECTED_READY = {
    "STM32F413MG",
    "STM32F413MH",
    "STM32F423MH",
    "STM32F446MC",
    "STM32F446ME",
}
EXPECTED_PROPOSAL = {"STM32F413MGY3TR", "STM32F413MHY3TR"}


class STM32F4Phase42WMYWLCSP81PolicyTests(unittest.TestCase):
    def _inventory(self):
        return build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)

    def test_my_maps_to_wlcsp81(self) -> None:
        self.assertEqual(_package_and_pins("M", "Y"), ("WLCSP", "81"))

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
            self.assertEqual(item["package_codes"], ["Y"])
            self.assertEqual(item["policy_blockers"], [])
        self.assertGreaterEqual(inventory["gap"]["policy_ready_count"], len(remaining_expected))
        self.assertGreaterEqual(inventory["production"]["exact_icpn_rows"], 331)
        self.assertGreaterEqual(inventory["production"]["base_device_count"], 109)

    def test_policy_evidence_is_bounded_and_denies_admission(self) -> None:
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        self.assertEqual(evidence["phase"], "4.2W")
        self.assertEqual(set(evidence["affected_base_devices"]), EXPECTED_READY)
        self.assertEqual(
            {item["icpn"] for item in evidence["official_evidence"]["observed_non_active_exact_icpns"]},
            EXPECTED_PROPOSAL,
        )
        self.assertFalse(evidence["production_write_applied"])
        self.assertTrue(evidence["exact_icpn_admission_deferred"])
        self.assertFalse(evidence["algorithm_equivalence_claimed"])
        self.assertTrue(evidence["fail_closed"])


if __name__ == "__main__":
    unittest.main()

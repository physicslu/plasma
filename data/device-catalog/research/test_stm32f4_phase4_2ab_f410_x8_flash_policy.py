#!/usr/bin/env python3
from __future__ import annotations

import json
import unittest
from pathlib import Path

from stm32f4_admission_policy import FLASH_BY_CODE
from stm32f4_coverage_gap_inventory import build_inventory

HERE = Path(__file__).resolve().parent
CATALOG = HERE / "openocd-parts-canonical.csv"
CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
EVIDENCE = HERE / "stm32f4-phase4.2ab-f410-x8-flash-policy-evidence.json"
EXPECTED_READY = {"STM32F410C8", "STM32F410T8"}


class STM32F4Phase42ABF410X8FlashPolicyTests(unittest.TestCase):
    def _inventory(self):
        return build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)

    def test_flash_code_8_maps_to_64_kib(self) -> None:
        self.assertEqual(FLASH_BY_CODE["8"], "64 KiB")

    def test_only_c8_and_t8_become_immediately_policy_ready(self) -> None:
        inventory = self._inventory()
        ready = {item["base_device"]: item for item in inventory["gap"]["policy_ready"]}
        blocked = {item["base_device"]: item for item in inventory["gap"]["policy_blocked"]}
        production = set(inventory["production"]["base_devices"])
        remaining_expected = EXPECTED_READY - production

        self.assertLessEqual(remaining_expected, set(ready))
        self.assertLessEqual(EXPECTED_READY - remaining_expected, production)
        self.assertTrue(EXPECTED_READY.isdisjoint(blocked))
        for base_device in remaining_expected:
            self.assertEqual(ready[base_device]["policy_blockers"], [])

        if remaining_expected == EXPECTED_READY:
            self.assertEqual(inventory["production"]["exact_icpn_rows"], 352)
            self.assertEqual(inventory["production"]["base_device_count"], 124)
            self.assertEqual(inventory["gap"]["base_device_count"], 25)
            self.assertEqual(inventory["gap"]["policy_ready_count"], 2)
            self.assertEqual(inventory["gap"]["policy_blocked_count"], 23)
            self.assertEqual(
                blocked["STM32F410R8"]["policy_blockers"],
                ["unsupported STM32F4 package code: I"],
            )

    def test_policy_evidence_is_bounded_and_denies_admission(self) -> None:
        evidence = json.loads(EVIDENCE.read_text(encoding="utf-8"))
        expected_delta = evidence["expected_immediate_delta_before_admission"]
        self.assertEqual(evidence["phase"], "4.2AB")
        self.assertEqual(set(evidence["affected_base_devices"]), {"STM32F410C8", "STM32F410R8", "STM32F410T8"})
        self.assertEqual(set(expected_delta["policy_ready_base_devices"]), EXPECTED_READY)
        self.assertEqual(expected_delta["policy_ready_count"], 2)
        self.assertEqual(expected_delta["policy_blocked_count"], 23)
        self.assertFalse(evidence["production_write_applied"])
        self.assertTrue(evidence["exact_icpn_admission_deferred"])
        self.assertFalse(evidence["algorithm_equivalence_claimed"])
        self.assertTrue(evidence["fail_closed"])


if __name__ == "__main__":
    unittest.main()

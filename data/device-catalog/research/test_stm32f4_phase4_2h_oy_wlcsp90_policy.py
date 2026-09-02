#!/usr/bin/env python3
from __future__ import annotations

import csv
import sys
import tempfile
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
PHASE42I_ADMITTED = {
    "STM32F405OEY6TR",
    "STM32F405OGY6TR",
    "STM32F415OGY6TR",
}


class STM32F4Phase42HOYWLCSP90PolicyTests(unittest.TestCase):
    def _historical_pre_phase42i(self, directory: Path) -> Path:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [row for row in reader if row["icpn"] not in PHASE42I_ADMITTED]
        self.assertEqual(len(rows), 208)

        historical = directory / "stm32f4-commercial-icpn.csv"
        with historical.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return historical

    def test_oy_maps_to_wlcsp90(self) -> None:
        self.assertEqual(_package_and_pins("O", "Y"), ("WLCSP", "90"))

    def test_current_production_contains_the_later_phase42i_admission(self) -> None:
        inventory = build_inventory(catalog_path=CATALOG, canonical_path=CANONICAL)
        self.assertEqual(inventory["production"]["exact_icpn_rows"], 211)
        production = set(inventory["production"]["base_devices"])
        self.assertTrue(EXPECTED_READY <= production)

    def test_historical_policy_replay_unlocks_exactly_three_bases(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            historical = self._historical_pre_phase42i(Path(tmp))
            inventory = build_inventory(catalog_path=CATALOG, canonical_path=historical)

        self.assertEqual(inventory["production"]["exact_icpn_rows"], 208)
        self.assertEqual(inventory["production"]["base_device_count"], 70)
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(inventory["gap"]["base_device_count"], 79)
        self.assertEqual(inventory["gap"]["policy_ready_count"], 3)
        self.assertEqual(inventory["gap"]["policy_blocked_count"], 76)

        ready = {item["base_device"]: item for item in inventory["gap"]["policy_ready"]}
        self.assertEqual(set(ready), EXPECTED_READY)
        for base in EXPECTED_READY:
            self.assertEqual(ready[base]["package_codes"], ["Y"])
            self.assertEqual(ready[base]["policy_blockers"], [])

        production = set(inventory["production"]["base_devices"])
        self.assertTrue(EXPECTED_READY.isdisjoint(production))


if __name__ == "__main__":
    unittest.main()

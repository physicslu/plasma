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
EXPECTED_READY = {
    "STM32F407IE", "STM32F407IG", "STM32F417IE", "STM32F417IG",
    "STM32F427IG", "STM32F427II", "STM32F429IE", "STM32F429IG", "STM32F429II",
    "STM32F437IG", "STM32F437II", "STM32F439IG", "STM32F439II",
    "STM32F469IE", "STM32F469IG", "STM32F469II", "STM32F479IG", "STM32F479II",
}
PHASE42K_ADMITTED = {
    "STM32F407IEH6", "STM32F407IEH6TR", "STM32F407IEH7", "STM32F407IET6",
    "STM32F407IGH6", "STM32F407IGH6TR", "STM32F407IGH7", "STM32F407IGT6",
    "STM32F407IGT7", "STM32F417IEH6", "STM32F417IET6", "STM32F417IGH6",
    "STM32F417IGH6TR", "STM32F417IGT6", "STM32F417IGT7",
}
class STM32F4Phase42JIHT176PolicyTests(unittest.TestCase):
    def _historical_pre_phase42k(self, directory: Path) -> Path:
        with CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            fields = list(reader.fieldnames or [])
            rows = [row for row in reader if row["icpn"] not in PHASE42K_ADMITTED]
        self.assertEqual(len(rows), 211)

        historical = directory / "stm32f4-commercial-icpn.csv"
        with historical.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        return historical

    def _historical_inventory(self) -> dict:
        with tempfile.TemporaryDirectory() as tmp:
            historical = self._historical_pre_phase42k(Path(tmp))
            return build_inventory(catalog_path=CATALOG, canonical_path=historical)

    def test_i_h_and_i_t_map_to_176_pin_packages(self) -> None:
        self.assertEqual(_package_and_pins("I", "H"), ("UFBGA", "176"))
        self.assertEqual(_package_and_pins("I", "T"), ("LQFP", "176"))
    def test_policy_unlocks_exactly_eighteen_bases(self) -> None:
        inventory = self._historical_inventory()
        self.assertEqual(inventory["production"]["exact_icpn_rows"], 211)
        self.assertEqual(inventory["production"]["base_device_count"], 73)
        self.assertEqual(inventory["openocd_ordering_pattern_base_device_count"], 149)
        self.assertEqual(inventory["gap"]["base_device_count"], 76)
        self.assertEqual(inventory["gap"]["policy_ready_count"], 18)
        self.assertEqual(inventory["gap"]["policy_blocked_count"], 58)
        ready = {item["base_device"] for item in inventory["gap"]["policy_ready"]}
        self.assertEqual(ready, EXPECTED_READY)
    def test_ready_bases_require_both_h_and_t_and_have_no_residual_blocker(self) -> None:
        inventory = self._historical_inventory()
        ready = {item["base_device"]: item for item in inventory["gap"]["policy_ready"]}
        for base in EXPECTED_READY:
            self.assertEqual(ready[base]["package_codes"], ["H", "T"])
            self.assertEqual(ready[base]["policy_blockers"], [])
    def test_no_production_write_occurs_in_policy_transaction(self) -> None:
        inventory = self._historical_inventory()
        production = set(inventory["production"]["base_devices"])
        self.assertTrue(EXPECTED_READY.isdisjoint(production))
if __name__ == "__main__":
    unittest.main()

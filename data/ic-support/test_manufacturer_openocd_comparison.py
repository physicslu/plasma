#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "data/ic-support/compare_manufacturer_openocd.py"
spec = importlib.util.spec_from_file_location("compare_manufacturer_openocd", MODULE_PATH)
assert spec and spec.loader
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class ManufacturerOpenOCDComparisonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.result = comparison.validate()
        cls.payload = comparison._load(comparison.COMPARISON)
        cls.rows = {row["id"]: row for row in cls.payload["observations"]}

    def test_comparison_passes_without_hardware_claim(self) -> None:
        self.assertEqual(self.result["result"], "PASS")
        self.assertFalse(self.result["hardware_runtime_ready"])
        self.assertFalse(self.result["physical_programming_qualified"])

    def test_core_flash_semantics_match(self) -> None:
        for row_id in (
            "flash_register_map",
            "flash_unlock_keys",
            "flash_status_bits",
            "medium_density_page_size",
            "program_alignment",
            "page_erase_core",
            "mass_erase_core",
            "program_core",
        ):
            self.assertEqual(self.rows[row_id]["classification"], "exact_match")

    def test_openocd_speed_does_not_fill_manufacturer_unknown(self) -> None:
        row = self.rows["debug_adapter_speed"]
        self.assertEqual(row["classification"], "manufacturer_unresolved_backend_value")
        self.assertIsNone(row["manufacturer"]["min_hz"])
        self.assertIsNone(row["manufacturer"]["max_hz"])
        self.assertIsNone(row["manufacturer"]["recommended_hz"])
        self.assertEqual(row["openocd"]["adapter_speed_khz"], 1000)

    def test_blue_pill_128k_override_is_explicit_conflict(self) -> None:
        row = self.rows["blue_pill_flash_override"]
        self.assertEqual(row["classification"], "conflict_or_out_of_spec")
        self.assertEqual(row["manufacturer"]["STM32F103C8T6_flash_kib"], 64)
        self.assertEqual(row["openocd"]["forced_flash_kib"], 128)

    def test_openocd_optimization_is_not_device_spec(self) -> None:
        self.assertEqual(self.rows["ram_flash_loader"]["classification"], "backend_optimization")
        self.assertEqual(
            self.rows["target_halted_requirement"]["classification"],
            "backend_assumption_or_default",
        )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "data/ic-support/compare_generated_programmer_openocd.py"

spec = importlib.util.spec_from_file_location("compare_generated_programmer_openocd", MODULE_PATH)
assert spec and spec.loader
comparison = importlib.util.module_from_spec(spec)
spec.loader.exec_module(comparison)


class GeneratedProgrammerOpenOCDDifferentialTests(unittest.TestCase):
    def test_current_generated_programmer_matches_pinned_openocd_review(self) -> None:
        result = comparison.validate()
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(result["flash_size_bytes"], 64 * 1024)
        self.assertFalse(result["hardware_runtime_ready"])
        self.assertFalse(result["physical_programming_qualified"])

    def test_blue_pill_128k_override_cannot_be_absorbed(self) -> None:
        generated = comparison.generated_module()
        generated.FLASH_SIZE = 128 * 1024
        with self.assertRaises(comparison.GeneratedOpenOCDComparisonError):
            comparison.validate(generated=generated)

    def test_backend_policy_leak_fails_closed(self) -> None:
        generated = comparison.generated_module()
        generated.ADAPTER_SPEED_HZ = 1_000_000
        with self.assertRaises(comparison.GeneratedOpenOCDComparisonError):
            comparison.validate(generated=generated)

    def test_openocd_source_pin_drift_fails_closed(self) -> None:
        release = comparison._load_json(comparison.OPENOCD_RELEASE)
        modified = copy.deepcopy(release)
        modified["source_commit"] = "0" * 40
        with self.assertRaises(comparison.GeneratedOpenOCDComparisonError):
            comparison.validate(release=modified)


if __name__ == "__main__":
    unittest.main()

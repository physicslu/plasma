#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = ROOT / "data/ic-support/manufacturer_program_model.py"
spec = importlib.util.spec_from_file_location("manufacturer_program_model", MODULE_PATH)
assert spec and spec.loader
model = importlib.util.module_from_spec(spec)
spec.loader.exec_module(model)


class ManufacturerProgrammingBaselineTests(unittest.TestCase):
    def test_baseline_is_frozen_and_non_executable(self) -> None:
        baseline = model.validate_baseline()
        self.assertEqual(baseline["target"]["icpn"], "STM32F103C8T6")
        self.assertEqual(baseline["status"], "frozen_manufacturer_only")
        self.assertFalse(baseline["qualification_boundary"]["hardware_runtime_ready"])

    def test_program_sequence_is_manufacturer_derived_halfword_flow(self) -> None:
        trace = model.normalized_operation_trace("program_halfword")
        self.assertEqual(
            [step["op"] for step in trace],
            [
                "poll_bit",
                "set_bit",
                "write_memory",
                "poll_bit",
                "reject_if_any_bit_set",
                "readback_compare",
            ],
        )
        self.assertEqual(trace[2]["width_bits"], 16)

    def test_swd_and_jtag_speed_unknown_is_preserved(self) -> None:
        baseline = model.validate_baseline()
        for name in ("SWD", "JTAG"):
            clock = baseline["programming_profile"]["interfaces"][name]["clock_hz"]
            self.assertIsNone(clock["manufacturer_min"])
            self.assertIsNone(clock["manufacturer_max"])
            self.assertIsNone(clock["manufacturer_recommended"])

    def test_digest_drift_fails_closed(self) -> None:
        baseline = json.loads(model.DEFAULT_BASELINE.read_text(encoding="utf-8"))
        baseline["device_profile"]["memory_map"]["main_flash"]["size_bytes"] = 1
        with tempfile.TemporaryDirectory() as tmp:
            candidate = Path(tmp) / "baseline.json"
            candidate.write_text(json.dumps(baseline, sort_keys=True), encoding="utf-8")
            with self.assertRaises(model.ManufacturerBaselineError):
                model.validate_baseline(candidate, model.DEFAULT_LOCK)


if __name__ == "__main__":
    unittest.main()

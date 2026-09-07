#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from device_catalog_admission_framework import AdmissionError, write_canonical_dataset  # noqa: E402
from stm32f2_admission_policy import CANONICAL_FIELDS  # noqa: E402
from stm32f2_phase4_3g_admission import (  # noqa: E402
    DEFAULT_CANONICAL,
    admission_plan_is_clean,
    build_admission_plan,
)

EXPECTED = {
    "STM32F205RCT6", "STM32F205RCT6TR", "STM32F205RCT7", "STM32F205RCT7TR",
    "STM32F207IEH6", "STM32F207IEH6TR", "STM32F207IET6",
    "STM32F215RGT6", "STM32F215RGT6TR",
    "STM32F217IGH6", "STM32F217IGH6TR", "STM32F217IGT6", "STM32F217IGT7",
}


class STM32F2Phase43GAdmissionTests(unittest.TestCase):
    def test_plan_is_exact_clean_and_read_only(self) -> None:
        plan = build_admission_plan()
        self.assertTrue(admission_plan_is_clean(plan))
        self.assertEqual({item["icpn"] for item in plan["candidates"]}, EXPECTED)
        self.assertEqual(plan["lifecycle_exclusions"], [])
        self.assertFalse(plan["production_write_applied"])
        self.assertFalse(plan["programming_algorithm_equivalence_claimed"])
        self.assertFalse(plan["runtime_programming_support_claimed"])

    def test_prestate_is_nine_rows_and_production_bound(self) -> None:
        with DEFAULT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(tuple(reader.fieldnames or ()), CANONICAL_FIELDS)
            rows = list(reader)
        self.assertEqual(len(rows), 9)
        manifest = json.loads((HERE.parent / "production" / "icpn-v1-manifest.json").read_text())
        source = next(item for item in manifest["sources"] if item["family"] == "STM32F2")
        self.assertEqual(source["row_count"], 9)

    def test_generic_writer_is_exact_and_idempotent_in_sandbox(self) -> None:
        plan = build_admission_plan()
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / DEFAULT_CANONICAL.name
            canonical.write_bytes(DEFAULT_CANONICAL.read_bytes())
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_after"], 22)
            self.assertEqual(set(first["added"]), EXPECTED)
            self.assertEqual(second["status"], "no_op")

    def test_writer_rejects_unbound_canonical_drift(self) -> None:
        plan = build_admission_plan()
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / DEFAULT_CANONICAL.name
            canonical.write_bytes(DEFAULT_CANONICAL.read_bytes())
            with canonical.open("a", encoding="utf-8") as handle:
                handle.write("unexpected\n")
            with self.assertRaisesRegex(AdmissionError, "changed after admission planning"):
                write_canonical_dataset(plan=plan, canonical_path=canonical)


if __name__ == "__main__":
    unittest.main()

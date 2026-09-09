#!/usr/bin/env python3
"""Regression tests for read-only STM32F3 Phase 4.4D admission planning."""

from __future__ import annotations

import csv
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import AdmissionError, write_canonical_dataset
from stm32f3_admission_policy import CANONICAL_FIELDS
from stm32f3_phase4_4d_admission import admission_plan_is_clean, build_admission_plan

EXPECTED = {
    "STM32F301C6T6",
    "STM32F301C6T6TR",
    "STM32F301C6T7",
    "STM32F302C6T6",
    "STM32F303C6T6",
    "STM32F318C8T6",
    "STM32F318C8Y6TR",
    "STM32F334C4T6",
    "STM32F373C8T6",
    "STM32F373C8T6TR",
}


def write_empty_canonical(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS, lineterminator="\n")
        writer.writeheader()


class STM32F3Phase44DAdmissionTests(unittest.TestCase):
    def test_current_absent_canonical_builds_clean_plan(self) -> None:
        plan = build_admission_plan()
        self.assertTrue(admission_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 10)
        self.assertEqual(plan["decision_counts"], {
            "admit": 10,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        })
        self.assertEqual({item["icpn"] for item in plan["candidates"]}, EXPECTED)
        self.assertEqual(plan["canonical_rows_before"], 0)
        self.assertTrue(plan["inputs"]["canonical_dataset_absent_before_admission"])
        self.assertEqual(plan["production_snapshot"]["exact_icpn_count"], 492)
        self.assertEqual(plan["production_snapshot"]["base_device_count"], 169)
        self.assertFalse(plan["production_write_applied"])
        self.assertFalse(plan["runtime_programming_support_claimed"])

    def test_sandbox_writer_is_exact_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / "stm32f3-commercial-icpn.csv"
            write_empty_canonical(canonical)
            plan = build_admission_plan(canonical_path=canonical)
            self.assertTrue(admission_plan_is_clean(plan))
            self.assertFalse(plan["inputs"]["canonical_dataset_absent_before_admission"])
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 0)
            self.assertEqual(first["rows_after"], 10)
            self.assertEqual(set(first["added"]), EXPECTED)
            self.assertEqual(second["status"], "no_op")
            with canonical.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual(len(rows), 10)
            self.assertEqual({row["icpn"] for row in rows}, EXPECTED)

    def test_writer_rejects_canonical_drift_after_planning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / "stm32f3-commercial-icpn.csv"
            write_empty_canonical(canonical)
            plan = build_admission_plan(canonical_path=canonical)
            with canonical.open("a", encoding="utf-8") as handle:
                handle.write("unexpected\n")
            with self.assertRaisesRegex(AdmissionError, "changed after admission planning"):
                write_canonical_dataset(plan=plan, canonical_path=canonical)

    def test_planner_rejects_valid_but_nonempty_prestate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / "stm32f3-commercial-icpn.csv"
            write_empty_canonical(canonical)
            clean_plan = build_admission_plan(canonical_path=canonical)
            valid_row = clean_plan["candidates"][0]["proposed_canonical_row"]
            with canonical.open("a", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS, lineterminator="\n")
                writer.writerow(valid_row)
            with self.assertRaisesRegex(AdmissionError, "zero-row STM32F3 canonical prestate"):
                build_admission_plan(canonical_path=canonical)

    def test_plan_preserves_policy_metadata(self) -> None:
        plan = build_admission_plan()
        rows = {
            item["icpn"]: item["proposed_canonical_row"]
            for item in plan["candidates"]
        }
        self.assertEqual(rows["STM32F318C8Y6TR"]["package"], "WLCSP")
        self.assertEqual(rows["STM32F318C8Y6TR"]["pin_count"], "49")
        self.assertEqual(rows["STM32F334C4T6"]["flash_size"], "16 KiB")
        self.assertEqual(rows["STM32F301C6T7"]["temperature_grade"], "-40 to 105 C")
        self.assertTrue(all(row["openocd_target_config"] == "tcl/target/stm32f3x.cfg" for row in rows.values()))


if __name__ == "__main__":
    unittest.main()

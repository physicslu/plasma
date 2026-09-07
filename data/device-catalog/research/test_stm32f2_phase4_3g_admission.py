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

from device_catalog_admission_framework import AdmissionError, file_sha256, write_canonical_dataset  # noqa: E402
from stm32f2_admission_policy import CANONICAL_FIELDS  # noqa: E402
from stm32f2_phase4_3g_admission import DEFAULT_CANONICAL, admission_plan_is_clean  # noqa: E402

PLAN_PATH = HERE / "stm32f2-phase4.3g-admission-plan.json"
AUDIT_PATH = HERE / "stm32f2-phase4.3g-admission-audit.json"
MANIFEST_PATH = HERE.parent / "production" / "icpn-v1-manifest.json"
EXPECTED_PLAN_SHA256 = "343350cc187254e63d7bd58f05f600bb822cf0f5df6279f506e093cae1179b65"
EXPECTED = {
    "STM32F205RCT6", "STM32F205RCT6TR", "STM32F205RCT7", "STM32F205RCT7TR",
    "STM32F207IEH6", "STM32F207IEH6TR", "STM32F207IET6",
    "STM32F215RGT6", "STM32F215RGT6TR", "STM32F217IGH6", "STM32F217IGH6TR",
    "STM32F217IGT6", "STM32F217IGT7",
}


class STM32F2Phase43GAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def _historical_canonical(self, path: Path) -> None:
        with DEFAULT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = [row for row in reader if row["icpn"] not in EXPECTED]
        self.assertEqual(len(rows), 9)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)

    def test_bound_plan_is_exact_clean_and_read_only(self) -> None:
        self.assertEqual(file_sha256(PLAN_PATH), EXPECTED_PLAN_SHA256)
        self.assertTrue(admission_plan_is_clean(self.plan))
        self.assertEqual({item["icpn"] for item in self.plan["candidates"]}, EXPECTED)
        self.assertEqual(self.plan["lifecycle_exclusions"], [])
        self.assertFalse(self.plan["production_write_applied"])
        self.assertFalse(self.plan["programming_algorithm_equivalence_claimed"])
        self.assertFalse(self.plan["runtime_programming_support_claimed"])

    def test_published_canonical_manifest_and_audit_are_bound(self) -> None:
        with DEFAULT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 22)
        self.assertTrue(EXPECTED.issubset({row["icpn"] for row in rows}))
        self.assertEqual(len({row["base_device"] for row in rows}), 8)
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        source = next(item for item in manifest["sources"] if item["family"] == "STM32F2")
        self.assertEqual(source["row_count"], 22)
        self.assertEqual(source["sha256"], file_sha256(DEFAULT_CANONICAL))
        self.assertEqual(source["sha256"], self.audit["canonical_csv_file_sha256"])
        self.assertEqual(self.audit["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(self.audit["production_exact_icpns_after"], 481)
        self.assertEqual(self.audit["production_family_count_after"], 3)
        self.assertEqual(self.audit["status"], "published")
        self.assertEqual(self.audit["lifecycle_exclusions"], [])

    def test_generic_writer_is_exact_and_idempotent_in_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / DEFAULT_CANONICAL.name
            self._historical_canonical(canonical)
            first = write_canonical_dataset(plan=self.plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=self.plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_after"], 22)
            self.assertEqual(set(first["added"]), EXPECTED)
            self.assertEqual(second["status"], "no_op")

    def test_writer_rejects_unbound_canonical_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / DEFAULT_CANONICAL.name
            self._historical_canonical(canonical)
            with canonical.open("a", encoding="utf-8") as handle:
                handle.write("unexpected\n")
            with self.assertRaisesRegex(AdmissionError, "changed after admission planning"):
                write_canonical_dataset(plan=self.plan, canonical_path=canonical)


if __name__ == "__main__":
    unittest.main()

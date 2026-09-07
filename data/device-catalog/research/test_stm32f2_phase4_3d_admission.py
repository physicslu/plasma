#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import json
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

from device_catalog_admission_framework import (  # noqa: E402
    AdmissionError,
    canonical_csv_sha256,
    file_sha256,
    write_canonical_dataset,
)
from stm32f2_admission_policy import CANONICAL_FIELDS  # noqa: E402
from stm32f2_phase4_3d_admission import (  # noqa: E402
    DEFAULT_CANONICAL,
    admission_plan_is_clean,
)

PLAN_PATH = HERE / "stm32f2-phase4.3d-admission-plan.json"
AUDIT_PATH = HERE / "stm32f2-phase4.3d-admission-audit.json"
MANIFEST_PATH = HERE.parent / "production" / "icpn-v1-manifest.json"
EXPECTED_PLAN_SHA256 = "b657e31ea214348e3153acc7a2514b11b48b88de4ca84f31237cf0574a36a8e8"

EXPECTED = {
    "STM32F205RBT6", "STM32F205RBT6TR", "STM32F205RBT7",
    "STM32F207ICH6", "STM32F207ICT6",
    "STM32F215RET6", "STM32F215RET6TR",
    "STM32F217IEH6", "STM32F217IET6",
}


class STM32F2Phase43DAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def _header_only_plan_and_file(self, canonical: Path) -> dict:
        canonical.write_text(",".join(CANONICAL_FIELDS) + "\n", encoding="utf-8")
        plan = copy.deepcopy(self.plan)
        plan["inputs"]["canonical_input_sha256"] = canonical_csv_sha256(
            list(CANONICAL_FIELDS), []
        )
        return plan

    def test_bound_plan_is_exact_clean_and_read_only(self) -> None:
        plan = self.plan
        self.assertEqual(file_sha256(PLAN_PATH), EXPECTED_PLAN_SHA256)
        self.assertTrue(admission_plan_is_clean(plan))
        self.assertEqual({item["icpn"] for item in plan["candidates"]}, EXPECTED)
        self.assertEqual(plan["lifecycle_exclusions"], [])
        self.assertFalse(plan["production_write_applied"])
        self.assertFalse(plan["programming_algorithm_equivalence_claimed"])
        self.assertFalse(plan["runtime_programming_support_claimed"])

    def test_published_canonical_and_manifest_are_exactly_bound(self) -> None:
        with DEFAULT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            self.assertEqual(tuple(reader.fieldnames or ()), CANONICAL_FIELDS)
            rows = list(reader)
        self.assertEqual({row["icpn"] for row in rows}, EXPECTED)
        self.assertEqual(len(rows), 9)
        self.assertTrue(all(row["family"] == "STM32F2" for row in rows))
        self.assertTrue(all(row["openocd_target_config"] == "tcl/target/stm32f2x.cfg" for row in rows))
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        source = next(item for item in manifest["sources"] if item["family"] == "STM32F2")
        self.assertEqual(source["row_count"], 9)
        self.assertEqual(source["sha256"], file_sha256(DEFAULT_CANONICAL))
        self.assertEqual(source["sha256"], self.audit["canonical_csv_file_sha256"])
        self.assertEqual(self.audit["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(self.audit["status"], "published")
        self.assertEqual(self.audit["lifecycle_exclusions"], [])
        self.assertFalse(self.audit["programming_algorithm_equivalence_claimed"])
        self.assertFalse(self.audit["runtime_programming_support_claimed"])

    def test_generic_writer_is_exact_and_idempotent_in_sandbox(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / DEFAULT_CANONICAL.name
            plan = self._header_only_plan_and_file(canonical)
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_after"], 9)
            self.assertEqual(set(first["added"]), EXPECTED)
            self.assertEqual(second["status"], "no_op")
            with canonical.open(newline="", encoding="utf-8") as handle:
                rows = list(csv.DictReader(handle))
            self.assertEqual({row["icpn"] for row in rows}, EXPECTED)
            self.assertTrue(all(row["family"] == "STM32F2" for row in rows))

    def test_writer_rejects_unbound_canonical_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / DEFAULT_CANONICAL.name
            plan = self._header_only_plan_and_file(canonical)
            with canonical.open("a", encoding="utf-8") as handle:
                handle.write("unexpected\n")
            with self.assertRaisesRegex(AdmissionError, "changed after admission planning"):
                write_canonical_dataset(plan=plan, canonical_path=canonical)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
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
    file_sha256,
    write_canonical_dataset,
)
from stm32f2_admission_policy import CANONICAL_FIELDS  # noqa: E402
from stm32f2_bounded_admission import (  # noqa: E402
    admission_plan_is_clean,
    build_admission_plan,
    load_admission_spec,
)
from stm32f2_bounded_policy import DEFAULT_CANONICAL  # noqa: E402

AUDIT_PATH = HERE / "stm32f2-phase4.3j-admission-audit.json"
MANIFEST_PATH = HERE.parent / "production" / "icpn-v1-manifest.json"
PRESTATE_MANIFEST_PATH = HERE / "stm32f2-phase4.3j-production-manifest-prestate.json"
F1_CANONICAL = HERE / "stm32f1-commercial-icpn.csv"
F4_CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
EXPECTED_PLAN_SHA256 = "1b8649c284210076d74fa4b418c5f40554f5d74e1b03062054685d70f34faba8"
EXPECTED_CANONICAL_SHA256 = "69a9e02be14237bd2c683bc63eed4bd132ba62c5e8c334ef0e85671f868003d0"
EXPECTED_CANONICAL_BLOB = "1bec0770179f3849c6cfbb66aea9ad9d63610f55"
EXPECTED_PRESTATE_F2_SHA256 = "9746ba2d13d36f0c60d1a6997fde23b2d97fe2aae34b27297885a41343655621"
EXPECTED = {
    "STM32F205RET6",
    "STM32F205RET6TR",
    "STM32F205RET7",
    "STM32F205RET7TR",
    "STM32F205REY6TR",
    "STM32F207IFH6",
    "STM32F207IFH6TR",
    "STM32F207IFT6",
    "STM32F215VET6",
    "STM32F217VET6",
    "STM32F217VET6TR",
}


class STM32F2Phase43JAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def _historical_canonical(self, path: Path) -> None:
        with DEFAULT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            reader = csv.DictReader(handle)
            rows = [row for row in reader if row["icpn"] not in EXPECTED]
        self.assertEqual(len(rows), 22)
        with path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS, lineterminator="\n")
            writer.writeheader()
            writer.writerows(rows)
        self.assertEqual(file_sha256(path), EXPECTED_PRESTATE_F2_SHA256)

    def _historical_transaction_paths(self, root: Path) -> tuple[Path, Path]:
        research = root / "research"
        production = root / "production"
        research.mkdir(parents=True)
        production.mkdir(parents=True)

        canonical = research / DEFAULT_CANONICAL.name
        self._historical_canonical(canonical)
        (research / F1_CANONICAL.name).write_bytes(F1_CANONICAL.read_bytes())
        (research / F4_CANONICAL.name).write_bytes(F4_CANONICAL.read_bytes())
        manifest = production / "icpn-v1-manifest.json"
        manifest.write_bytes(PRESTATE_MANIFEST_PATH.read_bytes())
        return canonical, manifest

    def _historical_plan(self, canonical: Path, manifest: Path) -> dict:
        plan = build_admission_plan(
            phase="4.3J",
            canonical_path=canonical,
            production_manifest_path=manifest,
        )
        spec = load_admission_spec("4.3J")
        self.assertTrue(admission_plan_is_clean(plan, spec=spec))
        payload = json.dumps(plan, indent=2, sort_keys=True) + "\n"
        self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(), EXPECTED_PLAN_SHA256)
        return plan

    def test_published_canonical_manifest_and_audit_are_bound(self) -> None:
        with DEFAULT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 33)
        self.assertTrue(EXPECTED.issubset({row["icpn"] for row in rows}))
        self.assertEqual(len({row["base_device"] for row in rows}), 12)
        self.assertEqual(file_sha256(DEFAULT_CANONICAL), EXPECTED_CANONICAL_SHA256)

        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        source = next(item for item in manifest["sources"] if item["family"] == "STM32F2")
        self.assertEqual(source["row_count"], 33)
        self.assertEqual(source["sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(source["git_blob_sha"], EXPECTED_CANONICAL_BLOB)

        self.assertEqual(self.audit["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(self.audit["canonical_csv_file_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(self.audit["canonical_csv_git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(set(self.audit["added_exact_icpns"]), EXPECTED)
        self.assertEqual(self.audit["stm32f2_rows_before"], 22)
        self.assertEqual(self.audit["stm32f2_rows_after"], 33)
        self.assertEqual(self.audit["production_exact_icpns_before"], 481)
        self.assertEqual(self.audit["production_exact_icpns_after"], 492)
        self.assertEqual(self.audit["status"], "published")
        self.assertEqual(self.audit["lifecycle_exclusions"], [])
        self.assertFalse(self.audit["programming_algorithm_equivalence_claimed"])
        self.assertFalse(self.audit["runtime_programming_support_claimed"])

    def test_historical_plan_replay_and_writer_are_exact_and_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical, manifest = self._historical_transaction_paths(Path(tmp))
            plan = self._historical_plan(canonical, manifest)
            self.assertEqual({item["icpn"] for item in plan["candidates"]}, EXPECTED)
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 22)
            self.assertEqual(first["rows_after"], 33)
            self.assertEqual(set(first["added"]), EXPECTED)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(file_sha256(canonical), EXPECTED_CANONICAL_SHA256)

    def test_writer_rejects_unbound_historical_canonical_drift(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical, manifest = self._historical_transaction_paths(Path(tmp))
            plan = self._historical_plan(canonical, manifest)
            with canonical.open("a", encoding="utf-8") as handle:
                handle.write("unexpected\n")
            with self.assertRaisesRegex(AdmissionError, "changed after admission planning"):
                write_canonical_dataset(plan=plan, canonical_path=canonical)

    def test_new_metadata_contract_is_preserved_in_production_rows(self) -> None:
        with DEFAULT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["STM32F205REY6TR"]["package"], "WLCSP")
        self.assertEqual(rows["STM32F205REY6TR"]["pin_count"], "66")
        self.assertEqual(rows["STM32F207IFH6"]["flash_size"], "768 KiB")
        self.assertEqual(rows["STM32F215VET6"]["pin_count"], "100")
        self.assertEqual(rows["STM32F217VET6TR"]["pin_count"], "100")


if __name__ == "__main__":
    unittest.main()

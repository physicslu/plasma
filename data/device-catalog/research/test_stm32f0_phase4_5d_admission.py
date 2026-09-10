#!/usr/bin/env python3
"""Post-publication regressions for STM32F0 Phase 4.5D admission."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import AdmissionError, file_sha256, write_canonical_dataset
from stm32f0_admission_policy import CANONICAL_FIELDS
from stm32f0_phase4_5d_admission import admission_plan_is_clean, build_admission_plan

HERE = Path(__file__).resolve().parent
CURRENT_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
PRESTATE_MANIFEST = HERE / "stm32f0-phase4.5d-production-manifest-prestate.json"
AUDIT_PATH = HERE / "stm32f0-phase4.5d-admission-audit.json"
CURRENT_CANONICAL = HERE / "stm32f0-commercial-icpn.csv"

EXPECTED_PLAN_SHA256 = "37eebcd8e8a537b28916934a4d4651aea3f1d1f7d449cb6586a1f641a884c5f1"
EXPECTED_CANONICAL_SHA256 = "c5e138eced2389cf99948536308142a2488bdaefa619130b9b50b6fc52cd80c9"
EXPECTED_CANONICAL_BLOB = "ad9a5b0e643dcbee3118dff9f9863c637d66e3d6"


def write_empty_canonical(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS, lineterminator="\n").writeheader()


class STM32F0Phase45DAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def _historical_plan(self, canonical: Path) -> dict:
        self.assertFalse(canonical.exists())
        plan = build_admission_plan(
            canonical_path=canonical,
            production_manifest_path=PRESTATE_MANIFEST,
        )
        self.assertTrue(admission_plan_is_clean(plan))
        payload = json.dumps(plan, indent=2, sort_keys=True) + "\n"
        self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(), EXPECTED_PLAN_SHA256)
        return plan

    def test_published_canonical_manifest_and_audit_are_bound(self) -> None:
        with CURRENT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 42)
        self.assertEqual(len({row["icpn"] for row in rows}), 42)
        self.assertEqual(len({row["base_device"] for row in rows}), 13)
        self.assertEqual(file_sha256(CURRENT_CANONICAL), EXPECTED_CANONICAL_SHA256)
        self.assertTrue(all(row["family"] == "STM32F0" for row in rows))
        self.assertTrue(
            all(row["openocd_target_config"] == "tcl/target/stm32f0x.cfg" for row in rows)
        )

        manifest = json.loads(CURRENT_MANIFEST.read_text(encoding="utf-8"))
        source = next(item for item in manifest["sources"] if item["family"] == "STM32F0")
        self.assertEqual(source["row_count"], 42)
        self.assertEqual(source["sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(source["git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        families = [item["family"] for item in manifest["sources"]]
        self.assertEqual(families.count("STM32F0"), 1)
        self.assertEqual(len(families), len(set(families)))
        self.assertGreaterEqual(
            sum(int(item["row_count"]) for item in manifest["sources"]),
            self.audit["production_exact_icpns_after"],
        )
        self.assertGreaterEqual(len(families), self.audit["production_family_count_after"])

        self.assertEqual(self.audit["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(self.audit["canonical_csv_file_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(self.audit["canonical_csv_git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(set(self.audit["added_exact_icpns"]), {row["icpn"] for row in rows})
        self.assertEqual(self.audit["stm32f0_rows_before"], 0)
        self.assertEqual(self.audit["stm32f0_rows_after"], 42)
        self.assertEqual(self.audit["stm32f0_base_devices_after"], 13)
        self.assertEqual(self.audit["production_exact_icpns_before"], 502)
        self.assertEqual(self.audit["production_exact_icpns_after"], 544)
        self.assertEqual(self.audit["production_base_devices_before"], 175)
        self.assertEqual(self.audit["production_base_devices_after"], 188)
        self.assertEqual(self.audit["production_family_count_before"], 4)
        self.assertEqual(self.audit["production_family_count_after"], 5)
        self.assertEqual(self.audit["status"], "published")
        self.assertFalse(self.audit["programming_algorithm_equivalence_claimed"])
        self.assertFalse(self.audit["physical_target_qualification_claimed"])
        self.assertFalse(self.audit["runtime_programming_support_claimed"])
        self.assertFalse(self.audit["full_stm32f0_surface_covered"])

    def test_historical_plan_replays_exactly_and_writer_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical = Path(tmp) / "stm32f0-commercial-icpn.csv"
            plan = self._historical_plan(canonical)
            self.assertEqual(plan["candidate_count"], 42)
            self.assertEqual(plan["production_snapshot"]["exact_icpn_count"], 502)
            self.assertEqual(plan["production_snapshot"]["base_device_count"], 175)
            self.assertEqual(plan["canonical_rows_before"], 0)

            write_empty_canonical(canonical)
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_after"], 42)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(file_sha256(canonical), EXPECTED_CANONICAL_SHA256)

    def test_current_published_canonical_cannot_be_re_admitted(self) -> None:
        with self.assertRaisesRegex(AdmissionError, "zero-row STM32F0 canonical prestate"):
            build_admission_plan()

    def test_published_metadata_contract_is_preserved(self) -> None:
        with CURRENT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["STM32F078CBY6TR"]["package"], "WLCSP")
        self.assertEqual(rows["STM32F078CBY6TR"]["pin_count"], "49")
        self.assertEqual(rows["STM32F098CCT7"]["flash_size"], "256 KiB")
        self.assertEqual(rows["STM32F071C8U7"]["temperature_grade"], "-40 to 105 C")
        self.assertEqual(rows["STM32F030C6T6"]["openocd_target_config"], "tcl/target/stm32f0x.cfg")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Post-publication regressions for STM32F3 Phase 4.4D admission."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import AdmissionError, file_sha256, read_csv, write_canonical_dataset
from stm32f3_admission_policy import CANONICAL_FIELDS
from stm32f3_phase4_4d_admission import admission_plan_is_clean, build_admission_plan

HERE = Path(__file__).resolve().parent
CURRENT_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
PRESTATE_MANIFEST = HERE / "stm32f3-phase4.4d-production-manifest-prestate.json"
AUDIT_PATH = HERE / "stm32f3-phase4.4d-admission-audit.json"
CURRENT_CANONICAL = HERE / "stm32f3-commercial-icpn.csv"
F1_CANONICAL = HERE / "stm32f1-commercial-icpn.csv"
F2_CANONICAL = HERE / "stm32f2-commercial-icpn.csv"
F4_CANONICAL = HERE / "stm32f4-commercial-icpn.csv"

EXPECTED_PLAN_SHA256 = "d8cdab4d4c8f4fbecdc7fbf58ca7c9b58c8089389f5c8c36f0c7b7cd067b1495"
EXPECTED_CANONICAL_SHA256 = "c371b7a1c3b271afb9c8c823a4d12071be57da1aa11d138b59d39911489e1ee8"
EXPECTED_CANONICAL_BLOB = "39f0d18c8e54ece6098090b24277bd365462106e"
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
        csv.DictWriter(handle, fieldnames=CANONICAL_FIELDS, lineterminator="\n").writeheader()


def production_snapshot(manifest_path: Path) -> tuple[int, int, dict[str, int]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    for source in manifest["sources"]:
        family = source["family"]
        source_path = (manifest_path.parent / source["path"]).resolve()
        _, rows = read_csv(source_path)
        assert len(rows) == source["row_count"]
        family_counts[family] = len(rows)
        base_devices.update((family, row["base_device"]) for row in rows)
    return sum(family_counts.values()), len(base_devices), family_counts


class STM32F3Phase44DAdmissionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def _historical_transaction_paths(self, root: Path) -> tuple[Path, Path]:
        research = root / "research"
        production = root / "production"
        research.mkdir(parents=True)
        production.mkdir(parents=True)
        for source in (F1_CANONICAL, F2_CANONICAL, F4_CANONICAL):
            (research / source.name).write_bytes(source.read_bytes())
        manifest = production / "icpn-v1-manifest.json"
        manifest.write_bytes(PRESTATE_MANIFEST.read_bytes())
        canonical = research / CURRENT_CANONICAL.name
        return canonical, manifest

    def _historical_plan(self, canonical: Path, manifest: Path) -> dict:
        self.assertFalse(canonical.exists())
        plan = build_admission_plan(
            canonical_path=canonical,
            production_manifest_path=manifest,
            production_manifest_binding_name="icpn-v1-manifest.json",
        )
        self.assertTrue(admission_plan_is_clean(plan))
        payload = json.dumps(plan, indent=2, sort_keys=True) + "\n"
        self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(), EXPECTED_PLAN_SHA256)
        return plan

    def test_published_canonical_manifest_and_audit_are_bound(self) -> None:
        with CURRENT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 10)
        self.assertEqual({row["icpn"] for row in rows}, EXPECTED)
        self.assertEqual(len({row["base_device"] for row in rows}), 6)
        self.assertEqual(file_sha256(CURRENT_CANONICAL), EXPECTED_CANONICAL_SHA256)

        manifest = json.loads(CURRENT_MANIFEST.read_text(encoding="utf-8"))
        source = next(item for item in manifest["sources"] if item["family"] == "STM32F3")
        self.assertEqual(source["row_count"], 10)
        self.assertEqual(source["sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(source["git_blob_sha"], EXPECTED_CANONICAL_BLOB)

        exact_count, base_count, family_counts = production_snapshot(CURRENT_MANIFEST)
        self.assertEqual(family_counts["STM32F3"], 10)
        self.assertGreaterEqual(exact_count, self.audit["production_exact_icpns_after"])
        self.assertGreaterEqual(base_count, self.audit["production_base_devices_after"])
        self.assertGreaterEqual(len(family_counts), self.audit["production_family_count_after"])

        self.assertEqual(self.audit["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(self.audit["canonical_csv_file_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(self.audit["canonical_csv_git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(set(self.audit["added_exact_icpns"]), EXPECTED)
        self.assertEqual(self.audit["stm32f3_rows_before"], 0)
        self.assertEqual(self.audit["stm32f3_rows_after"], 10)
        self.assertEqual(self.audit["stm32f3_base_devices_before"], 0)
        self.assertEqual(self.audit["stm32f3_base_devices_after"], 6)
        self.assertEqual(self.audit["production_exact_icpns_before"], 492)
        self.assertEqual(self.audit["production_exact_icpns_after"], 502)
        self.assertEqual(self.audit["production_base_devices_before"], 169)
        self.assertEqual(self.audit["production_base_devices_after"], 175)
        self.assertEqual(self.audit["production_family_count_before"], 3)
        self.assertEqual(self.audit["production_family_count_after"], 4)
        self.assertEqual(self.audit["status"], "published")
        self.assertEqual(self.audit["lifecycle_exclusions"], [])
        self.assertFalse(self.audit["programming_algorithm_equivalence_claimed"])
        self.assertFalse(self.audit["runtime_programming_support_claimed"])
        self.assertFalse(self.audit["full_stm32f3_surface_covered"])

    def test_historical_plan_replays_exactly_and_writer_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical, manifest = self._historical_transaction_paths(Path(tmp))
            plan = self._historical_plan(canonical, manifest)
            self.assertEqual({item["icpn"] for item in plan["candidates"]}, EXPECTED)
            self.assertEqual(plan["production_snapshot"]["exact_icpn_count"], 492)
            self.assertEqual(plan["production_snapshot"]["base_device_count"], 169)
            self.assertEqual(plan["canonical_rows_before"], 0)
            self.assertTrue(plan["inputs"]["canonical_dataset_absent_before_admission"])

            write_empty_canonical(canonical)
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_before"], 0)
            self.assertEqual(first["rows_after"], 10)
            self.assertEqual(set(first["added"]), EXPECTED)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(file_sha256(canonical), EXPECTED_CANONICAL_SHA256)

    def test_writer_rejects_historical_canonical_drift_after_planning(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            canonical, manifest = self._historical_transaction_paths(Path(tmp))
            plan = self._historical_plan(canonical, manifest)
            write_empty_canonical(canonical)
            with canonical.open("a", encoding="utf-8") as handle:
                handle.write("unexpected\n")
            with self.assertRaisesRegex(AdmissionError, "changed after admission planning"):
                write_canonical_dataset(plan=plan, canonical_path=canonical)

    def test_current_published_canonical_cannot_be_re_admitted(self) -> None:
        with self.assertRaisesRegex(AdmissionError, "zero-row STM32F3 canonical prestate"):
            build_admission_plan()

    def test_published_metadata_contract_is_preserved(self) -> None:
        with CURRENT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["STM32F318C8Y6TR"]["package"], "WLCSP")
        self.assertEqual(rows["STM32F318C8Y6TR"]["pin_count"], "49")
        self.assertEqual(rows["STM32F334C4T6"]["flash_size"], "16 KiB")
        self.assertEqual(rows["STM32F301C6T7"]["temperature_grade"], "-40 to 105 C")
        self.assertTrue(
            all(row["openocd_target_config"] == "tcl/target/stm32f3x.cfg" for row in rows.values())
        )


if __name__ == "__main__":
    unittest.main()

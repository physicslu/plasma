#!/usr/bin/env python3
"""Post-publication regressions for STM32F7 Phase 4.6E."""

from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import AdmissionError, file_sha256, read_csv, write_canonical_dataset
from stm32f7_admission_policy import CANONICAL_FIELDS
from stm32f7_phase4_6d_admission import admission_plan_is_clean, build_admission_plan

HERE = Path(__file__).resolve().parent
CURRENT_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
PRESTATE_MANIFEST = HERE / "stm32f7-phase4.6c-production-manifest-prestate.json"
PLAN_PATH = HERE / "stm32f7-phase4.6d-admission-plan.json"
AUDIT_PATH = HERE / "stm32f7-phase4.6e-publication-audit.json"
CURRENT_CANONICAL = HERE / "stm32f7-commercial-icpn.csv"

EXPECTED_PLAN_SHA256 = "1e13d87d9d4e445efb5dbb43b79bad1bf3b5b916126095fb5a55c58580691a7e"
EXPECTED_CANONICAL_SHA256 = "c71434cc85068353a1aabdfe24059573c3e8092505fcdb1d6eda7f2374fa64d7"
EXPECTED_CANONICAL_BLOB = "d61ebd2c56edf6bb7b1cadc381c23d071fe7967f"
EXPECTED_MANIFEST_SHA256 = "4b05b3e3e7cb8e9b8cc426f9358d758f04d5bc4944b23e44ee0cad1d3bea1cd3"
EXPECTED_PROPOSAL_SHA256 = "a4b91cfc04af2f950ec2ce0457668a65d9aa081132b6685b15f697c311d136bb"
EXPECTED_ICPNS = {
    "STM32F722ICK6", "STM32F722ICT6", "STM32F723ICK6", "STM32F723ICT6",
    "STM32F730I8K6", "STM32F730I8K6TR", "STM32F732IEK6", "STM32F732IET6",
    "STM32F733IEK6", "STM32F733IET6", "STM32F745IEK6", "STM32F745IEK6TR",
    "STM32F745IEK7", "STM32F745IEK7TR", "STM32F745IET6", "STM32F745IET7",
    "STM32F750N8H6", "STM32F778AIY6TR", "STM32F779AIY6TR",
}


def production_snapshot(manifest_path: Path) -> tuple[int, int, dict[str, int]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    for source in manifest["sources"]:
        family = source["family"]
        source_path = (manifest_path.parent / source["path"]).resolve()
        _, rows = read_csv(source_path)
        self_count = int(source["row_count"])
        if len(rows) != self_count:
            raise AssertionError(f"{family}: manifest row_count drift")
        family_counts[family] = len(rows)
        base_devices.update((family, row["base_device"]) for row in rows)
    return sum(family_counts.values()), len(base_devices), family_counts


def write_empty_canonical(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=list(CANONICAL_FIELDS), lineterminator="\n").writeheader()


class STM32F7Phase46EPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def test_published_canonical_manifest_and_audit_are_bound(self) -> None:
        with CURRENT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 19)
        self.assertEqual({row["icpn"] for row in rows}, EXPECTED_ICPNS)
        self.assertEqual(len({row["base_device"] for row in rows}), 9)
        self.assertEqual(file_sha256(CURRENT_CANONICAL), EXPECTED_CANONICAL_SHA256)
        self.assertTrue(all(row["family"] == "STM32F7" for row in rows))
        self.assertTrue(all(row["openocd_target_config"] == "tcl/target/stm32f7x.cfg" for row in rows))

        manifest = json.loads(CURRENT_MANIFEST.read_text(encoding="utf-8"))
        source = next(item for item in manifest["sources"] if item["family"] == "STM32F7")
        self.assertEqual(source["row_count"], 19)
        self.assertEqual(source["sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(source["git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(file_sha256(CURRENT_MANIFEST), EXPECTED_MANIFEST_SHA256)

        exact_count, base_count, family_counts = production_snapshot(CURRENT_MANIFEST)
        self.assertEqual(exact_count, 563)
        self.assertEqual(base_count, 197)
        self.assertEqual(family_counts, {
            "STM32F0": 42,
            "STM32F1": 75,
            "STM32F2": 33,
            "STM32F3": 10,
            "STM32F4": 384,
            "STM32F7": 19,
        })

        self.assertEqual(self.audit["status"], "published")
        self.assertEqual(self.audit["publication_proposal_sha256"], EXPECTED_PROPOSAL_SHA256)
        self.assertEqual(self.audit["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(self.audit["canonical_csv_file_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(self.audit["canonical_csv_git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(self.audit["production_manifest_sha256_after"], EXPECTED_MANIFEST_SHA256)
        self.assertEqual(set(self.audit["added_exact_icpns"]), EXPECTED_ICPNS)
        self.assertEqual(self.audit["stm32f7_rows_before"], 0)
        self.assertEqual(self.audit["stm32f7_rows_after"], 19)
        self.assertEqual(self.audit["stm32f7_base_devices_after"], 9)
        self.assertEqual(self.audit["production_exact_icpns_before"], 544)
        self.assertEqual(self.audit["production_exact_icpns_after"], 563)
        self.assertEqual(self.audit["production_base_devices_before"], 188)
        self.assertEqual(self.audit["production_base_devices_after"], 197)
        self.assertEqual(self.audit["production_family_count_before"], 5)
        self.assertEqual(self.audit["production_family_count_after"], 6)
        self.assertTrue(self.audit["canonical_write_applied"])
        self.assertTrue(self.audit["production_write_applied"])
        self.assertFalse(self.audit["programming_algorithm_equivalence_claimed"])
        self.assertFalse(self.audit["physical_target_qualification_claimed"])
        self.assertFalse(self.audit["runtime_programming_support_claimed"])
        self.assertFalse(self.audit["full_stm32f7_surface_covered"])

    def test_historical_frozen_plan_replays_and_writer_is_idempotent(self) -> None:
        self.assertEqual(file_sha256(PLAN_PATH), EXPECTED_PLAN_SHA256)
        with tempfile.TemporaryDirectory() as td:
            canonical = Path(td) / "stm32f7-commercial-icpn.csv"
            plan = build_admission_plan(
                canonical_path=canonical,
                production_manifest_path=PRESTATE_MANIFEST,
            )
            self.assertTrue(admission_plan_is_clean(plan))
            payload = json.dumps(plan, indent=2, sort_keys=True) + "\n"
            self.assertEqual(hashlib.sha256(payload.encode()).hexdigest(), EXPECTED_PLAN_SHA256)
            write_empty_canonical(canonical)
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_after"], 19)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(file_sha256(canonical), EXPECTED_CANONICAL_SHA256)

    def test_current_published_canonical_cannot_be_re_admitted(self) -> None:
        with self.assertRaisesRegex(AdmissionError, "zero-row STM32F7 canonical prestate"):
            build_admission_plan()

    def test_published_edge_metadata_is_preserved(self) -> None:
        with CURRENT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["STM32F750N8H6"]["flash_size"], "64 KiB")
        self.assertEqual(rows["STM32F750N8H6"]["package"], "TFBGA")
        self.assertEqual(rows["STM32F750N8H6"]["pin_count"], "216")
        self.assertEqual(rows["STM32F745IEK7TR"]["temperature_grade"], "-40 to 105 C")
        self.assertEqual(rows["STM32F778AIY6TR"]["package"], "WLCSP")
        self.assertEqual(rows["STM32F779AIY6TR"]["option_suffix"], "TR")


if __name__ == "__main__":
    unittest.main()

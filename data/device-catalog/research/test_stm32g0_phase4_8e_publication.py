#!/usr/bin/env python3
"""Post-publication regressions for STM32G0 Phase 4.8E."""
from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import AdmissionError, file_sha256, read_csv, write_canonical_dataset
from stm32g0_admission_policy import CANONICAL_FIELDS
from stm32g0_phase4_8d_admission import EXPECTED_CAPABILITY_UNRESOLVED, admission_plan_is_clean, build_admission_plan

HERE = Path(__file__).resolve().parent
CURRENT_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
PRESTATE_MANIFEST = HERE / "stm32g0-phase4.8c-production-manifest-prestate.json"
PLAN_PATH = HERE / "stm32g0-phase4.8d-admission-plan.json"
AUDIT_PATH = HERE / "stm32g0-phase4.8e-publication-audit.json"
CURRENT_CANONICAL = HERE / "stm32g0-commercial-icpn.csv"

EXPECTED_PLAN_SHA256 = "d5f83bb3a2417a368e2d0bfb66a146e47b7649675341dc44e9d28c0a5de39801"
EXPECTED_CANONICAL_SHA256 = "70cc049b7e4c282af407c65bbf41a8f7128e54285b76275cb5f3071b9d03e012"
EXPECTED_CANONICAL_BLOB = "514f3a9b15b7ba31982f7b1ed322b1bac610909a"
EXPECTED_MANIFEST_SHA256 = "0dbb7df5a3ddc771326507fb42a47416d892d1d17f4e4141dde37cde23e95ddf"
EXPECTED_AUDIT_SHA256 = "63b0e7e5d8a0fa9ce53b26f493cf8f3506edd158ef2d95ad207cd4da2a782ac9"
EXPECTED_ICPNS = {
    "STM32G030C6T6", "STM32G030C6T6TR", "STM32G031C4T6", "STM32G031C4U6",
    "STM32G041C6T6", "STM32G050C6T6", "STM32G051C6T6", "STM32G051C6U6",
    "STM32G051C6U6TR", "STM32G051C6U7", "STM32G051C6U7TR", "STM32G061C6T6",
    "STM32G061C6U6", "STM32G070CBT6", "STM32G070CBT6TR", "STM32G071C8T3",
    "STM32G071C8T3TR", "STM32G071C8T6", "STM32G071C8T6TR", "STM32G071C8T7",
    "STM32G071C8T7TR", "STM32G071C8U3", "STM32G071C8U3TR", "STM32G071C8U6TR",
    "STM32G071C8U7", "STM32G071C8U7TR", "STM32G081CBT3", "STM32G081CBT3TR",
    "STM32G081CBT6", "STM32G081CBT6TR", "STM32G081CBU3", "STM32G081CBU3TR",
    "STM32G081CBU6", "STM32G0B0CET6", "STM32G0B0CET6TR", "STM32G0B1CBT3",
    "STM32G0B1CBT3TR", "STM32G0B1CBT6", "STM32G0B1CBT6TR", "STM32G0B1CBU3",
    "STM32G0B1CBU3TR", "STM32G0B1CBU6", "STM32G0B1CBU6TR", "STM32G0B1CBU7",
    "STM32G0B1CBU7TR", "STM32G0C1CCU6", "STM32G0C1CCU6TR",
}


def production_snapshot(manifest_path: Path) -> tuple[int, int, dict[str, int]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    for source in manifest["sources"]:
        family = source["family"]
        source_path = (manifest_path.parent / source["path"]).resolve()
        _, rows = read_csv(source_path)
        if len(rows) != int(source["row_count"]):
            raise AssertionError(f"{family}: manifest row_count drift")
        family_counts[family] = len(rows)
        base_devices.update((family, row["base_device"]) for row in rows)
    return sum(family_counts.values()), len(base_devices), family_counts


def write_empty_canonical(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=list(CANONICAL_FIELDS), lineterminator="\n").writeheader()


class STM32G0Phase48EPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))

    def test_published_canonical_manifest_and_audit_are_bound(self) -> None:
        self.assertEqual(file_sha256(PLAN_PATH), EXPECTED_PLAN_SHA256)
        self.assertEqual(file_sha256(CURRENT_CANONICAL), EXPECTED_CANONICAL_SHA256)
        self.assertEqual(file_sha256(CURRENT_MANIFEST), EXPECTED_MANIFEST_SHA256)
        self.assertEqual(file_sha256(AUDIT_PATH), EXPECTED_AUDIT_SHA256)

        with CURRENT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 47)
        self.assertEqual({row["icpn"] for row in rows}, EXPECTED_ICPNS)
        self.assertEqual(len({row["base_device"] for row in rows}), 12)
        self.assertTrue(all(row["family"] == "STM32G0" for row in rows))
        self.assertTrue(all(row["openocd_target_config"] == "tcl/target/stm32g0x.cfg" for row in rows))
        self.assertTrue(all(row["mapping_status"] == "deterministic_ordering_pattern" for row in rows))
        self.assertTrue(all(row["existing_identifier_kind"] == "ordering_pattern" for row in rows))
        self.assertTrue(all(row["cmsis_device_name"] == "" for row in rows))

        manifest = json.loads(CURRENT_MANIFEST.read_text(encoding="utf-8"))
        source = next(item for item in manifest["sources"] if item["family"] == "STM32G0")
        self.assertEqual(source["row_count"], 47)
        self.assertEqual(source["sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(source["git_blob_sha"], EXPECTED_CANONICAL_BLOB)

        exact_count, base_count, family_counts = production_snapshot(CURRENT_MANIFEST)
        self.assertEqual(exact_count, 610)
        self.assertEqual(base_count, 209)
        self.assertEqual(family_counts, {
            "STM32F0": 42, "STM32F1": 75, "STM32F2": 33, "STM32F3": 10,
            "STM32F4": 384, "STM32F7": 19, "STM32G0": 47,
        })

        self.assertEqual(self.audit["status"], "published")
        self.assertEqual(self.audit["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(self.audit["canonical_csv_file_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(self.audit["canonical_csv_git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(self.audit["production_manifest_sha256_after"], EXPECTED_MANIFEST_SHA256)
        self.assertEqual(set(self.audit["added_exact_icpns"]), EXPECTED_ICPNS)
        self.assertEqual(self.audit["manufacturer_verified_identity_count"], 49)
        self.assertEqual(self.audit["published_exact_icpn_count"], 47)
        self.assertEqual(self.audit["stm32g0_rows_before"], 0)
        self.assertEqual(self.audit["stm32g0_rows_after"], 47)
        self.assertEqual(self.audit["stm32g0_base_devices_after"], 12)
        self.assertEqual(self.audit["production_exact_icpns_before"], 563)
        self.assertEqual(self.audit["production_exact_icpns_after"], 610)
        self.assertEqual(self.audit["production_base_devices_before"], 197)
        self.assertEqual(self.audit["production_base_devices_after"], 209)
        self.assertEqual(self.audit["production_family_count_before"], 6)
        self.assertEqual(self.audit["production_family_count_after"], 7)
        self.assertTrue(self.audit["canonical_write_applied"])
        self.assertTrue(self.audit["production_write_applied"])

    def test_capability_unresolved_n_identities_remain_outside_publication(self) -> None:
        unresolved = self.audit["capability_unresolved"]
        self.assertEqual(self.audit["capability_unresolved_count"], 2)
        self.assertFalse(self.audit["capability_unresolved_is_identity_rejection"])
        self.assertEqual({item["icpn"] for item in unresolved}, set(EXPECTED_CAPABILITY_UNRESOLVED))
        for item in unresolved:
            self.assertEqual(item["identity_status"], "manufacturer_verified_active")
            self.assertEqual(item["capability_status"], "openocd_ordering_pattern_unresolved")
            self.assertEqual(item["policy_action"], "exclude_from_canonical_admission_until_positive_capability_evidence")
        self.assertTrue(set(EXPECTED_CAPABILITY_UNRESOLVED).isdisjoint(EXPECTED_ICPNS))
        with CURRENT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            published = {row["icpn"] for row in csv.DictReader(handle)}
        self.assertTrue(set(EXPECTED_CAPABILITY_UNRESOLVED).isdisjoint(published))

    def test_historical_frozen_plan_replays_and_writer_is_idempotent(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            canonical = Path(td) / "stm32g0-commercial-icpn.csv"
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
            self.assertEqual(first["rows_after"], 47)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(file_sha256(canonical), EXPECTED_CANONICAL_SHA256)

    def test_current_published_canonical_cannot_be_re_admitted(self) -> None:
        with self.assertRaisesRegex(AdmissionError, "zero-row STM32G0 canonical prestate"):
            build_admission_plan()

    def test_published_edge_metadata_is_preserved(self) -> None:
        with CURRENT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertEqual(rows["STM32G031C4T6"]["flash_size"], "16 KiB")
        self.assertEqual(rows["STM32G071C8T3"]["temperature_grade"], "-40 to 125 C")
        self.assertEqual(rows["STM32G071C8U7TR"]["package"], "UFQFPN")
        self.assertEqual(rows["STM32G0B0CET6"]["flash_size"], "512 KiB")
        self.assertEqual(rows["STM32G0C1CCU6"]["flash_size"], "256 KiB")
        self.assertNotIn("STM32G0B1CBT6N", rows)
        self.assertNotIn("STM32G0B1CBU6N", rows)

    def test_publication_does_not_overclaim_capability_or_runtime(self) -> None:
        for flag in (
            "programming_algorithm_equivalence_claimed",
            "n_product_version_capability_equivalence_claimed",
            "physical_target_qualification_claimed",
            "runtime_programming_support_claimed",
            "full_stm32g0_surface_covered",
        ):
            self.assertFalse(self.audit[flag])


if __name__ == "__main__":
    unittest.main()

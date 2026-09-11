#!/usr/bin/env python3
"""Post-publication hard-lock regressions for STM32G4 Phase 4.9E."""
from __future__ import annotations

import csv
import hashlib
import json
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import AdmissionError, file_sha256, read_csv, write_canonical_dataset
from stm32g4_admission_policy import CANONICAL_FIELDS
from stm32g4_metadata_policy import EXPECTED_PROPOSAL_EXCLUSIONS, SOURCE_UNAVAILABLE_BASES
from stm32g4_phase4_9d_admission import admission_plan_is_clean, build_admission_plan

HERE = Path(__file__).resolve().parent
CURRENT_MANIFEST = HERE.parent / "production" / "icpn-v1-manifest.json"
PRESTATE_MANIFEST = HERE / "stm32g4-phase4.9c-production-manifest-prestate.json"
PLAN_PATH = HERE / "stm32g4-phase4.9d-admission-plan.json"
PROPOSAL_PATH = HERE / "stm32g4-phase4.9e-publication-proposal.json"
AUDIT_PATH = HERE / "stm32g4-phase4.9e-publication-audit.json"
CURRENT_CANONICAL = HERE / "stm32g4-commercial-icpn.csv"

EXPECTED_PLAN_SHA256 = "4ba41c97414ca4eb45b069f08b0200e2e53faaaed2cd5e4e57e7ac260d3d1291"
EXPECTED_PROPOSAL_SHA256 = "d6d6cd248e78658cb47b4781199d39d84d51ed9df0a032386e003bd1e6c23478"
EXPECTED_CANONICAL_SHA256 = "2e20c585687e9bc3148c7835575695a7d06f497c29409818b9b56064df7b07a8"
EXPECTED_CANONICAL_BLOB = "52958c5313e95f924a628c6a69c9f3b2f4ca5e05"
EXPECTED_PRESTATE_MANIFEST_SHA256 = "0dbb7df5a3ddc771326507fb42a47416d892d1d17f4e4141dde37cde23e95ddf"
EXPECTED_G4_POST_MANIFEST_SHA256 = "93c2a4541daeb1d4aa1dcc57edef54042862eb6d9da03e3a6b401e4b8481b11d"
EXPECTED_AUDIT_SHA256 = "f0fb375f33f119d1073fbc9a4d2cbbd640bf59f5f43943551210b3085d2fd8df"
EXPECTED_ICPNS = {
    "STM32G431C6T6", "STM32G431C6U6", "STM32G441CBT6", "STM32G441CBU6",
    "STM32G441CBY6TR", "STM32G473CBT3", "STM32G473CBT6", "STM32G473CBU6",
    "STM32G474CBT3", "STM32G474CBT3TR", "STM32G474CBT6TR", "STM32G474CBU6",
    "STM32G483CET3", "STM32G483CET6", "STM32G483CEU6", "STM32G484CET6",
    "STM32G484CEU3", "STM32G484CEU6", "STM32G491CCT3", "STM32G491CCT6",
    "STM32G491CCT6TR", "STM32G491CCU6", "STM32G491CCU6TR", "STM32G4A1CET6",
    "STM32G4A1CEU6",
}


def production_snapshot(manifest_path: Path) -> tuple[int, int, dict[str, int]]:
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    family_counts: dict[str, int] = {}
    base_devices: set[tuple[str, str]] = set()
    for source in manifest["sources"]:
        family = source["family"]
        source_path = (manifest_path.parent / source["path"]).resolve()
        _, rows = read_csv(source_path)
        data = source_path.read_bytes()
        if len(rows) != int(source["row_count"]):
            raise AssertionError(f"{family}: manifest row_count drift")
        if hashlib.sha256(data).hexdigest() != source["sha256"]:
            raise AssertionError(f"{family}: manifest source SHA-256 drift")
        blob = hashlib.sha1(f"blob {len(data)}\0".encode() + data).hexdigest()
        if blob != source["git_blob_sha"]:
            raise AssertionError(f"{family}: manifest Git blob drift")
        family_counts[family] = len(rows)
        base_devices.update((family, row["base_device"]) for row in rows)
    return sum(family_counts.values()), len(base_devices), family_counts


def write_empty_canonical(path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        csv.DictWriter(handle, fieldnames=list(CANONICAL_FIELDS), lineterminator="\n").writeheader()


class STM32G4Phase49EPublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        cls.proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))

    def test_published_canonical_manifest_proposal_and_audit_are_bound(self) -> None:
        self.assertEqual(file_sha256(PLAN_PATH), EXPECTED_PLAN_SHA256)
        self.assertEqual(file_sha256(PROPOSAL_PATH), EXPECTED_PROPOSAL_SHA256)
        self.assertEqual(file_sha256(CURRENT_CANONICAL), EXPECTED_CANONICAL_SHA256)
        self.assertEqual(file_sha256(AUDIT_PATH), EXPECTED_AUDIT_SHA256)

        with CURRENT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = list(csv.DictReader(handle))
        self.assertEqual(len(rows), 25)
        self.assertEqual({row["icpn"] for row in rows}, EXPECTED_ICPNS)
        self.assertEqual(len({row["base_device"] for row in rows}), 8)
        self.assertTrue(all(row["family"] == "STM32G4" for row in rows))
        self.assertTrue(all(row["openocd_target_config"] == "tcl/target/stm32g4x.cfg" for row in rows))
        self.assertTrue(all(row["existing_identifier_kind"] == "ordering_pattern" for row in rows))
        self.assertTrue(all(row["cmsis_device_name"] == "" for row in rows))

        manifest = json.loads(CURRENT_MANIFEST.read_text(encoding="utf-8"))
        source = next(item for item in manifest["sources"] if item["family"] == "STM32G4")
        self.assertEqual(source["row_count"], 25)
        self.assertEqual(source["sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(source["git_blob_sha"], EXPECTED_CANONICAL_BLOB)

        exact_count, base_count, family_counts = production_snapshot(CURRENT_MANIFEST)
        self.assertGreaterEqual(exact_count, 635)
        self.assertGreaterEqual(base_count, 217)
        for family, count in {
            "STM32F0": 42, "STM32F1": 75, "STM32F2": 33, "STM32F3": 10,
            "STM32F4": 384, "STM32F7": 19, "STM32G0": 47, "STM32G4": 25,
        }.items():
            self.assertEqual(family_counts.get(family), count)

        self.assertEqual(self.proposal["status"], "publication_proposal_clean")
        self.assertEqual(self.proposal["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(self.proposal["canonical_csv_file_sha256_proposed"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(self.proposal["canonical_csv_git_blob_sha_proposed"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(self.proposal["production_manifest_sha256_proposed"], EXPECTED_G4_POST_MANIFEST_SHA256)

        self.assertEqual(self.audit["status"], "published")
        self.assertEqual(self.audit["admission_plan_sha256"], EXPECTED_PLAN_SHA256)
        self.assertEqual(self.audit["publication_proposal_sha256"], EXPECTED_PROPOSAL_SHA256)
        self.assertEqual(self.audit["canonical_csv_file_sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(self.audit["canonical_csv_git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(self.audit["production_manifest_sha256_before"], EXPECTED_PRESTATE_MANIFEST_SHA256)
        self.assertEqual(self.audit["production_manifest_sha256_after"], EXPECTED_G4_POST_MANIFEST_SHA256)
        self.assertEqual(set(self.audit["added_exact_icpns"]), EXPECTED_ICPNS)
        self.assertEqual(self.audit["published_exact_icpn_count"], 25)
        self.assertEqual(self.audit["stm32g4_rows_before"], 0)
        self.assertEqual(self.audit["stm32g4_rows_after"], 25)
        self.assertEqual(self.audit["stm32g4_base_devices_after"], 8)
        self.assertEqual(self.audit["production_exact_icpns_before"], 610)
        self.assertEqual(self.audit["production_exact_icpns_after"], 635)
        self.assertEqual(self.audit["production_base_devices_before"], 209)
        self.assertEqual(self.audit["production_base_devices_after"], 217)
        self.assertEqual(self.audit["production_family_count_before"], 7)
        self.assertEqual(self.audit["production_family_count_after"], 8)
        self.assertTrue(self.audit["canonical_write_applied"])
        self.assertTrue(self.audit["production_write_applied"])

    def test_historical_plan_replays_against_frozen_prestate_and_writer_is_idempotent(self) -> None:
        self.assertEqual(file_sha256(PRESTATE_MANIFEST), EXPECTED_PRESTATE_MANIFEST_SHA256)
        with tempfile.TemporaryDirectory() as td:
            canonical = Path(td) / "stm32g4-commercial-icpn.csv"
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
            self.assertEqual(first["rows_after"], 25)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(file_sha256(canonical), EXPECTED_CANONICAL_SHA256)

    def test_current_published_canonical_cannot_be_re_admitted(self) -> None:
        with self.assertRaisesRegex(AdmissionError, "zero-row STM32G4 canonical prestate"):
            build_admission_plan()

    def test_edge_metadata_and_exclusions_remain_explicit(self) -> None:
        with CURRENT_CANONICAL.open(newline="", encoding="utf-8") as handle:
            rows = {row["icpn"]: row for row in csv.DictReader(handle)}
        self.assertEqual(
            (rows["STM32G441CBY6TR"]["package"], rows["STM32G441CBY6TR"]["pin_count"], rows["STM32G441CBY6TR"]["option_suffix"]),
            ("WLCSP", "49", "TR"),
        )
        self.assertEqual(self.audit["source_unavailable_base_devices"], sorted(SOURCE_UNAVAILABLE_BASES))
        self.assertEqual(self.audit["proposal_exact_identity_exclusions"], sorted(EXPECTED_PROPOSAL_EXCLUSIONS))
        self.assertFalse(self.audit["bounded_commercial_surface_complete"])
        self.assertEqual(self.audit["capability_unresolved_count"], 0)
        self.assertEqual(self.audit["capability_unresolved"], [])
        self.assertTrue(set(EXPECTED_PROPOSAL_EXCLUSIONS).isdisjoint(rows))

    def test_publication_does_not_overclaim_programmer_support(self) -> None:
        for flag in (
            "programming_algorithm_equivalence_claimed",
            "flash_geometry_equivalence_claimed",
            "option_security_semantics_claimed",
            "physical_target_qualification_claimed",
            "hil_qualification_claimed",
            "runtime_programming_support_claimed",
            "full_stm32g4_surface_covered",
        ):
            self.assertFalse(self.audit[flag], flag)


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Post-publication hard-lock regressions for STM32U0 U0.5."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import file_sha256, write_canonical_dataset
from publish_stm32u0_phase_u0_5 import (
    AUDIT_PATH,
    CANONICAL_PATH,
    EXPECTED_AUDIT_SHA256,
    EXPECTED_CANONICAL_BLOB,
    EXPECTED_CANONICAL_SHA256,
    EXPECTED_PLAN_SHA256,
    EXPECTED_POST_MANIFEST_BLOB,
    EXPECTED_POST_MANIFEST_SHA256,
    EXPECTED_PRESTATE_MANIFEST_BLOB,
    EXPECTED_PRESTATE_MANIFEST_SHA256,
    EXPECTED_PROPOSAL_SHA256,
    PLAN_PATH,
    PRESTATE_MANIFEST,
    PRODUCTION_MANIFEST,
    PROPOSAL_PATH,
    _historical_plan,
    _write_empty_canonical,
    publish,
    verify_current_publication,
)
from stm32u0_admission_policy import CANONICAL_FIELDS
from stm32u0_phase_u0_4_admission import STM32U0AdmissionError, build_admission_plan


class STM32U0PhaseU05PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen_plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        with CANONICAL_PATH.open(newline="", encoding="utf-8") as handle:
            cls.rows = list(csv.DictReader(handle))

    def test_published_canonical_manifest_proposal_and_audit_are_bound(self) -> None:
        summary = verify_current_publication()
        self.assertEqual(summary["production_exact_icpns"], 703)
        self.assertEqual(summary["production_base_devices"], 243)
        self.assertEqual(summary["production_family_count"], 9)
        self.assertEqual(summary["published_exact_icpns"], 68)
        self.assertEqual(summary["published_base_devices"], 26)

        self.assertEqual(file_sha256(PLAN_PATH), EXPECTED_PLAN_SHA256)
        self.assertEqual(file_sha256(PROPOSAL_PATH), EXPECTED_PROPOSAL_SHA256)
        self.assertEqual(file_sha256(CANONICAL_PATH), EXPECTED_CANONICAL_SHA256)
        self.assertEqual(file_sha256(PRODUCTION_MANIFEST), EXPECTED_POST_MANIFEST_SHA256)
        self.assertEqual(file_sha256(AUDIT_PATH), EXPECTED_AUDIT_SHA256)
        self.assertEqual(self.audit["canonical_csv_git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(self.audit["production_manifest_git_blob_sha_after"], EXPECTED_POST_MANIFEST_BLOB)
        self.assertEqual(self.audit["production_manifest_git_blob_sha_before"], EXPECTED_PRESTATE_MANIFEST_BLOB)
        self.assertEqual(self.audit["production_manifest_sha256_before"], EXPECTED_PRESTATE_MANIFEST_SHA256)

    def test_exact_identity_set_and_manifest_source_are_hard_locked(self) -> None:
        self.assertEqual(len(self.rows), 68)
        self.assertEqual(len({row["base_device"] for row in self.rows}), 26)
        self.assertEqual({row["icpn"] for row in self.rows}, set(self.frozen_plan["admission_exact_icpns"]))
        self.assertTrue(all(row["family"] == "STM32U0" for row in self.rows))
        self.assertTrue(all(row["cmsis_device_name"] == "" for row in self.rows))
        self.assertTrue(all(row["existing_identifier_kind"] == "ordering_pattern" for row in self.rows))
        self.assertTrue(all(row["openocd_target_config"] == "tcl/target/stm32u0x.cfg" for row in self.rows))

        manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
        source = next(item for item in manifest["sources"] if item["family"] == "STM32U0")
        self.assertEqual(source["row_count"], 68)
        self.assertEqual(source["sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(source["git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(source["path"], "../research/stm32u0-commercial-icpn.csv")

    def test_historical_u04_replays_and_canonical_writer_is_idempotent(self) -> None:
        plan = _historical_plan()
        with tempfile.TemporaryDirectory() as td:
            canonical = Path(td) / "stm32u0-commercial-icpn.csv"
            _write_empty_canonical(canonical)
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_after"], 68)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(file_sha256(canonical), EXPECTED_CANONICAL_SHA256)

    def test_current_published_canonical_cannot_be_readmitted(self) -> None:
        with self.assertRaisesRegex(STM32U0AdmissionError, "zero-row STM32U0 canonical prestate"):
            build_admission_plan(
                canonical_path=CANONICAL_PATH,
                production_manifest_path=PRESTATE_MANIFEST,
            )

    def test_edge_metadata_and_packing_identity_survive_publication(self) -> None:
        rows = {row["icpn"]: row for row in self.rows}
        self.assertEqual(
            (rows["STM32U073M8I6"]["package"], rows["STM32U073M8I6"]["pin_count"], rows["STM32U073M8I6"]["existing_identifier"]),
            ("UFBGA", "81", "STM32U073M8Ix"),
        )
        self.assertEqual(
            (rows["STM32U073M8T6"]["package"], rows["STM32U073M8T6"]["pin_count"], rows["STM32U073M8T6"]["existing_identifier"]),
            ("LQFP", "80", "STM32U073M8Tx"),
        )
        self.assertEqual(rows["STM32U083CCT6TR"]["option_suffix"], "TR")
        self.assertEqual(rows["STM32U083CCT6TR"]["icpn"], "STM32U083CCT6TR")

    def test_publication_does_not_overclaim_programmer_support(self) -> None:
        self.assertTrue(self.audit["canonical_write_applied"])
        self.assertTrue(self.audit["production_write_applied"])
        self.assertTrue(self.audit["bounded_commercial_surface_complete"])
        self.assertEqual(self.audit["capability_unresolved_count"], 0)
        self.assertEqual(self.audit["capability_unresolved"], [])
        for flag in (
            "programming_algorithm_equivalence_claimed",
            "flash_geometry_equivalence_claimed",
            "option_security_semantics_claimed",
            "physical_target_qualification_claimed",
            "hil_qualification_claimed",
            "runtime_programming_support_claimed",
            "full_stm32u0_surface_covered",
        ):
            self.assertFalse(self.audit[flag], flag)

    def test_publisher_is_no_op_after_expected_publication(self) -> None:
        result = publish()
        self.assertEqual(result, {"status": "no_op_already_published", "published_exact_icpns": 68})


if __name__ == "__main__":
    unittest.main()

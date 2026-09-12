#!/usr/bin/env python3
"""Post-publication hard-lock regressions for STM32C0 C0.5."""
from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from device_catalog_admission_framework import file_sha256, write_canonical_dataset
from publish_stm32c0_phase_c0_5 import (
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
    EXPECTED_PUBLISHED_BASES,
    EXPECTED_PUBLISHED_ROWS,
    EXPECTED_UNRESOLVED,
    PLAN_PATH,
    PRESTATE_MANIFEST,
    PRODUCTION_MANIFEST,
    PROPOSAL_PATH,
    _historical_plan,
    _write_empty_canonical,
    publish,
    verify_current_publication,
)
from stm32c0_phase_c0_4_admission import (
    EXPECTED_CAPABILITY_UNRESOLVED,
    STM32C0AdmissionError,
    build_admission_plan,
)


class STM32C0PhaseC05PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.frozen_plan = json.loads(PLAN_PATH.read_text(encoding="utf-8"))
        cls.proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        with CANONICAL_PATH.open(newline="", encoding="utf-8") as handle:
            cls.rows = list(csv.DictReader(handle))

    def test_publication_artifacts_and_production_state_are_bound(self) -> None:
        summary = verify_current_publication()
        self.assertGreaterEqual(summary["production_exact_icpns"], 912)
        self.assertGreaterEqual(summary["production_base_devices"], 293)
        self.assertGreaterEqual(summary["production_family_count"], 10)
        self.assertEqual(summary["published_exact_icpns"], EXPECTED_PUBLISHED_ROWS)
        self.assertEqual(summary["published_base_devices"], EXPECTED_PUBLISHED_BASES)
        self.assertEqual(summary["capability_unresolved"], EXPECTED_UNRESOLVED)

        self.assertEqual(file_sha256(PLAN_PATH), EXPECTED_PLAN_SHA256)
        self.assertEqual(file_sha256(PROPOSAL_PATH), EXPECTED_PROPOSAL_SHA256)
        self.assertEqual(file_sha256(CANONICAL_PATH), EXPECTED_CANONICAL_SHA256)
        self.assertEqual(file_sha256(AUDIT_PATH), EXPECTED_AUDIT_SHA256)
        self.assertEqual(self.audit["canonical_csv_git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(self.audit["production_manifest_git_blob_sha_after"], EXPECTED_POST_MANIFEST_BLOB)
        self.assertEqual(self.audit["production_manifest_sha256_after"], EXPECTED_POST_MANIFEST_SHA256)
        self.assertEqual(self.audit["production_manifest_git_blob_sha_before"], EXPECTED_PRESTATE_MANIFEST_BLOB)
        self.assertEqual(self.audit["production_manifest_sha256_before"], EXPECTED_PRESTATE_MANIFEST_SHA256)

    def test_exact_published_set_and_unresolved_exclusion_are_hard_locked(self) -> None:
        identities = {row["icpn"] for row in self.rows}
        unresolved = set(EXPECTED_CAPABILITY_UNRESOLVED)
        self.assertEqual(len(self.rows), EXPECTED_PUBLISHED_ROWS)
        self.assertEqual(len(identities), EXPECTED_PUBLISHED_ROWS)
        self.assertEqual(identities, set(self.proposal["added_exact_icpns"]))
        self.assertFalse(identities & unresolved)
        self.assertEqual(set(self.audit["capability_unresolved_exact_icpns"]), unresolved)
        self.assertEqual(self.audit["capability_unresolved_count"], EXPECTED_UNRESOLVED)
        self.assertFalse(self.audit["capability_unresolved_is_identity_rejection"])
        self.assertTrue(all(row["family"] == "STM32C0" for row in self.rows))
        self.assertTrue(all(row["cmsis_device_name"] == "" for row in self.rows))
        self.assertTrue(all(row["existing_identifier_kind"] == "ordering_pattern" for row in self.rows))
        self.assertTrue(all(row["openocd_target_config"] == "tcl/target/stm32c0x.cfg" for row in self.rows))

        manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
        source = next(item for item in manifest["sources"] if item["family"] == "STM32C0")
        self.assertEqual(source["row_count"], EXPECTED_PUBLISHED_ROWS)
        self.assertEqual(source["sha256"], EXPECTED_CANONICAL_SHA256)
        self.assertEqual(source["git_blob_sha"], EXPECTED_CANONICAL_BLOB)
        self.assertEqual(source["path"], "../research/stm32c0-commercial-icpn.csv")

    def test_historical_c04_replays_and_canonical_writer_is_idempotent(self) -> None:
        plan = _historical_plan()
        with tempfile.TemporaryDirectory() as td:
            canonical = Path(td) / "stm32c0-commercial-icpn.csv"
            _write_empty_canonical(canonical)
            first = write_canonical_dataset(plan=plan, canonical_path=canonical)
            second = write_canonical_dataset(plan=plan, canonical_path=canonical)
            self.assertEqual(first["status"], "written")
            self.assertEqual(first["rows_after"], EXPECTED_PUBLISHED_ROWS)
            self.assertEqual(second["status"], "no_op")
            self.assertEqual(file_sha256(canonical), EXPECTED_CANONICAL_SHA256)

    def test_current_published_canonical_cannot_be_readmitted(self) -> None:
        with self.assertRaisesRegex(STM32C0AdmissionError, "zero-row STM32C0 canonical prestate"):
            build_admission_plan(
                canonical_path=CANONICAL_PATH,
                production_manifest_path=PRESTATE_MANIFEST,
            )

    def test_c071_commercial_suffix_and_package_semantics_survive_publication(self) -> None:
        rows = {row["icpn"]: row for row in self.rows}
        self.assertEqual(
            (rows["STM32C071FBP6"]["package"], rows["STM32C071FBP6"]["pin_count"], rows["STM32C071FBP6"]["option_suffix"]),
            ("TSSOP", "20", ""),
        )
        self.assertEqual(
            (rows["STM32C071FBP6NTR"]["package"], rows["STM32C071FBP6NTR"]["pin_count"], rows["STM32C071FBP6NTR"]["option_suffix"]),
            ("TSSOP", "20", "NTR"),
        )
        self.assertEqual(rows["STM32C071C8T6N"]["option_suffix"], "N")
        self.assertNotIn("STM32C071FBY6TR", rows)

    def test_c091_c092_series_identity_stays_separate(self) -> None:
        rows = {row["icpn"]: row for row in self.rows}
        self.assertEqual(rows["STM32C091RCI6"]["series"], "STM32C091")
        self.assertEqual(rows["STM32C092RCI6"]["series"], "STM32C092")
        self.assertNotIn("STM32C091RBI6", rows)
        self.assertNotIn("STM32C092RBI6", rows)

    def test_publication_does_not_overclaim_programmer_support(self) -> None:
        self.assertTrue(self.audit["canonical_write_applied"])
        self.assertTrue(self.audit["production_write_applied"])
        self.assertTrue(self.audit["bounded_commercial_surface_complete"])
        self.assertTrue(self.audit["published_surface_partial_due_to_capability"])
        for flag in (
            "programming_algorithm_equivalence_claimed",
            "flash_geometry_equivalence_claimed",
            "option_security_semantics_claimed",
            "physical_target_qualification_claimed",
            "hil_qualification_claimed",
            "runtime_programming_support_claimed",
            "full_stm32c0_surface_covered",
        ):
            self.assertFalse(self.audit[flag], flag)

    def test_publisher_is_no_op_after_expected_publication(self) -> None:
        result = publish()
        self.assertEqual(result, {"status": "no_op_already_published", "published_exact_icpns": 209})


if __name__ == "__main__":
    unittest.main()

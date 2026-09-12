#!/usr/bin/env python3
"""Post-publication hard-lock regressions for STM32L0 L0.5."""
from __future__ import annotations

import csv
import hashlib
import json
import unittest

from publish_stm32l0_phase_l0_5 import (
    AUDIT_PATH,
    BASELINE_PATH,
    CANONICAL_PATH,
    EXPECTED_EXACT_SET_SHA256,
    EXPECTED_PLAN_GIT_BLOB,
    EXPECTED_POSTSTATE,
    EXPECTED_PRESTATE,
    EXPECTED_PRESTATE_MANIFEST_BLOB,
    EXPECTED_PRESTATE_MANIFEST_SHA256,
    EXPECTED_PUBLISHED_BASES,
    EXPECTED_PUBLISHED_ROWS,
    FAMILY,
    PLAN_PATH,
    PRODUCTION_MANIFEST,
    PROPOSAL_PATH,
    _git_blob_sha,
    _set_sha,
    publish,
    verify_current_publication,
)


class STM32L0PhaseL05PublicationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.proposal = json.loads(PROPOSAL_PATH.read_text(encoding="utf-8"))
        cls.audit = json.loads(AUDIT_PATH.read_text(encoding="utf-8"))
        cls.baseline = json.loads(BASELINE_PATH.read_text(encoding="utf-8"))
        with CANONICAL_PATH.open(newline="", encoding="utf-8") as handle:
            cls.rows = list(csv.DictReader(handle))

    def test_publication_state_is_valid(self) -> None:
        summary = verify_current_publication()
        self.assertGreaterEqual(summary["production_exact_icpns"], EXPECTED_POSTSTATE[0])
        self.assertGreaterEqual(summary["production_base_devices"], EXPECTED_POSTSTATE[1])
        self.assertGreaterEqual(summary["production_family_count"], EXPECTED_POSTSTATE[2])
        self.assertEqual(summary["stm32l0_production"], EXPECTED_PUBLISHED_ROWS)
        self.assertEqual(summary["published_exact_icpns"], EXPECTED_PUBLISHED_ROWS)
        self.assertEqual(summary["published_base_devices"], EXPECTED_PUBLISHED_BASES)

    def test_exact_published_set_is_hard_locked(self) -> None:
        identities = {row["icpn"] for row in self.rows}
        self.assertEqual(len(self.rows), EXPECTED_PUBLISHED_ROWS)
        self.assertEqual(len(identities), EXPECTED_PUBLISHED_ROWS)
        self.assertEqual(len({row["base_device"] for row in self.rows}), EXPECTED_PUBLISHED_BASES)
        self.assertEqual(_set_sha(identities), EXPECTED_EXACT_SET_SHA256)
        self.assertEqual(identities, set(self.proposal["added_exact_icpns"]))
        self.assertEqual(identities, set(self.audit["added_exact_icpns"]))
        self.assertEqual(self.baseline["published_exact_icpn_set_sha256"], EXPECTED_EXACT_SET_SHA256)

    def test_canonical_rows_retain_admission_semantics(self) -> None:
        self.assertTrue(all(row["family"] == FAMILY for row in self.rows))
        self.assertTrue(all(row["cmsis_device_name"] == "" for row in self.rows))
        self.assertTrue(all(row["existing_identifier_kind"] == "ordering_pattern" for row in self.rows))
        self.assertTrue(all(row["mapping_status"] == "deterministic_ordering_pattern" for row in self.rows))
        self.assertTrue(all(row["openocd_target_config"] == "tcl/target/stm32l0.cfg" for row in self.rows))
        self.assertTrue(all(row["verification_status"] == "verified_st_datasheet_ordering_information_plus_retained_exact_identity" for row in self.rows))

    def test_production_manifest_has_one_bound_l0_source(self) -> None:
        manifest = json.loads(PRODUCTION_MANIFEST.read_text(encoding="utf-8"))
        sources = [source for source in manifest["sources"] if source["family"] == FAMILY]
        self.assertEqual(len(sources), 1)
        source = sources[0]
        data = CANONICAL_PATH.read_bytes()
        self.assertEqual(source["row_count"], EXPECTED_PUBLISHED_ROWS)
        self.assertEqual(source["path"], "../research/stm32l0-commercial-icpn.csv")
        self.assertEqual(source["sha256"], hashlib.sha256(data).hexdigest())
        self.assertEqual(source["git_blob_sha"], _git_blob_sha(data))

    def test_baseline_binds_transaction_inputs_and_outputs(self) -> None:
        self.assertEqual(self.baseline["admission_plan_git_blob_sha"], EXPECTED_PLAN_GIT_BLOB)
        self.assertEqual(_git_blob_sha(PLAN_PATH.read_bytes()), EXPECTED_PLAN_GIT_BLOB)
        self.assertEqual(self.baseline["prestate_manifest_git_blob_sha"], EXPECTED_PRESTATE_MANIFEST_BLOB)
        self.assertEqual(self.baseline["prestate_manifest_sha256"], EXPECTED_PRESTATE_MANIFEST_SHA256)
        self.assertEqual(self.baseline["production_prestate"], {
            "exact_icpns": EXPECTED_PRESTATE[0], "base_devices": EXPECTED_PRESTATE[1],
            "families": EXPECTED_PRESTATE[2], "stm32l0": 0,
        })
        self.assertEqual(self.baseline["production_poststate"], {
            "exact_icpns": EXPECTED_POSTSTATE[0], "base_devices": EXPECTED_POSTSTATE[1],
            "families": EXPECTED_POSTSTATE[2], "stm32l0": EXPECTED_PUBLISHED_ROWS,
        })

    def test_publication_does_not_overclaim_programmer_support(self) -> None:
        self.assertTrue(self.audit["canonical_write_applied"])
        self.assertTrue(self.audit["production_write_applied"])
        self.assertFalse(self.audit["published_surface_partial_due_to_capability"])
        self.assertEqual(self.audit["capability_unresolved_count"], 0)
        for flag in (
            "programming_algorithm_equivalence_claimed",
            "flash_geometry_equivalence_claimed",
            "option_security_semantics_claimed",
            "physical_target_qualification_claimed",
            "ppu_physical_validation_claimed",
            "socket_physical_validation_claimed",
            "hil_qualification_claimed",
            "runtime_programming_support_claimed",
        ):
            self.assertFalse(self.audit[flag], flag)
        self.assertEqual(set(self.baseline["claims"].values()), {False})

    def test_publisher_is_idempotent_after_expected_publication(self) -> None:
        result = publish()
        self.assertEqual(result, {"status": "no_op_already_published", "published_exact_icpns": EXPECTED_PUBLISHED_ROWS})


if __name__ == "__main__":
    unittest.main()

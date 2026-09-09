#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from device_catalog_admission_framework import CandidateManualReview
from stm32g0_admission_policy import CANONICAL_FIELDS, TARGET_CONFIG, build_canonical_row
from stm32g0_phase4_8d_admission import (
    EXPECTED_CAPABILITY_UNRESOLVED,
    STM32G0AdmissionError,
    admission_plan_is_clean,
    build_admission_plan,
)


class STM32G0Phase48DAdmissionTests(unittest.TestCase):
    @staticmethod
    def _historical_plan() -> dict:
        with tempfile.TemporaryDirectory() as td:
            canonical = Path(td) / "stm32g0-commercial-icpn.csv"
            return build_admission_plan(canonical_path=canonical)

    def test_clean_plan_admits_47_and_preserves_two_capability_unresolved_identities(self) -> None:
        plan = self._historical_plan()
        self.assertTrue(admission_plan_is_clean(plan))
        self.assertEqual(plan["manufacturer_verified_identity_count"], 49)
        self.assertEqual(plan["candidate_count"], 47)
        self.assertEqual(plan["decision_counts"], {
            "admit": 47, "already_present": 0, "manual_review_required": 0, "reject": 0,
        })
        self.assertEqual(plan["capability_unresolved_count"], 2)
        self.assertEqual({x["icpn"] for x in plan["capability_unresolved"]}, set(EXPECTED_CAPABILITY_UNRESOLVED))
        self.assertFalse(plan["capability_unresolved_is_identity_rejection"])
        self.assertFalse(plan["canonical_write_applied"])
        self.assertFalse(plan["production_write_applied"])
        self.assertFalse(plan["n_product_version_capability_equivalence_claimed"])

    def test_all_47_admission_candidates_have_unique_g0_ordering_mapping(self) -> None:
        plan = self._historical_plan()
        self.assertEqual(len(plan["candidates"]), 47)
        for item in plan["candidates"]:
            self.assertEqual(item["decision"], "admit")
            mapping = item["base_mapping"]
            row = item["proposed_canonical_row"]
            self.assertEqual(mapping["status"], "unique")
            self.assertEqual(mapping["match_count"], 1)
            self.assertEqual(mapping["target_configs"], [TARGET_CONFIG])
            self.assertEqual(mapping["identifier_kind"], "ordering_pattern")
            self.assertEqual(row["openocd_target_config"], TARGET_CONFIG)
            self.assertEqual(row["mapping_status"], "deterministic_ordering_pattern")
            self.assertEqual(row["cmsis_device_name"], "")

    def test_n_identities_are_not_rewritten_as_standard_siblings(self) -> None:
        plan = self._historical_plan()
        admitted = {x["icpn"] for x in plan["candidates"]}
        unresolved = {x["icpn"] for x in plan["capability_unresolved"]}
        self.assertTrue(set(EXPECTED_CAPABILITY_UNRESOLVED).isdisjoint(admitted))
        self.assertEqual(unresolved, set(EXPECTED_CAPABILITY_UNRESOLVED))
        self.assertIn("STM32G0B1CBT6", admitted)
        self.assertIn("STM32G0B1CBU6", admitted)
        self.assertNotEqual("STM32G0B1CBT6N", "STM32G0B1CBT6")

    def test_global_mapping_failure_does_not_get_mislabeled_as_clean_exclusion(self) -> None:
        with patch(
            "stm32g0_phase4_8d_admission.resolve_mapping",
            return_value={"status": "unmapped", "match_count": 0, "target_configs": []},
        ):
            with self.assertRaises(STM32G0AdmissionError):
                self._historical_plan()

    def test_wrong_target_config_is_manual_review_at_row_boundary(self) -> None:
        plan = self._historical_plan()
        item = plan["candidates"][0]
        candidate = {
            "manufacturer": item["manufacturer"],
            "base_device": item["base_device"],
            "icpn": item["icpn"],
            "authoritative_evidence": copy.deepcopy(item["authoritative_evidence"]),
            "base_mapping": {
                "status": "unique", "match_count": 1,
                "target_configs": ["tcl/target/stm32f4x.cfg"],
                "identifier_kind": "ordering_pattern",
                "existing_identifier": item["base_mapping"]["existing_identifier"],
            },
        }
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_nonzero_canonical_prestate_is_rejected(self) -> None:
        plan = self._historical_plan()
        row = plan["candidates"][0]["proposed_canonical_row"]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "stm32g0-commercial-icpn.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(CANONICAL_FIELDS))
                writer.writeheader(); writer.writerow(row)
            with self.assertRaises(STM32G0AdmissionError):
                build_admission_plan(canonical_path=path)


if __name__ == "__main__":
    unittest.main()

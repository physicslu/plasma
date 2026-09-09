#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import tempfile
import unittest
from unittest.mock import patch

from device_catalog_admission_framework import CandidateManualReview
from stm32f7_admission_policy import CANONICAL_FIELDS, TARGET_CONFIG, build_canonical_row
from stm32f7_phase4_6d_admission import (
    DEFAULT_CANONICAL,
    STM32F7AdmissionError,
    admission_plan_is_clean,
    build_admission_plan,
)


class STM32F7Phase46DAdmissionTests(unittest.TestCase):
    @staticmethod
    def _candidate_input(item: dict) -> dict:
        return {
            "manufacturer": item["manufacturer"],
            "base_device": item["base_device"],
            "icpn": item["icpn"],
            "authoritative_evidence": copy.deepcopy(item["authoritative_evidence"]),
            "base_mapping": copy.deepcopy(item["base_mapping"]),
        }

    def test_clean_plan_admits_exactly_19(self) -> None:
        plan = build_admission_plan()
        self.assertTrue(admission_plan_is_clean(plan))
        self.assertEqual(plan["candidate_count"], 19)
        self.assertEqual(plan["decision_counts"], {
            "admit": 19,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        })
        self.assertEqual(plan["canonical_rows_before"], 0)
        self.assertEqual(plan["canonical_dataset_admission"], "planned")
        self.assertEqual(plan["required_target_config"], TARGET_CONFIG)
        self.assertEqual(plan["lifecycle_exclusions_preserved"], 5)
        self.assertEqual(plan["source_unavailable_exclusions_preserved"], 2)
        self.assertFalse(plan["canonical_write_applied"])
        self.assertFalse(plan["production_write_applied"])
        self.assertFalse(plan["programming_algorithm_equivalence_claimed"])
        self.assertFalse(plan["physical_target_qualification_claimed"])
        self.assertFalse(plan["runtime_programming_support_claimed"])

    def test_all_admitted_rows_have_unique_f7_mapping(self) -> None:
        plan = build_admission_plan()
        admitted = [item for item in plan["candidates"] if item["decision"] == "admit"]
        self.assertEqual(len(admitted), 19)
        for item in admitted:
            row = item["proposed_canonical_row"]
            self.assertIsInstance(row, dict)
            self.assertEqual(row["openocd_target_config"], TARGET_CONFIG)
            self.assertEqual(row["existing_identifier_kind"], "ordering_pattern")
            self.assertEqual(row["mapping_status"], "deterministic_ordering_pattern")
            self.assertTrue(row["existing_identifier"])

    def test_unmapped_candidate_fails_clean_plan(self) -> None:
        with patch(
            "stm32f7_phase4_6d_admission.resolve_mapping",
            return_value={"status": "unmapped", "match_count": 0, "target_configs": []},
        ):
            plan = build_admission_plan()
        self.assertFalse(admission_plan_is_clean(plan))
        self.assertEqual(plan["decision_counts"]["manual_review_required"], 19)
        self.assertEqual(plan["decision_counts"]["admit"], 0)

    def test_ambiguous_candidate_fails_clean_plan(self) -> None:
        mapping = {
            "status": "ambiguous",
            "match_count": 2,
            "target_configs": [TARGET_CONFIG, "tcl/target/other.cfg"],
            "identifier_kind": "ordering_pattern",
            "existing_identifier": "STM32F722ICKx",
        }
        with patch("stm32f7_phase4_6d_admission.resolve_mapping", return_value=mapping):
            plan = build_admission_plan()
        self.assertFalse(admission_plan_is_clean(plan))
        self.assertEqual(plan["decision_counts"]["manual_review_required"], 19)

    def test_wrong_target_config_is_manual_review(self) -> None:
        plan = build_admission_plan()
        item = next(item for item in plan["candidates"] if item["decision"] == "admit")
        candidate = self._candidate_input(item)
        candidate["base_mapping"] = {
            "status": "unique",
            "match_count": 1,
            "target_configs": ["tcl/target/stm32f4x.cfg"],
            "identifier_kind": "ordering_pattern",
            "existing_identifier": "STM32F722ICKx",
        }
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_non_ordering_identifier_is_manual_review(self) -> None:
        plan = build_admission_plan()
        item = next(item for item in plan["candidates"] if item["decision"] == "admit")
        candidate = self._candidate_input(item)
        candidate["base_mapping"] = {
            "status": "unique",
            "match_count": 1,
            "target_configs": [TARGET_CONFIG],
            "identifier_kind": "exact",
            "existing_identifier": candidate["icpn"],
        }
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_nonzero_canonical_prestate_is_rejected(self) -> None:
        plan = build_admission_plan()
        row = next(
            item["proposed_canonical_row"]
            for item in plan["candidates"]
            if item["decision"] == "admit"
        )
        with tempfile.TemporaryDirectory() as td:
            path = __import__("pathlib").Path(td) / "stm32f7-commercial-icpn.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(CANONICAL_FIELDS))
                writer.writeheader()
                writer.writerow(row)
            with self.assertRaises(STM32F7AdmissionError):
                build_admission_plan(canonical_path=path)

    def test_default_canonical_is_absent_before_publication(self) -> None:
        self.assertFalse(DEFAULT_CANONICAL.exists())


if __name__ == "__main__":
    unittest.main()

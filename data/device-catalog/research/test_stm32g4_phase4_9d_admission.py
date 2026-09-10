#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from device_catalog_admission_framework import CandidateManualReview
from stm32g4_admission_policy import CANONICAL_FIELDS, TARGET_CONFIG, build_canonical_row
from stm32g4_metadata_policy import EXPECTED_PROPOSAL_EXCLUSIONS, SOURCE_UNAVAILABLE_BASES
from stm32g4_phase4_9d_admission import (
    EXPECTED_ADMITTABLE_COUNT,
    EXPECTED_CAPABILITY_UNRESOLVED,
    STM32G4AdmissionError,
    admission_plan_is_clean,
    build_admission_plan,
)


class STM32G4Phase49DAdmissionTests(unittest.TestCase):
    @staticmethod
    def _historical_plan() -> dict:
        with tempfile.TemporaryDirectory() as td:
            canonical = Path(td) / "stm32g4-commercial-icpn.csv"
            return build_admission_plan(canonical_path=canonical)

    def test_clean_plan_admits_all_25_verified_active_identities(self) -> None:
        plan = self._historical_plan()
        self.assertTrue(admission_plan_is_clean(plan))
        self.assertEqual(plan["manufacturer_verified_identity_count"], 25)
        self.assertEqual(plan["candidate_count"], EXPECTED_ADMITTABLE_COUNT)
        self.assertEqual(plan["decision_counts"], {
            "admit": 25, "already_present": 0, "manual_review_required": 0, "reject": 0,
        })
        self.assertEqual(plan["capability_unresolved_count"], 0)
        self.assertEqual(plan["capability_unresolved"], [])
        self.assertEqual(EXPECTED_CAPABILITY_UNRESOLVED, frozenset())
        self.assertFalse(plan["canonical_write_applied"])
        self.assertFalse(plan["production_write_applied"])

    def test_all_25_candidates_have_one_strict_g4_ordering_pattern_route(self) -> None:
        plan = self._historical_plan()
        self.assertEqual(len(plan["candidates"]), 25)
        for item in plan["candidates"]:
            self.assertEqual(item["decision"], "admit")
            mapping = item["base_mapping"]
            row = item["proposed_canonical_row"]
            self.assertEqual(mapping["status"], "unique")
            self.assertEqual(mapping["match_count"], 1)
            self.assertEqual(mapping["target_configs"], [TARGET_CONFIG])
            self.assertEqual(mapping["identifier_kind"], "ordering_pattern")
            self.assertTrue(mapping["existing_identifier"].endswith("x"))
            self.assertEqual(row["openocd_target_config"], TARGET_CONFIG)
            self.assertEqual(row["mapping_status"], "deterministic_ordering_pattern")
            self.assertEqual(row["existing_identifier_kind"], "ordering_pattern")
            self.assertEqual(row["cmsis_device_name"], "")

    def test_wlcsp49_metadata_survives_route_admission_without_normalization(self) -> None:
        plan = self._historical_plan()
        item = next(x for x in plan["candidates"] if x["icpn"] == "STM32G441CBY6TR")
        row = item["proposed_canonical_row"]
        self.assertEqual(item["base_mapping"]["existing_identifier"], "STM32G441CBYx")
        self.assertEqual(row["package"], "WLCSP")
        self.assertEqual(row["pin_count"], "49")
        self.assertEqual(row["option_suffix"], "TR")

    def test_source_unavailable_and_proposal_exclusions_never_enter_admission_candidates(self) -> None:
        plan = self._historical_plan()
        admitted = {x["icpn"] for x in plan["candidates"]}
        self.assertTrue(admitted.isdisjoint(EXPECTED_PROPOSAL_EXCLUSIONS))
        self.assertEqual(plan["proposal_exact_identity_exclusions"], sorted(EXPECTED_PROPOSAL_EXCLUSIONS))
        self.assertEqual(plan["source_unavailable_base_devices"], sorted(SOURCE_UNAVAILABLE_BASES))
        self.assertFalse(plan["bounded_commercial_surface_complete"])
        self.assertTrue(all(not any(icpn.startswith(base) for base in SOURCE_UNAVAILABLE_BASES) for icpn in admitted))

    def test_mapping_loss_fails_closed_instead_of_shrinking_admission_set(self) -> None:
        with patch(
            "stm32g4_phase4_9d_admission.resolve_mapping",
            return_value={"status": "unmapped", "match_count": 0, "target_configs": []},
        ):
            with self.assertRaises(STM32G4AdmissionError):
                self._historical_plan()

    def test_wrong_target_config_is_manual_review_at_canonical_row_boundary(self) -> None:
        plan = self._historical_plan()
        item = plan["candidates"][0]
        candidate = {
            "manufacturer": item["manufacturer"],
            "base_device": item["base_device"],
            "icpn": item["icpn"],
            "authoritative_evidence": copy.deepcopy(item["authoritative_evidence"]),
            "base_mapping": {
                "status": "unique",
                "match_count": 1,
                "target_configs": ["tcl/target/stm32g0x.cfg"],
                "identifier_kind": "ordering_pattern",
                "existing_identifier": item["base_mapping"]["existing_identifier"],
            },
        }
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_cmsis_alias_cannot_satisfy_canonical_route_gate(self) -> None:
        plan = self._historical_plan()
        item = plan["candidates"][0]
        candidate = {
            "manufacturer": item["manufacturer"],
            "base_device": item["base_device"],
            "icpn": item["icpn"],
            "authoritative_evidence": copy.deepcopy(item["authoritative_evidence"]),
            "base_mapping": {
                "status": "unique",
                "match_count": 1,
                "target_configs": [TARGET_CONFIG],
                "identifier_kind": "cmsis_device_name",
                "existing_identifier": "STM32G431xx",
            },
        }
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_nonzero_canonical_prestate_is_rejected(self) -> None:
        plan = self._historical_plan()
        row = plan["candidates"][0]["proposed_canonical_row"]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "stm32g4-commercial-icpn.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(CANONICAL_FIELDS))
                writer.writeheader()
                writer.writerow(row)
            with self.assertRaises(STM32G4AdmissionError):
                build_admission_plan(canonical_path=path)

    def test_route_planning_does_not_claim_programming_or_hil_equivalence(self) -> None:
        plan = self._historical_plan()
        for flag in (
            "programming_algorithm_equivalence_claimed",
            "flash_geometry_equivalence_claimed",
            "option_security_semantics_claimed",
            "physical_target_qualification_claimed",
            "hil_qualification_claimed",
            "runtime_programming_support_claimed",
            "full_stm32g4_surface_covered",
        ):
            self.assertFalse(plan[flag])
        self.assertEqual(plan["canonical_dataset_admission"], "planned")


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import copy
import csv
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from device_catalog_admission_framework import CandidateManualReview
from stm32u0_admission_policy import CANONICAL_FIELDS, TARGET_CONFIG, build_canonical_row
from stm32u0_phase_u0_4_admission import (
    EXPECTED_ADMITTABLE_COUNT,
    EXPECTED_CAPABILITY_UNRESOLVED,
    STM32U0AdmissionError,
    admission_plan_is_clean,
    admission_summary,
    build_admission_plan,
)


class STM32U0PhaseU04AdmissionTests(unittest.TestCase):
    @staticmethod
    def _historical_plan() -> dict:
        with tempfile.TemporaryDirectory() as td:
            canonical = Path(td) / "stm32u0-commercial-icpn.csv"
            return build_admission_plan(canonical_path=canonical)

    def test_clean_plan_admits_all_68_verified_active_identities(self) -> None:
        plan = self._historical_plan()
        self.assertTrue(admission_plan_is_clean(plan))
        self.assertEqual(plan["manufacturer_verified_identity_count"], 68)
        self.assertEqual(plan["metadata_ready_count"], 68)
        self.assertEqual(plan["candidate_count"], EXPECTED_ADMITTABLE_COUNT)
        self.assertEqual(plan["decision_counts"], {
            "admit": 68,
            "already_present": 0,
            "manual_review_required": 0,
            "reject": 0,
        })
        self.assertEqual(plan["capability_unresolved_count"], 0)
        self.assertEqual(plan["capability_unresolved"], [])
        self.assertEqual(EXPECTED_CAPABILITY_UNRESOLVED, frozenset())
        self.assertFalse(plan["canonical_write_applied"])
        self.assertFalse(plan["production_write_applied"])

    def test_all_68_candidates_have_one_strict_u0_ordering_pattern_route(self) -> None:
        plan = self._historical_plan()
        self.assertEqual(len(plan["candidates"]), 68)
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

    def test_package_dependent_m_code_survives_route_admission(self) -> None:
        plan = self._historical_plan()
        by_icpn = {item["icpn"]: item for item in plan["candidates"]}
        m_i = by_icpn["STM32U073M8I6"]
        m_t = by_icpn["STM32U073M8T6"]
        self.assertEqual(m_i["base_mapping"]["existing_identifier"], "STM32U073M8Ix")
        self.assertEqual(m_t["base_mapping"]["existing_identifier"], "STM32U073M8Tx")
        self.assertEqual(m_i["proposed_canonical_row"]["package"], "UFBGA")
        self.assertEqual(m_i["proposed_canonical_row"]["pin_count"], "81")
        self.assertEqual(m_t["proposed_canonical_row"]["package"], "LQFP")
        self.assertEqual(m_t["proposed_canonical_row"]["pin_count"], "80")

    def test_tr_suffix_routes_on_commercial_core_without_identity_loss(self) -> None:
        plan = self._historical_plan()
        item = next(x for x in plan["candidates"] if x["icpn"] == "STM32U083CCT6TR")
        self.assertEqual(item["base_mapping"]["existing_identifier"], "STM32U083CCTx")
        self.assertEqual(item["proposed_canonical_row"]["icpn"], "STM32U083CCT6TR")
        self.assertEqual(item["proposed_canonical_row"]["option_suffix"], "TR")

    def test_mapping_loss_fails_closed_instead_of_shrinking_admission_set(self) -> None:
        with patch(
            "stm32u0_phase_u0_4_admission.resolve_mapping",
            return_value={"status": "unmapped", "match_count": 0, "target_configs": []},
        ):
            with self.assertRaises(STM32U0AdmissionError):
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
                "existing_identifier": "STM32U031G6YxT",
            },
        }
        with self.assertRaises(CandidateManualReview):
            build_canonical_row(candidate, list(CANONICAL_FIELDS))

    def test_nonzero_canonical_prestate_is_rejected(self) -> None:
        plan = self._historical_plan()
        row = plan["candidates"][0]["proposed_canonical_row"]
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "stm32u0-commercial-icpn.csv"
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(CANONICAL_FIELDS))
                writer.writeheader()
                writer.writerow(row)
            with self.assertRaises(STM32U0AdmissionError):
                build_admission_plan(canonical_path=path)

    def test_compact_summary_preserves_exact_scope_and_zero_write_boundary(self) -> None:
        summary = admission_summary(self._historical_plan())
        self.assertEqual(summary["manufacturer_verified_identity_count"], 68)
        self.assertEqual(summary["metadata_ready_count"], 68)
        self.assertEqual(summary["capability_admittable_count"], 68)
        self.assertEqual(summary["current_mapping_replay"], {
            "unique": 68, "ambiguous": 0, "unmapped": 0,
        })
        self.assertEqual(len(summary["admission_exact_icpns"]), 68)
        self.assertEqual(len(set(summary["admission_exact_icpns"])), 68)
        self.assertTrue(all(value is False for value in summary["claims"].values()))
        self.assertTrue(summary["fail_closed"])

    def test_route_planning_does_not_claim_programming_or_hil_equivalence(self) -> None:
        plan = self._historical_plan()
        for flag in (
            "programming_algorithm_equivalence_claimed",
            "flash_geometry_equivalence_claimed",
            "option_security_semantics_claimed",
            "physical_target_qualification_claimed",
            "hil_qualification_claimed",
            "runtime_programming_support_claimed",
            "full_stm32u0_surface_covered",
        ):
            self.assertFalse(plan[flag])
        self.assertEqual(plan["canonical_dataset_admission"], "planned")
        self.assertEqual(plan["production_snapshot"]["stm32u0_exact_icpn_count"], 0)


if __name__ == "__main__":
    unittest.main()

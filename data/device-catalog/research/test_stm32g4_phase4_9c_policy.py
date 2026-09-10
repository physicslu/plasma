#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest
from collections import Counter

from device_catalog_admission_framework import AdmissionError, CandidateManualReview, CandidateReject
from device_catalog_evidence_framework import read_json
from stm32g4_metadata_policy import (
    DEFAULT_ORDERING_AUTHORITY,
    EXPECTED_ACTIVE_CANDIDATE_COUNT,
    EXPECTED_PROPOSAL_EXCLUSIONS,
    METADATA_FIELDS,
    SOURCE_UNAVAILABLE_BASES,
    SUPPORTED_BASE_DEVICES,
    build_candidate_inputs,
    build_metadata_row,
    load_ordering_authority,
)
from stm32g4_phase4_9c_policy import EXPECTED_METADATA_DISTRIBUTION, build_policy_plan, policy_plan_is_clean
from validate_stm32g4_phase4_9b_retained_evidence import BASELINE, EVIDENCE, main as validate_retained


class STM32G4Phase49CPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.assert_retained = validate_retained()
        cls.baseline = read_json(BASELINE)
        cls.provenance = read_json(EVIDENCE / "provenance.json")
        cls.evidence_id = cls.provenance["evidence_id"]
        cls.candidates = build_candidate_inputs(
            discovery_baseline=cls.baseline,
            evidence_id=cls.evidence_id,
        )
        cls.rows = [build_metadata_row(candidate, list(METADATA_FIELDS)) for candidate in cls.candidates]

    def test_phase49b_bounded_clean_commercial_incomplete_state_is_expected(self) -> None:
        self.assertEqual(self.assert_retained, 0)
        aggregate = self.baseline["aggregate"]
        self.assertTrue(aggregate["bounded_discovery_clean"])
        self.assertFalse(aggregate["commercial_identity_clean"])
        self.assertEqual(aggregate["source_unavailable_exclusions"], 3)
        self.assertEqual(aggregate["active_exact_icpn_candidates"], 25)
        self.assertEqual(aggregate["identity_manual_intervention_required"], 0)
        self.assertFalse(self.provenance["production_admission_ready"])

    def test_only_25_retained_active_identities_enter_metadata_scope(self) -> None:
        self.assertEqual(len(self.candidates), EXPECTED_ACTIVE_CANDIDATE_COUNT)
        self.assertEqual(len({item["icpn"] for item in self.candidates}), 25)
        self.assertEqual({item["base_device"] for item in self.candidates}, set(SUPPORTED_BASE_DEVICES))
        candidate_icpns = {item["icpn"] for item in self.candidates}
        self.assertTrue(candidate_icpns.isdisjoint(EXPECTED_PROPOSAL_EXCLUSIONS))
        self.assertTrue(candidate_icpns.isdisjoint(SOURCE_UNAVAILABLE_BASES))

    def test_three_404_targets_and_three_proposals_remain_excluded(self) -> None:
        unavailable = {
            item["base_device"]
            for item in self.baseline["targets"]
            if item["disposition"] == "source_unavailable_excluded"
        }
        proposals = {
            item["icpn"]
            for target in self.baseline["targets"]
            if target.get("disposition") == "active_candidates"
            for item in target["excluded_non_active_part_numbers"]
        }
        self.assertEqual(unavailable, set(SOURCE_UNAVAILABLE_BASES))
        self.assertEqual(proposals, set(EXPECTED_PROPOSAL_EXCLUSIONS))

    def test_all_25_candidates_decode_without_openocd_or_cmsis_metadata_authority(self) -> None:
        self.assertEqual(len(self.rows), 25)
        for row in self.rows:
            self.assertEqual(tuple(row), METADATA_FIELDS)
            self.assertEqual(row["manufacturer"], "STMicroelectronics")
            self.assertEqual(row["family"], "STM32G4")
            self.assertEqual(row["source_authority"], "STMicroelectronics official")
            self.assertNotIn("openocd", row["source_type"].lower())
            self.assertNotIn("cmsis", row["source_type"].lower())
            self.assertIn("st.com/resource/en/datasheet/", row["source_reference"])

    def test_wlcsp49_is_package_specific_not_global_c_pin_normalization(self) -> None:
        by_icpn = {row["icpn"]: row for row in self.rows}
        wlcsp = by_icpn["STM32G441CBY6TR"]
        self.assertEqual(wlcsp["package"], "WLCSP")
        self.assertEqual(wlcsp["pin_count"], "49")
        self.assertEqual(by_icpn["STM32G441CBT6"]["pin_count"], "48")
        self.assertEqual(by_icpn["STM32G441CBU6"]["pin_count"], "48")

    def test_metadata_distribution_is_frozen_for_retained_active_set(self) -> None:
        observed = {
            "flash_size": dict(sorted(Counter(row["flash_size"] for row in self.rows).items())),
            "package": dict(sorted(Counter(row["package"] for row in self.rows).items())),
            "pin_count": dict(sorted(Counter(row["pin_count"] for row in self.rows).items())),
            "temperature_grade": dict(sorted(Counter(row["temperature_grade"] for row in self.rows).items())),
            "option_suffix": dict(sorted(Counter(row["option_suffix"] for row in self.rows).items())),
        }
        self.assertEqual(observed, EXPECTED_METADATA_DISTRIBUTION)

    def test_structured_ordering_authority_is_exactly_eight_series_and_fail_closed(self) -> None:
        authority = load_ordering_authority(DEFAULT_ORDERING_AUTHORITY)
        self.assertEqual(set(authority), {
            "STM32G431", "STM32G441", "STM32G473", "STM32G474",
            "STM32G483", "STM32G484", "STM32G491", "STM32G4A1",
        })
        self.assertFalse(authority["STM32G483"]["review"]["visual_ordering_table"])
        for series, record in authority.items():
            self.assertTrue(record["review"]["text_extraction"], series)
            self.assertTrue(record["datasheet_url"].startswith("https://www.st.com/resource/en/datasheet/"))

    def test_source_unavailable_target_cannot_be_promoted_without_new_evidence(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        target = next(item for item in baseline["targets"] if item["base_device"] == "STM32G411C6")
        target["disposition"] = "active_candidates"
        target["commercial_identity_status"] = "verified_active"
        target["exact_icpns"] = ["STM32G411C6T6"]
        with self.assertRaises(AdmissionError):
            build_candidate_inputs(discovery_baseline=baseline, evidence_id=self.evidence_id)

    def test_proposal_exact_identity_cannot_be_promoted_to_active(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        target = next(item for item in baseline["targets"] if item["base_device"] == "STM32G441CB")
        target["exact_icpns"].append("STM32G441CBT3")
        target["excluded_non_active_part_numbers"] = [
            item for item in target["excluded_non_active_part_numbers"] if item["icpn"] != "STM32G441CBT3"
        ]
        with self.assertRaises(AdmissionError):
            build_candidate_inputs(discovery_baseline=baseline, evidence_id=self.evidence_id)

    def test_unbound_package_temperature_and_option_codes_fail_closed(self) -> None:
        source = next(item for item in self.candidates if item["icpn"] == "STM32G491CCT6")

        package = copy.deepcopy(source)
        package["icpn"] = "STM32G491CCY6"
        with self.assertRaises(CandidateManualReview):
            build_metadata_row(package, list(METADATA_FIELDS))

        temperature = copy.deepcopy(source)
        temperature["icpn"] = "STM32G491CCT7"
        with self.assertRaises(CandidateManualReview):
            build_metadata_row(temperature, list(METADATA_FIELDS))

        option = copy.deepcopy(source)
        option["icpn"] = "STM32G491CCT6N"
        with self.assertRaises(CandidateReject):
            build_metadata_row(option, list(METADATA_FIELDS))

    def test_policy_planner_is_clean_without_authorizing_production(self) -> None:
        plan = build_policy_plan()
        self.assertTrue(policy_plan_is_clean(plan))
        self.assertEqual(plan["decision_counts"], {
            "metadata_ready": 25,
            "manual_review_required": 0,
            "reject": 0,
        })
        self.assertEqual(plan["production_snapshot"]["exact_icpn_count"], 610)
        self.assertEqual(plan["production_snapshot"]["base_device_count"], 209)
        self.assertEqual(plan["production_snapshot"]["stm32g4_exact_icpn_count"], 0)
        self.assertFalse(plan["production_write_applied"])
        self.assertTrue(plan["capability_mapping_deferred"])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest
from collections import Counter

from device_catalog_admission_framework import AdmissionError, CandidateReject
from device_catalog_evidence_framework import read_json
from stm32g0_metadata_policy import (
    DATASHEET_AUTHORITIES,
    EXPECTED_ACTIVE_CANDIDATE_COUNT,
    METADATA_FIELDS,
    SUPPORTED_BASE_DEVICES,
    build_candidate_inputs,
    build_metadata_row,
)
from validate_stm32g0_phase4_8b_retained_evidence import BASELINE, EVIDENCE, main as validate_retained


class STM32G0Phase48CPolicyTests(unittest.TestCase):
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

    def test_phase48b_retained_gate_is_metadata_policy_eligible(self) -> None:
        self.assertEqual(self.assert_retained, 0)
        self.assertTrue(self.baseline["aggregate"]["bounded_discovery_clean"])
        self.assertTrue(self.baseline["aggregate"]["commercial_identity_clean"])
        self.assertEqual(self.baseline["aggregate"]["active_exact_icpn_candidates"], 49)
        self.assertFalse(self.provenance["production_admission_ready"])

    def test_all_retained_active_identities_are_projected_and_proposals_are_not(self) -> None:
        self.assertEqual(len(self.candidates), EXPECTED_ACTIVE_CANDIDATE_COUNT)
        self.assertEqual(len({item["icpn"] for item in self.candidates}), 49)
        self.assertEqual({item["base_device"] for item in self.candidates}, set(SUPPORTED_BASE_DEVICES))
        candidate_icpns = {item["icpn"] for item in self.candidates}
        proposal_icpns = {
            item["icpn"]
            for target in self.baseline["targets"]
            for item in target["excluded_non_active_part_numbers"]
        }
        self.assertEqual(proposal_icpns, {"STM32G0C1CCT6", "STM32G0C1CCT6N", "STM32G0C1CCU6N"})
        self.assertTrue(candidate_icpns.isdisjoint(proposal_icpns))

    def test_all_49_active_candidates_decode_without_openocd_or_cmsis_authority(self) -> None:
        self.assertEqual(len(self.rows), 49)
        by_icpn = {row["icpn"]: row for row in self.rows}
        for row in self.rows:
            self.assertEqual(tuple(row), METADATA_FIELDS)
            self.assertEqual(row["manufacturer"], "STMicroelectronics")
            self.assertEqual(row["family"], "STM32G0")
            self.assertEqual(row["pin_count"], "48")
            self.assertEqual(row["source_authority"], "STMicroelectronics official")
            self.assertNotIn("openocd", row["source_type"].lower())
            self.assertNotIn("cmsis", row["source_type"].lower())

        self.assertEqual(by_icpn["STM32G031C4T6"]["flash_size"], "16 KiB")
        self.assertEqual(by_icpn["STM32G051C6U7TR"]["package"], "UFQFPN")
        self.assertEqual(by_icpn["STM32G051C6U7TR"]["temperature_grade"], "-40 to 105 C")
        self.assertEqual(by_icpn["STM32G071C8T3"]["temperature_grade"], "-40 to 125 C")
        self.assertEqual(by_icpn["STM32G0B0CET6"]["flash_size"], "512 KiB")
        self.assertEqual(by_icpn["STM32G0C1CCU6"]["flash_size"], "256 KiB")

    def test_n_product_version_is_preserved_not_normalized_away(self) -> None:
        by_icpn = {row["icpn"]: row for row in self.rows}
        expected = {"STM32G0B1CBT6N", "STM32G0B1CBU6N"}
        self.assertTrue(expected.issubset(by_icpn))
        for icpn in expected:
            self.assertEqual(by_icpn[icpn]["option_suffix"], "N")
            self.assertIn("preserved_n_product_version", by_icpn[icpn]["verification_status"])
        self.assertNotEqual(by_icpn["STM32G0B1CBT6N"]["icpn"], by_icpn["STM32G0B1CBT6"]["icpn"])

    def test_metadata_distribution_is_frozen_for_retained_active_set(self) -> None:
        self.assertEqual(Counter(row["package"] for row in self.rows), Counter({"LQFP": 26, "UFQFPN": 23}))
        self.assertEqual(Counter(row["temperature_grade"] for row in self.rows), Counter({
            "-40 to 85 C": 29, "-40 to 125 C": 12, "-40 to 105 C": 8,
        }))
        self.assertEqual(Counter(row["option_suffix"] for row in self.rows), Counter({"": 27, "TR": 20, "N": 2}))
        self.assertEqual(Counter(row["flash_size"] for row in self.rows), Counter({
            "128 KiB": 21, "32 KiB": 11, "64 KiB": 11,
            "16 KiB": 2, "512 KiB": 2, "256 KiB": 2,
        }))

    def test_all_12_subfamilies_have_explicit_official_ordering_authority(self) -> None:
        self.assertEqual(len(DATASHEET_AUTHORITIES), 12)
        for authority in DATASHEET_AUTHORITIES.values():
            self.assertTrue(authority.startswith("https://www.st.com/resource/en/datasheet/"))
            self.assertTrue(authority.endswith(".pdf"))

    def test_forged_n_version_on_non_n_base_fails_closed(self) -> None:
        candidate = next(item for item in self.candidates if item["icpn"] == "STM32G071C8T6")
        forged = copy.deepcopy(candidate)
        forged["icpn"] = "STM32G071C8T6N"
        with self.assertRaises(CandidateReject):
            build_metadata_row(forged, list(METADATA_FIELDS))

    def test_retained_identity_drift_fails_before_metadata_decode(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        target = next(item for item in baseline["targets"] if item["base_device"] == "STM32G0C1CC")
        target["disposition"] = "lifecycle_excluded"
        with self.assertRaises(AdmissionError):
            build_candidate_inputs(discovery_baseline=baseline, evidence_id=self.evidence_id)


if __name__ == "__main__":
    unittest.main()

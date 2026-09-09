#!/usr/bin/env python3
from __future__ import annotations

import copy
import unittest
from collections import Counter

from device_catalog_admission_framework import AdmissionError, CandidateReject
from device_catalog_evidence_framework import read_json
from stm32f7_metadata_policy import (
    DATASHEET_AUTHORITIES,
    EXPECTED_ACTIVE_CANDIDATE_COUNT,
    F750_EXACT_PRODUCT_AUTHORITY,
    LIFECYCLE_EXCLUDED_BASES,
    METADATA_FIELDS,
    SOURCE_UNAVAILABLE_BASES,
    SUPPORTED_BASE_DEVICES,
    build_candidate_inputs,
    build_metadata_row,
)
from validate_stm32f7_phase4_6b_retained_evidence import (
    DEFAULT_BASELINE,
    DEFAULT_EVIDENCE_DIR,
    validate as validate_retained_evidence,
)


class STM32F7Phase46CPolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retained_report = validate_retained_evidence()
        cls.baseline = read_json(DEFAULT_BASELINE)
        cls.provenance = read_json(DEFAULT_EVIDENCE_DIR / "provenance.json")
        cls.evidence_id = cls.provenance["evidence_id"]
        cls.candidates = build_candidate_inputs(
            discovery_baseline=cls.baseline,
            evidence_id=cls.evidence_id,
        )
        cls.rows = [build_metadata_row(candidate, list(METADATA_FIELDS)) for candidate in cls.candidates]

    def test_phase46b_retained_gate_is_policy_eligible_but_not_commercially_complete(self) -> None:
        self.assertEqual(self.retained_report["status"], "valid")
        self.assertTrue(self.retained_report["bounded_discovery_clean"])
        self.assertFalse(self.retained_report["commercial_identity_clean"])
        self.assertEqual(self.retained_report["active_exact_icpn_candidates"], 19)
        self.assertFalse(self.retained_report["production_admission_ready"])

    def test_only_active_dispositions_become_metadata_candidates(self) -> None:
        self.assertEqual(len(self.candidates), EXPECTED_ACTIVE_CANDIDATE_COUNT)
        self.assertEqual(len({item["icpn"] for item in self.candidates}), 19)
        self.assertEqual({item["base_device"] for item in self.candidates}, set(SUPPORTED_BASE_DEVICES))
        self.assertTrue({item["base_device"] for item in self.candidates}.isdisjoint(LIFECYCLE_EXCLUDED_BASES))
        self.assertTrue({item["base_device"] for item in self.candidates}.isdisjoint(SOURCE_UNAVAILABLE_BASES))

    def test_all_19_active_candidates_decode_without_manual_inference(self) -> None:
        self.assertEqual(len(self.rows), 19)
        by_icpn = {row["icpn"]: row for row in self.rows}
        self.assertEqual(set(by_icpn), {item["icpn"] for item in self.candidates})
        for row in self.rows:
            self.assertEqual(tuple(row), METADATA_FIELDS)
            self.assertEqual(row["manufacturer"], "STMicroelectronics")
            self.assertEqual(row["family"], "STM32F7")
            self.assertEqual(row["source_authority"], "STMicroelectronics official")

        self.assertEqual(by_icpn["STM32F722ICK6"]["package"], "UFBGA")
        self.assertEqual(by_icpn["STM32F722ICT6"]["package"], "LQFP")
        self.assertEqual(by_icpn["STM32F722ICK6"]["flash_size"], "256 KiB")
        self.assertEqual(by_icpn["STM32F730I8K6TR"]["flash_size"], "64 KiB")
        self.assertEqual(by_icpn["STM32F730I8K6TR"]["option_suffix"], "TR")
        self.assertEqual(by_icpn["STM32F745IEK7"]["temperature_grade"], "-40 to 105 C")
        self.assertEqual(by_icpn["STM32F750N8H6"]["package"], "TFBGA")
        self.assertEqual(by_icpn["STM32F750N8H6"]["pin_count"], "216")
        self.assertEqual(by_icpn["STM32F750N8H6"]["flash_size"], "64 KiB")
        self.assertEqual(by_icpn["STM32F778AIY6TR"]["package"], "WLCSP")
        self.assertEqual(by_icpn["STM32F778AIY6TR"]["pin_count"], "180")
        self.assertEqual(by_icpn["STM32F778AIY6TR"]["flash_size"], "2048 KiB")

    def test_metadata_distribution_is_frozen_for_current_active_set(self) -> None:
        self.assertEqual(Counter(row["package"] for row in self.rows), Counter({
            "UFBGA": 10, "LQFP": 6, "WLCSP": 2, "TFBGA": 1,
        }))
        self.assertEqual(Counter(row["flash_size"] for row in self.rows), Counter({
            "512 KiB": 10, "256 KiB": 4, "64 KiB": 3, "2048 KiB": 2,
        }))
        self.assertEqual(Counter(row["temperature_grade"] for row in self.rows), Counter({
            "-40 to 85 C": 16, "-40 to 105 C": 3,
        }))
        self.assertEqual(Counter(row["option_suffix"] for row in self.rows), Counter({"": 14, "TR": 5}))
        self.assertEqual(Counter(row["pin_count"] for row in self.rows), Counter({"176": 16, "180": 2, "216": 1}))

    def test_datasheet_authority_is_shared_by_subfamily_groups(self) -> None:
        self.assertEqual(DATASHEET_AUTHORITIES["STM32F722"], DATASHEET_AUTHORITIES["STM32F723"])
        self.assertEqual(DATASHEET_AUTHORITIES["STM32F732"], DATASHEET_AUTHORITIES["STM32F733"])
        self.assertEqual(DATASHEET_AUTHORITIES["STM32F778"], DATASHEET_AUTHORITIES["STM32F779"])
        self.assertTrue(F750_EXACT_PRODUCT_AUTHORITY.endswith("/stm32f750n8.html"))

    def test_lifecycle_exclusion_cannot_be_promoted_by_mutating_disposition(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        target = next(item for item in baseline["targets"] if item["base_device"] == "STM32F746BE")
        target["disposition"] = "active_candidates"
        target["exact_icpns"] = ["STM32F746BET6"]
        with self.assertRaises(AdmissionError):
            build_candidate_inputs(discovery_baseline=baseline, evidence_id=self.evidence_id)

    def test_source_unavailable_target_cannot_be_promoted_without_evidence(self) -> None:
        baseline = copy.deepcopy(self.baseline)
        target = next(item for item in baseline["targets"] if item["base_device"] == "STM32F768AI")
        target["disposition"] = "active_candidates"
        target["exact_icpns"] = ["STM32F768AIY6"]
        with self.assertRaises(AdmissionError):
            build_candidate_inputs(discovery_baseline=baseline, evidence_id=self.evidence_id)

    def test_f750_override_accepts_only_retained_exact_identity(self) -> None:
        candidate = next(item for item in self.candidates if item["base_device"] == "STM32F750N8")
        forged = copy.deepcopy(candidate)
        forged["icpn"] = "STM32F750N8H7"
        with self.assertRaises(CandidateReject):
            build_metadata_row(forged, list(METADATA_FIELDS))

    def test_openocd_is_not_an_input_to_metadata_policy(self) -> None:
        for row in self.rows:
            self.assertNotIn("openocd", row["source_type"].lower())
            self.assertNotIn("openocd", row["source_reference"].lower())


if __name__ == "__main__":
    unittest.main()

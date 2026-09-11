#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from device_catalog_admission_framework import AdmissionError, CandidateReject
from device_catalog_evidence_framework import read_json
from stm32u0_metadata_policy import (
    DEFAULT_ORDERING_AUTHORITY,
    EXPECTED_ACTIVE_CANDIDATE_COUNT,
    METADATA_FIELDS,
    SUPPORTED_BASE_DEVICES,
    build_candidate_inputs,
    build_metadata_row,
    load_ordering_authority,
)
from stm32u0_phase_u0_3_policy import (
    EXPECTED_METADATA_DISTRIBUTION,
    build_policy_plan,
    policy_plan_is_clean,
)
from validate_stm32u0_phase_u0_2_retained_evidence import BASELINE, EVIDENCE, main as validate_retained


class STM32U0PhaseU03PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retained_status = validate_retained()
        cls.baseline = read_json(BASELINE)
        cls.provenance = read_json(EVIDENCE / "provenance.json")
        cls.candidates = build_candidate_inputs()
        cls.rows = [build_metadata_row(candidate, list(METADATA_FIELDS)) for candidate in cls.candidates]

    def test_u02_clean_retained_boundary_is_the_only_identity_input(self) -> None:
        self.assertEqual(self.retained_status, 0)
        aggregate = self.baseline["aggregate"]
        self.assertTrue(aggregate["bounded_discovery_clean"])
        self.assertTrue(aggregate["commercial_identity_clean"])
        self.assertEqual(aggregate["active_exact_icpn_candidates"], 68)
        self.assertEqual(aggregate["source_unavailable_exclusions"], 0)
        self.assertEqual(aggregate["identity_manual_intervention_required"], 0)
        self.assertFalse(self.provenance["production_admission_ready"])

    def test_exactly_68_retained_active_identities_from_26_bases_enter_metadata_scope(self) -> None:
        self.assertEqual(len(self.candidates), EXPECTED_ACTIVE_CANDIDATE_COUNT)
        self.assertEqual(len({item["icpn"] for item in self.candidates}), 68)
        self.assertEqual({item["base_device"] for item in self.candidates}, set(SUPPORTED_BASE_DEVICES))
        self.assertEqual(len(SUPPORTED_BASE_DEVICES), 26)

    def test_all_68_decode_without_openocd_or_cmsis_metadata_authority(self) -> None:
        self.assertEqual(len(self.rows), 68)
        for row in self.rows:
            self.assertEqual(tuple(row), METADATA_FIELDS)
            self.assertEqual(row["manufacturer"], "STMicroelectronics")
            self.assertEqual(row["family"], "STM32U0")
            self.assertEqual(row["source_authority"], "STMicroelectronics official")
            self.assertEqual(row["source_type"], "manufacturer_ordering_information")
            self.assertNotIn("openocd", row["source_reference"].lower())
            self.assertNotIn("cmsis", row["source_reference"].lower())
            self.assertIn("st.com/resource/en/datasheet/", row["source_reference"])

    def test_u073_u083_m_pin_count_depends_on_package(self) -> None:
        by_icpn = {row["icpn"]: row for row in self.rows}
        self.assertEqual(by_icpn["STM32U073M8I6"]["package"], "UFBGA")
        self.assertEqual(by_icpn["STM32U073M8I6"]["pin_count"], "81")
        self.assertEqual(by_icpn["STM32U073M8T6"]["package"], "LQFP")
        self.assertEqual(by_icpn["STM32U073M8T6"]["pin_count"], "80")
        self.assertEqual(by_icpn["STM32U083MCI6"]["pin_count"], "81")
        self.assertEqual(by_icpn["STM32U083MCT6"]["pin_count"], "80")

    def test_metadata_distribution_is_frozen_for_retained_68(self) -> None:
        observed = {
            "flash_size": dict(sorted(Counter(row["flash_size"] for row in self.rows).items())),
            "package": dict(sorted(Counter(row["package"] for row in self.rows).items())),
            "pin_count": dict(sorted(Counter(row["pin_count"] for row in self.rows).items())),
            "temperature_grade": dict(sorted(Counter(row["temperature_grade"] for row in self.rows).items())),
            "option_suffix": dict(sorted(Counter(row["option_suffix"] for row in self.rows).items())),
        }
        self.assertEqual(observed, EXPECTED_METADATA_DISTRIBUTION)

    def test_ordering_authority_is_exactly_three_current_rev2_documents(self) -> None:
        authority = load_ordering_authority(DEFAULT_ORDERING_AUTHORITY)
        self.assertEqual(set(authority), {"STM32U031", "STM32U073", "STM32U083"})
        expected = {
            "STM32U031": ("DS14581", 2, 124),
            "STM32U073": ("DS14548", 2, 135),
            "STM32U083": ("DS14463", 2, 135),
        }
        for series, (document, revision, page) in expected.items():
            record = authority[series]
            self.assertEqual(record["document_id"], document)
            self.assertEqual(record["revision"], revision)
            self.assertEqual(record["pdf_page"], page)
            self.assertEqual(record["ordering_section"], 8)
            self.assertTrue(record["review"]["structured_text"])
            self.assertFalse(record["current_revision_check"]["revision_drift"])
            self.assertEqual(record["current_revision_check"]["observed_revision"], revision)

    def test_legal_looking_but_unretained_exact_identity_is_rejected(self) -> None:
        source = copy.deepcopy(next(item for item in self.candidates if item["icpn"] == "STM32U073C8T6"))
        source["icpn"] = "STM32U073C8T3"
        with self.assertRaises(CandidateReject):
            build_metadata_row(source, list(METADATA_FIELDS))

    def test_cmsis_shaped_identity_cannot_enter_commercial_metadata_scope(self) -> None:
        source = copy.deepcopy(next(item for item in self.candidates if item["icpn"] == "STM32U031C6T6"))
        source["base_device"] = "STM32U031G6"
        source["icpn"] = "STM32U031G6Y6"
        with self.assertRaises(CandidateReject):
            build_metadata_row(source, list(METADATA_FIELDS))

    def test_revision_drift_fails_closed(self) -> None:
        payload = json.loads(DEFAULT_ORDERING_AUTHORITY.read_text(encoding="utf-8"))
        payload["records"][0]["current_revision_check"]["observed_revision"] = 3
        payload["records"][0]["current_revision_check"]["revision_drift"] = True
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "authority.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(AdmissionError):
                load_ordering_authority(path)

    def test_policy_planner_is_clean_without_authorizing_production_or_support(self) -> None:
        plan = build_policy_plan()
        self.assertTrue(policy_plan_is_clean(plan))
        self.assertEqual(plan["decision_counts"], {
            "metadata_ready": 68,
            "manual_review_required": 0,
            "reject": 0,
        })
        self.assertEqual(plan["production_snapshot"]["exact_icpn_count"], 635)
        self.assertEqual(plan["production_snapshot"]["base_device_count"], 217)
        self.assertEqual(plan["production_snapshot"]["stm32u0_exact_icpn_count"], 0)
        self.assertFalse(plan["production_write_applied"])
        self.assertTrue(plan["capability_mapping_deferred"])
        self.assertFalse(plan["programming_algorithm_equivalence_claimed"])
        self.assertFalse(plan["runtime_support_claimed"])


if __name__ == "__main__":
    unittest.main()

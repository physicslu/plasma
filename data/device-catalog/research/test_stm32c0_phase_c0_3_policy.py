#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path

from device_catalog_admission_framework import AdmissionError, CandidateReject, file_sha256
from stm32c0_metadata_policy import (
    DEFAULT_ORDERING_AUTHORITY,
    EXPECTED_ACTIVE_CANDIDATE_COUNT,
    EXPECTED_AUTHORITY_RECORDS,
    EXPECTED_EXCLUDED_NON_ACTIVE,
    METADATA_FIELDS,
    build_candidate_inputs,
    build_metadata_row,
    load_ordering_authority,
)
from stm32c0_phase_c0_3_policy import DEFAULT_PRODUCTION_MANIFEST, build_policy_plan, policy_plan_is_clean
from validate_stm32c0_phase_c0_2_retained_evidence import BASELINE, EVIDENCE, main as validate_retained


class STM32C0PhaseC03PolicyTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.retained_status = validate_retained()
        cls.baseline = json.loads(BASELINE.read_text(encoding="utf-8"))
        cls.summary = json.loads((EVIDENCE / "pilot-summary.json").read_text(encoding="utf-8"))
        cls.candidates = build_candidate_inputs()
        cls.rows = [build_metadata_row(candidate, list(METADATA_FIELDS)) for candidate in cls.candidates]

    def test_c02_clean_retained_boundary_is_the_only_identity_input(self) -> None:
        self.assertEqual(self.retained_status, 0)
        aggregate = self.baseline["aggregate"]
        self.assertTrue(aggregate["bounded_discovery_clean"])
        self.assertTrue(aggregate["commercial_identity_clean"])
        self.assertEqual(aggregate["active_exact_icpn_candidates"], 220)
        self.assertEqual(aggregate["source_unavailable_exclusions"], 0)
        self.assertEqual(aggregate["identity_manual_intervention_required"], 0)
        self.assertFalse(self.baseline["claims"]["production_write_authorized"])
        self.assertFalse(self.summary["openocd_routing"]["gates_commercial_identity"])

    def test_production_prestate_is_byte_locked(self) -> None:
        self.assertEqual(
            file_sha256(DEFAULT_PRODUCTION_MANIFEST),
            "903476d41997f9d20c237bccea0ee1e085fc343730e0d3740b2b82b0de0462b0",
        )

    def test_exactly_220_retained_active_identities_from_50_bases_enter_metadata_scope(self) -> None:
        self.assertEqual(len(self.candidates), EXPECTED_ACTIVE_CANDIDATE_COUNT)
        self.assertEqual(len({item["icpn"] for item in self.candidates}), 220)
        self.assertEqual(len({item["base_device"] for item in self.candidates}), 50)
        self.assertTrue(EXPECTED_EXCLUDED_NON_ACTIVE.isdisjoint({item["icpn"] for item in self.candidates}))

    def test_all_220_decode_without_openocd_or_cmsis_metadata_authority(self) -> None:
        self.assertEqual(len(self.rows), 220)
        for row in self.rows:
            self.assertEqual(tuple(row), METADATA_FIELDS)
            self.assertEqual(row["manufacturer"], "STMicroelectronics")
            self.assertEqual(row["family"], "STM32C0")
            self.assertEqual(row["source_authority"], "STMicroelectronics official")
            self.assertEqual(row["source_type"], "manufacturer_ordering_information")
            self.assertNotIn("openocd", row["source_reference"].lower())
            self.assertNotIn("cmsis", row["source_reference"].lower())
            self.assertIn("st.com/resource/en/datasheet/", row["source_reference"])

    def test_c071_product_version_and_packing_are_not_collapsed(self) -> None:
        by_icpn = {row["icpn"]: row for row in self.rows}
        self.assertEqual(by_icpn["STM32C071F8P6N"]["option_suffix"], "N")
        self.assertEqual(by_icpn["STM32C071KBT6NTR"]["option_suffix"], "NTR")
        self.assertEqual(by_icpn["STM32C071F8P6TR"]["option_suffix"], "TR")
        self.assertNotEqual(
            by_icpn["STM32C071F8P6N"]["option_suffix"],
            by_icpn["STM32C071F8P6TR"]["option_suffix"],
        )

    def test_c071_f_pin_count_is_package_dependent(self) -> None:
        by_icpn = {row["icpn"]: row for row in self.rows}
        self.assertEqual(by_icpn["STM32C071F8P6"]["package"], "TSSOP")
        self.assertEqual(by_icpn["STM32C071F8P6"]["pin_count"], "20")
        self.assertEqual(by_icpn["STM32C071FBY6TR"]["package"], "WLCSP")
        self.assertEqual(by_icpn["STM32C071FBY6TR"]["pin_count"], "19")

    def test_c091_c092_share_ds14720_without_series_collapse(self) -> None:
        c091 = next(row for row in self.rows if row["series"] == "STM32C091")
        c092 = next(row for row in self.rows if row["series"] == "STM32C092")
        self.assertEqual(c091["source_reference"], c092["source_reference"])
        self.assertIn("stm32c091cb.pdf", c091["source_reference"])
        self.assertNotEqual(c091["series"], c092["series"])
        self.assertTrue(c091["base_device"].startswith("STM32C091"))
        self.assertTrue(c092["base_device"].startswith("STM32C092"))

    def test_ordering_authority_is_exactly_six_current_documents_series_records(self) -> None:
        authority = load_ordering_authority(DEFAULT_ORDERING_AUTHORITY)
        self.assertEqual(set(authority), set(EXPECTED_AUTHORITY_RECORDS))
        for series, (document, revision, section, page) in EXPECTED_AUTHORITY_RECORDS.items():
            record = authority[series]
            self.assertEqual(record["document_id"], document)
            self.assertEqual(record["revision"], revision)
            self.assertEqual(record["ordering_section"], section)
            self.assertEqual(record["pdf_page"], page)
            self.assertTrue(record["review"]["structured_text"])
            self.assertFalse(record["current_revision_check"]["revision_drift"])
            self.assertEqual(record["current_revision_check"]["observed_revision"], revision)
        self.assertEqual(authority["STM32C091"]["document_id"], authority["STM32C092"]["document_id"])

    def test_preview_part_cannot_be_promoted_to_metadata_ready(self) -> None:
        source = copy.deepcopy(next(item for item in self.candidates if item["base_device"] == "STM32C091KB"))
        source["icpn"] = "STM32C091KBT3"
        with self.assertRaises(CandidateReject):
            build_metadata_row(source, list(METADATA_FIELDS))

    def test_legal_looking_but_unretained_exact_identity_is_rejected(self) -> None:
        source = copy.deepcopy(next(item for item in self.candidates if item["icpn"] == "STM32C071C8T3"))
        source["icpn"] = "STM32C071C8T3N"
        with self.assertRaises(CandidateReject):
            build_metadata_row(source, list(METADATA_FIELDS))

    def test_cmsis_shaped_identity_cannot_enter_commercial_metadata_scope(self) -> None:
        source = copy.deepcopy(self.candidates[0])
        source["base_device"] = "STM32C0xx"
        source["icpn"] = "STM32C0xx"
        with self.assertRaises(CandidateReject):
            build_metadata_row(source, list(METADATA_FIELDS))

    def test_revision_drift_fails_closed(self) -> None:
        payload = json.loads(DEFAULT_ORDERING_AUTHORITY.read_text(encoding="utf-8"))
        payload["records"][0]["current_revision_check"]["observed_revision"] = 6
        payload["records"][0]["current_revision_check"]["revision_drift"] = True
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "authority.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(AdmissionError):
                load_ordering_authority(path)

    def test_c071_n_semantics_cannot_be_removed_from_authority(self) -> None:
        payload = json.loads(DEFAULT_ORDERING_AUTHORITY.read_text(encoding="utf-8"))
        c071 = next(record for record in payload["records"] if record["series"] == "STM32C071")
        del c071["retained_semantics"]["option"]["N"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "authority.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaises(AdmissionError):
                load_ordering_authority(path)

    def test_metadata_distribution_preserves_distinct_options(self) -> None:
        options = Counter(row["option_suffix"] for row in self.rows)
        self.assertTrue(set(options).issubset({"", "TR", "N", "NTR"}))
        self.assertGreater(options["N"], 0)
        self.assertGreater(options["NTR"], 0)
        self.assertGreater(options["TR"], 0)

    def test_policy_planner_is_clean_without_authorizing_production_or_support(self) -> None:
        plan = build_policy_plan()
        self.assertTrue(policy_plan_is_clean(plan))
        self.assertEqual(plan["decision_counts"], {
            "metadata_ready": 220,
            "manual_review_required": 0,
            "reject": 0,
        })
        self.assertEqual(plan["production_snapshot"]["exact_icpn_count"], 703)
        self.assertEqual(plan["production_snapshot"]["base_device_count"], 243)
        self.assertEqual(plan["production_snapshot"]["stm32c0_exact_icpn_count"], 0)
        self.assertFalse(plan["production_write_applied"])
        self.assertFalse(plan["openocd_routing_gate_applied"])
        self.assertTrue(plan["capability_mapping_deferred"])
        self.assertFalse(plan["programming_algorithm_equivalence_claimed"])
        self.assertFalse(plan["runtime_support_claimed"])


if __name__ == "__main__":
    unittest.main()

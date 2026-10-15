"""NXP-only ADR-0002 Phase1 source/identity funnel negative regression tests."""
from __future__ import annotations

import copy
import unittest
from unittest.mock import patch

import nxp_phase1_funnel_audit_v1 as audit

class NxpPhase1FunnelTests(unittest.TestCase):
    def setUp(self):
        self.legacy = audit.read("legacy")
        self.reverse = audit.read("reverse")
        self.l82 = audit.read("lpc82x")
        self.l81 = audit.read("lpc81x")

    def run_audit(self, legacy=None, reverse=None, l82=None, l81=None):
        return audit.audit_from(
            self.legacy if legacy is None else legacy,
            self.reverse if reverse is None else reverse,
            self.l82 if l82 is None else l82,
            self.l81 if l81 is None else l81)

    def test_reproducible_phase1_funnel_counts(self):
        x = audit.verify()
        self.assertEqual(x["unique_exact_icpn_observations_or_candidates"], 566)
        self.assertEqual(x["phase1_identified_s1"], 240)
        self.assertEqual(x["phase1_information_complete_s1_complete"], 0)
        self.assertEqual(x["phase1_identity_review_backlog"], 326)
        self.assertEqual(x["phase1_identified_components"],
                         {"legacy_official_internal_identity_admitted": 224,
                          "new_official_exact_material_observed_lpc81x_lpc82x": 16})
        self.assertEqual(sum(x["backlog_components"].values()), 326)

    def test_phase2_phase3_not_audited_not_zero(self):
        result = self.run_audit()
        self.assertIsNone(result["phase2_software_qualified_s2"])
        self.assertIsNone(result["phase3_hil_validated_s3"])
        self.assertEqual(result["historical_research_priority_not_phase_counts"],
                         {"reverse_p0": 60, "reverse_p1": 5})

    def test_reject_legacy_research_promoted_by_missing_source(self):
        v = copy.deepcopy(self.legacy)
        missing = next(x for x in v if x["field_source_scope"] ==
                       "NO_EXACT_HTML_SOURCE_BYTES")
        missing["identity_state"] = "ADMITTED"
        with self.assertRaises(ValueError):
            self.run_audit(legacy=v)

    def test_reject_original_identity_provenance_substitution(self):
        v = copy.deepcopy(self.legacy)
        first = next(x for x in v if x["identity_state"] == "ADMITTED")
        first["manufacturer_uri"] = "https://example.com/not-nxp"
        with self.assertRaises(ValueError):
            self.run_audit(legacy=v)

    def test_reject_crosswave_duplicate_or_wrong_universe(self):
        v = copy.deepcopy(self.reverse)
        v[0]["icpn_observation"] = self.legacy[0]["icpn"]
        with self.assertRaises(ValueError):
            self.run_audit(reverse=v)

    def test_reject_wave_research_autopromotion(self):
        v = copy.deepcopy(self.reverse)
        v[0]["flash_programming_qualified"] = "true"
        with self.assertRaises(ValueError):
            self.run_audit(reverse=v)
        v = copy.deepcopy(self.reverse)
        v[0]["production_admitted"] = "true"
        with self.assertRaises(ValueError):
            self.run_audit(reverse=v)

    def test_reject_false_vendor_binary_custody_and_support(self):
        for field in ("original_pdf_bytes_archived", "programming_qualified",
                      "production_admitted", "physical_hil_verified"):
            v = copy.deepcopy(self.l81)
            v[0][field] = "true"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_audit(l81=v)
        for field in ("original_datasheet_pdf_binary_archived",
                      "openocd_programming_qualified", "physical_hil_verified"):
            v = copy.deepcopy(self.l82)
            v[0][field] = "true"
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.run_audit(l82=v)

    def test_reject_family_inference_from_unconfirmed_code(self):
        v = copy.deepcopy(self.l81)
        v[0]["icpn"] = "LPC812M101FAKE64J"
        with self.assertRaises(ValueError):
            self.run_audit(l81=v)

    def test_original_git_blob_lock_cannot_be_forged(self):
        src = copy.deepcopy(audit.SOURCE)
        filename, _ = src["legacy"]
        src["legacy"] = (filename, "0" * 40)
        with patch.object(audit, "SOURCE", src):
            with self.assertRaises(ValueError):
                audit.read("legacy")

    def test_base_device_alias_gap_is_not_info_complete(self):
        r = self.run_audit()
        self.assertEqual(
            r["provenance_quality_gaps"]["legacy_admitted_base_device_is_exact_icpn_alias"], 212)
        self.assertEqual(
            r["provenance_quality_gaps"]["legacy_501_io_supply_unknown"], 501)
        self.assertEqual(r["phase1_information_complete_s1_complete"], 0)

if __name__ == "__main__":
    unittest.main(verbosity=2)

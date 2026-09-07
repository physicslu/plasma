from __future__ import annotations

import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class KL25ReviewedEvidenceUnitsTest(unittest.TestCase):
    def test_reviewed_unit_definitions_are_fail_closed(self):
        doc = json.loads((HERE / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["status"], "reviewed_definitions_not_admitted_catalog")
        self.assertTrue(doc["trust_boundary"]["reviewed_unit_definitions_complete"])
        for key in [
            "evidence_unit_catalog_admission",
            "evidence_pack_admission",
            "applicability_binding_admission",
            "semantic_extraction_admission",
            "canonical_dataset_admission",
            "hil_admission",
            "production_admission",
            "destructive_security_operation_admission",
        ]:
            self.assertFalse(doc["trust_boundary"][key])

    def test_expected_nxp_native_units_exist(self):
        doc = json.loads((HERE / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8"))
        units = {u["unit_id"]: u for u in doc["units"]}
        expected = {
            "nxp-kl25-ftfa-register-model-v0",
            "nxp-kl25-ftfa-command-sequencing-v0",
            "nxp-kl25-program-longword-v0",
            "nxp-kl25-erase-sector-v0",
            "nxp-kl25-erase-all-blocks-v0",
            "nxp-kl25-flash-security-v0",
            "nxp-kl25-debug-security-interaction-v0",
            "nxp-kl25-swd-mdm-ap-v0",
        }
        self.assertTrue(expected.issubset(units))
        self.assertIn("FCCOB", units["nxp-kl25-ftfa-command-sequencing-v0"]["manufacturer_native_terms"])
        self.assertIn("MDM-AP", units["nxp-kl25-swd-mdm-ap-v0"]["manufacturer_native_terms"])

    def test_unit_boundaries_stay_within_reviewed_ranges(self):
        boundary = json.loads((HERE / "reviewed-candidate-boundary.json").read_text(encoding="utf-8"))
        doc = json.loads((HERE / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8"))
        rm_ranges = {
            b["role"]: tuple(b["pdf_pages"])
            for b in boundary["boundaries"]
            if b["source_id"] == "nxp_kl25_rm_rev3"
        }
        flash_lo, flash_hi = rm_ranges["flash_programming_core_candidate"]
        debug_lo, debug_hi = rm_ranges["debug_security_recovery_candidate"]
        for unit in doc["units"]:
            lo, hi = unit["pdf_page_range"]
            if unit["role"] == "DEBUG_PROGRAMMING_INTERFACE" or unit["unit_id"] == "nxp-kl25-debug-security-interaction-v0":
                self.assertGreaterEqual(lo, debug_lo)
                self.assertLessEqual(hi, debug_hi)
            else:
                self.assertGreaterEqual(lo, flash_lo)
                self.assertLessEqual(hi, flash_hi)

    def test_extraction_artifacts_are_not_promoted_to_unit_boundaries(self):
        doc = json.loads((HERE / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8"))
        self.assertEqual(doc["exclusions"]["caution_headings"], "NOT_UNIT_BOUNDARY")
        self.assertEqual(doc["exclusions"]["bit_name_only_headings"], "NOT_UNIT_BOUNDARY")
        self.assertIn("NORMALIZE", doc["exclusions"]["pdftotext_numbering_artifact_27_33_x"])
        self.assertEqual(doc["heading_normalization"]["27.33.x"], "27.3.3.x")
        register_unit = next(u for u in doc["units"] if u["unit_id"] == "nxp-kl25-ftfa-register-model-v0")
        self.assertIn("27.3.3.5 Flash Common Command Object Registers", register_unit["section_scope"])


if __name__ == "__main__":
    unittest.main()

from __future__ import annotations

import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class KL25EvidenceUnitConstructionTest(unittest.TestCase):
    def test_construction_remains_fail_closed(self):
        contract = json.loads((HERE / "evidence-unit-construction-contract.json").read_text(encoding="utf-8"))
        self.assertTrue(contract["admission"]["construction_candidate_catalog"])
        self.assertFalse(contract["admission"]["evidence_unit_catalog"])
        self.assertFalse(contract["admission"]["evidence_pack"])
        self.assertFalse(contract["admission"]["semantic_extraction"])
        self.assertFalse(contract["admission"]["production"])
        self.assertFalse(contract["admission"]["destructive_security_operation"])

    def test_reviewed_boundaries_drive_construction(self):
        boundary = json.loads((HERE / "reviewed-candidate-boundary.json").read_text(encoding="utf-8"))
        contract = json.loads((HERE / "evidence-unit-construction-contract.json").read_text(encoding="utf-8"))
        by_role = {b["role"]: b for b in boundary["boundaries"]}
        for role in contract["required_candidate_roles"]:
            self.assertIn(role, by_role)
        self.assertEqual(by_role["flash_programming_core_candidate"]["pdf_pages"], [419, 456])
        self.assertEqual(by_role["debug_security_recovery_candidate"]["pdf_pages"], [149, 157])

    def test_cross_vendor_guards_preserve_nxp_native_model(self):
        contract = json.loads((HERE / "evidence-unit-construction-contract.json").read_text(encoding="utf-8"))
        guards = contract["cross_vendor_guards"]
        self.assertTrue(guards["ftfa_fccob_fstat_are_manufacturer_near_terms"])
        self.assertTrue(guards["mdm_ap_security_recovery_is_not_flash_command_equivalence"])
        self.assertEqual(guards["forbidden_stm32_projection"], ["KEYR", "FLASH_CR", "PER", "MER", "PG"])

    def test_review_dimensions_require_structure_and_applicability(self):
        contract = json.loads((HERE / "evidence-unit-construction-contract.json").read_text(encoding="utf-8"))
        dims = contract["expected_next_review_dimensions"]
        for required in ["section_heading", "contiguous_page_span", "manufacturer_native_terms", "applicability_evidence"]:
            self.assertIn(required, dims)
        self.assertFalse(contract["method"]["manual_page_guessing_is_authoritative"])
        self.assertTrue(contract["evidence_unit_requirements"]["heading_evidence_required"])
        self.assertTrue(contract["evidence_unit_requirements"]["applicability_must_be_established_separately"])


if __name__ == "__main__":
    unittest.main()

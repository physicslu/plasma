from __future__ import annotations

import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class KL25ApplicabilityFoundationTest(unittest.TestCase):
    def test_applicability_remains_fail_closed(self):
        contract = json.loads((HERE / "applicability-contract.json").read_text(encoding="utf-8"))
        self.assertTrue(contract["admission"]["applicability_candidate_evidence"])
        for key in [
            "scope_bridge",
            "evidence_unit_catalog",
            "applicability_binding",
            "evidence_pack",
            "semantic_extraction",
            "canonical_dataset",
            "hil",
            "production",
            "destructive_security_operation",
        ]:
            self.assertFalse(contract["admission"][key])

    def test_identity_and_family_scope_are_distinct(self):
        contract = json.loads((HERE / "applicability-contract.json").read_text(encoding="utf-8"))
        bridge = contract["scope_bridge"]
        self.assertTrue(bridge["generic_family_header_may_establish_family_scope"])
        self.assertFalse(bridge["generic_family_header_may_establish_commercial_identity"])
        self.assertFalse(bridge["fuzzy_target_matching_allowed"])
        self.assertFalse(bridge["substring_identity_equivalence_allowed"])
        self.assertEqual(contract["candidate_claims"]["TARGET_EXACT_IDENTITY"]["terms"], ["MKL25Z128VLK4"])
        self.assertEqual(contract["candidate_claims"]["TARGET_DEVICE_EXPRESSION"]["terms"], ["MKL25Z128"])

    def test_all_reviewed_units_have_explicit_applicability_requirements(self):
        definitions = json.loads((HERE / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8"))
        contract = json.loads((HERE / "applicability-contract.json").read_text(encoding="utf-8"))
        unit_ids = {unit["unit_id"] for unit in definitions["units"]}
        self.assertEqual(unit_ids, set(contract["unit_requirements"]))
        for requirements in contract["unit_requirements"].values():
            self.assertTrue(requirements)

    def test_shared_reference_manual_is_not_sufficient_by_itself(self):
        contract = json.loads((HERE / "applicability-contract.json").read_text(encoding="utf-8"))
        policy = contract["unit_binding_policy"]
        self.assertTrue(policy["shared_reference_manual_does_not_by_itself_prove_unit_applicability"])
        self.assertTrue(policy["absence_of_exclusion_is_not_assumed_from_keyword_search"])
        self.assertTrue(policy["unknown_fails_closed"])

    def test_cross_vendor_module_model_is_preserved(self):
        contract = json.loads((HERE / "applicability-contract.json").read_text(encoding="utf-8"))
        self.assertIn("FTFA_MODULE_PRESENCE", contract["candidate_claims"])
        self.assertIn("SWD_DEBUG_PRESENCE", contract["candidate_claims"])
        self.assertIn("MDM_AP_PRESENCE", contract["candidate_claims"])
        self.assertIn("FLASH_SECURITY_MODEL", contract["candidate_claims"])
        self.assertIn("FTFA_MODULE_PRESENCE", contract["unit_requirements"]["nxp-kl25-program-longword-v0"])
        self.assertIn("MDM_AP_PRESENCE", contract["unit_requirements"]["nxp-kl25-swd-mdm-ap-v0"])


if __name__ == "__main__":
    unittest.main()

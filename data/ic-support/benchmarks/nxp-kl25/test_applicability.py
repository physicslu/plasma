from __future__ import annotations

import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class KL25ApplicabilityFoundationTest(unittest.TestCase):
    def test_applicability_admits_only_reviewed_binding_layers(self):
        contract = json.loads((HERE / "applicability-contract.json").read_text(encoding="utf-8"))
        for key in [
            "applicability_candidate_evidence",
            "scope_bridge",
            "evidence_unit_catalog",
            "applicability_binding",
        ]:
            self.assertTrue(contract["admission"][key])
        for key in [
            "evidence_pack",
            "semantic_extraction",
            "canonical_dataset",
            "hil",
            "production",
            "destructive_security_operation",
        ]:
            self.assertFalse(contract["admission"][key])

    def test_identity_family_and_document_membership_are_distinct(self):
        contract = json.loads((HERE / "applicability-contract.json").read_text(encoding="utf-8"))
        bridge = contract["scope_bridge"]
        self.assertFalse(bridge["generic_family_header_alone_may_establish_family_scope"])
        self.assertTrue(bridge["explicit_family_section_anchor_may_establish_family_scope"])
        self.assertFalse(bridge["generic_family_header_may_establish_commercial_identity"])
        self.assertFalse(bridge["fuzzy_target_matching_allowed"])
        self.assertFalse(bridge["substring_identity_equivalence_allowed"])
        self.assertFalse(bridge["missing_intermediate_device_expression_blocks_bridge"])
        self.assertEqual(
            bridge["required_claims"],
            ["TARGET_EXACT_IDENTITY", "RM_TARGET_MEMBERSHIP", "KL25_FAMILY_SCOPE"],
        )
        self.assertEqual(bridge["optional_observation_claims"], ["TARGET_DEVICE_EXPRESSION"])

    def test_missing_device_expression_must_not_be_synthesized(self):
        contract = json.loads((HERE / "applicability-contract.json").read_text(encoding="utf-8"))
        claim = contract["candidate_claims"]["TARGET_DEVICE_EXPRESSION"]
        self.assertTrue(claim["optional"])
        self.assertEqual(claim["absence_policy"], "DO_NOT_INFER_OR_SYNTHESIZE")
        self.assertEqual(claim["terms"], ["MKL25Z128"])

    def test_family_and_module_claims_are_section_bounded(self):
        contract = json.loads((HERE / "applicability-contract.json").read_text(encoding="utf-8"))
        claims = contract["candidate_claims"]
        self.assertEqual(claims["KL25_FAMILY_SCOPE"]["page_ranges"]["nxp_kl25_rm_rev3"], [[38, 44]])
        self.assertEqual(
            claims["FTFA_MODULE_PRESENCE"]["page_ranges"]["nxp_kl25_rm_rev3"],
            [[72, 74], [419, 456]],
        )
        self.assertEqual(claims["MDM_AP_PRESENCE"]["page_ranges"]["nxp_kl25_rm_rev3"], [[149, 157]])
        self.assertTrue(
            contract["unit_binding_policy"]["document_wide_header_hits_are_not_applicability_evidence"]
        )

    def test_all_reviewed_units_have_explicit_applicability_requirements(self):
        definitions = json.loads(
            (HERE / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8")
        )
        contract = json.loads((HERE / "applicability-contract.json").read_text(encoding="utf-8"))
        self.assertEqual(definitions["status"], "admitted_evidence_unit_catalog")
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
        self.assertIn(
            "FTFA_MODULE_PRESENCE",
            contract["unit_requirements"]["nxp-kl25-program-longword-v0"],
        )
        self.assertIn(
            "MDM_AP_PRESENCE",
            contract["unit_requirements"]["nxp-kl25-swd-mdm-ap-v0"],
        )


if __name__ == "__main__":
    unittest.main()

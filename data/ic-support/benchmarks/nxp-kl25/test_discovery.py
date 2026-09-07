from __future__ import annotations

import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent


class KL25DiscoveryContractTest(unittest.TestCase):
    def test_discovery_is_cross_vendor_and_fail_closed(self):
        contract = json.loads((HERE / "discovery-contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["target"], "MKL25Z128VLK4")
        self.assertTrue(contract["cross_vendor_guards"]["vendor_native_terms_are_preserved"])
        self.assertTrue(contract["cross_vendor_guards"]["candidate_hits_are_not_admitted_evidence"])
        self.assertFalse(contract["admission"]["evidence_pack"])
        self.assertFalse(contract["admission"]["semantic_extraction"])
        self.assertFalse(contract["admission"]["production"])
        self.assertFalse(contract["admission"]["destructive_security_operation"])

    def test_nxp_native_command_model_is_explicit(self):
        contract = json.loads((HERE / "discovery-contract.json").read_text(encoding="utf-8"))
        joined = " ".join(term for terms in contract["categories"].values() for term in terms)
        for term in ["FTFA", "FCCOB", "Program Longword", "Erase Flash Sector", "FSTAT", "FSEC", "MDM-AP"]:
            self.assertIn(term, joined)

    def test_device_identity_rejects_generic_family_headers(self):
        contract = json.loads((HERE / "discovery-contract.json").read_text(encoding="utf-8"))
        identity_terms = contract["categories"]["DEVICE_IDENTITY"]
        policy = contract["category_policies"]["DEVICE_IDENTITY"]
        self.assertIn("MKL25Z128VLK4", identity_terms)
        self.assertIn("MKL25Z128", identity_terms)
        for generic in ["Kinetis KL25", "KL25 Sub-Family"]:
            self.assertNotIn(generic, identity_terms)
            self.assertIn(generic, policy["forbidden_generic_family_headers"])
        self.assertTrue(contract["cross_vendor_guards"]["generic_family_header_is_not_device_identity_evidence"])

    def test_stm32_register_model_is_only_a_forbidden_assumption(self):
        contract = json.loads((HERE / "discovery-contract.json").read_text(encoding="utf-8"))
        forbidden = contract["cross_vendor_guards"]["forbidden_stm32_assumptions"]
        self.assertEqual(forbidden, ["KEYR", "FLASH_CR", "PER", "MER", "PG"])
        category_terms = [term for terms in contract["categories"].values() for term in terms]
        for term in forbidden:
            self.assertNotIn(term, category_terms)

    def test_preprocessing_is_deterministic(self):
        contract = json.loads((HERE / "discovery-contract.json").read_text(encoding="utf-8"))
        self.assertEqual(contract["preprocessing"]["tool"], "pdftotext")
        self.assertEqual(contract["preprocessing"]["arguments"], ["-layout", "-enc", "UTF-8"])
        self.assertEqual(contract["preprocessing"]["page_boundary"], "form_feed")


if __name__ == "__main__":
    unittest.main()

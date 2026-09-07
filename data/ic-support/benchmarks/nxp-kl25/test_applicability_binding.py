from __future__ import annotations

import copy
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location(
    "derive_applicability_binding", HERE / "derive_applicability_binding.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(MODULE)


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


class KL25ApplicabilityBindingTest(unittest.TestCase):
    def setUp(self):
        self.contract = load("applicability-contract.json")
        self.definitions = load("reviewed-evidence-unit-definitions.json")
        self.evidence_lock = load("retained-applicability-evidence-lock.json")
        self.reviewed = load("reviewed-applicability-claims.json")
        self.evidence_lock_path = HERE / "retained-applicability-evidence-lock.json"

    def derive(self, reviewed=None, evidence_lock=None):
        return MODULE.derive(
            copy.deepcopy(self.contract),
            copy.deepcopy(self.definitions),
            copy.deepcopy(evidence_lock if evidence_lock is not None else self.evidence_lock),
            copy.deepcopy(reviewed if reviewed is not None else self.reviewed),
            self.evidence_lock_path,
        )

    def test_retained_binding_admits_only_scope_catalog_and_binding(self):
        result = self.derive()
        self.assertEqual(result["scope_bridge"]["status"], "BOUND")
        self.assertTrue(result["applicability_exclusions_reviewed"])
        self.assertEqual({item["status"] for item in result["unit_bindings"].values()}, {"BOUND"})
        self.assertTrue(result["admission"]["scope_bridge"])
        self.assertTrue(result["admission"]["evidence_unit_catalog"])
        self.assertTrue(result["admission"]["applicability_binding"])
        for denied in [
            "evidence_pack",
            "semantic_extraction",
            "canonical_dataset",
            "hil",
            "production",
            "destructive_security_operation",
        ]:
            self.assertFalse(result["admission"][denied])

    def test_missing_exact_identity_makes_scope_and_all_units_unknown(self):
        reviewed = copy.deepcopy(self.reviewed)
        reviewed["claims"]["TARGET_EXACT_IDENTITY"]["review_status"] = "PENDING"
        reviewed["claims"]["TARGET_EXACT_IDENTITY"]["evidence"] = []
        result = self.derive(reviewed=reviewed)
        self.assertEqual(result["scope_bridge"]["status"], "UNKNOWN")
        self.assertEqual({item["status"] for item in result["unit_bindings"].values()}, {"UNKNOWN"})
        self.assertFalse(result["admission"]["applicability_binding"])

    def test_missing_ftfa_only_blocks_ftfa_dependent_units(self):
        reviewed = copy.deepcopy(self.reviewed)
        reviewed["claims"]["FTFA_MODULE_PRESENCE"]["review_status"] = "PENDING"
        reviewed["claims"]["FTFA_MODULE_PRESENCE"]["evidence"] = []
        result = self.derive(reviewed=reviewed)
        for unit_id in [
            "nxp-kl25-ftfa-register-model-v0",
            "nxp-kl25-ftfa-command-sequencing-v0",
            "nxp-kl25-program-longword-v0",
            "nxp-kl25-erase-sector-v0",
            "nxp-kl25-erase-all-blocks-v0",
            "nxp-kl25-flash-security-v0",
        ]:
            self.assertEqual(result["unit_bindings"][unit_id]["status"], "UNKNOWN")
        self.assertEqual(result["unit_bindings"]["nxp-kl25-swd-mdm-ap-v0"]["status"], "BOUND")
        self.assertEqual(
            result["unit_bindings"]["nxp-kl25-debug-security-interaction-v0"]["status"],
            "BOUND",
        )
        self.assertFalse(result["admission"]["applicability_binding"])

    def test_missing_mdm_ap_blocks_only_mdm_ap_dependent_units(self):
        reviewed = copy.deepcopy(self.reviewed)
        reviewed["claims"]["MDM_AP_PRESENCE"]["review_status"] = "PENDING"
        reviewed["claims"]["MDM_AP_PRESENCE"]["evidence"] = []
        result = self.derive(reviewed=reviewed)
        self.assertEqual(result["unit_bindings"]["nxp-kl25-swd-mdm-ap-v0"]["status"], "UNKNOWN")
        self.assertEqual(
            result["unit_bindings"]["nxp-kl25-debug-security-interaction-v0"]["status"],
            "UNKNOWN",
        )
        self.assertEqual(result["unit_bindings"]["nxp-kl25-program-longword-v0"]["status"], "BOUND")
        self.assertFalse(result["admission"]["applicability_binding"])

    def test_unreviewed_exclusions_block_every_unit_binding(self):
        reviewed = copy.deepcopy(self.reviewed)
        reviewed["applicability_exclusions"]["review_status"] = "PENDING"
        result = self.derive(reviewed=reviewed)
        self.assertEqual(result["scope_bridge"]["status"], "BOUND")
        self.assertEqual({item["status"] for item in result["unit_bindings"].values()}, {"UNKNOWN"})
        self.assertFalse(result["admission"]["applicability_binding"])

    def test_mutated_reviewed_page_hash_is_rejected(self):
        reviewed = copy.deepcopy(self.reviewed)
        reviewed["claims"]["FTFA_MODULE_PRESENCE"]["evidence"][0]["page_text_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "not in retained candidate evidence"):
            self.derive(reviewed=reviewed)

    def test_evidence_lock_mutation_is_rejected_by_retained_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "retained-applicability-evidence-lock.json"
            evidence_lock = copy.deepcopy(self.evidence_lock)
            evidence_lock["claims"]["KL25_FAMILY_SCOPE"]["candidate_count"] += 1
            path.write_text(json.dumps(evidence_lock, indent=2) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "evidence-lock SHA-256 mismatch"):
                MODULE.derive(
                    copy.deepcopy(self.contract),
                    copy.deepcopy(self.definitions),
                    evidence_lock,
                    copy.deepcopy(self.reviewed),
                    path,
                )

    def test_missing_intermediate_device_expression_does_not_block_binding(self):
        self.assertEqual(
            self.evidence_lock["claims"]["TARGET_DEVICE_EXPRESSION"]["candidate_count"],
            0,
        )
        result = self.derive()
        self.assertEqual(result["scope_bridge"]["status"], "BOUND")
        self.assertFalse(result["scope_bridge"]["intermediate_device_expression_required"])
        self.assertFalse(result["scope_bridge"]["fuzzy_identity_matching_used"])

    def test_synthesized_intermediate_device_expression_is_rejected(self):
        reviewed = copy.deepcopy(self.reviewed)
        reviewed["claims"]["TARGET_DEVICE_EXPRESSION"] = {
            "review_status": "REVIEWED",
            "rationale": "synthetic",
            "evidence": self.reviewed["claims"]["TARGET_EXACT_IDENTITY"]["evidence"][:1],
        }
        with self.assertRaises(ValueError):
            self.derive(reviewed=reviewed)

    def test_shared_rm_membership_alone_cannot_bind(self):
        reviewed = copy.deepcopy(self.reviewed)
        reviewed["claims"]["KL25_FAMILY_SCOPE"]["review_status"] = "PENDING"
        reviewed["claims"]["KL25_FAMILY_SCOPE"]["evidence"] = []
        result = self.derive(reviewed=reviewed)
        self.assertEqual(result["scope_bridge"]["status"], "UNKNOWN")
        self.assertFalse(result["admission"]["applicability_binding"])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
import json
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILDER_PATH = HERE / "build_evidence_pack.py"


def load_builder():
    spec = importlib.util.spec_from_file_location("nxp_kl25_pre_ai_builder", BUILDER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KL25PreAICITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_builder()
        cls.contract = json.loads((HERE / "evidence-pack-contract.json").read_text(encoding="utf-8"))
        cls.definitions = json.loads((HERE / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8"))
        cls.binding = json.loads((HERE / "applicability-binding.json").read_text(encoding="utf-8"))
        cls.source_lock = json.loads((HERE / "source-lock.json").read_text(encoding="utf-8"))
        max_page = max(unit["pdf_page_range"][1] for unit in cls.definitions["units"])
        cls.pages_by_source = {
            "nxp_kl25_rm_rev3": [
                f"Synthetic KL25 pre-AI page {page_number}\nFTFA FCCOB FSTAT SWD MDM-AP security"
                for page_number in range(1, max_page + 1)
            ]
        }

    def build_pre_ai(self):
        packs, bundle = self.builder.build_pack_set(
            contract=copy.deepcopy(self.contract),
            definitions=copy.deepcopy(self.definitions),
            binding=copy.deepcopy(self.binding),
            source_lock=copy.deepcopy(self.source_lock),
            pages_by_source=copy.deepcopy(self.pages_by_source),
            builder_sha256="c" * 64,
        )
        evidence_text = {
            pack_id: self.builder.materialize_evidence_text(pack, self.pages_by_source)
            for pack_id, pack in packs.items()
        }
        evidence_sha256 = {
            pack_id: self.builder.sha256_text(text)
            for pack_id, text in evidence_text.items()
        }
        manifest = self.builder.build_pre_ai_manifest(
            bundle=bundle,
            packs=packs,
            evidence_sha256=evidence_sha256,
        )
        return packs, bundle, evidence_text, manifest

    def test_ci_contract_stops_immediately_before_model_inference(self):
        packs, bundle, evidence_text, manifest = self.build_pre_ai()
        self.builder.validate_pre_ai_manifest(
            manifest,
            bundle=bundle,
            packs=packs,
            evidence_text=evidence_text,
        )
        policy = self.contract["pre_ai_ci"]
        self.assertTrue(policy["repository_ci_must_not_require_model_inference"])
        self.assertTrue(policy["repository_ci_must_test_pack_construction"])
        self.assertTrue(policy["repository_ci_must_test_dependency_closure"])
        self.assertTrue(policy["repository_ci_must_test_target_bundle"])
        self.assertTrue(policy["repository_ci_must_test_content_digest_validation"])
        self.assertTrue(policy["repository_ci_must_test_context_assembly"])
        self.assertFalse(manifest["execution"]["model_inference_required_in_repository_ci"])
        self.assertFalse(manifest["execution"]["semantic_extraction_admission"])

    def test_context_assembly_is_deterministic_and_contains_only_pre_ai_authority(self):
        packs, _, evidence_text, manifest = self.build_pre_ai()
        context_a = self.builder.assemble_model_context(
            manifest,
            packs=packs,
            evidence_text=evidence_text,
        )
        context_b = self.builder.assemble_model_context(
            manifest,
            packs=packs,
            evidence_text=evidence_text,
        )
        self.assertEqual(context_a, context_b)
        self.assertIn("TARGET: MKL25Z128VLK4", context_a)
        self.assertIn("manufacturer evidence only", context_a)
        self.assertNotIn("ground-truth", context_a.lower())
        self.assertNotIn("production profile", context_a.lower())
        self.assertNotIn("ollama_url", context_a.lower())
        self.assertNotIn("api_key", context_a.lower())

    def test_evidence_payload_mutation_is_rejected_before_ai(self):
        packs, bundle, evidence_text, manifest = self.build_pre_ai()
        pack_id = next(iter(sorted(evidence_text)))
        evidence_text[pack_id] += "mutated\n"
        with self.assertRaises(self.builder.KL25EvidencePackError):
            self.builder.validate_pre_ai_manifest(
                manifest,
                bundle=bundle,
                packs=packs,
                evidence_text=evidence_text,
            )

    def test_pack_digest_mutation_is_rejected_before_ai(self):
        packs, bundle, evidence_text, manifest = self.build_pre_ai()
        manifest = copy.deepcopy(manifest)
        manifest["packs"][0]["pack_digest"] = "0" * 64
        manifest["manifest_digest"] = self.builder.canonical_sha256(
            {key: value for key, value in manifest.items() if key != "manifest_digest"}
        )
        with self.assertRaises(self.builder.KL25EvidencePackError):
            self.builder.validate_pre_ai_manifest(
                manifest,
                bundle=bundle,
                packs=packs,
                evidence_text=evidence_text,
            )

    def test_pre_ai_manifest_forbids_ai_ownership_of_deterministic_governance(self):
        _, _, _, manifest = self.build_pre_ai()
        boundary = manifest["authority_boundary"]
        self.assertTrue(boundary["input_is_manufacturer_evidence_only"])
        self.assertFalse(boundary["canonical_ground_truth_allowed"])
        self.assertFalse(boundary["production_profile_allowed"])
        self.assertFalse(boundary["ai_may_change_applicability_binding"])
        self.assertFalse(boundary["ai_may_remove_deterministic_evidence"])


if __name__ == "__main__":
    unittest.main()

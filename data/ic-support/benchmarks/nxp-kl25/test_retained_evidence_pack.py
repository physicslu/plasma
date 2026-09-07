#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import json
import re
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
BUILDER_PATH = HERE / "build_evidence_pack.py"
HEX64 = re.compile(r"^[0-9a-f]{64}$")
HEX40 = re.compile(r"^[0-9a-f]{40}$")


def load_builder():
    spec = importlib.util.spec_from_file_location("nxp_kl25_retained_pack_builder", BUILDER_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class KL25RetainedEvidencePackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_builder()
        cls.retained = json.loads((HERE / "retained-evidence-pack-build.json").read_text(encoding="utf-8"))
        cls.contract = json.loads((HERE / "evidence-pack-contract.json").read_text(encoding="utf-8"))
        cls.definitions = json.loads((HERE / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8"))
        cls.binding = json.loads((HERE / "applicability-binding.json").read_text(encoding="utf-8"))
        cls.source_lock = json.loads((HERE / "source-lock.json").read_text(encoding="utf-8"))

    def test_retained_live_provenance_is_bound_to_current_deterministic_inputs(self):
        retained = self.retained
        self.assertEqual(retained["target"], "MKL25Z128VLK4")
        self.assertEqual(
            retained["evidence_pack_contract"]["digest"],
            self.builder.canonical_sha256(self.contract),
        )
        self.assertEqual(
            retained["definition_set"]["digest"],
            self.builder.canonical_sha256(self.definitions),
        )
        self.assertEqual(
            retained["applicability_binding"]["digest"],
            self.builder.canonical_sha256(self.binding),
        )
        self.assertEqual(
            retained["builder"]["sha256"],
            self.builder.sha256_file(BUILDER_PATH),
        )

    def test_retained_source_fingerprint_matches_source_lock(self):
        source = next(
            item for item in self.source_lock["sources"]
            if item["source_id"] == self.retained["source_lock"]["source_id"]
        )
        self.assertEqual(self.retained["source_lock"]["source_lock_id"], self.source_lock["source_lock_id"])
        self.assertEqual(self.retained["source_lock"]["algorithm"], source["integrity"]["algorithm"])
        self.assertEqual(self.retained["source_lock"]["digest"], source["integrity"]["digest"])
        self.assertEqual(self.retained["source_lock"]["byte_length"], source["integrity"]["byte_length"])

    def test_retained_pack_and_evidence_sets_are_complete(self):
        unit_ids = {item["unit_id"] for item in self.definitions["units"]}
        expected_pack_ids = {f"{unit_id}-pack-v0" for unit_id in unit_ids}
        pack_digests = self.retained["target_bundle"]["pack_digests"]
        evidence_digests = self.retained["pre_ai"]["evidence_sha256"]
        self.assertEqual(self.retained["target_bundle"]["pack_count"], 8)
        self.assertEqual(set(pack_digests), expected_pack_ids)
        self.assertEqual(set(evidence_digests), expected_pack_ids)
        for digest in [*pack_digests.values(), *evidence_digests.values()]:
            self.assertRegex(digest, HEX64)
        self.assertRegex(self.retained["target_bundle"]["bundle_digest"], HEX64)
        self.assertRegex(self.retained["pre_ai"]["manifest_digest"], HEX64)
        self.assertRegex(self.retained["pre_ai"]["model_context_sha256"], HEX64)

    def test_live_run_retained_no_manufacturer_text_or_model_inference(self):
        live = self.retained["live_source_validation"]
        self.assertIsInstance(live["workflow_run_id"], int)
        self.assertIsInstance(live["artifact_id"], int)
        self.assertTrue(live["artifact_digest"].startswith("sha256:"))
        self.assertRegex(live["artifact_digest"].split(":", 1)[1], HEX64)
        self.assertRegex(live["generation_head"], HEX40)
        self.assertFalse(live["manufacturer_text_retained"])
        self.assertFalse(live["semantic_extraction_executed"])
        self.assertTrue(self.retained["pre_ai"]["repository_ci_validates_through_context_assembly"])
        self.assertFalse(self.retained["pre_ai"]["model_inference_required_in_repository_ci"])

    def test_gate3_admission_stops_before_semantic_extraction(self):
        self.assertTrue(self.contract["admission"]["evidence_pack"])
        self.assertTrue(self.contract["admission"]["pre_ai_ci"])
        self.assertTrue(self.retained["admission"]["evidence_pack"])
        self.assertTrue(self.retained["admission"]["pre_ai_ci"])
        for key in [
            "semantic_extraction",
            "canonical_dataset",
            "hil",
            "production",
            "destructive_security_operation",
        ]:
            self.assertFalse(self.contract["admission"][key])
            self.assertFalse(self.retained["admission"][key])


if __name__ == "__main__":
    unittest.main()

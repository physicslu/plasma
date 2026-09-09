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


def load(name: str) -> dict:
    return json.loads((HERE / name).read_text(encoding="utf-8"))


class KL25RetainedEvidencePackTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.builder = load_builder()
        cls.retained_v0 = load("retained-evidence-pack-build.json")
        cls.retained_v1 = load("retained-evidence-pack-build-v1.json")
        cls.contract = load("evidence-pack-contract.json")
        # Gate 5.6 changes the active Program Longword boundary. Historical
        # retained proof remains bound to archived v0 inputs; the new proof is
        # independently bound to the corrected active inputs.
        cls.definitions_v0 = load("reviewed-evidence-unit-definitions-v0.json")
        cls.binding_v0 = load("applicability-binding-v0.json")
        cls.definitions_v1 = load("reviewed-evidence-unit-definitions.json")
        cls.binding_v1 = load("applicability-binding.json")
        cls.source_lock = load("source-lock.json")

    def assert_retained_identity(self, retained: dict, definitions: dict, binding: dict) -> None:
        self.assertEqual(retained["target"], "MKL25Z128VLK4")
        self.assertEqual(
            retained["evidence_pack_contract"]["digest"],
            self.builder.canonical_sha256(self.contract),
        )
        self.assertEqual(
            retained["definition_set"]["digest"],
            self.builder.canonical_sha256(definitions),
        )
        self.assertEqual(
            retained["applicability_binding"]["digest"],
            self.builder.canonical_sha256(binding),
        )
        self.assertEqual(
            retained["builder"]["sha256"],
            self.builder.sha256_file(BUILDER_PATH),
        )

    def assert_source_fingerprint(self, retained: dict) -> None:
        source = next(
            item for item in self.source_lock["sources"]
            if item["source_id"] == retained["source_lock"]["source_id"]
        )
        self.assertEqual(retained["source_lock"]["source_lock_id"], self.source_lock["source_lock_id"])
        self.assertEqual(retained["source_lock"]["algorithm"], source["integrity"]["algorithm"])
        self.assertEqual(retained["source_lock"]["digest"], source["integrity"]["digest"])
        self.assertEqual(retained["source_lock"]["byte_length"], source["integrity"]["byte_length"])

    def assert_pack_sets(self, retained: dict, definitions: dict) -> None:
        unit_ids = {item["unit_id"] for item in definitions["units"]}
        expected_pack_ids = {f"{unit_id}-pack-v0" for unit_id in unit_ids}
        pack_digests = retained["target_bundle"]["pack_digests"]
        evidence_digests = retained["pre_ai"]["evidence_sha256"]
        self.assertEqual(retained["target_bundle"]["pack_count"], 8)
        self.assertEqual(set(pack_digests), expected_pack_ids)
        self.assertEqual(set(evidence_digests), expected_pack_ids)
        for digest in [*pack_digests.values(), *evidence_digests.values()]:
            self.assertRegex(digest, HEX64)
        self.assertRegex(retained["target_bundle"]["bundle_digest"], HEX64)
        self.assertRegex(retained["pre_ai"]["manifest_digest"], HEX64)
        self.assertRegex(retained["pre_ai"]["model_context_sha256"], HEX64)

    def assert_non_ai_retention(self, retained: dict) -> None:
        live = retained["live_source_validation"]
        self.assertIsInstance(live["workflow_run_id"], int)
        self.assertIsInstance(live["artifact_id"], int)
        self.assertTrue(live["artifact_digest"].startswith("sha256:"))
        self.assertRegex(live["artifact_digest"].split(":", 1)[1], HEX64)
        self.assertRegex(live["generation_head"], HEX40)
        self.assertFalse(live["manufacturer_text_retained"])
        self.assertFalse(live["semantic_extraction_executed"])
        self.assertTrue(retained["pre_ai"]["repository_ci_validates_through_context_assembly"])
        self.assertFalse(retained["pre_ai"]["model_inference_required_in_repository_ci"])
        for key in [
            "semantic_extraction",
            "canonical_dataset",
            "hil",
            "production",
            "destructive_security_operation",
        ]:
            self.assertFalse(retained["admission"][key])

    def test_retained_v0_is_bound_to_historical_inputs(self):
        self.assert_retained_identity(self.retained_v0, self.definitions_v0, self.binding_v0)
        self.assert_source_fingerprint(self.retained_v0)
        self.assert_pack_sets(self.retained_v0, self.definitions_v0)
        self.assert_non_ai_retention(self.retained_v0)

    def test_retained_v1_is_bound_to_corrected_active_inputs(self):
        self.assertEqual(
            self.retained_v1["evidence_boundary_release_id"],
            "nxp-kl25-evidence-boundary-release-v1",
        )
        self.assert_retained_identity(self.retained_v1, self.definitions_v1, self.binding_v1)
        self.assert_source_fingerprint(self.retained_v1)
        self.assert_pack_sets(self.retained_v1, self.definitions_v1)
        self.assert_non_ai_retention(self.retained_v1)
        live = self.retained_v1["live_source_validation"]
        self.assertTrue(live["program_longword_p446_validated"])
        self.assertFalse(live["program_longword_p447_admitted"])

    def test_gate56_changes_bundle_and_only_program_longword_evidence_payload(self):
        self.assertNotEqual(
            self.retained_v0["target_bundle"]["bundle_digest"],
            self.retained_v1["target_bundle"]["bundle_digest"],
        )
        self.assertNotEqual(
            self.retained_v0["pre_ai"]["manifest_digest"],
            self.retained_v1["pre_ai"]["manifest_digest"],
        )
        program_pack = "nxp-kl25-program-longword-v0-pack-v0"
        for pack_id, old_digest in self.retained_v0["pre_ai"]["evidence_sha256"].items():
            new_digest = self.retained_v1["pre_ai"]["evidence_sha256"][pack_id]
            if pack_id == program_pack:
                self.assertNotEqual(old_digest, new_digest)
            else:
                self.assertEqual(old_digest, new_digest)
        # Pack digests all change because every pack binds the active definition
        # and applicability-binding digests even when its manufacturer text is unchanged.
        self.assertTrue(all(
            self.retained_v0["target_bundle"]["pack_digests"][pack_id]
            != self.retained_v1["target_bundle"]["pack_digests"][pack_id]
            for pack_id in self.retained_v0["target_bundle"]["pack_digests"]
        ))

    def test_gate3_and_gate56_admissions_stop_before_semantic_extraction(self):
        self.assertTrue(self.contract["admission"]["evidence_pack"])
        self.assertTrue(self.contract["admission"]["pre_ai_ci"])
        for retained in (self.retained_v0, self.retained_v1):
            self.assertTrue(retained["admission"]["evidence_pack"])
            self.assertTrue(retained["admission"]["pre_ai_ci"])
            for key in [
                "semantic_extraction",
                "canonical_dataset",
                "hil",
                "production",
                "destructive_security_operation",
            ]:
                self.assertFalse(self.contract["admission"][key])
                self.assertFalse(retained["admission"][key])


if __name__ == "__main__":
    unittest.main()

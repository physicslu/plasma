#!/usr/bin/env python3
"""Gate 5.7A primary-scoped bounded extraction regressions; model/network free."""
from __future__ import annotations

import copy
import json
import socket
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import bounded_extraction as bounded
import build_evidence_pack as builder
import qualify_bounded_run as qualification
import run_live_bounded_qualification as live
import test_semantic_runner as fixtures
from test_live_model_qualification import UNIT_FIXTURES

HERE = Path(__file__).resolve().parent
PRIMARY_CONTRACT_PATH = HERE / "live-bounded-primary-qualification-contract.json"
LEGACY_CONTRACT_PATH = HERE / "live-bounded-qualification-contract.json"


class Gate57APrimaryScopeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.KL25SemanticRunnerTest.setUpClass()
        cls.production_contract = json.loads(PRIMARY_CONTRACT_PATH.read_text(encoding="utf-8"))
        cls.legacy_contract = json.loads(LEGACY_CONTRACT_PATH.read_text(encoding="utf-8"))

    def setUp(self):
        self.fixture = fixtures.KL25SemanticRunnerTest()
        self.packs, self.bundle, self.evidence, self.manifest = self.fixture.build_inputs()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.input_dir = root / "pre-ai-boundary-v1"
        self.output_dir = root / "bounded-primary-run"
        (self.input_dir / "packs").mkdir(parents=True)
        (self.input_dir / "evidence").mkdir()
        (self.input_dir / "pre-ai-input.json").write_text(json.dumps(self.manifest), encoding="utf-8")
        (self.input_dir / "target-bundle.json").write_text(json.dumps(self.bundle), encoding="utf-8")
        for pack_id, pack in self.packs.items():
            (self.input_dir / "packs" / f"{pack_id}.json").write_text(json.dumps(pack), encoding="utf-8")
            (self.input_dir / "evidence" / f"{pack_id}.txt").write_text(self.evidence[pack_id], encoding="utf-8")

        self.contract = copy.deepcopy(self.production_contract)
        self.contract["required_input"]["bundle_digest"] = self.manifest["bundle_digest"]
        self.contract["required_input"]["pre_ai_manifest_digest"] = self.manifest["manifest_digest"]
        self.contract["required_input"]["bounded_contract_digest"] = builder.canonical_sha256(bounded.policy())
        self.calls: list[dict] = []
        self.identity_calls = 0
        for name in ("socket", "create_connection"):
            guard = patch.object(socket, name, side_effect=AssertionError("network forbidden in Gate 5.7A CI"))
            guard.start()
            self.addCleanup(guard.stop)

    def identity(self, **kwargs):
        self.identity_calls += 1
        self.assertEqual(kwargs["ollama_url"], "http://127.0.0.1:11434")
        self.assertEqual(kwargs["model_id"], "qwen3.8:27b-mlx")
        return {
            "ollama_url_policy": "loopback_only",
            "ollama_version": "0.33.3",
            "model_id": "qwen3.8:27b-mlx",
            "model_digest": "sha256:" + "a" * 64,
            "model_size_bytes": 1,
            "model_modified_at": "synthetic",
        }

    @staticmethod
    def primary_ref(pack):
        refs = sorted(bounded._primary_page_refs(pack))
        return refs[0]

    @staticmethod
    def dependency_ref(pack):
        primary = bounded._primary_page_refs(pack)
        dependency = sorted(bounded.semantic._allowed_page_refs(pack) - primary)
        if not dependency:
            raise AssertionError(f"fixture has no dependency page: {pack['primary_unit_id']}")
        return dependency[0]

    def pack_for_unit(self, unit_id):
        return next(pack for pack in self.packs.values() if pack["primary_unit_id"] == unit_id)

    def transport(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        self.assertEqual(kwargs["runtime_label"], "kl25-live-bounded-primary-scoped-qualification")
        self.assertEqual(kwargs["options"]["ollama_url"], "http://127.0.0.1:11434")
        schema = kwargs["options"]["format_schema"]
        unit_id = schema["properties"]["unit_results"]["items"]["properties"]["primary_unit_id"]["enum"][0]
        pack = self.pack_for_unit(unit_id)
        source, page = self.primary_ref(pack)
        raw = {
            "schema_version": "0.1.0",
            "target": "MKL25Z128VLK4",
            "unit_results": [{
                "primary_unit_id": unit_id,
                "state": "FACTS",
                "facts": [{
                    "fact_id": f"gate57a-{unit_id}",
                    "kind": "CONSTRAINT",
                    "statement": UNIT_FIXTURES[unit_id][2],
                    "evidence": [{"source_id": source, "pdf_page_number": page}],
                }],
            }],
        }
        return {
            "raw_text": json.dumps(raw),
            "response_model": "qwen3.8:27b-mlx",
            "done": True,
            "done_reason": "stop",
            "usage": {"input_tokens": 2500, "generation_tokens": 300},
            "timing": {"wall_time_ms": 1.0},
        }

    def execute(self, transport=None):
        return live.execute_live_bounded_qualification(
            input_dir=self.input_dir,
            output_dir=self.output_dir,
            ollama_url="http://127.0.0.1:11434",
            contract_override=copy.deepcopy(self.contract),
            contract_path=PRIMARY_CONTRACT_PATH,
            identity_query=self.identity,
            transport=transport or self.transport,
        )

    def test_contract_changes_scope_not_evidence_or_generation_envelope(self):
        qualification.validate_contract(self.production_contract)
        qualification.validate_contract(self.legacy_contract)
        current = self.production_contract
        legacy = self.legacy_contract
        self.assertEqual(current["required_input"], legacy["required_input"])
        self.assertEqual(current["live_runtime"]["generation"], legacy["live_runtime"]["generation"])
        self.assertEqual(current["live_runtime"]["generation"]["num_ctx"], 65536)
        self.assertEqual(current["live_runtime"]["generation"]["max_tokens"], 8192)
        self.assertEqual(current["live_runtime"]["automatic_retries"], 0)
        self.assertEqual(current["live_runtime"]["semantic_scope"], bounded.PRIMARY_SCOPE_POLICY)
        self.assertNotIn("semantic_scope", legacy["live_runtime"])

    def test_primary_only_facts_reach_ready_for_review(self):
        result, provenance, report = self.execute()
        self.assertEqual(self.identity_calls, 1)
        self.assertEqual(len(self.calls), 8)
        self.assertEqual(result["aggregate"]["status"], "INTEGRITY_PASS")
        self.assertEqual(report["status"], "READY_FOR_REVIEW")
        self.assertEqual(report["semantic_screening"]["status"], "PASS")
        self.assertEqual(provenance["execution"]["semantic_scope"], bounded.PRIMARY_SCOPE_POLICY)
        self.assertEqual(result["aggregate"]["semantic_scope"], bounded.PRIMARY_SCOPE_POLICY)
        self.assertTrue(all(child["status"] == "success" for child in result["children"]))

    def test_primary_plus_dependency_citation_is_allowed(self):
        debug_unit = "nxp-kl25-debug-security-interaction-v0"

        def transport(**kwargs):
            response = self.transport(**kwargs)
            parsed = json.loads(response["raw_text"])
            unit = parsed["unit_results"][0]
            if unit["primary_unit_id"] == debug_unit:
                pack = self.pack_for_unit(debug_unit)
                source, page = self.dependency_ref(pack)
                unit["facts"][0]["evidence"].append({"source_id": source, "pdf_page_number": page})
                response["raw_text"] = json.dumps(parsed)
            return response

        result, _, report = self.execute(transport=transport)
        self.assertEqual(result["aggregate"]["status"], "INTEGRITY_PASS")
        self.assertEqual(report["status"], "READY_FOR_REVIEW")

    def test_dependency_only_fact_is_rejected_before_screening(self):
        debug_unit = "nxp-kl25-debug-security-interaction-v0"

        def transport(**kwargs):
            response = self.transport(**kwargs)
            parsed = json.loads(response["raw_text"])
            unit = parsed["unit_results"][0]
            if unit["primary_unit_id"] == debug_unit:
                pack = self.pack_for_unit(debug_unit)
                source, page = self.dependency_ref(pack)
                unit["facts"][0]["evidence"] = [{"source_id": source, "pdf_page_number": page}]
                response["raw_text"] = json.dumps(parsed)
            return response

        result, _, report = self.execute(transport=transport)
        self.assertEqual(result["aggregate"]["status"], "REJECTED_INTEGRITY")
        self.assertEqual(report["status"], "REJECTED_INTEGRITY")
        self.assertEqual(report["semantic_screening"]["status"], "NOT_REACHED")
        failed = next(child for child in result["children"] if child["status"] == "error")
        self.assertEqual(failed["binding"]["primary_unit_id"], debug_unit)
        self.assertEqual(failed["error"]["class"], "bounded_integrity_error")
        self.assertIn("requires at least one PRIMARY citation", failed["error"]["message"])

    def test_provider_schema_requires_primary_citation_per_fact(self):
        self.execute()
        debug_unit = "nxp-kl25-debug-security-interaction-v0"
        call = next(
            item for item in self.calls
            if item["options"]["format_schema"]["properties"]["unit_results"]["items"]["properties"]["primary_unit_id"]["enum"][0]
            == debug_unit
        )
        evidence_schema = call["options"]["format_schema"]["properties"]["unit_results"]["items"]["properties"]["facts"]["items"]["properties"]["evidence"]
        self.assertIn("contains", evidence_schema)
        pack = self.pack_for_unit(debug_unit)
        primary = bounded._primary_page_refs(pack)
        contains_pairs = {
            (item["properties"]["source_id"]["enum"][0], item["properties"]["pdf_page_number"]["enum"][0])
            for item in evidence_schema["contains"]["anyOf"]
        }
        self.assertEqual(contains_pairs, primary)
        self.assertIn("PRIMARY-SCOPED FACT GENERATION POLICY", call["prompt"])
        self.assertIn("Dependency pages are SUPPORTING CONTEXT ONLY", call["prompt"])

    def test_program_longword_gate56_boundary_is_unchanged(self):
        self.execute()
        call = next(
            item for item in self.calls
            if item["options"]["format_schema"]["properties"]["unit_results"]["items"]["properties"]["primary_unit_id"]["enum"][0]
            == "nxp-kl25-program-longword-v0"
        )
        evidence_schema = call["options"]["format_schema"]["properties"]["unit_results"]["items"]["properties"]["facts"]["items"]["properties"]["evidence"]
        all_pairs = {
            (item["properties"]["source_id"]["enum"][0], item["properties"]["pdf_page_number"]["enum"][0])
            for item in evidence_schema["items"]["anyOf"]
        }
        self.assertIn(("nxp_kl25_rm_rev3", 446), all_pairs)
        self.assertNotIn(("nxp_kl25_rm_rev3", 447), all_pairs)


if __name__ == "__main__":
    unittest.main()

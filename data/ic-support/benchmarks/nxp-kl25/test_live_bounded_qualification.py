#!/usr/bin/env python3
"""Gate 5.7 model-free regressions. No network or model weights are used."""
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
import run_live_bounded_qualification as live
import test_semantic_runner as fixtures
from test_live_model_qualification import UNIT_FIXTURES

HERE = Path(__file__).resolve().parent


class KL25LiveBoundedQualificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.KL25SemanticRunnerTest.setUpClass()
        cls.production_contract = json.loads(
            (HERE / "live-bounded-qualification-contract.json").read_text(encoding="utf-8")
        )

    def setUp(self):
        self.fixture = fixtures.KL25SemanticRunnerTest()
        self.packs, self.bundle, self.evidence, self.manifest = self.fixture.build_inputs()
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.input_dir = root / "pre-ai-boundary-v1"
        self.output_dir = root / "bounded-run"
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
            guard = patch.object(socket, name, side_effect=AssertionError("network forbidden in Gate 5.7 CI"))
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

    def primary_ref(self, pack):
        primary = pack["primary_unit_id"]
        unit = next(
            item for item in pack["included_units"]
            if item["unit_id"] == primary and item["origin"] == "PRIMARY"
        )
        return unit["source_id"], unit["pdf_page_range"][0]

    def transport(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        self.assertEqual(kwargs["runtime_label"], "kl25-live-bounded-qualification")
        self.assertEqual(kwargs["options"]["ollama_url"], "http://127.0.0.1:11434")
        schema = kwargs["options"]["format_schema"]
        unit_id = schema["properties"]["unit_results"]["items"]["properties"]["primary_unit_id"]["enum"][0]
        pack = next(pack for pack in self.packs.values() if pack["primary_unit_id"] == unit_id)
        source, page = self.primary_ref(pack)
        statement = UNIT_FIXTURES[unit_id][2]
        raw = {
            "schema_version": "0.1.0",
            "target": "MKL25Z128VLK4",
            "unit_results": [{
                "primary_unit_id": unit_id,
                "state": "FACTS",
                "facts": [{
                    "fact_id": f"gate57-{unit_id}",
                    "kind": "CONSTRAINT",
                    "statement": statement,
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

    def execute(self, transport=None, contract=None):
        return live.execute_live_bounded_qualification(
            input_dir=self.input_dir,
            output_dir=self.output_dir,
            ollama_url="http://127.0.0.1:11434",
            contract_override=copy.deepcopy(contract or self.contract),
            identity_query=self.identity,
            transport=transport or self.transport,
        )

    def test_production_contract_pins_gate56_release_and_gate55_base(self):
        contract = self.production_contract
        required = contract["required_input"]
        self.assertEqual(required["evidence_boundary_release_id"], "nxp-kl25-evidence-boundary-release-v1")
        self.assertEqual(required["bundle_digest"], "ffe9bfaa8a6ed47c8edd6d952fe1ca2cc114513c2a1f0832892ab9484e7322bf")
        self.assertEqual(required["pre_ai_manifest_digest"], "03155ede421cddb7c2ab64e079ef43b1124a7c78cbedf1e7a08c60c29796bb6e")
        self.assertEqual(required["bounded_contract_id"], "nxp-kl25-bounded-extraction-v1")
        self.assertEqual(required["bounded_contract_digest"], builder.canonical_sha256(bounded.policy()))
        runtime = contract["live_runtime"]
        self.assertEqual(runtime["execution_mode"], "live_bounded_sequential")
        self.assertEqual(runtime["primary_unit_count"], 8)
        self.assertEqual(runtime["automatic_retries"], 0)
        self.assertEqual(runtime["generation"]["max_tokens"], 8192)
        self.assertEqual(runtime["generation"]["num_ctx"], 65536)
        self.assertFalse(contract["review"]["gate57_can_issue_qualified"])

    def test_eight_sequential_live_profiles_reach_ready_for_review(self):
        result, provenance, report = self.execute()
        self.assertEqual(self.identity_calls, 1)
        self.assertEqual(len(self.calls), 8)
        self.assertEqual(result["aggregate"]["status"], "INTEGRITY_PASS")
        self.assertEqual(report["status"], "READY_FOR_REVIEW")
        self.assertEqual(report["review"]["status"], "PENDING")
        self.assertEqual(result["aggregate"]["qualification_status"], "NOT_QUALIFIED")
        self.assertTrue(all(v is False for v in result["aggregate"]["admission"].values()))
        self.assertTrue(all(child["status"] == "success" for child in result["children"]))
        for child in result["children"]:
            binding = child["binding"]
            self.assertEqual(binding["execution_contract_id"], "nxp-kl25-live-bounded-qualification-v1")
            self.assertEqual(binding["execution_mode"], "live_bounded_sequential")
            self.assertEqual(binding["transport"], "ollama_native_chat")
            self.assertEqual(binding["runtime_label"], "kl25-live-bounded-qualification")
            self.assertEqual(binding["model_digest"], "a" * 64)
        self.assertEqual(provenance["execution"]["automatic_retries"], 0)
        self.assertEqual(len(provenance["children"]), 8)
        self.assertFalse(provenance["manufacturer_text_retained_in_provenance"])
        saved = json.loads((self.output_dir / "qualification-report.json").read_text())
        self.assertEqual(saved, report)
        for index, child in enumerate(result["children"], 1):
            self.assertEqual((self.output_dir / f"unit-{index:02d}" / "raw-response.txt").read_text(),
                             child["raw_response"])

    def test_program_longword_schema_allows_p446_and_rejects_p447(self):
        self.execute()
        call = next(
            call for call in self.calls
            if call["options"]["format_schema"]["properties"]["unit_results"]["items"]["properties"]["primary_unit_id"]["enum"][0]
            == "nxp-kl25-program-longword-v0"
        )
        refs = call["options"]["format_schema"]["properties"]["unit_results"]["items"]["properties"]["facts"]["items"]["properties"]["evidence"]["items"]["anyOf"]
        pairs = {
            (item["properties"]["source_id"]["enum"][0], item["properties"]["pdf_page_number"]["enum"][0])
            for item in refs
        }
        self.assertIn(("nxp_kl25_rm_rev3", 446), pairs)
        self.assertNotIn(("nxp_kl25_rm_rev3", 447), pairs)

    def test_length_failure_is_retained_without_retry_and_rejected_integrity(self):
        def transport(**kwargs):
            response = self.transport(**kwargs)
            if len(self.calls) == 1:
                response["done_reason"] = "length"
                response["usage"]["generation_tokens"] = 8192
            return response
        result, _, report = self.execute(transport=transport)
        self.assertEqual(len(self.calls), 8)
        self.assertEqual(sum(child["status"] == "error" for child in result["children"]), 1)
        self.assertEqual(result["aggregate"]["status"], "REJECTED_INTEGRITY")
        self.assertEqual(report["status"], "REJECTED_INTEGRITY")
        failed = next(child for child in result["children"] if child["status"] == "error")
        self.assertEqual(failed["transport_metadata"]["done_reason"], "length")

    def test_out_of_pack_p447_is_rejected_without_repair(self):
        def transport(**kwargs):
            response = self.transport(**kwargs)
            parsed = json.loads(response["raw_text"])
            unit = parsed["unit_results"][0]
            if unit["primary_unit_id"] == "nxp-kl25-program-longword-v0":
                unit["facts"][0]["evidence"][0]["pdf_page_number"] = 447
                response["raw_text"] = json.dumps(parsed)
            return response
        result, _, report = self.execute(transport=transport)
        self.assertEqual(len(self.calls), 8)
        self.assertEqual(result["aggregate"]["status"], "REJECTED_INTEGRITY")
        self.assertEqual(report["status"], "REJECTED_INTEGRITY")
        failed = next(child for child in result["children"] if child["status"] == "error")
        self.assertIn("p447", failed["error"]["message"])

    def test_semantic_screening_failure_is_distinct_from_integrity(self):
        def transport(**kwargs):
            response = self.transport(**kwargs)
            parsed = json.loads(response["raw_text"])
            unit = parsed["unit_results"][0]
            if unit["primary_unit_id"] == "nxp-kl25-swd-mdm-ap-v0":
                unit["facts"][0]["statement"] = "A syntactically valid but incomplete interface statement."
                response["raw_text"] = json.dumps(parsed)
            return response
        result, _, report = self.execute(transport=transport)
        self.assertEqual(result["aggregate"]["status"], "INTEGRITY_PASS")
        self.assertEqual(report["integrity"]["status"], "PASS")
        self.assertEqual(report["status"], "REJECTED_SCREENING")
        self.assertTrue(any("swd-mdm-ap" in error for error in report["semantic_screening"]["errors"]))

    def test_wrong_gate56_manifest_blocks_before_identity_and_transport(self):
        contract = copy.deepcopy(self.contract)
        contract["required_input"]["pre_ai_manifest_digest"] = "0" * 64
        with self.assertRaises(live.LiveBoundedExecutionError):
            self.execute(contract=contract)
        self.assertEqual(self.identity_calls, 0)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.output_dir.exists())

    def test_non_loopback_url_is_rejected_without_provider_call(self):
        with self.assertRaises(Exception):
            live.execute_live_bounded_qualification(
                input_dir=self.input_dir,
                output_dir=self.output_dir,
                ollama_url="http://192.0.2.10:11434",
                contract_override=copy.deepcopy(self.contract),
                identity_query=self.identity,
                transport=self.transport,
            )
        self.assertEqual(self.identity_calls, 0)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.output_dir.exists())

    def test_gate55_default_profile_remains_mock_only(self):
        requests = bounded.prepare_requests(
            contract=copy.deepcopy(self.fixture.contract),
            pre_ai_manifest=copy.deepcopy(self.manifest),
            packs=copy.deepcopy(self.packs),
            evidence_text=copy.deepcopy(self.evidence),
            model_id="mock-gate55",
            model_digest="b" * 64,
        )
        self.assertEqual(len(requests), 8)
        self.assertTrue(all(request["binding"]["execution_mode"] == "mock_only" for request in requests))
        self.assertTrue(all(request["binding"]["transport"] == "mock" for request in requests))
        self.assertTrue(all(request["binding"]["runtime_label"] == "gate55-model-free" for request in requests))


if __name__ == "__main__":
    unittest.main()

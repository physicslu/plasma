#!/usr/bin/env python3
"""Model-free Gate 5.5 regressions. All manufacturer page text is synthetic."""
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
import semantic_extraction as semantic
import test_semantic_runner as fixtures


class BoundedExtractionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fixtures.KL25SemanticRunnerTest.setUpClass()

    def setUp(self):
        self.fixture = fixtures.KL25SemanticRunnerTest()
        packs, _, evidence, manifest = self.fixture.build_inputs()
        self.inputs = dict(contract=copy.deepcopy(self.fixture.contract),
                           pre_ai_manifest=manifest, packs=packs, evidence_text=evidence,
                           model_id="mock-gate55", model_digest="a" * 64)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.output = Path(self.temp.name) / "new-run"
        self.calls = []
        for name in ("socket", "create_connection"):
            guard = patch.object(socket, name, side_effect=AssertionError("network forbidden"))
            guard.start()
            self.addCleanup(guard.stop)

    def mock(self, **kwargs):
        self.calls.append(copy.deepcopy(kwargs))
        unit = kwargs["options"]["format_schema"]["properties"]["unit_results"]["items"]["properties"]["primary_unit_id"]["enum"][0]
        pack = next(p for p in self.inputs["packs"].values() if p["primary_unit_id"] == unit)
        raw = self.fixture.valid_output({pack["pack_id"]: pack})
        return {"raw_text": json.dumps(raw), "response_model": "mock-gate55",
                "done": True, "done_reason": "stop",
                "usage": {"input_tokens": 1000, "generation_tokens": 100},
                "timing": {"wall_time_ms": 1}}

    def execute(self, transport=None):
        return bounded.execute_bounded_run(**self.inputs, transport=transport or self.mock,
                                           output_dir=self.output)

    def aggregate(self, children):
        return bounded.aggregate_results(children, **self.inputs)

    def reseal(self, child):
        child["record_digest"] = bounded._digest_without(child, "record_digest")

    def test_exact_eight_isolated_requests_and_no_input_mutation(self):
        before = copy.deepcopy(self.inputs)
        requests = bounded.prepare_requests(**self.inputs)
        self.assertEqual(len(requests), 8)
        for request in requests:
            binding = request["binding"]
            pack = self.inputs["packs"][binding["pack_id"]]
            self.assertIn(self.inputs["evidence_text"][binding["pack_id"]], request["prompt"])
            for other in self.inputs["packs"].values():
                if other["primary_unit_id"] != binding["primary_unit_id"]:
                    self.assertNotIn(other["primary_unit_id"], request["prompt"])
            schema = request["options"]["format_schema"]
            units = schema["properties"]["unit_results"]
            self.assertEqual((units["minItems"], units["maxItems"]), (1, 1))
            self.assertEqual(units["items"]["properties"]["primary_unit_id"]["enum"], [binding["primary_unit_id"]])
            refs = units["items"]["properties"]["facts"]["items"]["properties"]["evidence"]["items"]["anyOf"]
            pairs = {(r["properties"]["source_id"]["enum"][0], r["properties"]["pdf_page_number"]["enum"][0]) for r in refs}
            self.assertEqual(pairs, semantic._allowed_page_refs(pack))
            for source, page in pairs:
                self.assertIn(f"=== BEGIN {source} PDF_PAGE {page} ", request["prompt"])
            if binding["primary_unit_id"] == "nxp-kl25-program-longword-v0":
                self.assertIn("PDF_PAGE 446 ", request["prompt"])
                self.assertIn(("nxp_kl25_rm_rev3", 446), pairs)
                self.assertIn("PDF_PAGE 445 ", request["prompt"])
                self.assertNotIn(("nxp_kl25_rm_rev3", 447), pairs)
        self.assertEqual(self.inputs, before)
        self.assertEqual(self.calls, [])

    def test_success_retention_order_independence_and_denied_qualification(self):
        result = self.execute()
        self.assertEqual(len(self.calls), 8)
        self.assertEqual(result["aggregate"]["status"], "INTEGRITY_PASS")
        self.assertEqual(result["aggregate"]["qualification_status"], "NOT_QUALIFIED")
        self.assertEqual(result["aggregate"]["acceptance_blockers"], [])
        self.assertTrue(all(v is False for v in result["aggregate"]["admission"].values()))
        self.assertEqual(self.aggregate(list(reversed(result["children"]))), result["aggregate"])
        for index, child in enumerate(result["children"], 1):
            unit_dir = self.output / f"unit-{index:02d}"
            self.assertEqual((unit_dir / "raw-response.txt").read_bytes(), child["raw_response"].encode())
            self.assertEqual(json.loads((unit_dir / "unit-run.json").read_text()), child)
            original = json.loads(child["raw_response"])["unit_results"][0]
            self.assertIn(original, result["aggregate"]["response"]["unit_results"])
        self.assertEqual(json.loads((self.output / "aggregate-report.json").read_text()), result["aggregate"])

    def test_pre_ai_and_contract_corruption_blocks_all_calls_and_writes(self):
        for corruption in ("manifest", "evidence", "pack_content", "missing_pack", "admission", "contract"):
            with self.subTest(corruption=corruption):
                original = copy.deepcopy(self.inputs)
                if corruption == "manifest":
                    self.inputs["pre_ai_manifest"]["manifest_digest"] = "0" * 64
                elif corruption == "evidence":
                    key = next(iter(self.inputs["evidence_text"]))
                    self.inputs["evidence_text"][key] += "injected"
                elif corruption == "pack_content":
                    next(iter(self.inputs["packs"].values()))["page_refs"][0]["pdf_page_number"] = 999
                elif corruption == "missing_pack":
                    self.inputs["packs"].pop(next(iter(self.inputs["packs"])))
                elif corruption == "admission":
                    self.inputs["contract"]["admission"]["production"] = True
                else:
                    self.inputs["contract"]["contract_id"] = "weaker"
                with self.assertRaises((ValueError, builder.KL25EvidencePackError, semantic.SemanticExtractionError)):
                    self.execute()
                self.assertEqual(self.calls, [])
                self.assertFalse(self.output.exists())
                self.inputs = original

    def test_truncated_json_retains_length_telemetry_without_retry(self):
        def transport(**kwargs):
            result = self.mock(**kwargs)
            if len(self.calls) == 1:
                result["raw_text"] = result["raw_text"][:-2]
                result["done_reason"] = "length"
                result["usage"]["generation_tokens"] = 8192
            return result
        result = self.execute(transport)
        self.assertEqual(len(self.calls), 8)
        child = result["children"][0]
        self.assertEqual(child["error"]["class"], "model_output_invalid_json")
        self.assertEqual(child["transport_metadata"]["done_reason"], "length")
        self.assertNotIn("response", child)
        self.assertEqual(sum(c["status"] == "success" for c in result["children"]), 7)
        self.assertEqual(result["aggregate"]["status"], "REJECTED_INTEGRITY")
        self.assertNotIn("response", result["aggregate"])

    def test_page447_is_still_rejected_for_program_longword(self):
        def transport(**kwargs):
            result = self.mock(**kwargs)
            raw = json.loads(result["raw_text"])
            unit = raw["unit_results"][0]
            if unit["primary_unit_id"] == "nxp-kl25-program-longword-v0":
                unit["facts"][0]["evidence"][0]["pdf_page_number"] = 447
                result["raw_text"] = json.dumps(raw)
            return result
        result = self.execute(transport)
        child = next(c for c in result["children"] if c["status"] == "error")
        self.assertEqual(child["error"]["class"], "model_output_evidence_error")
        self.assertIn("p447", child["error"]["message"])
        self.assertEqual(result["aggregate"]["status"], "REJECTED_INTEGRITY")
        self.assertNotIn("response", result["aggregate"])

    def test_missing_duplicate_and_unknown_units_rejected(self):
        children = self.execute()["children"]
        for changed in (children[:-1], children + [children[0]]):
            self.assertEqual(self.aggregate(changed)["status"], "REJECTED_INTEGRITY")
        changed = copy.deepcopy(children)
        changed[0]["binding"]["primary_unit_id"] = "unknown"
        self.reseal(changed[0])
        self.assertEqual(self.aggregate(changed)["status"], "REJECTED_INTEGRITY")

    def test_forged_provenance_rejected_even_when_resealed(self):
        children = self.execute()["children"]
        for key in ("model_id", "model_digest", "pack_digest", "bundle_digest",
                    "pre_ai_manifest_digest", "prompt_sha256", "output_schema_sha256",
                    "semantic_contract_digest", "bounded_contract_digest", "request_digest", "code_fingerprints"):
            with self.subTest(key=key):
                changed = copy.deepcopy(children)
                changed[0]["binding"][key] = "forged"
                self.reseal(changed[0])
                self.assertEqual(self.aggregate(changed)["status"], "REJECTED_INTEGRITY")

    def test_raw_parsed_and_digest_disagreement_rejected(self):
        children = self.execute()["children"]
        for mode in ("raw", "parsed", "record_digest", "raw_digest"):
            with self.subTest(mode=mode):
                changed = copy.deepcopy(children)
                child = changed[0]
                if mode == "raw":
                    child["raw_response"] += " trailing prose"
                    child["raw_response_sha256"] = builder.sha256_text(child["raw_response"])
                elif mode == "parsed":
                    child["response"]["unit_results"][0]["facts"][0]["statement"] = "repaired"
                elif mode == "raw_digest":
                    child["raw_response_sha256"] = "0" * 64
                else:
                    child["record_digest"] = "0" * 64
                if mode != "record_digest":
                    self.reseal(child)
                self.assertEqual(self.aggregate(changed)["status"], "REJECTED_INTEGRITY")

    def test_resealed_success_with_invalid_citation_is_reparsed(self):
        children = self.execute()["children"]
        child = children[0]
        parsed = child["response"]
        parsed["unit_results"][0]["facts"][0]["evidence"][0]["pdf_page_number"] = 999
        child["raw_response"] = json.dumps(parsed)
        child["raw_response_sha256"] = builder.sha256_text(child["raw_response"])
        self.reseal(child)
        self.assertEqual(self.aggregate(children)["status"], "REJECTED_INTEGRITY")

    def test_duplicate_global_fact_ids_are_not_renamed(self):
        def transport(**kwargs):
            result = self.mock(**kwargs)
            parsed = json.loads(result["raw_text"])
            parsed["unit_results"][0]["facts"][0]["fact_id"] = "same-id"
            result["raw_text"] = json.dumps(parsed)
            return result
        result = self.execute(transport)
        self.assertTrue(all(c["status"] == "success" for c in result["children"]))
        self.assertEqual(result["aggregate"]["status"], "REJECTED_INTEGRITY")
        self.assertTrue(any("duplicate fact_id" in e for e in result["aggregate"]["errors"]))

    def test_abnormal_completion_and_missing_usage_fail_closed(self):
        children = self.execute()["children"]
        for mode in ("length", "done", "model", "missing_usage", "boolean_tokens", "overflow", "context", "timing"):
            with self.subTest(mode=mode):
                changed = copy.deepcopy(children)
                m = changed[0]["transport_metadata"]
                if mode == "length":
                    m["done_reason"] = "length"
                elif mode == "done":
                    m["done"] = False
                elif mode == "model":
                    m["response_model"] = "wrong"
                elif mode == "missing_usage":
                    m.pop("usage")
                elif mode == "boolean_tokens":
                    m["usage"]["generation_tokens"] = True
                elif mode == "overflow":
                    m["usage"]["generation_tokens"] = 8193
                elif mode == "context":
                    m["usage"]["input_tokens"] = 60000
                else:
                    m.pop("timing")
                self.reseal(changed[0])
                self.assertEqual(self.aggregate(changed)["status"], "REJECTED_INTEGRITY")

    def test_transport_timeout_does_not_retry_or_cancel_other_units(self):
        def transport(**kwargs):
            result = self.mock(**kwargs)
            if len(self.calls) == 1:
                raise TimeoutError("synthetic timeout")
            return result
        result = self.execute(transport)
        self.assertEqual(len(self.calls), 8)
        self.assertEqual(result["children"][0]["error"]["class"], "transport_timeout")
        self.assertEqual(sum(c["status"] == "success" for c in result["children"]), 7)

    def test_existing_output_directory_is_never_overwritten(self):
        result = self.execute()
        original = (self.output / "aggregate-report.json").read_bytes()
        with self.assertRaises(FileExistsError):
            self.execute()
        self.assertEqual(len(self.calls), 8)
        self.assertEqual((self.output / "aggregate-report.json").read_bytes(), original)
        self.assertEqual(result["aggregate"]["status"], "INTEGRITY_PASS")

    def test_unknown_is_valid_structure_but_never_qualification(self):
        def transport(**kwargs):
            result = self.mock(**kwargs)
            parsed = json.loads(result["raw_text"])
            parsed["unit_results"][0].update(state="UNKNOWN", facts=[])
            result["raw_text"] = json.dumps(parsed)
            return result
        result = self.execute(transport)
        self.assertEqual(result["aggregate"]["status"], "INTEGRITY_PASS")
        self.assertEqual(result["aggregate"]["qualification_status"], "NOT_QUALIFIED")

    def test_duplicate_json_keys_are_not_silently_normalized(self):
        def transport(**kwargs):
            result = self.mock(**kwargs)
            result["raw_text"] = result["raw_text"].replace(
                '"schema_version": "0.1.0"', '"schema_version": "bad", "schema_version": "0.1.0"')
            return result
        result = self.execute(transport)
        self.assertTrue(all(c["error"]["class"] == "model_output_invalid_json" for c in result["children"]))

    def test_empty_raw_response_is_preserved_exactly(self):
        def transport(**kwargs):
            result = self.mock(**kwargs)
            result["raw_text"] = "  \n"
            return result
        result = self.execute(transport)
        self.assertTrue(all(c["raw_response"] == "  \n" for c in result["children"]))
        self.assertEqual((self.output / "unit-01/raw-response.txt").read_bytes(), b"  \n")
        self.assertEqual(result["aggregate"]["status"], "REJECTED_INTEGRITY")

    def test_no_live_import_or_cli_and_frozen_budget(self):
        source = (bounded.HERE / "bounded_extraction.py").read_text()
        self.assertNotIn("import ollama", source)
        self.assertNotIn("import requests", source)
        self.assertNotIn("import subprocess", source)
        self.assertNotIn('if __name__ == "__main__"', source)
        rules = bounded.policy()
        self.assertEqual(rules["evidence_boundary_release_id"], "nxp-kl25-evidence-boundary-release-v1")
        self.assertEqual(rules["known_acceptance_blockers"], [])
        result = self.execute()
        self.assertEqual(result["aggregate"]["status"], "INTEGRITY_PASS")
        self.assertTrue(all(c["options"]["max_tokens"] == 8192 for c in self.calls))


if __name__ == "__main__":
    unittest.main()

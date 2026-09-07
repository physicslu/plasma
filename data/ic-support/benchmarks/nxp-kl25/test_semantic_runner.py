#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

import build_evidence_pack as builder
import semantic_runner as runner

HERE = Path(__file__).resolve().parent


class CapturingTransport:
    def __init__(self, response: dict | None = None, exc: BaseException | None = None):
        self.response = response
        self.exc = exc
        self.called = False
        self.prompt = None
        self.kwargs = None

    def __call__(self, **kwargs):
        self.called = True
        self.prompt = kwargs["prompt"]
        self.kwargs = kwargs
        if self.exc is not None:
            raise self.exc
        return self.response


class KL25SemanticRunnerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((HERE / "semantic-extraction-contract.json").read_text(encoding="utf-8"))
        cls.pack_contract = json.loads((HERE / "evidence-pack-contract.json").read_text(encoding="utf-8"))
        cls.definitions = json.loads((HERE / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8"))
        cls.binding = json.loads((HERE / "applicability-binding.json").read_text(encoding="utf-8"))
        cls.source_lock = json.loads((HERE / "source-lock.json").read_text(encoding="utf-8"))
        max_page = max(unit["pdf_page_range"][1] for unit in cls.definitions["units"])
        cls.pages_by_source = {
            "nxp_kl25_rm_rev3": [
                f"Synthetic KL25 Gate 4 page {page_number}\nFTFA FCCOB FSTAT SWD MDM-AP security"
                for page_number in range(1, max_page + 1)
            ]
        }

    def build_inputs(self):
        packs, bundle = builder.build_pack_set(
            contract=copy.deepcopy(self.pack_contract),
            definitions=copy.deepcopy(self.definitions),
            binding=copy.deepcopy(self.binding),
            source_lock=copy.deepcopy(self.source_lock),
            pages_by_source=copy.deepcopy(self.pages_by_source),
            builder_sha256="d" * 64,
        )
        evidence_text = {
            pack_id: builder.materialize_evidence_text(pack, self.pages_by_source)
            for pack_id, pack in packs.items()
        }
        evidence_sha256 = {
            pack_id: builder.sha256_text(text)
            for pack_id, text in evidence_text.items()
        }
        manifest = builder.build_pre_ai_manifest(
            bundle=bundle,
            packs=packs,
            evidence_sha256=evidence_sha256,
        )
        return packs, bundle, evidence_text, manifest

    def valid_output(self, packs, *, all_unknown: bool = False):
        unit_results = []
        for pack in sorted(packs.values(), key=lambda item: item["primary_unit_id"]):
            primary = pack["primary_unit_id"]
            if all_unknown:
                unit_results.append({"primary_unit_id": primary, "state": "UNKNOWN", "facts": []})
                continue
            first_ref = pack["page_refs"][0]
            unit_results.append(
                {
                    "primary_unit_id": primary,
                    "state": "FACTS",
                    "facts": [
                        {
                            "fact_id": f"fact-{primary}",
                            "kind": "CONSTRAINT",
                            "statement": f"Synthetic manufacturer-near CI fact for {primary}.",
                            "evidence": [
                                {
                                    "source_id": first_ref["source_id"],
                                    "pdf_page_number": first_ref["pdf_page_number"],
                                }
                            ],
                        }
                    ],
                }
            )
        return {
            "schema_version": "0.1.0",
            "target": "MKL25Z128VLK4",
            "unit_results": unit_results,
        }

    def execute(self, transport, *, contract=None, manifest=None, packs=None, evidence_text=None):
        if packs is None or evidence_text is None or manifest is None:
            built_packs, _, built_evidence, built_manifest = self.build_inputs()
            packs = packs or built_packs
            evidence_text = evidence_text or built_evidence
            manifest = manifest or built_manifest
        return runner.execute_semantic_run(
            contract=copy.deepcopy(contract or self.contract),
            pre_ai_manifest=copy.deepcopy(manifest),
            packs=copy.deepcopy(packs),
            evidence_text=copy.deepcopy(evidence_text),
            transport=transport,
            transport_label="mock",
            model_id="mock-model",
            runtime_label="repository-ci",
            request_options={"temperature": 0.0},
        )

    def test_success_is_bound_to_pre_ai_manifest_and_preserves_denied_admissions(self):
        packs, _, evidence_text, manifest = self.build_inputs()
        transport = CapturingTransport({"raw_text": json.dumps(self.valid_output(packs))})
        record = self.execute(transport, manifest=manifest, packs=packs, evidence_text=evidence_text)
        self.assertEqual(record["status"], "success")
        self.assertTrue(record["transport_invoked"])
        self.assertEqual(record["target"], "MKL25Z128VLK4")
        self.assertEqual(record["pre_ai_manifest_digest"], manifest["manifest_digest"])
        self.assertEqual(record["bundle_digest"], manifest["bundle_digest"])
        self.assertEqual(len(record["response"]["unit_results"]), 8)
        boundary = record["trust_boundary"]
        self.assertFalse(boundary["semantic_extraction_admission"])
        self.assertFalse(boundary["model_quality_admission"])
        self.assertFalse(boundary["canonical_dataset_admission"])
        self.assertFalse(boundary["production_admission"])
        self.assertFalse(boundary["destructive_security_operation_admission"])

    def test_unknown_is_a_valid_fail_closed_semantic_result(self):
        packs, _, evidence_text, manifest = self.build_inputs()
        transport = CapturingTransport({"raw_text": json.dumps(self.valid_output(packs, all_unknown=True))})
        record = self.execute(transport, manifest=manifest, packs=packs, evidence_text=evidence_text)
        self.assertEqual(record["status"], "success")
        self.assertTrue(all(item["state"] == "UNKNOWN" for item in record["response"]["unit_results"]))

    def test_pre_ai_digest_mutation_blocks_transport_before_inference(self):
        packs, _, evidence_text, manifest = self.build_inputs()
        manifest = copy.deepcopy(manifest)
        manifest["manifest_digest"] = "0" * 64
        transport = CapturingTransport({"raw_text": json.dumps(self.valid_output(packs))})
        record = self.execute(transport, manifest=manifest, packs=packs, evidence_text=evidence_text)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"]["class"], "pre_ai_validation_error")
        self.assertFalse(record["transport_invoked"])
        self.assertFalse(transport.called)

    def test_timeout_is_classified_without_partial_semantics(self):
        transport = CapturingTransport(exc=runner.SemanticTransportTimeout("mock timeout"))
        record = self.execute(transport)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"]["class"], "transport_timeout")
        self.assertNotIn("response", record)

    def test_connection_failure_is_classified_without_partial_semantics(self):
        transport = CapturingTransport(exc=runner.SemanticTransportUnavailable("mock connection refused"))
        record = self.execute(transport)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"]["class"], "transport_unavailable")
        self.assertNotIn("response", record)

    def test_transport_protocol_failure_is_classified(self):
        transport = CapturingTransport({"not_raw_text": "bad protocol"})
        record = self.execute(transport)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"]["class"], "transport_protocol_error")

    def test_malformed_model_json_is_rejected(self):
        transport = CapturingTransport({"raw_text": "{not-json"})
        record = self.execute(transport)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"]["class"], "model_output_invalid_json")

    def test_missing_primary_unit_result_is_rejected(self):
        packs, _, evidence_text, manifest = self.build_inputs()
        value = self.valid_output(packs)
        value["unit_results"].pop()
        transport = CapturingTransport({"raw_text": json.dumps(value)})
        record = self.execute(transport, manifest=manifest, packs=packs, evidence_text=evidence_text)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"]["class"], "model_output_schema_error")

    def test_unsupported_fact_kind_is_rejected(self):
        packs, _, evidence_text, manifest = self.build_inputs()
        value = self.valid_output(packs)
        value["unit_results"][0]["facts"][0]["kind"] = "STM32_FLASH_CR_PROJECTION"
        transport = CapturingTransport({"raw_text": json.dumps(value)})
        record = self.execute(transport, manifest=manifest, packs=packs, evidence_text=evidence_text)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"]["class"], "model_output_schema_error")

    def test_out_of_pack_evidence_citation_is_rejected(self):
        packs, _, evidence_text, manifest = self.build_inputs()
        value = self.valid_output(packs)
        value["unit_results"][0]["facts"][0]["evidence"][0]["pdf_page_number"] = 9999
        transport = CapturingTransport({"raw_text": json.dumps(value)})
        record = self.execute(transport, manifest=manifest, packs=packs, evidence_text=evidence_text)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"]["class"], "model_output_evidence_error")

    def test_runner_exception_is_fail_closed(self):
        transport = CapturingTransport(exc=RuntimeError("unexpected mock transport bug"))
        record = self.execute(transport)
        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"]["class"], "runner_internal_error")
        self.assertNotIn("response", record)

    def test_prompt_exposes_manufacturer_evidence_not_canonical_or_production_authority(self):
        packs, _, evidence_text, manifest = self.build_inputs()
        transport = CapturingTransport({"raw_text": json.dumps(self.valid_output(packs))})
        record = self.execute(transport, manifest=manifest, packs=packs, evidence_text=evidence_text)
        self.assertEqual(record["status"], "success")
        prompt = transport.prompt
        self.assertIn("manufacturer-near", prompt.lower())
        self.assertIn("FTFA", prompt)
        self.assertIn("FCCOB", prompt)
        self.assertIn("MDM-AP", prompt)
        self.assertNotIn("KEYR", prompt)
        self.assertNotIn("FLASH_CR", prompt)
        self.assertNotIn("canonical ground truth", prompt.lower())
        self.assertNotIn("production profile", prompt.lower())
        self.assertEqual(transport.kwargs["model_id"], "mock-model")
        self.assertEqual(transport.kwargs["runtime_label"], "repository-ci")

    def test_gate4_contract_keeps_real_model_admissions_false(self):
        admission = self.contract["admission"]
        self.assertFalse(admission["mock_runner_ci"])
        self.assertFalse(admission["semantic_extraction"])
        self.assertFalse(admission["model_quality"])
        self.assertFalse(admission["canonical_dataset"])
        self.assertFalse(admission["hil"])
        self.assertFalse(admission["production"])
        self.assertFalse(admission["destructive_security_operation"])


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import unittest
from unittest import mock

import semantic_extraction as semantic
import semantic_runner as runner


class CapturingTransport:
    def __init__(self, response):
        self.response = response
        self.kwargs = None

    def __call__(self, **kwargs):
        self.kwargs = kwargs
        return self.response


class KL25OutputContractHardeningTest(unittest.TestCase):
    def setUp(self):
        self.contract = {
            "schema_version": "0.1.0",
            "target": "MKL25Z128VLK4",
            "output": {
                "allowed_fact_kinds": ["REGISTER", "CONSTRAINT"],
            },
            "admission": {
                "semantic_extraction": False,
                "model_quality": False,
            },
        }
        self.packs = {
            "pack-a": {
                "pack_id": "pack-a",
                "primary_unit_id": "unit-a",
                "page_refs": [
                    {"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": 150},
                    {"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": 151},
                ],
            },
            "pack-b": {
                "pack_id": "pack-b",
                "primary_unit_id": "unit-b",
                "page_refs": [
                    {"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": 422},
                ],
            },
        }

    def test_provider_schema_requires_object_evidence_shape(self):
        schema = semantic.build_output_json_schema(self.contract, packs=self.packs)
        self.assertFalse(schema["additionalProperties"])
        units = schema["properties"]["unit_results"]
        self.assertEqual(units["minItems"], 2)
        self.assertEqual(units["maxItems"], 2)
        self.assertEqual(
            units["items"]["properties"]["primary_unit_id"]["enum"],
            ["unit-a", "unit-b"],
        )
        evidence = units["items"]["properties"]["facts"]["items"]["properties"]["evidence"]
        self.assertEqual(evidence["type"], "array")
        self.assertEqual(evidence["minItems"], 1)
        ref = evidence["items"]
        self.assertEqual(ref["type"], "object")
        self.assertFalse(ref["additionalProperties"])
        self.assertEqual(ref["required"], ["source_id", "pdf_page_number"])
        self.assertEqual(ref["properties"]["source_id"]["enum"], ["nxp_kl25_rm_rev3"])

    def test_prompt_removes_citation_representation_ambiguity(self):
        prompt, _ = semantic.render_prompt(
            "manufacturer evidence",
            contract=self.contract,
            packs=self.packs,
        )
        self.assertIn('"source_id":"nxp_kl25_rm_rev3"', prompt)
        self.assertIn('"pdf_page_number":150', prompt)
        self.assertIn("Never encode an evidence citation as a string", prompt)
        self.assertIn("Do not emit analysis, reasoning, <think> tags", prompt)

    def test_invalid_model_json_keeps_provider_completion_metadata(self):
        transport = CapturingTransport(
            {
                "raw_text": "{not-one-json-document",
                "response_model": "qwen3.8:27b-mlx",
                "done": True,
                "done_reason": "stop",
                "usage": {"input_tokens": 12000, "generation_tokens": 4096},
                "timing": {"wall_time_ms": 1000.0},
            }
        )
        with mock.patch("build_evidence_pack.validate_pre_ai_manifest"), mock.patch(
            "build_evidence_pack.assemble_model_context", return_value="manufacturer context"
        ), mock.patch(
            "semantic_extraction.build_output_json_schema", return_value={"type": "object"}
        ), mock.patch(
            "semantic_extraction.render_prompt", return_value=("prompt", {"primary_unit_count": 2})
        ), mock.patch(
            "semantic_extraction.parse_model_result",
            side_effect=semantic.ModelOutputInvalidJSON("model output is not one valid JSON document"),
        ):
            record = runner.execute_semantic_run(
                contract=self.contract,
                pre_ai_manifest={
                    "target": "MKL25Z128VLK4",
                    "bundle_digest": "b" * 64,
                    "manifest_digest": "m" * 64,
                },
                packs=self.packs,
                evidence_text={"pack-a": "a", "pack-b": "b"},
                transport=transport,
                transport_label="ollama_native_chat",
                model_id="qwen3.8:27b-mlx",
                runtime_label="repository-ci",
                request_options={"temperature": 0.0},
            )

        self.assertEqual(record["status"], "error")
        self.assertEqual(record["error"]["class"], "model_output_invalid_json")
        self.assertTrue(record["transport_invoked"])
        self.assertEqual(record["transport_metadata"]["response_model"], "qwen3.8:27b-mlx")
        self.assertTrue(record["transport_metadata"]["done"])
        self.assertEqual(record["transport_metadata"]["usage"]["generation_tokens"], 4096)
        self.assertEqual(transport.kwargs["options"]["format_schema"], {"type": "object"})
        self.assertEqual(record["runtime"]["output_format"], "json_schema")


if __name__ == "__main__":
    unittest.main()

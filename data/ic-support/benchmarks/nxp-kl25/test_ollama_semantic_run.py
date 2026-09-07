#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_evidence_pack as builder
import run_ollama_semantic

HERE = Path(__file__).resolve().parent


class FakeResponse:
    def __init__(self, body: bytes):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return self.body


class KL25OllamaSemanticRunTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pack_contract = json.loads((HERE / "evidence-pack-contract.json").read_text(encoding="utf-8"))
        cls.definitions = json.loads((HERE / "reviewed-evidence-unit-definitions.json").read_text(encoding="utf-8"))
        cls.binding = json.loads((HERE / "applicability-binding.json").read_text(encoding="utf-8"))
        cls.source_lock = json.loads((HERE / "source-lock.json").read_text(encoding="utf-8"))
        max_page = max(unit["pdf_page_range"][1] for unit in cls.definitions["units"])
        cls.pages_by_source = {
            "nxp_kl25_rm_rev3": [
                f"Synthetic KL25 executable runner page {page_number}\nFTFA FCCOB FSTAT SWD MDM-AP security"
                for page_number in range(1, max_page + 1)
            ]
        }

    def build_workspace(self, input_dir: Path):
        packs, bundle = builder.build_pack_set(
            contract=copy.deepcopy(self.pack_contract),
            definitions=copy.deepcopy(self.definitions),
            binding=copy.deepcopy(self.binding),
            source_lock=copy.deepcopy(self.source_lock),
            pages_by_source=copy.deepcopy(self.pages_by_source),
            builder_sha256="e" * 64,
        )
        builder.write_artifacts(
            output_dir=input_dir,
            packs=packs,
            bundle=bundle,
            pages_by_source=self.pages_by_source,
        )
        return packs

    def valid_output(self, packs):
        unit_results = []
        for pack in sorted(packs.values(), key=lambda item: item["primary_unit_id"]):
            ref = pack["page_refs"][0]
            unit_results.append(
                {
                    "primary_unit_id": pack["primary_unit_id"],
                    "state": "FACTS",
                    "facts": [
                        {
                            "fact_id": f"wire-{pack['primary_unit_id']}",
                            "kind": "CONSTRAINT",
                            "statement": "Synthetic CI fact proving executable runner wiring.",
                            "evidence": [
                                {
                                    "source_id": ref["source_id"],
                                    "pdf_page_number": ref["pdf_page_number"],
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

    def test_gate3_workspace_to_real_ollama_adapter_to_run_artifacts(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "pre-ai"
            output_dir = root / "semantic"
            packs = self.build_workspace(input_dir)
            model_text = json.dumps(self.valid_output(packs))
            outer = {
                "model": "qwen3.8:27b-mlx",
                "message": {"role": "assistant", "content": model_text},
                "done": True,
                "prompt_eval_count": 321,
                "eval_count": 123,
            }
            captured = {}

            def fake_urlopen(request, timeout):
                captured["url"] = request.full_url
                captured["payload"] = json.loads(request.data.decode("utf-8"))
                captured["timeout"] = timeout
                return FakeResponse(json.dumps(outer).encode("utf-8"))

            with mock.patch("urllib.request.urlopen", side_effect=fake_urlopen):
                record = run_ollama_semantic.execute_workspace(
                    input_dir=input_dir,
                    output_dir=output_dir,
                    ollama_url="http://127.0.0.1:11434",
                    model_id="qwen3.8:27b-mlx",
                    runtime_label="repository-ci",
                    num_ctx=32768,
                    max_tokens=4096,
                    temperature=0.0,
                    seed=11,
                    timeout_seconds=30.0,
                )

            self.assertEqual(record["status"], "success")
            self.assertEqual(captured["url"], "http://127.0.0.1:11434/api/chat")
            self.assertEqual(captured["payload"]["model"], "qwen3.8:27b-mlx")
            self.assertIn("PLASMA NXP KL25", captured["payload"]["messages"][0]["content"])
            self.assertTrue((output_dir / "semantic-run.json").is_file())
            self.assertEqual((output_dir / "raw-response.txt").read_text(encoding="utf-8"), model_text)
            retained = json.loads((output_dir / "semantic-run.json").read_text(encoding="utf-8"))
            self.assertEqual(retained["pre_ai_manifest_digest"], record["pre_ai_manifest_digest"])
            self.assertFalse(retained["trust_boundary"]["semantic_extraction_admission"])

    def test_workspace_tamper_fails_before_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "pre-ai"
            self.build_workspace(input_dir)
            bundle_path = input_dir / "target-bundle.json"
            bundle = json.loads(bundle_path.read_text(encoding="utf-8"))
            bundle["bundle_digest"] = "0" * 64
            bundle_path.write_text(json.dumps(bundle), encoding="utf-8")
            with mock.patch("urllib.request.urlopen") as mocked:
                with self.assertRaises(run_ollama_semantic.SemanticWorkspaceError):
                    run_ollama_semantic.execute_workspace(
                        input_dir=input_dir,
                        output_dir=root / "semantic",
                        ollama_url="http://127.0.0.1:11434",
                        model_id="qwen3.8:27b-mlx",
                        runtime_label="repository-ci",
                        num_ctx=32768,
                        max_tokens=4096,
                        temperature=0.0,
                        seed=None,
                        timeout_seconds=30.0,
                    )
                mocked.assert_not_called()

    def test_extra_pack_file_fails_closed_before_http(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "pre-ai"
            self.build_workspace(input_dir)
            (input_dir / "packs" / "unexpected.json").write_text("{}", encoding="utf-8")
            with mock.patch("urllib.request.urlopen") as mocked:
                with self.assertRaises(run_ollama_semantic.SemanticWorkspaceError):
                    run_ollama_semantic.load_pre_ai_workspace(input_dir)
                mocked.assert_not_called()

    def test_invalid_model_output_is_retained_for_local_diagnosis_but_not_admitted(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "pre-ai"
            output_dir = root / "semantic"
            self.build_workspace(input_dir)
            raw = "not-valid-semantic-json"
            outer = {
                "model": "qwen3.8:27b-mlx",
                "message": {"role": "assistant", "content": raw},
                "done": True,
            }
            with mock.patch(
                "urllib.request.urlopen",
                return_value=FakeResponse(json.dumps(outer).encode("utf-8")),
            ):
                record = run_ollama_semantic.execute_workspace(
                    input_dir=input_dir,
                    output_dir=output_dir,
                    ollama_url="http://127.0.0.1:11434",
                    model_id="qwen3.8:27b-mlx",
                    runtime_label="repository-ci",
                    num_ctx=32768,
                    max_tokens=4096,
                    temperature=0.0,
                    seed=None,
                    timeout_seconds=30.0,
                )
            self.assertEqual(record["status"], "error")
            self.assertEqual(record["error"]["class"], "model_output_invalid_json")
            self.assertEqual((output_dir / "raw-response.txt").read_text(encoding="utf-8"), raw)
            self.assertFalse(record["trust_boundary"]["semantic_extraction_admission"])


if __name__ == "__main__":
    unittest.main()

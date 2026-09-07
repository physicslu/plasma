#!/usr/bin/env python3
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_evidence_pack as builder
import run_live_model_qualification as live

HERE = Path(__file__).resolve().parent

UNIT_FIXTURES = {
    "nxp-kl25-ftfa-register-model-v0": (422, 431, "FTFA register model exposes FSTAT status and FCCOB command object registers."),
    "nxp-kl25-ftfa-command-sequencing-v0": (435, 439, "FCCOB command sequencing launches through CCIF and checks ACCERR or FPVIOL status."),
    "nxp-kl25-program-longword-v0": (444, 445, "Program Longword uses the FCCOB command object."),
    "nxp-kl25-erase-sector-v0": (446, 448, "Erase Flash Sector defines the sector erase behavior."),
    "nxp-kl25-erase-all-blocks-v0": (451, 452, "Erase All Blocks is constrained by flash protection."),
    "nxp-kl25-flash-security-v0": (454, 455, "FSEC defines security controls including SEC and MEEN."),
    "nxp-kl25-debug-security-interaction-v0": (149, 150, "SWD access changes in secure security state and mass erase is constrained."),
    "nxp-kl25-swd-mdm-ap-v0": (151, 157, "SWD exposes MDM-AP status and mass erase control."),
}


class KL25RunLiveModelQualificationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.contract = json.loads((HERE / "live-model-qualification-contract.json").read_text(encoding="utf-8"))

    def packs(self):
        result = {}
        for unit_id, (start, end, _) in UNIT_FIXTURES.items():
            pack_id = f"{unit_id}-pack-v0"
            result[pack_id] = {
                "pack_id": pack_id,
                "primary_unit_id": unit_id,
                "included_units": [
                    {
                        "unit_id": unit_id,
                        "origin": "PRIMARY",
                        "source_id": "nxp_kl25_rm_rev3",
                        "pdf_page_range": [start, end],
                    }
                ],
            }
        return result

    def semantic_record(self, raw_text):
        response = json.loads(raw_text)
        return {
            "schema_version": "0.1.0",
            "artifact_type": "kl25_semantic_extraction_run",
            "target": "MKL25Z128VLK4",
            "bundle_digest": self.contract["required_input"]["bundle_digest"],
            "pre_ai_manifest_digest": self.contract["required_input"]["pre_ai_manifest_digest"],
            "semantic_contract_id": self.contract["required_input"]["semantic_contract_id"],
            "runtime": {
                "transport": "ollama_native_chat",
                "runtime_label": "kl25-live-model-qualification",
                "model_id": "qwen3.8:27b-mlx",
            },
            "prompt": {"sha256": "c" * 64, "byte_length": 5000},
            "status": "success",
            "response": response,
            "transport_metadata": {
                "response_model": "qwen3.8:27b-mlx",
                "done": True,
                "done_reason": "stop",
                "usage": {"input_tokens": 10000, "generation_tokens": 1000},
                "timing": {"wall_time_ms": 1234.0},
            },
            "transport_invoked": True,
            "raw_response_sha256": builder.sha256_text(raw_text),
        }

    def raw_text(self):
        unit_results = []
        for unit_id, (start, _, statement) in UNIT_FIXTURES.items():
            unit_results.append(
                {
                    "primary_unit_id": unit_id,
                    "state": "FACTS",
                    "facts": [
                        {
                            "fact_id": f"live-{unit_id}",
                            "kind": "CONSTRAINT",
                            "statement": statement,
                            "evidence": [{"source_id": "nxp_kl25_rm_rev3", "pdf_page_number": start}],
                        }
                    ],
                }
            )
        return json.dumps({"schema_version": "0.1.0", "target": "MKL25Z128VLK4", "unit_results": unit_results})

    def test_frozen_live_wiring_records_runtime_identity_and_is_ready_for_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            input_dir = root / "input"
            output_dir = root / "output"
            input_dir.mkdir()
            packs = self.packs()
            manifest = {
                "target": "MKL25Z128VLK4",
                "bundle_digest": self.contract["required_input"]["bundle_digest"],
                "manifest_digest": self.contract["required_input"]["pre_ai_manifest_digest"],
            }
            raw = self.raw_text()
            record = self.semantic_record(raw)

            def fake_execute_workspace(**kwargs):
                self.assertEqual(kwargs["model_id"], "qwen3.8:27b-mlx")
                self.assertEqual(kwargs["runtime_label"], "kl25-live-model-qualification")
                self.assertEqual(kwargs["num_ctx"], 32768)
                self.assertEqual(kwargs["max_tokens"], 4096)
                self.assertEqual(kwargs["temperature"], 0.0)
                self.assertEqual(kwargs["seed"], 0)
                self.assertEqual(kwargs["timeout_seconds"], 1800.0)
                output_dir.mkdir(parents=True, exist_ok=True)
                (output_dir / "raw-response.txt").write_text(raw, encoding="utf-8")
                (output_dir / "semantic-run.json").write_text(json.dumps(record), encoding="utf-8")
                return record

            identity = {
                "ollama_url_policy": "loopback_only",
                "ollama_version": "0.12.0",
                "model_id": "qwen3.8:27b-mlx",
                "model_digest": "sha256:" + "d" * 64,
            }
            with mock.patch("run_ollama_semantic.load_pre_ai_workspace", return_value=(manifest, packs, {}, {})), mock.patch(
                "ollama_live_runtime.query_ollama_runtime_identity", return_value=identity
            ) as preflight, mock.patch("run_ollama_semantic.execute_workspace", side_effect=fake_execute_workspace):
                retained, provenance, report = live.execute_live_qualification(
                    input_dir=input_dir,
                    output_dir=output_dir,
                    ollama_url="http://127.0.0.1:11434",
                )

            self.assertEqual(retained["status"], "success")
            self.assertEqual(report["status"], "READY_FOR_REVIEW")
            self.assertEqual(provenance["ollama_runtime_identity"]["model_digest"], "sha256:" + "d" * 64)
            self.assertFalse(provenance["execution"]["host"]["hostname_retained"])
            self.assertTrue((output_dir / "live-run-provenance.json").is_file())
            self.assertTrue((output_dir / "qualification-report.json").is_file())
            preflight.assert_called_once()

    def test_gate3_digest_mismatch_blocks_all_ollama_http(self):
        manifest = {
            "target": "MKL25Z128VLK4",
            "bundle_digest": "0" * 64,
            "manifest_digest": self.contract["required_input"]["pre_ai_manifest_digest"],
        }
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "run_ollama_semantic.load_pre_ai_workspace", return_value=(manifest, self.packs(), {}, {})
        ), mock.patch("ollama_live_runtime.query_ollama_runtime_identity") as identity, mock.patch(
            "run_ollama_semantic.execute_workspace"
        ) as inference:
            with self.assertRaises(live.LiveQualificationExecutionError):
                live.execute_live_qualification(
                    input_dir=Path(tmp) / "input",
                    output_dir=Path(tmp) / "output",
                    ollama_url="http://127.0.0.1:11434",
                )
            identity.assert_not_called()
            inference.assert_not_called()

    def test_non_loopback_provider_is_rejected_before_identity_or_inference(self):
        manifest = {
            "target": "MKL25Z128VLK4",
            "bundle_digest": self.contract["required_input"]["bundle_digest"],
            "manifest_digest": self.contract["required_input"]["pre_ai_manifest_digest"],
        }
        with tempfile.TemporaryDirectory() as tmp, mock.patch(
            "run_ollama_semantic.load_pre_ai_workspace", return_value=(manifest, self.packs(), {}, {})
        ), mock.patch("ollama_live_runtime.query_ollama_runtime_identity") as identity, mock.patch(
            "run_ollama_semantic.execute_workspace"
        ) as inference:
            with self.assertRaises(Exception):
                live.execute_live_qualification(
                    input_dir=Path(tmp) / "input",
                    output_dir=Path(tmp) / "output",
                    ollama_url="http://192.168.1.10:11434",
                )
            identity.assert_not_called()
            inference.assert_not_called()


if __name__ == "__main__":
    unittest.main()

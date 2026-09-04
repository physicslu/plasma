from __future__ import annotations

import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock

import ab_benchmark as harness
import score_ab_benchmark as scorer

HERE = Path(__file__).resolve().parent


def synthetic_observed() -> dict:
    return {
        "profile_relationships": {
            "programming": "shared",
            "memory_geometry": "different",
            "package_hardware": "unknown",
            "option": "shared",
            "security": "shared",
        },
        "parts": {
            "STM32F103C8T6": {
                "base_device": "DEVICE-A",
                "flash_size_bytes": 1,
                "page_size_bytes": 1,
                "page_count": 1,
            },
            "STM32F103CBT6": {
                "base_device": "DEVICE-B",
                "flash_size_bytes": 2,
                "page_size_bytes": 1,
                "page_count": 2,
            },
        },
        "programming_contract": {
            "program_granularity_bytes": 1,
            "unlock_keys": ["KEY1", "KEY2"],
            "write_erase_requires_hsi": True,
        },
        "option_contract": {
            "region_start": "0x1",
            "region_size_bytes": 1,
            "encoding": "synthetic",
        },
        "security_contract": {
            "read_unprotect_is_destructive": True,
            "write_protection_granularity_bytes": 1,
        },
    }


def evidence_for(observed: dict, *, source_id: str = harness.DS_SOURCE_ID, page: int = 0) -> dict:
    return {
        path: [{"source_id": source_id, "physical_page_index": page}]
        for path, value in scorer.flatten_leaves(observed).items()
        if not scorer.is_missing_or_unknown(value)
    }


def synthetic_run(arm: str, observed: dict, evidence: dict, *, trial: int = 1, order: int = 1) -> dict:
    ds_pages = [0, 1] if arm == "full_context" else [0]
    return {
        "schema_version": harness.RUN_SCHEMA_VERSION,
        "experiment_id": harness.EXPERIMENT_ID,
        "arm": arm,
        "trial_index": trial,
        "order_position": order,
        "source_lock_id": "stm32f103c-source-lock-v0",
        "source_digests": {
            harness.DS_SOURCE_ID: "sha256:" + "a" * 64,
            harness.PM_SOURCE_ID: "sha256:" + "b" * 64,
        },
        "context_manifest_digest": "c" * 64,
        "context": {
            "datasheet_mode": "FULL_LOCKED_SOURCE" if arm == "full_context" else "DETERMINISTIC_EVIDENCE_PACK",
            "datasheet_sha256": "d" * 64 if arm == "full_context" else "e" * 64,
            "datasheet_input_bytes": 200 if arm == "full_context" else 100,
            "datasheet_physical_pages": ds_pages,
            "programming_manual_sha256": "f" * 64,
            "programming_manual_input_bytes": 50,
            "programming_manual_physical_pages": [0, 1],
            "preprocessor": {"name": "pdftotext", "version": "synthetic", "arguments": ["-layout", "-enc", "UTF-8"]},
            "normalization": {"contract_id": "synthetic", "digest": "1" * 64},
        },
        "prompt": {
            "template_sha256": "2" * 64,
            "observed_schema_sha256": "3" * 64,
            "rendered_sha256": "4" * 64,
            "rendered_byte_length": 300 if arm == "full_context" else 200,
        },
        "runtime": {
            "transport": "openai_compatible_chat_completions",
            "runtime_label": "synthetic-runtime",
            "model_id": "synthetic-model",
        },
        "generation": {"temperature": 0.0, "max_tokens": 100, "seed": 7, "stream": True},
        "measurement": {"peak_memory_bytes": None, "peak_memory_status": "not_reported_by_remote_endpoint"},
        "status": "success",
        "response_model": "synthetic-model",
        "streaming_observed": True,
        "timing": {"ttft_ms": 10.0, "total_time_ms": 20.0},
        "usage": {"input_tokens": 100, "generation_tokens": 20, "total_tokens": 120, "status": "runtime_reported"},
        "response": {"observed": observed, "evidence": evidence},
        "raw_response_sha256": "5" * 64,
    }


class _SSEHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):  # noqa: A003
        return

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        payload = json.loads(self.rfile.read(length).decode("utf-8"))
        if payload.get("stream") is not True:
            self.send_error(400)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Connection", "close")
        self.end_headers()
        chunks = [
            {"model": "synthetic-model", "choices": [{"delta": {"content": "{\"ok\":"}}]},
            {"model": "synthetic-model", "choices": [{"delta": {"content": "true}"}}]},
            {"model": "synthetic-model", "choices": [], "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15}},
        ]
        for index, chunk in enumerate(chunks):
            if index == 1:
                time.sleep(0.01)
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode("utf-8"))
            self.wfile.flush()
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()
        self.close_connection = True


class ABBenchmarkTest(unittest.TestCase):
    def test_generation_module_does_not_name_ground_truth(self):
        source = (HERE / "ab_benchmark.py").read_text(encoding="utf-8")
        self.assertNotIn("extraction-ground-truth", source)
        self.assertNotIn("ground-truth.json", source)

    def test_prompt_does_not_reveal_arm_identity(self):
        template = harness.PROMPT_TEMPLATE.read_text(encoding="utf-8")
        self.assertNotIn("full_context", template)
        self.assertNotIn("reduced_context", template)
        self.assertNotIn("45-page", template)

    def test_model_result_schema_validation(self):
        observed = synthetic_observed()
        raw = json.dumps({"observed": observed, "evidence": evidence_for(observed)})
        parsed = harness.parse_model_result(raw)
        self.assertEqual(parsed["observed"], observed)
        broken = json.loads(raw)
        broken["observed"]["unexpected"] = 1
        with self.assertRaises(harness.ABBenchmarkError):
            harness.parse_model_result(json.dumps(broken))

    def test_streaming_endpoint_measures_ttft_and_usage(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), _SSEHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            result = harness.openai_compatible_chat(
                base_url=f"http://127.0.0.1:{server.server_port}/v1",
                model="synthetic-model",
                prompt="synthetic",
                api_key=None,
                temperature=0.0,
                max_tokens=10,
                seed=1,
                timeout_seconds=5.0,
            )
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=1.0)
        self.assertEqual(result["raw_text"], '{"ok":true}')
        self.assertTrue(result["streaming_observed"])
        self.assertIsNotNone(result["ttft_ms"])
        self.assertGreater(result["total_time_ms"], 0)
        self.assertEqual(result["usage"]["prompt_tokens"], 12)

    def test_score_separates_wrong_missing_and_provenance(self):
        expected = synthetic_observed()
        observed = json.loads(json.dumps(expected))
        observed["parts"]["STM32F103C8T6"]["flash_size_bytes"] = 99
        observed["parts"]["STM32F103CBT6"]["base_device"] = None
        evidence = evidence_for(observed)
        evidence.pop("$.programming_contract.program_granularity_bytes")
        evidence["$.security_contract.read_unprotect_is_destructive"] = [
            {"source_id": harness.DS_SOURCE_ID, "physical_page_index": 99}
        ]
        run = synthetic_run("reduced_context", observed, evidence)
        score = scorer.score_run(run, expected)
        self.assertEqual(score["wrong_assertion_count"], 1)
        self.assertEqual(score["missing_unknown_count"], 1)  # only base_device changed from a known expected value to null
        self.assertEqual(score["uncited_assertion_count"], 1)
        self.assertEqual(score["out_of_context_citation_count"], 1)
        self.assertGreaterEqual(score["unsupported_inference_proxy_count"], 3)

    def test_exact_score_with_valid_in_arm_citations(self):
        expected = synthetic_observed()
        evidence = evidence_for(expected, page=0)
        run = synthetic_run("full_context", expected, evidence)
        score = scorer.score_run(run, expected)
        self.assertEqual(score["exact_accuracy"], 1.0)
        self.assertEqual(score["wrong_assertion_count"], 0)
        self.assertEqual(score["uncited_assertion_count"], 0)
        self.assertEqual(score["unsupported_inference_proxy_count"], 0)

    def test_pair_rejects_controlled_variable_drift(self):
        observed = synthetic_observed()
        full = synthetic_run("full_context", observed, evidence_for(observed), order=1)
        reduced = synthetic_run("reduced_context", observed, evidence_for(observed), order=2)
        scorer.validate_pair(full, reduced)
        reduced["runtime"]["model_id"] = "different-model"
        with self.assertRaises(scorer.ABScoreError):
            scorer.validate_pair(full, reduced)

    def test_context_manifest_detects_file_drift(self):
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp)
            contexts = workspace / "contexts"
            contexts.mkdir()
            (contexts / "ds-full.txt").write_text("FULL", encoding="utf-8")
            (contexts / "ds-reduced.txt").write_text("REDUCED", encoding="utf-8")
            (contexts / "pm-full.txt").write_text("PM", encoding="utf-8")

            def meta(name: str, pages: list[int], mode: str, source_id: str):
                payload = (contexts / name).read_bytes()
                return {
                    "mode": mode,
                    "file": name,
                    "sha256": harness.sha256_bytes(payload),
                    "byte_length": len(payload),
                    "source_id": source_id,
                    "physical_pages": pages,
                }

            manifest = {
                "schema_version": harness.CONTEXT_SCHEMA_VERSION,
                "experiment_id": harness.EXPERIMENT_ID,
                "source_lock_id": "stm32f103c-source-lock-v0",
                "source_digests": {},
                "preprocessor": {},
                "normalization": {},
                "evidence_pack": {},
                "arms": {
                    "full_context": {
                        "datasheet": meta("ds-full.txt", [0, 1], "FULL_LOCKED_SOURCE", harness.DS_SOURCE_ID),
                        "programming_manual": meta("pm-full.txt", [0], "FULL_LOCKED_SOURCE", harness.PM_SOURCE_ID),
                    },
                    "reduced_context": {
                        "datasheet": meta("ds-reduced.txt", [0], "DETERMINISTIC_EVIDENCE_PACK", harness.DS_SOURCE_ID),
                        "programming_manual": meta("pm-full.txt", [0], "FULL_LOCKED_SOURCE", harness.PM_SOURCE_ID),
                    },
                },
                "trust_boundary": {"ground_truth_used_during_generation": False},
            }
            manifest["manifest_digest"] = harness.canonical_sha256(manifest)
            (workspace / "context-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            harness.validate_context_manifest(workspace, manifest)
            (contexts / "ds-reduced.txt").write_text("DRIFT", encoding="utf-8")
            with self.assertRaises(harness.ABBenchmarkError):
                harness.validate_context_manifest(workspace, manifest)

    def test_trial_order_alternates(self):
        calls: list[tuple[int, str, int]] = []
        with tempfile.TemporaryDirectory() as tmp:
            workspace = Path(tmp) / "workspace"
            results = Path(tmp) / "results"
            contexts = workspace / "contexts"
            contexts.mkdir(parents=True)
            for name, text in (("ds-full.txt", "F"), ("ds-reduced.txt", "R"), ("pm-full.txt", "P")):
                (contexts / name).write_text(text, encoding="utf-8")

            def component(name: str, mode: str, pages: list[int]):
                payload = (contexts / name).read_bytes()
                return {
                    "mode": mode,
                    "file": name,
                    "sha256": harness.sha256_bytes(payload),
                    "byte_length": len(payload),
                    "physical_pages": pages,
                }

            manifest = {
                "schema_version": harness.CONTEXT_SCHEMA_VERSION,
                "experiment_id": harness.EXPERIMENT_ID,
                "source_lock_id": "stm32f103c-source-lock-v0",
                "source_digests": {},
                "preprocessor": {},
                "normalization": {},
                "evidence_pack": {},
                "arms": {
                    "full_context": {
                        "datasheet": component("ds-full.txt", "FULL_LOCKED_SOURCE", [0, 1]),
                        "programming_manual": component("pm-full.txt", "FULL_LOCKED_SOURCE", [0]),
                    },
                    "reduced_context": {
                        "datasheet": component("ds-reduced.txt", "DETERMINISTIC_EVIDENCE_PACK", [0]),
                        "programming_manual": component("pm-full.txt", "FULL_LOCKED_SOURCE", [0]),
                    },
                },
                "trust_boundary": {"ground_truth_used_during_generation": False},
            }
            manifest["manifest_digest"] = harness.canonical_sha256(manifest)
            (workspace / "context-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

            def fake_execute_arm(**kwargs):
                calls.append((kwargs["trial_index"], kwargs["arm_name"], kwargs["order_position"]))
                return {"status": "success"}

            with mock.patch.object(harness, "execute_arm", side_effect=fake_execute_arm):
                harness.run_pair(
                    workspace=workspace,
                    results_dir=results,
                    base_url="http://unused/v1",
                    model="m",
                    runtime_label="r",
                    api_key=None,
                    trials=3,
                    temperature=0.0,
                    max_tokens=1,
                    seed=None,
                    timeout_seconds=1.0,
                    inter_arm_delay_seconds=0.0,
                )
        self.assertEqual(
            calls,
            [
                (1, "full_context", 1),
                (1, "reduced_context", 2),
                (2, "reduced_context", 1),
                (2, "full_context", 2),
                (3, "full_context", 1),
                (3, "reduced_context", 2),
            ],
        )


if __name__ == "__main__":
    unittest.main()

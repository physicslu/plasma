from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

import ab_benchmark as harness
import score_ab_benchmark as scorer


def make_run(arm: str, observed: dict, *, trial: int, order: int) -> dict:
    leaves = scorer.flatten_leaves(observed)
    evidence = {
        path: [{"source_id": harness.DS_SOURCE_ID, "physical_page_index": 0}]
        for path, value in leaves.items()
        if not scorer.is_missing_or_unknown(value)
    }
    full = arm == "full_context"
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
            "datasheet_mode": "FULL_LOCKED_SOURCE" if full else "DETERMINISTIC_EVIDENCE_PACK",
            "datasheet_sha256": ("d" if full else "e") * 64,
            "datasheet_input_bytes": 2000 if full else 800,
            "datasheet_physical_pages": [0, 1] if full else [0],
            "programming_manual_sha256": "f" * 64,
            "programming_manual_input_bytes": 500,
            "programming_manual_physical_pages": [0, 1],
            "preprocessor": {"name": "pdftotext", "version": "synthetic", "arguments": ["-layout", "-enc", "UTF-8"]},
            "normalization": {"contract_id": "synthetic", "digest": "1" * 64},
        },
        "prompt": {
            "template_sha256": "2" * 64,
            "observed_schema_sha256": "3" * 64,
            "rendered_sha256": ("4" if full else "5") * 64,
            "rendered_byte_length": 3000 if full else 1800,
        },
        "runtime": {
            "transport": "openai_compatible_chat_completions",
            "runtime_label": "synthetic-runtime",
            "model_id": "synthetic-model",
        },
        "generation": {"temperature": 0.0, "max_tokens": 1000, "seed": 7, "stream": True},
        "measurement": {"peak_memory_bytes": None, "peak_memory_status": "not_reported_by_remote_endpoint"},
        "status": "success",
        "response_model": "synthetic-model",
        "streaming_observed": True,
        "timing": {
            "ttft_ms": 100.0 if full else 50.0,
            "total_time_ms": 500.0 if full else 300.0,
        },
        "usage": {
            "input_tokens": 1000 if full else 600,
            "generation_tokens": 100,
            "total_tokens": 1100 if full else 700,
            "status": "runtime_reported",
        },
        "response": {"observed": observed, "evidence": evidence},
        "raw_response_sha256": "6" * 64,
    }


class ABScorePipelineTest(unittest.TestCase):
    def test_end_to_end_score_aggregates_paired_trials(self):
        truth = json.loads(scorer.GROUND_TRUTH.read_text(encoding="utf-8"))["expected"]
        with tempfile.TemporaryDirectory() as tmp:
            results = Path(tmp)
            for trial in (1, 2):
                trial_dir = results / f"trial-{trial:03d}"
                trial_dir.mkdir()
                full_order, reduced_order = ((1, 2) if trial % 2 else (2, 1))
                full = make_run("full_context", truth, trial=trial, order=full_order)
                reduced = make_run("reduced_context", truth, trial=trial, order=reduced_order)
                (trial_dir / "full_context.run.json").write_text(json.dumps(full), encoding="utf-8")
                (trial_dir / "reduced_context.run.json").write_text(json.dumps(reduced), encoding="utf-8")

            report = scorer.score_results(results)

        self.assertTrue(report["acceptance"]["correctness_non_regression_all_trials"])
        self.assertEqual(report["aggregate"]["full_context"]["exact_accuracy_mean"], 1.0)
        self.assertEqual(report["aggregate"]["reduced_context"]["exact_accuracy_mean"], 1.0)
        self.assertEqual(report["performance_delta"]["input_tokens"]["reduction_percent"], 40.0)
        self.assertEqual(report["performance_delta"]["ttft_ms"]["reduction_percent"], 50.0)
        self.assertEqual(
            [trial["execution_order"] for trial in report["trials"]],
            [
                ["full_context", "reduced_context"],
                ["reduced_context", "full_context"],
            ],
        )


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import ab_benchmark as harness
import ollama_extraction_run as ollama_transport
import semantic_extraction_v8 as semantic


def _known_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def execute_arm(*, workspace: Path, arm_name: str, output_dir: Path, ollama_url: str, model: str,
                runtime_label: str, num_ctx: int, max_tokens: int, temperature: float,
                seed: int | None, timeout_seconds: float) -> dict[str, Any]:
    context, arm, context_manifest = harness.load_arm_context(workspace, arm_name)
    prompt, prompt_meta = semantic.render_prompt(context)
    run_context = {
        "datasheet_mode": arm["datasheet"]["mode"],
        "datasheet_sha256": arm["datasheet"]["sha256"],
        "datasheet_input_bytes": arm["datasheet"]["byte_length"],
        "datasheet_physical_pages": arm["datasheet"]["physical_pages"],
        "programming_manual_sha256": arm["programming_manual"]["sha256"],
        "programming_manual_input_bytes": arm["programming_manual"]["byte_length"],
        "programming_manual_physical_pages": arm["programming_manual"]["physical_pages"],
        "preprocessor": context_manifest["preprocessor"],
        "normalization": context_manifest["normalization"],
    }
    generation = {"temperature": temperature, "max_tokens": max_tokens, "seed": seed, "stream": False,
                  "think": False, "truncate": False, "shift": False, "num_ctx": num_ctx}
    record: dict[str, Any] = {
        "schema_version": semantic.SEMANTIC_RUN_SCHEMA_VERSION,
        "experiment_id": semantic.SEMANTIC_EXPERIMENT_ID,
        "arm": arm_name,
        "source_lock_id": context_manifest["source_lock_id"],
        "source_digests": context_manifest["source_digests"],
        "context_manifest_digest": context_manifest["manifest_digest"],
        "context": run_context,
        "prompt": prompt_meta,
        "runtime": {"transport": "ollama_native_chat", "runtime_label": runtime_label, "model_id": model,
                    "ollama_url": ollama_url, "configured_context_tokens": num_ctx},
        "generation": generation,
        "measurement": {"peak_memory_bytes": None, "peak_memory_status": "not_reported_by_remote_endpoint"},
        "trust_boundary": {
            "manufacturer_only_generation": True,
            "ai_emits_programming_relationship": False,
            "ai_emits_option_relationship": False,
            "ai_emits_security_relationship": False,
            "per_target_memory_geometry_facts": True,
            "per_target_package_hardware_facts": True,
            "ai_emits_memory_geometry_relationship": False,
            "ai_emits_package_hardware_relationship": False,
            "canonicalization_contract_visible_to_generation": False,
            "security_applicability_visible_to_generation": False,
            "ground_truth_visible_to_generation": False,
            "destructive_security_operation_admission": False,
            "canonical_dataset_admission": False,
            "production_admission": False,
        },
        "status": "pending",
    }
    raw_text = ""
    try:
        response = ollama_transport.ollama_native_chat(
            ollama_url=ollama_url, model=model, prompt=prompt, num_ctx=num_ctx, max_tokens=max_tokens,
            temperature=temperature, seed=seed, timeout_seconds=timeout_seconds,
        )
        raw_text = response["raw_text"]
        parsed = semantic.parse_model_result(raw_text, allowed_pages=semantic.allowed_pages_from_run_context(run_context))
        input_tokens = _known_int(response.get("prompt_eval_count"))
        generation_tokens = _known_int(response.get("eval_count"))
        record["status"] = "success"
        record["response_model"] = response.get("response_model")
        record["done"] = response.get("done")
        record["done_reason"] = response.get("done_reason")
        record["timing"] = {
            "ttft_ms": None, "total_time_ms": response.get("wall_time_ms"),
            "total_duration_ns": response.get("total_duration_ns"), "load_duration_ns": response.get("load_duration_ns"),
            "prompt_eval_duration_ns": response.get("prompt_eval_duration_ns"), "eval_duration_ns": response.get("eval_duration_ns"),
        }
        record["usage"] = {
            "input_tokens": input_tokens,
            "cached_input_tokens": _known_int(response.get("prompt_eval_cached_count")),
            "generation_tokens": generation_tokens,
            "total_tokens": input_tokens + generation_tokens if input_tokens is not None and generation_tokens is not None else None,
            "status": "runtime_reported",
        }
        record["response"] = parsed
    except (harness.ABBenchmarkError, semantic.SemanticExtractionError, ollama_transport.OllamaExtractionError) as exc:
        record["status"] = "error"
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}

    record["raw_response_sha256"] = harness.sha256_text(raw_text)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{arm_name}.semantic-v8"
    (output_dir / f"{stem}.raw.txt").write_text(raw_text, encoding="utf-8")
    (output_dir / f"{stem}.run.json").write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one STM32F103C v8 semantic extraction through bounded Ollama native chat")
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", required=True)
    parser.add_argument("--runtime-label", required=True)
    parser.add_argument("--arm", choices=("full_context", "reduced_context"), default="reduced_context")
    parser.add_argument("--num-ctx", type=int, default=65536)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    args = parser.parse_args()
    try:
        record = execute_arm(workspace=args.workspace, arm_name=args.arm, output_dir=args.output_dir,
                             ollama_url=args.ollama_url, model=args.model, runtime_label=args.runtime_label,
                             num_ctx=args.num_ctx, max_tokens=args.max_tokens, temperature=args.temperature,
                             seed=args.seed, timeout_seconds=args.timeout_seconds)
        print(f"Ollama v8 semantic extraction {record['status']}: arm={args.arm}; input_tokens={record.get('usage', {}).get('input_tokens')}; generation_tokens={record.get('usage', {}).get('generation_tokens')}")
        if record["status"] != "success":
            print(record.get("error", {}).get("message", "unknown error"), file=sys.stderr)
            return 1
        return 0
    except (OSError, json.JSONDecodeError, harness.ABBenchmarkError, semantic.SemanticExtractionError) as exc:
        print(f"Ollama v8 semantic extraction FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

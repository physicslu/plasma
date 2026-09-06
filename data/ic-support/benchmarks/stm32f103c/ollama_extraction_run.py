#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import ab_benchmark as harness


class OllamaExtractionError(RuntimeError):
    pass


def _json_object(payload: bytes, *, context: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OllamaExtractionError(f"{context}: response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise OllamaExtractionError(f"{context}: JSON root must be an object")
    return value


def ollama_native_chat(
    *,
    ollama_url: str,
    model: str,
    prompt: str,
    num_ctx: int,
    max_tokens: int,
    temperature: float,
    seed: int | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    if num_ctx < 2:
        raise OllamaExtractionError("num_ctx must be >= 2")
    if max_tokens < 1:
        raise OllamaExtractionError("max_tokens must be >= 1")

    options: dict[str, Any] = {
        "num_ctx": num_ctx,
        "num_predict": max_tokens,
        "temperature": temperature,
    }
    if seed is not None:
        options["seed"] = seed

    request_payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "truncate": False,
        "shift": False,
        "options": options,
    }
    endpoint = ollama_url.rstrip("/") + "/api/chat"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(request_payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )

    start_ns = time.perf_counter_ns()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            payload = _json_object(response.read(), context=endpoint)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise OllamaExtractionError(f"Ollama HTTP {exc.code}: {body[:500]}") from exc
    except TimeoutError as exc:
        raise OllamaExtractionError(
            f"Ollama extraction timed out after {timeout_seconds:g} seconds"
        ) from exc
    except urllib.error.URLError as exc:
        raise OllamaExtractionError(f"Ollama endpoint unavailable: {exc}") from exc
    end_ns = time.perf_counter_ns()

    message = payload.get("message")
    if not isinstance(message, dict):
        raise OllamaExtractionError("Ollama response message must be an object")
    raw_text = message.get("content")
    if not isinstance(raw_text, str) or raw_text == "":
        raise OllamaExtractionError("Ollama response returned empty content")

    return {
        "raw_text": raw_text,
        "response_model": payload.get("model"),
        "done": payload.get("done"),
        "done_reason": payload.get("done_reason"),
        "wall_time_ms": (end_ns - start_ns) / 1_000_000.0,
        "total_duration_ns": payload.get("total_duration"),
        "load_duration_ns": payload.get("load_duration"),
        "prompt_eval_count": payload.get("prompt_eval_count"),
        "prompt_eval_cached_count": payload.get("prompt_eval_cached_count"),
        "prompt_eval_duration_ns": payload.get("prompt_eval_duration"),
        "eval_count": payload.get("eval_count"),
        "eval_duration_ns": payload.get("eval_duration"),
    }


def _known_int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def execute_arm(
    *,
    workspace: Path,
    arm_name: str,
    output_dir: Path,
    ollama_url: str,
    model: str,
    runtime_label: str,
    num_ctx: int,
    max_tokens: int,
    temperature: float,
    seed: int | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    context, arm, context_manifest = harness.load_arm_context(workspace, arm_name)
    prompt, prompt_meta = harness.render_prompt(context)
    generation = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": seed,
        "stream": False,
        "think": False,
        "truncate": False,
        "shift": False,
        "num_ctx": num_ctx,
    }
    record: dict[str, Any] = {
        "schema_version": harness.RUN_SCHEMA_VERSION,
        "experiment_id": harness.EXPERIMENT_ID,
        "arm": arm_name,
        "trial_index": 1,
        "order_position": 1,
        "source_lock_id": context_manifest["source_lock_id"],
        "source_digests": context_manifest["source_digests"],
        "context_manifest_digest": context_manifest["manifest_digest"],
        "context": {
            "datasheet_mode": arm["datasheet"]["mode"],
            "datasheet_sha256": arm["datasheet"]["sha256"],
            "datasheet_input_bytes": arm["datasheet"]["byte_length"],
            "datasheet_physical_pages": arm["datasheet"]["physical_pages"],
            "programming_manual_sha256": arm["programming_manual"]["sha256"],
            "programming_manual_input_bytes": arm["programming_manual"]["byte_length"],
            "programming_manual_physical_pages": arm["programming_manual"]["physical_pages"],
            "preprocessor": context_manifest["preprocessor"],
            "normalization": context_manifest["normalization"],
        },
        "prompt": prompt_meta,
        "runtime": {
            "transport": "ollama_native_chat",
            "runtime_label": runtime_label,
            "model_id": model,
            "ollama_url": ollama_url,
            "configured_context_tokens": num_ctx,
        },
        "generation": generation,
        "measurement": {
            "peak_memory_bytes": None,
            "peak_memory_status": "not_reported_by_remote_endpoint",
        },
        "status": "pending",
    }

    raw_text = ""
    try:
        response = ollama_native_chat(
            ollama_url=ollama_url,
            model=model,
            prompt=prompt,
            num_ctx=num_ctx,
            max_tokens=max_tokens,
            temperature=temperature,
            seed=seed,
            timeout_seconds=timeout_seconds,
        )
        raw_text = response["raw_text"]
        parsed = harness.parse_model_result(raw_text)
        input_tokens = _known_int(response.get("prompt_eval_count"))
        generation_tokens = _known_int(response.get("eval_count"))
        record["status"] = "success"
        record["response_model"] = response.get("response_model")
        record["streaming_observed"] = False
        record["done"] = response.get("done")
        record["done_reason"] = response.get("done_reason")
        record["timing"] = {
            "ttft_ms": None,
            "total_time_ms": response.get("wall_time_ms"),
            "total_duration_ns": response.get("total_duration_ns"),
            "load_duration_ns": response.get("load_duration_ns"),
            "prompt_eval_duration_ns": response.get("prompt_eval_duration_ns"),
            "eval_duration_ns": response.get("eval_duration_ns"),
        }
        record["usage"] = {
            "input_tokens": input_tokens,
            "cached_input_tokens": _known_int(response.get("prompt_eval_cached_count")),
            "generation_tokens": generation_tokens,
            "total_tokens": (
                input_tokens + generation_tokens
                if input_tokens is not None and generation_tokens is not None
                else None
            ),
            "status": "runtime_reported",
        }
        record["response"] = parsed
    except (harness.ABBenchmarkError, OllamaExtractionError) as exc:
        record["status"] = "error"
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}

    record["raw_response_sha256"] = harness.sha256_text(raw_text)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / f"{arm_name}.raw.txt").write_text(raw_text, encoding="utf-8")
    (output_dir / f"{arm_name}.run.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return record


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run one STM32F103C benchmark arm through Ollama native chat with an explicit context budget"
    )
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
        record = execute_arm(
            workspace=args.workspace,
            arm_name=args.arm,
            output_dir=args.output_dir,
            ollama_url=args.ollama_url,
            model=args.model,
            runtime_label=args.runtime_label,
            num_ctx=args.num_ctx,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            seed=args.seed,
            timeout_seconds=args.timeout_seconds,
        )
        print(
            f"Ollama extraction {record['status']}: arm={args.arm}; "
            f"input_tokens={record.get('usage', {}).get('input_tokens')}; "
            f"generation_tokens={record.get('usage', {}).get('generation_tokens')}"
        )
        if record["status"] != "success":
            print(record.get("error", {}).get("message", "unknown error"), file=sys.stderr)
            return 1
        return 0
    except (OSError, json.JSONDecodeError, harness.ABBenchmarkError, OllamaExtractionError) as exc:
        print(f"Ollama extraction FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import ab_benchmark as harness

PROBE_SCHEMA_VERSION = "0.1.0"
OVER_CONTEXT_RE = re.compile(
    r"input length \((?P<input_tokens>\d+) tokens\) exceeds .*context length "
    r"\((?P<context_tokens>\d+) tokens\)",
    re.IGNORECASE,
)


class OllamaProbeError(RuntimeError):
    pass


def _json_object(payload: bytes, *, context: str) -> dict[str, Any]:
    try:
        value = json.loads(payload.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise OllamaProbeError(f"{context}: response is not valid JSON") from exc
    if not isinstance(value, dict):
        raise OllamaProbeError(f"{context}: JSON root must be an object")
    return value


def _request_json(
    request: urllib.request.Request,
    *,
    timeout_seconds: float,
) -> dict[str, Any]:
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            return _json_object(response.read(), context=str(request.full_url))
    except urllib.error.HTTPError:
        raise
    except urllib.error.URLError as exc:
        raise OllamaProbeError(f"Ollama endpoint unavailable: {exc}") from exc
    except TimeoutError as exc:
        raise OllamaProbeError(
            f"Ollama context probe timed out after {timeout_seconds:g} seconds"
        ) from exc


def running_model_snapshot(*, ollama_url: str, model: str, timeout_seconds: float) -> dict[str, Any] | None:
    request = urllib.request.Request(
        ollama_url.rstrip("/") + "/api/ps",
        headers={"Accept": "application/json"},
        method="GET",
    )
    payload = _request_json(request, timeout_seconds=timeout_seconds)
    models = payload.get("models")
    if not isinstance(models, list):
        raise OllamaProbeError("/api/ps: models must be an array")
    for item in models:
        if not isinstance(item, dict):
            continue
        if item.get("name") == model or item.get("model") == model:
            details = item.get("details") if isinstance(item.get("details"), dict) else {}
            return {
                "name": item.get("name"),
                "model": item.get("model"),
                "digest": item.get("digest"),
                "size_bytes": item.get("size"),
                "size_vram_bytes": item.get("size_vram"),
                "context_length": item.get("context_length"),
                "family": details.get("family"),
                "parameter_size": details.get("parameter_size"),
                "quantization_level": details.get("quantization_level"),
            }
    return None


def _over_context_result(
    *,
    body: dict[str, Any],
    status_code: int,
    num_ctx: int,
    elapsed_ms: float,
) -> dict[str, Any] | None:
    error = body.get("error")
    if not isinstance(error, str):
        return None
    match = OVER_CONTEXT_RE.search(error)
    if match is None:
        return None
    input_tokens = int(match.group("input_tokens"))
    runtime_context_tokens = int(match.group("context_tokens"))
    return {
        "status": "over_context",
        "http_status": status_code,
        "prompt_tokens": input_tokens,
        "configured_context_tokens": num_ctx,
        "runtime_context_tokens": runtime_context_tokens,
        "headroom_tokens": num_ctx - input_tokens,
        "probe_elapsed_ms": elapsed_ms,
        "runtime_error": error,
    }


def probe_prompt(
    *,
    ollama_url: str,
    model: str,
    prompt: str,
    num_ctx: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    if num_ctx < 2:
        raise OllamaProbeError("num_ctx must be >= 2")
    endpoint = ollama_url.rstrip("/") + "/api/chat"
    request_payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "truncate": False,
        "shift": False,
        "options": {
            "num_ctx": num_ctx,
            "num_predict": 1,
            "temperature": 0,
        },
    }
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(request_payload, separators=(",", ":")).encode("utf-8"),
        headers={"Content-Type": "application/json", "Accept": "application/json"},
        method="POST",
    )
    start_ns = time.perf_counter_ns()
    try:
        response = _request_json(request, timeout_seconds=timeout_seconds)
    except urllib.error.HTTPError as exc:
        elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
        body = _json_object(exc.read(), context=f"Ollama HTTP {exc.code}")
        over_context = _over_context_result(
            body=body,
            status_code=exc.code,
            num_ctx=num_ctx,
            elapsed_ms=elapsed_ms,
        )
        if over_context is not None:
            return over_context
        error = body.get("error")
        raise OllamaProbeError(
            f"Ollama context probe HTTP {exc.code}: {error if isinstance(error, str) else body}"
        ) from exc

    elapsed_ms = (time.perf_counter_ns() - start_ns) / 1_000_000.0
    prompt_tokens = response.get("prompt_eval_count")
    if not isinstance(prompt_tokens, int) or isinstance(prompt_tokens, bool):
        raise OllamaProbeError("Ollama response did not report prompt_eval_count")
    return {
        "status": "fits_context",
        "http_status": 200,
        "prompt_tokens": prompt_tokens,
        "configured_context_tokens": num_ctx,
        "runtime_context_tokens": num_ctx,
        "headroom_tokens": num_ctx - prompt_tokens,
        "probe_elapsed_ms": elapsed_ms,
        "prompt_eval_duration_ns": response.get("prompt_eval_duration"),
        "load_duration_ns": response.get("load_duration"),
        "total_duration_ns": response.get("total_duration"),
    }


def _reduction_percent(full: int | None, reduced: int | None) -> float | None:
    if full is None or reduced is None or full == 0:
        return None
    return (full - reduced) / full * 100.0


def probe_workspace(
    *,
    workspace: Path,
    ollama_url: str,
    model: str,
    num_ctx: int,
    timeout_seconds: float,
) -> dict[str, Any]:
    arms: dict[str, Any] = {}
    for arm_name in ("full_context", "reduced_context"):
        context, _, manifest = harness.load_arm_context(workspace, arm_name)
        prompt, prompt_meta = harness.render_prompt(context)
        measurement = probe_prompt(
            ollama_url=ollama_url,
            model=model,
            prompt=prompt,
            num_ctx=num_ctx,
            timeout_seconds=timeout_seconds,
        )
        arms[arm_name] = {
            "prompt": prompt_meta,
            "measurement": measurement,
        }

    full_tokens = arms["full_context"]["measurement"].get("prompt_tokens")
    reduced_tokens = arms["reduced_context"]["measurement"].get("prompt_tokens")
    full_tokens = full_tokens if isinstance(full_tokens, int) else None
    reduced_tokens = reduced_tokens if isinstance(reduced_tokens, int) else None
    runtime_snapshot = running_model_snapshot(
        ollama_url=ollama_url,
        model=model,
        timeout_seconds=timeout_seconds,
    )
    report: dict[str, Any] = {
        "schema_version": PROBE_SCHEMA_VERSION,
        "experiment_id": harness.EXPERIMENT_ID,
        "source_lock_id": manifest["source_lock_id"],
        "context_manifest_digest": manifest["manifest_digest"],
        "runtime": {
            "transport": "ollama_native_chat_context_probe",
            "ollama_url": ollama_url,
            "model_id": model,
            "configured_context_tokens": num_ctx,
            "truncate": False,
            "shift": False,
            "num_predict": 1,
            "thinking": False,
            "running_model_after_probe": runtime_snapshot,
            "running_context_matches_configured": (
                runtime_snapshot is not None
                and runtime_snapshot.get("context_length") == num_ctx
            ),
        },
        "arms": arms,
        "comparison": {
            "full_prompt_tokens": full_tokens,
            "reduced_prompt_tokens": reduced_tokens,
            "token_reduction_percent": _reduction_percent(full_tokens, reduced_tokens),
            "both_fit_configured_context": all(
                arms[name]["measurement"]["status"] == "fits_context"
                for name in ("full_context", "reduced_context")
            ),
        },
        "trust_boundary": {
            "ground_truth_used": False,
            "probe_is_accuracy_benchmark": False,
            "prompt_truncation_allowed": False,
        },
    }
    report["report_digest"] = harness.canonical_sha256(report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Measure exact Ollama prompt-token demand for the prepared STM32F103C A/B arms "
            "without increasing the configured context budget or allowing truncation"
        )
    )
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", required=True)
    parser.add_argument("--num-ctx", type=int, default=32768)
    parser.add_argument("--timeout-seconds", type=float, default=300.0)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    try:
        report = probe_workspace(
            workspace=args.workspace,
            ollama_url=args.ollama_url,
            model=args.model,
            num_ctx=args.num_ctx,
            timeout_seconds=args.timeout_seconds,
        )
        if args.output is not None:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        for arm_name in ("full_context", "reduced_context"):
            measurement = report["arms"][arm_name]["measurement"]
            print(
                f"- {arm_name}: {measurement['status']}; "
                f"prompt_tokens={measurement.get('prompt_tokens')}; "
                f"headroom={measurement.get('headroom_tokens')}"
            )
        comparison = report["comparison"]
        print(
            "Ollama context probe PASS: "
            f"token reduction={comparison['token_reduction_percent']}; "
            f"both_fit_configured_context={comparison['both_fit_configured_context']}"
        )
        return 0
    except (OSError, json.JSONDecodeError, harness.ABBenchmarkError, OllamaProbeError) as exc:
        print(f"Ollama context probe FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

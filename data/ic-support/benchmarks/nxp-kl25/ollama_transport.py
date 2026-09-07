#!/usr/bin/env python3
from __future__ import annotations

import json
import socket
import time
import urllib.error
import urllib.request
from typing import Any

import semantic_runner as runner


def ollama_native_chat_transport(
    *,
    prompt: str,
    model_id: str,
    runtime_label: str,
    options: dict[str, Any],
) -> dict[str, Any]:
    del runtime_label  # retained by the orchestration record, not sent to the provider
    ollama_url = str(options.get("ollama_url", "http://127.0.0.1:11434")).rstrip("/")
    num_ctx = int(options.get("num_ctx", 65536))
    max_tokens = int(options.get("max_tokens", 4096))
    temperature = float(options.get("temperature", 0.0))
    timeout_seconds = float(options.get("timeout_seconds", 1800.0))
    seed = options.get("seed")
    format_schema = options.get("format_schema")

    if not prompt:
        raise runner.SemanticTransportProtocolError("Ollama prompt must not be empty")
    if not model_id:
        raise runner.SemanticTransportProtocolError("Ollama model_id must not be empty")
    if num_ctx <= 0 or max_tokens <= 0 or timeout_seconds <= 0:
        raise runner.SemanticTransportProtocolError("Ollama numeric request bounds must be positive")
    if not isinstance(format_schema, dict) or not format_schema:
        raise runner.SemanticTransportProtocolError("Ollama structured output requires a non-empty JSON Schema object")

    generation_options: dict[str, Any] = {
        "num_ctx": num_ctx,
        "num_predict": max_tokens,
        "temperature": temperature,
    }
    if seed is not None:
        generation_options["seed"] = int(seed)
    payload = {
        "model": model_id,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "think": False,
        "truncate": False,
        "shift": False,
        "format": format_schema,
        "options": generation_options,
    }
    request = urllib.request.Request(
        f"{ollama_url}/api/chat",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
    except (TimeoutError, socket.timeout) as exc:
        raise runner.SemanticTransportTimeout(f"Ollama request timed out after {timeout_seconds}s") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise runner.SemanticTransportUnavailable(f"Ollama HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise runner.SemanticTransportTimeout(f"Ollama request timed out after {timeout_seconds}s") from exc
        raise runner.SemanticTransportUnavailable(f"Ollama unavailable: {exc.reason}") from exc
    except OSError as exc:
        raise runner.SemanticTransportUnavailable(f"Ollama transport failed: {exc}") from exc
    wall_ms = (time.perf_counter() - started) * 1000.0

    try:
        outer = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise runner.SemanticTransportProtocolError("Ollama response is not valid UTF-8 JSON") from exc
    if not isinstance(outer, dict):
        raise runner.SemanticTransportProtocolError("Ollama response JSON root must be an object")
    message = outer.get("message")
    if not isinstance(message, dict):
        raise runner.SemanticTransportProtocolError("Ollama response missing message object")
    raw_text = message.get("content")
    if not isinstance(raw_text, str) or raw_text.strip() == "":
        raise runner.SemanticTransportProtocolError("Ollama response message.content is empty")

    return {
        "raw_text": raw_text,
        "response_model": outer.get("model"),
        "done": outer.get("done"),
        "done_reason": outer.get("done_reason"),
        "usage": {
            "input_tokens": outer.get("prompt_eval_count"),
            "generation_tokens": outer.get("eval_count"),
        },
        "timing": {
            "wall_time_ms": wall_ms,
            "total_duration_ns": outer.get("total_duration"),
            "load_duration_ns": outer.get("load_duration"),
            "prompt_eval_duration_ns": outer.get("prompt_eval_duration"),
            "eval_duration_ns": outer.get("eval_duration"),
        },
    }

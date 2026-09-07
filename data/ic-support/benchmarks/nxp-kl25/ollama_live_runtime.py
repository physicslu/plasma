#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import socket
import urllib.error
import urllib.parse
import urllib.request
from typing import Any

import semantic_runner as runner

MODEL_DIGEST = re.compile(r"^(?:sha256:)?[0-9a-f]{64}$", re.IGNORECASE)
LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def normalize_loopback_ollama_url(value: str) -> str:
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme != "http":
        raise runner.SemanticTransportProtocolError("live qualification requires an http loopback Ollama URL")
    if parsed.username is not None or parsed.password is not None:
        raise runner.SemanticTransportProtocolError("Ollama URL credentials are not allowed")
    if parsed.hostname not in LOOPBACK_HOSTS:
        raise runner.SemanticTransportProtocolError("live qualification requires a loopback Ollama endpoint")
    if parsed.path not in {"", "/"} or parsed.params or parsed.query or parsed.fragment:
        raise runner.SemanticTransportProtocolError("Ollama URL must be an endpoint root")
    port = parsed.port or 80
    host = f"[{parsed.hostname}]" if ":" in parsed.hostname else parsed.hostname
    return f"http://{host}:{port}"


def _get_json(url: str, *, timeout_seconds: float) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            body = response.read()
    except (TimeoutError, socket.timeout) as exc:
        raise runner.SemanticTransportTimeout(f"Ollama preflight timed out after {timeout_seconds}s") from exc
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise runner.SemanticTransportUnavailable(f"Ollama preflight HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        if isinstance(exc.reason, (TimeoutError, socket.timeout)):
            raise runner.SemanticTransportTimeout(f"Ollama preflight timed out after {timeout_seconds}s") from exc
        raise runner.SemanticTransportUnavailable(f"Ollama preflight unavailable: {exc.reason}") from exc
    except OSError as exc:
        raise runner.SemanticTransportUnavailable(f"Ollama preflight failed: {exc}") from exc

    try:
        value = json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise runner.SemanticTransportProtocolError("Ollama preflight response is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict):
        raise runner.SemanticTransportProtocolError("Ollama preflight JSON root must be an object")
    return value


def query_ollama_runtime_identity(
    *,
    ollama_url: str,
    model_id: str,
    timeout_seconds: float = 10.0,
) -> dict[str, Any]:
    root = normalize_loopback_ollama_url(ollama_url)
    version_doc = _get_json(f"{root}/api/version", timeout_seconds=timeout_seconds)
    version = version_doc.get("version")
    if not isinstance(version, str) or not version.strip():
        raise runner.SemanticTransportProtocolError("Ollama /api/version did not return a version string")

    tags_doc = _get_json(f"{root}/api/tags", timeout_seconds=timeout_seconds)
    models = tags_doc.get("models")
    if not isinstance(models, list):
        raise runner.SemanticTransportProtocolError("Ollama /api/tags did not return a models array")

    matches: list[dict[str, Any]] = []
    for item in models:
        if not isinstance(item, dict):
            continue
        if item.get("name") == model_id or item.get("model") == model_id:
            matches.append(item)
    if len(matches) != 1:
        raise runner.SemanticTransportProtocolError(
            f"Ollama model identity must resolve exactly once for {model_id!r}; matches={len(matches)}"
        )
    digest = matches[0].get("digest")
    if not isinstance(digest, str) or MODEL_DIGEST.fullmatch(digest) is None:
        raise runner.SemanticTransportProtocolError("Ollama model digest is missing or malformed")

    return {
        "ollama_url_policy": "loopback_only",
        "ollama_version": version,
        "model_id": model_id,
        "model_digest": digest,
        "model_size_bytes": matches[0].get("size"),
        "model_modified_at": matches[0].get("modified_at"),
    }

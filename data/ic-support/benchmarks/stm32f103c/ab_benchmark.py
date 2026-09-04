#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
IC_SUPPORT_ROOT = HERE.parents[1]
EVIDENCE_PACK_ROOT = IC_SUPPORT_ROOT / "evidence-pack"
SOURCE_LOCK = HERE / "source-lock.json"
OBSERVED_SCHEMA = HERE / "extraction-observed.schema.json"
BENCHMARK_CONTRACT = HERE / "evidence-pack-benchmark-v0.json"
PROMPT_TEMPLATE = HERE / "ab-benchmark-prompt-v0.txt"
POLICY = EVIDENCE_PACK_ROOT / "policies" / "st-ds5319-rev20-programming-v0.json"
SOURCE_TRANSPORT = IC_SUPPORT_ROOT / "evidence" / "source_integrity.py"
DS_SOURCE_ID = "st_ds5319_rev20"
PM_SOURCE_ID = "st_pm0075_rev2"
EXPERIMENT_ID = "stm32f103c-full-vs-evidence-pack-v0"
RUN_SCHEMA_VERSION = "0.1.0"
CONTEXT_SCHEMA_VERSION = "0.1.0"

sys.path.insert(0, str(EVIDENCE_PACK_ROOT))
from preprocessing import (  # noqa: E402
    DEFAULT_NORMALIZATION,
    extract_pdf_text,
    load_json as load_evidence_json,
    normalize_page_text,
    preprocess_locked_pdf,
    sha256_file,
    split_physical_pages,
)
from semantic_pack import (  # noqa: E402
    DEFAULT_RULES,
    DEFAULT_TAXONOMY,
    build_semantic_artifacts,
    materialize_evidence_text,
)


class ABBenchmarkError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ABBenchmarkError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def canonical_sha256(value: Any) -> str:
    return hashlib.sha256(canonical_bytes(value)).hexdigest()


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_text(value: str) -> str:
    return sha256_bytes(value.encode("utf-8"))


def _source_entry(source_lock: dict[str, Any], source_id: str) -> dict[str, Any]:
    matches = [
        source
        for source in source_lock.get("sources", [])
        if isinstance(source, dict) and source.get("source_id") == source_id
    ]
    require(len(matches) == 1, f"{source_id}: exact source-lock entry required")
    return matches[0]


def manufacturer_source_digests(source_lock: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    for source_id in (DS_SOURCE_ID, PM_SOURCE_ID):
        source = _source_entry(source_lock, source_id)
        integrity = source.get("integrity")
        require(isinstance(integrity, dict), f"{source_id}: integrity required")
        algorithm = integrity.get("algorithm")
        digest = integrity.get("digest")
        require(isinstance(algorithm, str) and isinstance(digest, str), f"{source_id}: digest required")
        out[source_id] = f"{algorithm}:{digest}"
    return out


def _load_source_transport():
    spec = importlib.util.spec_from_file_location("plasma_ic_source_integrity", SOURCE_TRANSPORT)
    require(spec is not None and spec.loader is not None, "cannot load canonical source transport")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _materialize_source(
    *,
    source_lock: dict[str, Any],
    source_id: str,
    destination: Path,
    provided_path: Path | None,
    fetch_sources: bool,
) -> Path:
    source = _source_entry(source_lock, source_id)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if provided_path is not None:
        require(provided_path.is_file(), f"{provided_path}: source file not found")
        shutil.copyfile(provided_path, destination)
    elif fetch_sources:
        transport = _load_source_transport()
        payload, final_url = transport.fetch_bytes(source["requested_url"])
        destination.write_bytes(payload)
        print(f"materialized {source_id}: {len(payload)} bytes from {final_url}")
    else:
        raise ABBenchmarkError(f"{source_id}: provide a local locked PDF or use --fetch-sources")
    return destination


def normalized_pages_from_pdf(pdf: Path, manifest: dict[str, Any], pdftotext: str) -> list[str]:
    extracted_text, tool = extract_pdf_text(pdf, pdftotext)
    require(tool == manifest["preprocessor"], "pdftotext fingerprint changed during context materialization")
    normalization = load_evidence_json(DEFAULT_NORMALIZATION)
    pages = [normalize_page_text(page, normalization) for page in split_physical_pages(extracted_text)]
    require(len(pages) == manifest["page_count"], "normalized page count mismatch")
    for page, observed in zip(pages, manifest["pages"]):
        require(
            sha256_text(page) == observed["normalized_content_sha256"],
            f"page {observed['pdf_page_index']}: normalized content drift",
        )
    return pages


def materialize_full_document_text(
    *, source_id: str, pages: list[str], manifest: dict[str, Any]
) -> str:
    require(len(pages) == manifest["page_count"], "full-document page count mismatch")
    chunks = [f"# Plasma Manufacturer Evidence\n# source_id={source_id}\n"]
    for index, page in enumerate(pages):
        digest = manifest["pages"][index]["normalized_content_sha256"]
        chunks.append(f"\n===== {source_id} physical-page {index} sha256={digest} =====\n")
        chunks.append(page)
    return "".join(chunks)


def _write_context_file(path: Path, text: str) -> dict[str, Any]:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    payload = text.encode("utf-8")
    return {
        "file": path.name,
        "sha256": sha256_bytes(payload),
        "byte_length": len(payload),
    }


def prepare_workspace(
    *,
    workspace: Path,
    ds_pdf: Path | None,
    pm_pdf: Path | None,
    fetch_sources: bool,
    pdftotext: str,
) -> dict[str, Any]:
    source_lock = load_json(SOURCE_LOCK)
    require(source_lock.get("source_lock_id") == "stm32f103c-source-lock-v0", "unexpected source-lock ID")
    workspace.mkdir(parents=True, exist_ok=True)
    source_dir = workspace / "sources"
    context_dir = workspace / "contexts"
    ds_local = _materialize_source(
        source_lock=source_lock,
        source_id=DS_SOURCE_ID,
        destination=source_dir / f"{DS_SOURCE_ID}.pdf",
        provided_path=ds_pdf,
        fetch_sources=fetch_sources,
    )
    pm_local = _materialize_source(
        source_lock=source_lock,
        source_id=PM_SOURCE_ID,
        destination=source_dir / f"{PM_SOURCE_ID}.pdf",
        provided_path=pm_pdf,
        fetch_sources=fetch_sources,
    )

    ds_manifest = preprocess_locked_pdf(
        pdf=ds_local,
        source_lock_path=SOURCE_LOCK,
        source_id=DS_SOURCE_ID,
        normalization_path=DEFAULT_NORMALIZATION,
        pdftotext=pdftotext,
    )
    pm_manifest = preprocess_locked_pdf(
        pdf=pm_local,
        source_lock_path=SOURCE_LOCK,
        source_id=PM_SOURCE_ID,
        normalization_path=DEFAULT_NORMALIZATION,
        pdftotext=pdftotext,
    )
    require(ds_manifest["preprocessor"] == pm_manifest["preprocessor"], "DS/PM preprocessor fingerprints differ")
    require(ds_manifest["normalization"] == pm_manifest["normalization"], "DS/PM normalization fingerprints differ")

    ds_pages = normalized_pages_from_pdf(ds_local, ds_manifest, pdftotext)
    pm_pages = normalized_pages_from_pdf(pm_local, pm_manifest, pdftotext)
    full_ds = materialize_full_document_text(source_id=DS_SOURCE_ID, pages=ds_pages, manifest=ds_manifest)
    full_pm = materialize_full_document_text(source_id=PM_SOURCE_ID, pages=pm_pages, manifest=pm_manifest)

    policy = load_json(POLICY)
    taxonomy = load_evidence_json(DEFAULT_TAXONOMY)
    rules = load_evidence_json(DEFAULT_RULES)
    semantic_builder_sha = sha256_file(EVIDENCE_PACK_ROOT / "semantic_pack.py")
    artifacts = build_semantic_artifacts(
        manifest=ds_manifest,
        policy=policy,
        source_lock=source_lock,
        taxonomy=taxonomy,
        rules=rules,
        builder_sha256=semantic_builder_sha,
        normalized_pages=ds_pages,
    )
    reduced_ds = materialize_evidence_text(
        normalized_pages=ds_pages,
        catalog=artifacts["catalog"],
        pack=artifacts["pack"],
    )
    catalog_by_id = {unit["unit_id"]: unit for unit in artifacts["catalog"]["units"]}
    reduced_pages = sorted(
        int(catalog_by_id[entry["unit_id"]]["pdf_page_index"])
        for entry in artifacts["pack"]["included_units"]
    )

    full_ds_meta = _write_context_file(context_dir / "ds-full.txt", full_ds)
    reduced_ds_meta = _write_context_file(context_dir / "ds-reduced.txt", reduced_ds)
    pm_meta = _write_context_file(context_dir / "pm-full.txt", full_pm)

    manifest: dict[str, Any] = {
        "schema_version": CONTEXT_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "source_lock_id": source_lock["source_lock_id"],
        "source_digests": manufacturer_source_digests(source_lock),
        "preprocessor": ds_manifest["preprocessor"],
        "normalization": ds_manifest["normalization"],
        "evidence_pack": {
            "pack_id": artifacts["pack"]["pack_id"],
            "pack_digest": artifacts["pack"]["pack_digest"],
            "catalog_digest": artifacts["catalog"]["catalog_digest"],
            "included_datasheet_pages": reduced_pages,
            "included_datasheet_page_count": len(reduced_pages),
        },
        "arms": {
            "full_context": {
                "datasheet": {
                    "mode": "FULL_LOCKED_SOURCE",
                    **full_ds_meta,
                    "source_id": DS_SOURCE_ID,
                    "physical_pages": list(range(ds_manifest["page_count"])),
                },
                "programming_manual": {
                    "mode": "FULL_LOCKED_SOURCE",
                    **pm_meta,
                    "source_id": PM_SOURCE_ID,
                    "physical_pages": list(range(pm_manifest["page_count"])),
                },
            },
            "reduced_context": {
                "datasheet": {
                    "mode": "DETERMINISTIC_EVIDENCE_PACK",
                    **reduced_ds_meta,
                    "source_id": DS_SOURCE_ID,
                    "physical_pages": reduced_pages,
                    "pack_id": artifacts["pack"]["pack_id"],
                    "pack_digest": artifacts["pack"]["pack_digest"],
                },
                "programming_manual": {
                    "mode": "FULL_LOCKED_SOURCE",
                    **pm_meta,
                    "source_id": PM_SOURCE_ID,
                    "physical_pages": list(range(pm_manifest["page_count"])),
                },
            },
        },
        "trust_boundary": {
            "manufacturer_only": True,
            "ground_truth_used_during_prepare": False,
            "ground_truth_used_during_generation": False,
            "canonical_dataset_admission": False,
            "production_admission": False,
        },
    }
    manifest["manifest_digest"] = canonical_sha256(manifest)
    (workspace / "context-manifest.json").write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(
        "A/B workspace PASS: "
        f"DS {len(ds_pages)} pages -> {len(reduced_pages)} Evidence Pack pages; "
        f"PM {len(pm_pages)} pages"
    )
    return manifest


def validate_context_manifest(workspace: Path, manifest: dict[str, Any]) -> None:
    digest = manifest.get("manifest_digest")
    payload = {key: value for key, value in manifest.items() if key != "manifest_digest"}
    require(digest == canonical_sha256(payload), "context manifest digest mismatch")
    require(manifest.get("experiment_id") == EXPERIMENT_ID, "context experiment mismatch")
    require(manifest.get("trust_boundary", {}).get("ground_truth_used_during_generation") is False, "generation trust boundary mismatch")
    context_dir = workspace / "contexts"
    for arm_name in ("full_context", "reduced_context"):
        arm = manifest.get("arms", {}).get(arm_name)
        require(isinstance(arm, dict), f"{arm_name}: context arm required")
        for component in ("datasheet", "programming_manual"):
            meta = arm.get(component)
            require(isinstance(meta, dict), f"{arm_name}.{component}: metadata required")
            path = context_dir / str(meta.get("file"))
            require(path.is_file(), f"{path}: context file missing")
            payload_bytes = path.read_bytes()
            require(len(payload_bytes) == meta.get("byte_length"), f"{path}: byte length drift")
            require(sha256_bytes(payload_bytes) == meta.get("sha256"), f"{path}: digest drift")


def load_arm_context(workspace: Path, arm_name: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    manifest = load_json(workspace / "context-manifest.json")
    validate_context_manifest(workspace, manifest)
    arm = manifest["arms"].get(arm_name)
    require(isinstance(arm, dict), f"unknown benchmark arm: {arm_name}")
    context_dir = workspace / "contexts"
    datasheet = (context_dir / arm["datasheet"]["file"]).read_text(encoding="utf-8")
    programming_manual = (context_dir / arm["programming_manual"]["file"]).read_text(encoding="utf-8")
    context = datasheet + "\n\n" + programming_manual
    return context, arm, manifest


def render_prompt(context: str) -> tuple[str, dict[str, Any]]:
    template = PROMPT_TEMPLATE.read_text(encoding="utf-8")
    schema_text = OBSERVED_SCHEMA.read_text(encoding="utf-8").strip()
    require("{{OBSERVED_SCHEMA}}" in template and "{{CONTEXT}}" in template, "prompt template placeholders missing")
    rendered = template.replace("{{OBSERVED_SCHEMA}}", schema_text).replace("{{CONTEXT}}", context)
    return rendered, {
        "template_sha256": sha256_text(template),
        "observed_schema_sha256": sha256_text(schema_text),
        "rendered_sha256": sha256_text(rendered),
        "rendered_byte_length": len(rendered.encode("utf-8")),
    }


def _type_matches(value: Any, type_name: str) -> bool:
    if type_name == "null":
        return value is None
    if type_name == "object":
        return isinstance(value, dict)
    if type_name == "array":
        return isinstance(value, list)
    if type_name == "string":
        return isinstance(value, str)
    if type_name == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if type_name == "boolean":
        return isinstance(value, bool)
    return False


def validate_against_schema(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []
    schema_type = schema.get("type")
    allowed_types = schema_type if isinstance(schema_type, list) else [schema_type]
    allowed_types = [item for item in allowed_types if isinstance(item, str)]
    if allowed_types and not any(_type_matches(value, item) for item in allowed_types):
        return [f"{path}: type mismatch, allowed={allowed_types}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: value not in enum")
    if isinstance(value, int) and not isinstance(value, bool) and isinstance(schema.get("minimum"), int):
        if value < schema["minimum"]:
            errors.append(f"{path}: below minimum")
    if isinstance(value, dict):
        properties = schema.get("properties", {})
        required = schema.get("required", [])
        for key in required:
            if key not in value:
                errors.append(f"{path}.{key}: missing")
        if schema.get("additionalProperties") is False:
            for key in value:
                if key not in properties:
                    errors.append(f"{path}.{key}: unexpected")
        for key, child in value.items():
            child_schema = properties.get(key)
            if isinstance(child_schema, dict):
                errors.extend(validate_against_schema(child, child_schema, f"{path}.{key}"))
    if isinstance(value, list) and isinstance(schema.get("items"), dict):
        for index, child in enumerate(value):
            errors.extend(validate_against_schema(child, schema["items"], f"{path}[{index}]"))
    return errors


def parse_model_result(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if text.startswith("```json") and text.endswith("```"):
        text = text[len("```json") : -3].strip()
    elif text.startswith("```") and text.endswith("```"):
        text = text[3:-3].strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ABBenchmarkError(f"model response is not one JSON object: {exc}") from exc
    require(isinstance(payload, dict), "model response root must be object")
    require(set(payload) == {"observed", "evidence"}, "model response requires exactly observed + evidence")
    require(isinstance(payload["observed"], dict), "model observed must be object")
    require(isinstance(payload["evidence"], dict), "model evidence must be object")
    schema = load_json(OBSERVED_SCHEMA)
    errors = validate_against_schema(payload["observed"], schema)
    require(not errors, "observed schema validation failed: " + "; ".join(errors[:10]))
    return payload


def _delta_text(delta: Any) -> str:
    if isinstance(delta, str):
        return delta
    if isinstance(delta, list):
        parts: list[str] = []
        for item in delta:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "".join(parts)
    return ""


def openai_compatible_chat(
    *,
    base_url: str,
    model: str,
    prompt: str,
    api_key: str | None,
    temperature: float,
    max_tokens: int,
    seed: int | None,
    timeout_seconds: float,
) -> dict[str, Any]:
    endpoint = base_url.rstrip("/") + "/chat/completions"
    request_payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": True,
        "stream_options": {"include_usage": True},
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if seed is not None:
        request_payload["seed"] = seed
    headers = {"Content-Type": "application/json", "Accept": "text/event-stream"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        endpoint,
        data=json.dumps(request_payload, separators=(",", ":")).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    start_ns = time.perf_counter_ns()
    first_content_ns: int | None = None
    content_parts: list[str] = []
    usage: dict[str, Any] | None = None
    response_model: str | None = None
    streaming_observed = False
    try:
        with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
            content_type = response.headers.get("Content-Type", "")
            if "text/event-stream" in content_type:
                streaming_observed = True
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    if isinstance(event.get("model"), str):
                        response_model = event["model"]
                    if isinstance(event.get("usage"), dict):
                        usage = event["usage"]
                    choices = event.get("choices")
                    if not isinstance(choices, list) or not choices:
                        continue
                    choice = choices[0]
                    if not isinstance(choice, dict):
                        continue
                    delta = choice.get("delta", {})
                    text = _delta_text(delta.get("content") if isinstance(delta, dict) else None)
                    if text:
                        if first_content_ns is None:
                            first_content_ns = time.perf_counter_ns()
                        content_parts.append(text)
            else:
                body = response.read()
                event = json.loads(body.decode("utf-8"))
                response_model = event.get("model") if isinstance(event.get("model"), str) else None
                usage = event.get("usage") if isinstance(event.get("usage"), dict) else None
                choices = event.get("choices")
                require(isinstance(choices, list) and choices, "non-stream response has no choices")
                message = choices[0].get("message", {}) if isinstance(choices[0], dict) else {}
                text = _delta_text(message.get("content") if isinstance(message, dict) else None)
                require(text != "", "non-stream response has no content")
                content_parts.append(text)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise ABBenchmarkError(f"model endpoint HTTP {exc.code}: {body[:500]}") from exc
    except urllib.error.URLError as exc:
        raise ABBenchmarkError(f"model endpoint unavailable: {exc}") from exc
    end_ns = time.perf_counter_ns()
    raw_text = "".join(content_parts)
    require(raw_text != "", "model endpoint returned empty content")
    return {
        "raw_text": raw_text,
        "response_model": response_model,
        "streaming_observed": streaming_observed,
        "ttft_ms": None if first_content_ns is None else (first_content_ns - start_ns) / 1_000_000.0,
        "total_time_ms": (end_ns - start_ns) / 1_000_000.0,
        "usage": usage,
    }


def _usage_int(usage: dict[str, Any] | None, key: str) -> int | None:
    if not isinstance(usage, dict):
        return None
    value = usage.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def execute_arm(
    *,
    workspace: Path,
    arm_name: str,
    trial_index: int,
    order_position: int,
    base_url: str,
    model: str,
    runtime_label: str,
    api_key: str | None,
    temperature: float,
    max_tokens: int,
    seed: int | None,
    timeout_seconds: float,
    output_dir: Path,
) -> dict[str, Any]:
    context, arm, context_manifest = load_arm_context(workspace, arm_name)
    prompt, prompt_meta = render_prompt(context)
    generation = {
        "temperature": temperature,
        "max_tokens": max_tokens,
        "seed": seed,
        "stream": True,
    }
    record: dict[str, Any] = {
        "schema_version": RUN_SCHEMA_VERSION,
        "experiment_id": EXPERIMENT_ID,
        "arm": arm_name,
        "trial_index": trial_index,
        "order_position": order_position,
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
            "transport": "openai_compatible_chat_completions",
            "runtime_label": runtime_label,
            "model_id": model,
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
        response = openai_compatible_chat(
            base_url=base_url,
            model=model,
            prompt=prompt,
            api_key=api_key,
            temperature=temperature,
            max_tokens=max_tokens,
            seed=seed,
            timeout_seconds=timeout_seconds,
        )
        raw_text = response["raw_text"]
        parsed = parse_model_result(raw_text)
        usage = response["usage"]
        record["status"] = "success"
        record["response_model"] = response["response_model"]
        record["streaming_observed"] = response["streaming_observed"]
        record["timing"] = {
            "ttft_ms": response["ttft_ms"],
            "total_time_ms": response["total_time_ms"],
        }
        record["usage"] = {
            "input_tokens": _usage_int(usage, "prompt_tokens"),
            "generation_tokens": _usage_int(usage, "completion_tokens"),
            "total_tokens": _usage_int(usage, "total_tokens"),
            "status": "runtime_reported" if isinstance(usage, dict) else "not_reported",
        }
        record["response"] = parsed
    except ABBenchmarkError as exc:
        record["status"] = "error"
        record["error"] = {"type": type(exc).__name__, "message": str(exc)}
    record["raw_response_sha256"] = sha256_text(raw_text)

    output_dir.mkdir(parents=True, exist_ok=True)
    raw_path = output_dir / f"{arm_name}.raw.txt"
    run_path = output_dir / f"{arm_name}.run.json"
    raw_path.write_text(raw_text, encoding="utf-8")
    run_path.write_text(json.dumps(record, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return record


def run_pair(
    *,
    workspace: Path,
    results_dir: Path,
    base_url: str,
    model: str,
    runtime_label: str,
    api_key: str | None,
    trials: int,
    temperature: float,
    max_tokens: int,
    seed: int | None,
    timeout_seconds: float,
    inter_arm_delay_seconds: float,
) -> None:
    require(trials >= 1, "trials must be >= 1")
    load_arm_context(workspace, "full_context")
    load_arm_context(workspace, "reduced_context")
    for trial in range(1, trials + 1):
        order = (
            ["full_context", "reduced_context"]
            if trial % 2 == 1
            else ["reduced_context", "full_context"]
        )
        trial_dir = results_dir / f"trial-{trial:03d}"
        print(f"A/B trial {trial}/{trials}: {' -> '.join(order)}")
        for position, arm_name in enumerate(order, start=1):
            record = execute_arm(
                workspace=workspace,
                arm_name=arm_name,
                trial_index=trial,
                order_position=position,
                base_url=base_url,
                model=model,
                runtime_label=runtime_label,
                api_key=api_key,
                temperature=temperature,
                max_tokens=max_tokens,
                seed=seed,
                timeout_seconds=timeout_seconds,
                output_dir=trial_dir,
            )
            print(f"- {arm_name}: {record['status']}")
            if position < len(order) and inter_arm_delay_seconds > 0:
                time.sleep(inter_arm_delay_seconds)
    print(f"A/B generation complete: {results_dir}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Prepare and run the STM32F103C Evidence Pack A/B benchmark")
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare = subparsers.add_parser("prepare", help="Build manufacturer-only full/reduced benchmark contexts")
    prepare.add_argument("--workspace", type=Path, required=True)
    prepare.add_argument("--ds-pdf", type=Path)
    prepare.add_argument("--pm-pdf", type=Path)
    prepare.add_argument("--fetch-sources", action="store_true")
    prepare.add_argument("--pdftotext", default="pdftotext")

    run = subparsers.add_parser("run-pair", help="Run paired full/reduced trials against an OpenAI-compatible endpoint")
    run.add_argument("--workspace", type=Path, required=True)
    run.add_argument("--results-dir", type=Path, required=True)
    run.add_argument("--base-url", required=True, help="OpenAI-compatible base URL ending in /v1")
    run.add_argument("--model", required=True)
    run.add_argument("--runtime-label", required=True)
    run.add_argument("--api-key-env", default="OPENAI_API_KEY")
    run.add_argument("--trials", type=int, default=3)
    run.add_argument("--temperature", type=float, default=0.0)
    run.add_argument("--max-tokens", type=int, default=4096)
    run.add_argument("--seed", type=int)
    run.add_argument("--timeout-seconds", type=float, default=600.0)
    run.add_argument("--inter-arm-delay-seconds", type=float, default=0.0)

    args = parser.parse_args()
    try:
        if args.command == "prepare":
            prepare_workspace(
                workspace=args.workspace,
                ds_pdf=args.ds_pdf,
                pm_pdf=args.pm_pdf,
                fetch_sources=args.fetch_sources,
                pdftotext=args.pdftotext,
            )
        elif args.command == "run-pair":
            api_key = os.environ.get(args.api_key_env) or None
            run_pair(
                workspace=args.workspace,
                results_dir=args.results_dir,
                base_url=args.base_url,
                model=args.model,
                runtime_label=args.runtime_label,
                api_key=api_key,
                trials=args.trials,
                temperature=args.temperature,
                max_tokens=args.max_tokens,
                seed=args.seed,
                timeout_seconds=args.timeout_seconds,
                inter_arm_delay_seconds=args.inter_arm_delay_seconds,
            )
        else:
            raise ABBenchmarkError(f"unsupported command: {args.command}")
        return 0
    except (OSError, json.JSONDecodeError, ABBenchmarkError) as exc:
        print(f"IC Evidence A/B benchmark FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

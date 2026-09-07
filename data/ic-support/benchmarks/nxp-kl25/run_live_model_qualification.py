#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path
from typing import Any

import build_evidence_pack as builder
import ollama_live_runtime
import qualify_semantic_run as qualification
import run_ollama_semantic
import semantic_runner

HERE = Path(__file__).resolve().parent


class LiveQualificationExecutionError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveQualificationExecutionError(message)


def _read_contract() -> dict[str, Any]:
    path = HERE / "live-model-qualification-contract.json"
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveQualificationExecutionError("live-model qualification contract is unreadable") from exc
    require(isinstance(value, dict), "live-model qualification contract root must be an object")
    return value


def _code_fingerprints() -> dict[str, str]:
    names = [
        "live-model-qualification-contract.json",
        "semantic-extraction-contract.json",
        "run_live_model_qualification.py",
        "run_ollama_semantic.py",
        "ollama_live_runtime.py",
        "ollama_transport.py",
        "semantic_runner.py",
        "semantic_extraction.py",
        "qualify_semantic_run.py",
    ]
    return {name: builder.sha256_file(HERE / name) for name in names}


def execute_live_qualification(
    *,
    input_dir: Path,
    output_dir: Path,
    ollama_url: str,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    contract = _read_contract()
    required = contract["required_input"]
    runtime = contract["live_runtime"]
    generation = runtime["generation"]
    output_protocol = runtime.get("output_protocol", {})
    require(output_protocol.get("format") == "json_schema", "qualification output protocol must use json_schema")
    require(output_protocol.get("structured_output_required") is True, "structured output must be required")

    # Validate all Gate 3 bytes/digests before any local-model HTTP request.
    manifest, packs, _, _ = run_ollama_semantic.load_pre_ai_workspace(input_dir)
    require(manifest.get("target") == contract.get("target"), "qualification target mismatch")
    require(manifest.get("bundle_digest") == required.get("bundle_digest"), "qualification bundle digest mismatch")
    require(
        manifest.get("manifest_digest") == required.get("pre_ai_manifest_digest"),
        "qualification pre-AI manifest digest mismatch",
    )

    normalized_ollama_url = ollama_live_runtime.normalize_loopback_ollama_url(ollama_url)
    identity = ollama_live_runtime.query_ollama_runtime_identity(
        ollama_url=normalized_ollama_url,
        model_id=runtime["model_id"],
        timeout_seconds=10.0,
    )

    record = run_ollama_semantic.execute_workspace(
        input_dir=input_dir,
        output_dir=output_dir,
        ollama_url=normalized_ollama_url,
        model_id=runtime["model_id"],
        runtime_label=runtime["runtime_label"],
        num_ctx=generation["num_ctx"],
        max_tokens=generation["max_tokens"],
        temperature=generation["temperature"],
        seed=generation["seed"],
        timeout_seconds=generation["timeout_seconds"],
    )

    raw_path = output_dir / "raw-response.txt"
    raw_response = raw_path.read_text(encoding="utf-8")
    semantic_runtime = record.get("runtime", {})
    provenance: dict[str, Any] = {
        "schema_version": "0.2.0",
        "artifact_type": "kl25_live_model_run_provenance",
        "target": contract["target"],
        "bundle_digest": record.get("bundle_digest"),
        "pre_ai_manifest_digest": record.get("pre_ai_manifest_digest"),
        "semantic_run_digest": builder.canonical_sha256(record),
        "raw_response_sha256": builder.sha256_text(raw_response),
        "ollama_runtime_identity": identity,
        "execution": {
            "transport": runtime["transport"],
            "model_id": runtime["model_id"],
            "runtime_label": runtime["runtime_label"],
            "ollama_endpoint_policy": "loopback_only",
            "output_protocol": {
                **dict(output_protocol),
                "output_schema_sha256": semantic_runtime.get("output_schema_sha256"),
            },
            "generation": dict(generation),
            "host": {
                "system": platform.system(),
                "machine": platform.machine(),
                "python_version": platform.python_version(),
                "hostname_retained": False,
            },
        },
        "code_fingerprints": _code_fingerprints(),
        "manufacturer_text_retained_in_provenance": False,
    }
    provenance["provenance_digest"] = builder.canonical_sha256(provenance)
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "live-run-provenance.json").write_text(
        json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    report = qualification.assess_live_run(
        contract=contract,
        semantic_run=record,
        raw_response=raw_response,
        provenance=provenance,
        packs=packs,
        reviewed_verdict=None,
    )
    (output_dir / "qualification-report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return record, provenance, report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute the frozen NXP KL25 qwen3.8:27b-mlx live-model qualification experiment"
    )
    parser.add_argument("--input-dir", type=Path, required=True, help="Exact Gate 3 Evidence Pack output directory")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    args = parser.parse_args()
    try:
        record, provenance, report = execute_live_qualification(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            ollama_url=args.ollama_url,
        )
        print(
            "KL25 live model run: "
            f"semantic={record['status']}; qualification={report['status']}; "
            f"model_digest={provenance['ollama_runtime_identity']['model_digest']}"
        )
        return 0 if report["status"] == "READY_FOR_REVIEW" else 1
    except (
        LiveQualificationExecutionError,
        qualification.LiveModelQualificationError,
        run_ollama_semantic.SemanticWorkspaceError,
        semantic_runner.SemanticTransportError,
        OSError,
        ValueError,
    ) as exc:
        print(f"KL25 live model qualification FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

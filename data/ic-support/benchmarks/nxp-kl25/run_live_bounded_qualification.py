#!/usr/bin/env python3
from __future__ import annotations

import argparse
import copy
import json
import platform
import sys
from pathlib import Path
from typing import Any, Callable

import bounded_extraction as bounded
import build_evidence_pack as builder
import ollama_live_runtime
import ollama_transport
import qualify_bounded_run as qualification
import run_ollama_semantic

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACT_PATH = HERE / "live-bounded-qualification-contract.json"


class LiveBoundedExecutionError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise LiveBoundedExecutionError(message)


def _read_contract(path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, Any]:
    try:
        resolved = path.resolve()
        require(resolved.parent == HERE, "live bounded contract must be stored in the KL25 benchmark directory")
        value = json.loads(resolved.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LiveBoundedExecutionError("live bounded qualification contract is unreadable") from exc
    require(isinstance(value, dict), "live bounded qualification contract root must be an object")
    return value


def _code_fingerprints(contract_path: Path = DEFAULT_CONTRACT_PATH) -> dict[str, str]:
    resolved = contract_path.resolve()
    require(resolved.parent == HERE, "fingerprinted live bounded contract must be repository-local")
    names = [
        resolved.name,
        "bounded-extraction-contract.json",
        "semantic-extraction-contract.json",
        "run_live_bounded_qualification.py",
        "qualify_bounded_run.py",
        "bounded_extraction.py",
        "ollama_live_runtime.py",
        "ollama_transport.py",
        "run_ollama_semantic.py",
        "semantic_extraction.py",
        "semantic_context.py",
        "semantic_runner.py",
        "build_evidence_pack.py",
    ]
    return {name: builder.sha256_file(HERE / name) for name in names}


def _write_json_new(path: Path, value: dict[str, Any]) -> None:
    with path.open("x", encoding="utf-8") as stream:
        stream.write(json.dumps(value, indent=2, ensure_ascii=False) + "\n")


def execute_live_bounded_qualification(
    *, input_dir: Path, output_dir: Path, ollama_url: str,
    contract_override: dict[str, Any] | None = None,
    contract_path: Path | None = None,
    identity_query: Callable[..., dict[str, Any]] | None = None,
    transport: Callable[..., dict[str, Any]] | None = None,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    selected_contract_path = (contract_path or DEFAULT_CONTRACT_PATH).resolve()
    contract = copy.deepcopy(
        contract_override if contract_override is not None else _read_contract(selected_contract_path)
    )
    qualification.validate_contract(contract)
    required = contract["required_input"]
    runtime = contract["live_runtime"]
    rules = bounded.policy()

    manifest, packs, evidence_text, semantic_contract = run_ollama_semantic.load_pre_ai_workspace(input_dir)
    require(manifest.get("target") == contract.get("target"), "live bounded target mismatch")
    require(manifest.get("bundle_digest") == required.get("bundle_digest"), "live bounded bundle digest mismatch")
    require(manifest.get("manifest_digest") == required.get("pre_ai_manifest_digest"),
            "live bounded pre-AI manifest digest mismatch")
    require(semantic_contract.get("contract_id") == required.get("semantic_contract_id"),
            "live bounded semantic contract mismatch")
    require(rules.get("contract_id") == required.get("bounded_contract_id"),
            "live bounded base contract id mismatch")
    require(builder.canonical_sha256(rules) == required.get("bounded_contract_digest"),
            "live bounded base contract digest mismatch")
    require(rules.get("evidence_boundary_release_id") == required.get("evidence_boundary_release_id"),
            "live bounded evidence release mismatch")

    normalized_url = ollama_live_runtime.normalize_loopback_ollama_url(ollama_url)
    identity_fn = identity_query or ollama_live_runtime.query_ollama_runtime_identity
    identity = identity_fn(
        ollama_url=normalized_url,
        model_id=runtime["model_id"],
        timeout_seconds=10.0,
    )
    model_digest = qualification.normalized_model_digest(identity.get("model_digest"))
    require(identity.get("model_id") == runtime["model_id"], "runtime identity model mismatch")
    require(identity.get("ollama_url_policy") == "loopback_only", "runtime identity endpoint policy mismatch")

    profile = qualification.execution_profile_from_contract(contract)
    provider_transport = transport or ollama_transport.ollama_native_chat_transport

    def live_transport(**kwargs):
        options = copy.deepcopy(kwargs["options"])
        options["ollama_url"] = normalized_url
        return provider_transport(
            prompt=kwargs["prompt"], model_id=kwargs["model_id"],
            runtime_label=kwargs["runtime_label"], options=options,
        )

    result = bounded.execute_bounded_run(
        contract=semantic_contract,
        pre_ai_manifest=manifest,
        packs=packs,
        evidence_text=evidence_text,
        transport=live_transport,
        model_id=runtime["model_id"],
        model_digest=model_digest,
        output_dir=output_dir,
        execution_profile=profile,
    )
    children = result["children"]
    aggregate = result["aggregate"]

    child_rows = sorted(
        ({
            "primary_unit_id": child.get("binding", {}).get("primary_unit_id"),
            "record_digest": child.get("record_digest"),
            "request_digest": child.get("binding", {}).get("request_digest"),
            "raw_response_sha256": child.get("raw_response_sha256"),
        } for child in children),
        key=lambda row: str(row["primary_unit_id"]),
    )
    execution: dict[str, Any] = {
        "execution_mode": runtime["execution_mode"],
        "transport": runtime["transport"],
        "model_id": runtime["model_id"],
        "runtime_label": runtime["runtime_label"],
        "ollama_endpoint_policy": "loopback_only",
        "generation": copy.deepcopy(runtime["generation"]),
        "automatic_retries": runtime["automatic_retries"],
        "primary_unit_count": runtime["primary_unit_count"],
        "host": {
            "system": platform.system(),
            "machine": platform.machine(),
            "python_version": platform.python_version(),
            "hostname_retained": False,
        },
    }
    if runtime.get("semantic_scope") is not None:
        execution["semantic_scope"] = copy.deepcopy(runtime["semantic_scope"])

    provenance: dict[str, Any] = {
        "schema_version": "0.1.0",
        "artifact_type": "kl25_live_bounded_run_provenance",
        "target": contract["target"],
        "bundle_digest": manifest["bundle_digest"],
        "pre_ai_manifest_digest": manifest["manifest_digest"],
        "live_bounded_contract_id": contract["contract_id"],
        "live_bounded_contract_digest": builder.canonical_sha256(contract),
        "bounded_contract_id": rules["contract_id"],
        "bounded_contract_digest": builder.canonical_sha256(rules),
        "aggregate_digest": aggregate["aggregate_digest"],
        "ollama_runtime_identity": copy.deepcopy(identity),
        "execution": execution,
        "children": child_rows,
        "code_fingerprints": _code_fingerprints(selected_contract_path),
        "manufacturer_text_retained_in_provenance": False,
    }
    provenance["provenance_digest"] = builder.canonical_sha256(provenance)
    _write_json_new(output_dir / "live-bounded-provenance.json", provenance)

    report = qualification.assess_bounded_live_run(
        contract=contract,
        aggregate=aggregate,
        children=children,
        provenance=provenance,
        semantic_contract=semantic_contract,
        pre_ai_manifest=manifest,
        packs=packs,
        evidence_text=evidence_text,
    )
    _write_json_new(output_dir / "qualification-report.json", report)
    return result, provenance, report


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Execute an NXP KL25 sequential per-Evidence-Unit live bounded qualification"
    )
    parser.add_argument("--input-dir", type=Path, required=True,
                        help="Corrected Gate 5.6 pre-AI workspace")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT_PATH,
                        help="Repository-local live bounded qualification contract")
    args = parser.parse_args()
    try:
        result, provenance, report = execute_live_bounded_qualification(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            ollama_url=args.ollama_url,
            contract_path=args.contract,
        )
        children = result["children"]
        passed = sum(child.get("status") == "success" for child in children)
        print(
            "KL25 live bounded run: "
            f"children={passed}/{len(children)}; aggregate={result['aggregate']['status']}; "
            f"qualification={report['status']}; "
            f"model_digest={provenance['ollama_runtime_identity']['model_digest']}"
        )
        return 0 if report["status"] == "READY_FOR_REVIEW" else 1
    except (
        LiveBoundedExecutionError,
        qualification.LiveBoundedQualificationError,
        bounded.BoundedExtractionError,
        run_ollama_semantic.SemanticWorkspaceError,
        OSError,
        ValueError,
    ) as exc:
        print(f"KL25 live bounded qualification FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

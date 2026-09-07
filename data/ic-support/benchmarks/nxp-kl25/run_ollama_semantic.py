#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import build_evidence_pack as builder
import ollama_transport
import semantic_context
import semantic_runner as runner

HERE = Path(__file__).resolve().parent
SAFE_ID = re.compile(r"^[A-Za-z0-9._-]+$")


class SemanticWorkspaceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SemanticWorkspaceError(message)


def _read_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SemanticWorkspaceError(f"cannot read valid JSON: {path}") from exc
    require(isinstance(value, dict), f"JSON root must be object: {path}")
    return value


def load_pre_ai_workspace(input_dir: Path) -> tuple[dict[str, Any], dict[str, dict[str, Any]], dict[str, str], dict[str, Any]]:
    manifest = _read_json(input_dir / "pre-ai-input.json")
    bundle = _read_json(input_dir / "target-bundle.json")
    contract = _read_json(HERE / "semantic-extraction-contract.json")

    require(bundle.get("artifact_type") == "kl25_target_evidence_bundle", "target bundle artifact mismatch")
    require(bundle.get("target") == manifest.get("target"), "target bundle target mismatch")
    require(bundle.get("bundle_id") == manifest.get("bundle_id"), "target bundle id mismatch")
    require(bundle.get("bundle_digest") == manifest.get("bundle_digest"), "target bundle digest pointer mismatch")
    calculated_bundle_digest = builder.canonical_sha256(
        {key: value for key, value in bundle.items() if key != "bundle_digest"}
    )
    require(bundle.get("bundle_digest") == calculated_bundle_digest, "target bundle self-digest mismatch")
    require(contract.get("target") == manifest.get("target"), "semantic contract target mismatch")

    listed = manifest.get("packs")
    require(isinstance(listed, list) and bool(listed), "pre-AI manifest packs missing")
    pack_ids: list[str] = []
    for index, item in enumerate(listed):
        require(isinstance(item, dict), f"pre-AI packs[{index}] must be object")
        pack_id = item.get("pack_id")
        require(isinstance(pack_id, str) and SAFE_ID.fullmatch(pack_id) is not None, f"unsafe pack id: {pack_id!r}")
        require(pack_id not in pack_ids, f"duplicate pack id: {pack_id}")
        pack_ids.append(pack_id)

    pack_dir = input_dir / "packs"
    evidence_dir = input_dir / "evidence"
    expected_pack_files = {f"{pack_id}.json" for pack_id in pack_ids}
    expected_evidence_files = {f"{pack_id}.txt" for pack_id in pack_ids}
    require(pack_dir.is_dir(), "missing packs directory")
    require(evidence_dir.is_dir(), "missing evidence directory")
    require({path.name for path in pack_dir.glob("*.json")} == expected_pack_files, "pack file set mismatch")
    require({path.name for path in evidence_dir.glob("*.txt")} == expected_evidence_files, "evidence file set mismatch")

    packs: dict[str, dict[str, Any]] = {}
    evidence_text: dict[str, str] = {}
    for pack_id in pack_ids:
        pack = _read_json(pack_dir / f"{pack_id}.json")
        require(pack.get("pack_id") == pack_id, f"{pack_id}: pack id mismatch")
        packs[pack_id] = pack
        try:
            evidence_text[pack_id] = (evidence_dir / f"{pack_id}.txt").read_text(encoding="utf-8")
        except OSError as exc:
            raise SemanticWorkspaceError(f"cannot read evidence for {pack_id}") from exc

    require(set(bundle.get("pack_digests", {})) == set(packs), "target bundle pack set mismatch")
    for pack_id, pack in packs.items():
        require(
            bundle["pack_digests"].get(pack_id) == pack.get("pack_digest"),
            f"{pack_id}: target bundle pack digest mismatch",
        )

    try:
        builder.validate_pre_ai_manifest(
            manifest,
            bundle=bundle,
            packs=packs,
            evidence_text=evidence_text,
        )
    except builder.KL25EvidencePackError as exc:
        raise SemanticWorkspaceError(f"pre-AI workspace validation failed: {exc}") from exc
    return manifest, packs, evidence_text, contract


def execute_workspace(
    *,
    input_dir: Path,
    output_dir: Path,
    ollama_url: str,
    model_id: str,
    runtime_label: str,
    num_ctx: int,
    max_tokens: int,
    temperature: float,
    seed: int | None,
    timeout_seconds: float,
    context_strategy: str = semantic_context.LEGACY_CONTEXT_STRATEGY,
) -> dict[str, Any]:
    manifest, packs, evidence_text, contract = load_pre_ai_workspace(input_dir)
    captured_raw: dict[str, str] = {"text": ""}

    def transport_proxy(**kwargs):
        response = ollama_transport.ollama_native_chat_transport(**kwargs)
        raw = response.get("raw_text")
        if isinstance(raw, str):
            captured_raw["text"] = raw
        return response

    record = runner.execute_semantic_run(
        contract=contract,
        pre_ai_manifest=manifest,
        packs=packs,
        evidence_text=evidence_text,
        transport=transport_proxy,
        transport_label="ollama_native_chat",
        model_id=model_id,
        runtime_label=runtime_label,
        request_options={
            "ollama_url": ollama_url,
            "num_ctx": num_ctx,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "seed": seed,
            "timeout_seconds": timeout_seconds,
        },
        context_strategy=context_strategy,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "semantic-run.json").write_text(
        json.dumps(record, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    (output_dir / "raw-response.txt").write_text(captured_raw["text"], encoding="utf-8")
    return record


def main() -> int:
    parser = argparse.ArgumentParser(description="Run NXP KL25 manufacturer-near semantic extraction through Ollama")
    parser.add_argument("--input-dir", type=Path, required=True, help="Gate 3 Evidence Pack output directory")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--model", required=True)
    parser.add_argument("--runtime-label", required=True)
    parser.add_argument("--num-ctx", type=int, default=32768)
    parser.add_argument("--max-tokens", type=int, default=4096)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    parser.add_argument(
        "--context-strategy",
        choices=[semantic_context.LEGACY_CONTEXT_STRATEGY, semantic_context.COMPACT_CONTEXT_STRATEGY],
        default=semantic_context.LEGACY_CONTEXT_STRATEGY,
    )
    args = parser.parse_args()
    try:
        record = execute_workspace(
            input_dir=args.input_dir,
            output_dir=args.output_dir,
            ollama_url=args.ollama_url,
            model_id=args.model,
            runtime_label=args.runtime_label,
            num_ctx=args.num_ctx,
            max_tokens=args.max_tokens,
            temperature=args.temperature,
            seed=args.seed,
            timeout_seconds=args.timeout_seconds,
            context_strategy=args.context_strategy,
        )
    except (SemanticWorkspaceError, OSError, ValueError) as exc:
        print(f"KL25 semantic runner FAIL: {exc}", file=sys.stderr)
        return 1
    print(
        f"KL25 semantic runner {record['status']}: target={record['target']}; "
        f"model={record['runtime']['model_id']}; transport={record['runtime']['transport']}"
    )
    if record["status"] != "success":
        print(record.get("error", {}).get("message", "semantic extraction failed"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

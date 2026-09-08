#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import build_evidence_pack as builder
import run_ollama_semantic
import semantic_context
import semantic_extraction


def audit_workspace(input_dir: Path) -> dict[str, object]:
    manifest, packs, evidence_text, contract = run_ollama_semantic.load_pre_ai_workspace(input_dir)
    legacy_context = builder.assemble_model_context(manifest, packs=packs, evidence_text=evidence_text)
    compact_context, context_audit = semantic_context.assemble_compact_model_context(
        manifest,
        packs=packs,
        evidence_text=evidence_text,
    )
    legacy_prompt, _ = semantic_extraction.render_prompt(legacy_context, contract=contract, packs=packs)
    compact_prompt, _ = semantic_extraction.render_prompt(compact_context, contract=contract, packs=packs)

    result = dict(context_audit)
    result.update(
        {
            "legacy_prompt_sha256": builder.sha256_text(legacy_prompt),
            "legacy_prompt_bytes": len(legacy_prompt.encode("utf-8")),
            "compact_prompt_sha256": builder.sha256_text(compact_prompt),
            "compact_prompt_bytes": len(compact_prompt.encode("utf-8")),
            "prompt_byte_reduction_pct": round(
                100.0 * (len(legacy_prompt.encode("utf-8")) - len(compact_prompt.encode("utf-8")))
                / len(legacy_prompt.encode("utf-8")),
                2,
            ),
        }
    )
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit NXP KL25 semantic context compaction without model inference")
    parser.add_argument("--input-dir", type=Path, required=True)
    args = parser.parse_args()
    try:
        result = audit_workspace(args.input_dir)
    except Exception as exc:
        print(f"KL25 context audit FAIL: {exc}", file=sys.stderr)
        return 1

    print("===== KL25 CONTEXT AUDIT =====")
    for key in (
        "strategy",
        "page_occurrences",
        "unique_physical_pages",
        "duplicate_occurrences_removed",
        "page_occurrence_redundancy_pct",
        "legacy_context_bytes",
        "context_bytes",
        "context_byte_reduction_pct",
        "legacy_prompt_bytes",
        "compact_prompt_bytes",
        "prompt_byte_reduction_pct",
        "context_sha256",
        "compact_prompt_sha256",
    ):
        print(f"{key} = {result.get(key)}")
    print("gate3_artifacts_mutated =", result.get("gate3_artifacts_mutated"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

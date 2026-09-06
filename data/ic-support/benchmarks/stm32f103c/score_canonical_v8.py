#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import ab_benchmark as harness
import canonicalize_semantic_run_v8 as pipeline
import semantic_extraction_v8 as semantic

HERE = Path(__file__).resolve().parent
GROUND_TRUTH = HERE / "canonical-ground-truth-v6.json"
SCORE_SCHEMA_VERSION = "0.7.0"


class CanonicalScoreError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CanonicalScoreError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: JSON root must be object")
    return value


def is_missing(value: Any) -> bool:
    return value is None or value == "unknown"


def _validate_canonical_evidence(canonical_spec: dict[str, Any], evidence: dict[str, Any], *, context: dict[str, Any]) -> tuple[int, int, list[str]]:
    leaves = semantic.flatten_leaves(canonical_spec, "$.canonical_spec")
    asserted = {path for path, value in leaves.items() if not is_missing(value)}
    allowed = semantic.allowed_pages_from_run_context(context)
    uncited: list[str] = []
    out_of_context: set[str] = set()
    for path in sorted(asserted):
        citations = evidence.get(path)
        if not isinstance(citations, list) or not citations:
            uncited.append(path)
            continue
        valid = False
        for citation in citations:
            if not isinstance(citation, dict):
                out_of_context.add(path)
                continue
            source_id = citation.get("source_id")
            page_index = citation.get("physical_page_index")
            if isinstance(source_id, str) and isinstance(page_index, int) and not isinstance(page_index, bool) and source_id in allowed and page_index in allowed[source_id]:
                valid = True
            else:
                out_of_context.add(path)
        if not valid:
            out_of_context.add(path)
    unexpected = sorted(set(evidence) - asserted)
    require(not unexpected, f"unexpected canonical evidence paths: {unexpected[:5]}")
    return len(uncited), len(out_of_context), sorted(out_of_context)


def score_report(report: dict[str, Any]) -> dict[str, Any]:
    require(report.get("pipeline_id") == pipeline.PIPELINE_ID, "canonical pipeline ID mismatch")
    source_run = report.get("source_run")
    canonicalization = report.get("canonicalization")
    require(isinstance(source_run, dict), "source_run required")
    require(isinstance(canonicalization, dict), "canonicalization report required")
    truth = load_json(GROUND_TRUTH)
    expected = truth.get("expected")
    require(isinstance(expected, dict), "canonical ground truth expected object required")
    require(canonicalization.get("canonicalization_id") == truth.get("canonicalization_id"), "canonicalization ID mismatch")
    actual = canonicalization.get("canonical_spec")
    evidence = canonicalization.get("evidence")
    require(isinstance(actual, dict), "canonical_spec required")
    require(isinstance(evidence, dict), "canonical evidence required")
    expected_leaves = semantic.flatten_leaves(expected, "$.canonical_spec")
    actual_leaves = semantic.flatten_leaves(actual, "$.canonical_spec")
    require(set(actual_leaves) == set(expected_leaves), "canonical leaf paths do not match score contract")
    exact: list[str] = []
    wrong: list[str] = []
    missing: list[str] = []
    for path, expected_value in expected_leaves.items():
        actual_value = actual_leaves[path]
        if actual_value == expected_value:
            exact.append(path)
        elif is_missing(actual_value):
            missing.append(path)
        else:
            wrong.append(path)
    context = source_run.get("context")
    require(isinstance(context, dict), "source run context required")
    uncited_count, out_of_context_count, out_of_context_paths = _validate_canonical_evidence(actual, evidence, context=context)
    total = len(expected_leaves)
    return {
        "status": "scored",
        "total_field_count": total,
        "exact_field_count": len(exact),
        "exact_accuracy": len(exact) / total if total else 1.0,
        "wrong_assertion_count": len(wrong),
        "missing_unknown_count": len(missing),
        "uncited_assertion_count": uncited_count,
        "out_of_context_citation_count": out_of_context_count,
        "canonicalization_status": canonicalization.get("canonicalization_status"),
        "transformation_count": len(canonicalization.get("transformations", [])),
        "unresolved_path_count": len(canonicalization.get("unresolved_paths", [])),
        "paths": {"wrong": sorted(wrong), "missing_unknown": sorted(missing), "out_of_context_citation": out_of_context_paths},
        "trust_boundary": {
            "ground_truth_visible_to_generation": False,
            "programming_relationship_is_applicability_derived": True,
            "option_relationship_is_applicability_derived": True,
            "security_relationship_is_applicability_derived": True,
            "security_relationship_from_raw_generated_field_equality": False,
            "security_relationship_implies_destructive_transition_safety": False,
            "destructive_security_operation_admission": False,
            "memory_geometry_relationship_is_deterministic": True,
            "package_hardware_relationship_is_deterministic": True,
            "canonical_dataset_admission": False,
            "production_admission": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one canonicalized STM32F103C v8 semantic extraction run")
    parser.add_argument("--canonical", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = load_json(args.canonical)
        score = score_report(report)
        output = {
            "schema_version": SCORE_SCHEMA_VERSION,
            "pipeline_id": pipeline.PIPELINE_ID,
            "canonical_file": args.canonical.name,
            "canonical_sha256": harness.sha256_bytes(args.canonical.read_bytes()),
            "score_authority": {
                "ground_truth_file": GROUND_TRUTH.name,
                "ground_truth_sha256": harness.sha256_bytes(GROUND_TRUTH.read_bytes()),
                "generation_reads_ground_truth": False,
            },
            "score": score,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("IC canonical v8 scoring COMPLETE")
        print(f"- exact accuracy: {score.get('exact_accuracy')}")
        print(f"- wrong assertions: {score.get('wrong_assertion_count')}")
        print(f"- missing/unknown: {score.get('missing_unknown_count')}")
        return 0 if score.get("status") == "scored" else 1
    except (OSError, json.JSONDecodeError, CanonicalScoreError, semantic.SemanticExtractionError) as exc:
        print(f"IC canonical v8 scoring FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

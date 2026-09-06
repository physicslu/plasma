#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import ab_benchmark as harness
import canonicalize_semantic_facts as canonicalizer
import semantic_extraction_v2 as semantic

HERE = Path(__file__).resolve().parent
GROUND_TRUTH = HERE / "semantic-extraction-ground-truth-v0.json"
CANONICALIZATION_CONTRACT = HERE / "canonicalization-contract-v0.json"
SCORE_SCHEMA_VERSION = "0.1.0"


class SemanticScoreError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SemanticScoreError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: JSON root must be object")
    return value


def is_missing(value: Any) -> bool:
    return value is None or value == "unknown"


def _equivalent(
    *,
    path: str,
    actual: Any,
    expected: Any,
    comparison_rules: dict[str, Any],
    canonicalization_contract: dict[str, Any],
) -> bool:
    rule = comparison_rules.get(path)
    if rule is None:
        return actual == expected
    if rule == "HEX_ADDRESS_EQUIVALENT":
        if not isinstance(actual, str) or not isinstance(expected, str):
            return False
        try:
            return canonicalizer.normalize_hex_address(actual) == canonicalizer.normalize_hex_address(expected)
        except canonicalizer.CanonicalizationError:
            return False
    if rule == "OPTION_ENCODING_EQUIVALENT":
        if not isinstance(actual, str) or not isinstance(expected, str):
            return False
        try:
            return (
                canonicalizer.normalize_option_encoding(actual, canonicalization_contract)
                == canonicalizer.normalize_option_encoding(expected, canonicalization_contract)
            )
        except canonicalizer.CanonicalizationError:
            return False
    raise SemanticScoreError(f"{path}: unsupported comparison rule {rule!r}")


def score_run(run: dict[str, Any]) -> dict[str, Any]:
    require(run.get("experiment_id") == semantic.SEMANTIC_EXPERIMENT_ID, "semantic experiment ID mismatch")
    if run.get("status") != "success":
        return {
            "status": "run_error",
            "error": run.get("error"),
        }

    truth = load_json(GROUND_TRUTH)
    expected = truth.get("expected")
    comparison_rules = truth.get("comparison_rules", {})
    contract = load_json(CANONICALIZATION_CONTRACT)
    require(isinstance(expected, dict), "semantic ground truth expected object required")
    require(isinstance(comparison_rules, dict), "semantic comparison rules object required")

    response = run.get("response")
    require(isinstance(response, dict), "successful semantic run response required")
    facts = response.get("semantic_facts")
    evidence = response.get("evidence")
    require(isinstance(facts, dict), "semantic_facts required")
    require(isinstance(evidence, dict), "evidence required")

    expected_leaves = semantic.flatten_leaves(expected, "$.semantic_facts")
    actual_leaves = semantic.flatten_leaves(facts, "$.semantic_facts")
    require(set(actual_leaves) == set(expected_leaves), "semantic leaf paths do not match score contract")

    allowed_pages = semantic.allowed_pages_from_run_context(run.get("context", {}))
    semantic.validate_evidence(facts, evidence, allowed_pages=allowed_pages)

    literal_exact: list[str] = []
    semantically_correct: list[str] = []
    wrong_semantic: list[str] = []
    missing_unknown: list[str] = []
    representation_difference: list[str] = []

    for path, expected_value in expected_leaves.items():
        actual = actual_leaves[path]
        if actual == expected_value:
            literal_exact.append(path)
        if is_missing(actual):
            missing_unknown.append(path)
            continue
        if _equivalent(
            path=path,
            actual=actual,
            expected=expected_value,
            comparison_rules=comparison_rules,
            canonicalization_contract=contract,
        ):
            semantically_correct.append(path)
            if actual != expected_value:
                representation_difference.append(path)
        else:
            wrong_semantic.append(path)

    total = len(expected_leaves)
    asserted_paths = semantic.asserted_leaf_paths(facts)
    return {
        "status": "scored",
        "total_field_count": total,
        "literal_exact_count": len(literal_exact),
        "literal_exact_accuracy": len(literal_exact) / total if total else 1.0,
        "semantic_correct_count": len(semantically_correct),
        "semantic_accuracy": len(semantically_correct) / total if total else 1.0,
        "wrong_semantic_assertion_count": len(wrong_semantic),
        "missing_unknown_count": len(missing_unknown),
        "representation_difference_count": len(representation_difference),
        "asserted_leaf_count": len(asserted_paths),
        "evidence_path_count": len(evidence),
        "uncited_assertion_count": len(asserted_paths - set(evidence)),
        "out_of_context_citation_count": 0,
        "paths": {
            "wrong_semantic": sorted(wrong_semantic),
            "missing_unknown": sorted(missing_unknown),
            "representation_difference": sorted(representation_difference),
        },
        "trust_boundary": {
            "comparison_contract_visible_to_generation": False,
            "citation_presence_is_not_semantic_entailment_proof": True,
            "canonical_dataset_admission": False,
            "production_admission": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Score one STM32F103C v2 semantic extraction run")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        run = load_json(args.run)
        score = score_run(run)
        report = {
            "schema_version": SCORE_SCHEMA_VERSION,
            "experiment_id": semantic.SEMANTIC_EXPERIMENT_ID,
            "run_file": args.run.name,
            "run_sha256": harness.sha256_bytes(args.run.read_bytes()),
            "score_authority": {
                "ground_truth_file": GROUND_TRUTH.name,
                "ground_truth_sha256": harness.sha256_bytes(GROUND_TRUTH.read_bytes()),
                "canonicalization_contract_file": CANONICALIZATION_CONTRACT.name,
                "canonicalization_contract_sha256": harness.sha256_bytes(CANONICALIZATION_CONTRACT.read_bytes()),
                "generation_reads_score_authority": False,
            },
            "score": score,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print("IC semantic extraction scoring COMPLETE")
        print("- scoring completion is not a quality or production acceptance decision")
        print(f"- semantic accuracy: {score.get('semantic_accuracy')}")
        print(f"- literal exact accuracy: {score.get('literal_exact_accuracy')}")
        print(f"- wrong semantic assertions: {score.get('wrong_semantic_assertion_count')}")
        print(f"- representation differences: {score.get('representation_difference_count')}")
        print(f"- missing/unknown: {score.get('missing_unknown_count')}")
        print(f"- uncited assertions: {score.get('uncited_assertion_count')}")
        print(f"- out-of-context citations: {score.get('out_of_context_citation_count')}")
        return 0 if score.get("status") == "scored" else 1
    except (
        OSError,
        json.JSONDecodeError,
        SemanticScoreError,
        semantic.SemanticExtractionError,
        canonicalizer.CanonicalizationError,
    ) as exc:
        print(f"IC semantic extraction scoring FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

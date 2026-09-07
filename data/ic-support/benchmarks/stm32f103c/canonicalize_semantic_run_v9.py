#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import ab_benchmark as harness
import canonicalize_semantic_facts_v9 as canonicalizer
import semantic_extraction_v9 as semantic

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACT = HERE / "canonicalization-contract-v7.json"
PIPELINE_SCHEMA_VERSION = "0.8.0"
PIPELINE_ID = "stm32f103c-device-identity-ontology-semantic-to-canonical-v7"


class CanonicalRunError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CanonicalRunError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: JSON root must be object")
    return value


def canonicalize_run(run_path: Path, contract_path: Path = DEFAULT_CONTRACT) -> dict[str, Any]:
    run = load_json(run_path)
    require(run.get("status") == "success", "semantic run must be successful before canonicalization")
    require(run.get("experiment_id") == semantic.SEMANTIC_EXPERIMENT_ID, "semantic experiment ID mismatch")
    response = run.get("response")
    context = run.get("context")
    require(isinstance(response, dict), "semantic run response required")
    require(isinstance(context, dict), "semantic run context required")
    facts = response.get("semantic_facts")
    evidence = response.get("evidence")
    require(isinstance(facts, dict), "semantic_facts required")
    require(isinstance(evidence, dict), "evidence required")
    semantic.validate_semantic_facts(facts)
    semantic.validate_evidence(facts, evidence, allowed_pages=semantic.allowed_pages_from_run_context(context))
    contract = load_json(contract_path)
    canonicalization = canonicalizer.canonicalize_response(response, contract)
    return {
        "schema_version": PIPELINE_SCHEMA_VERSION,
        "pipeline_id": PIPELINE_ID,
        "source_run": {
            "file": run_path.name,
            "sha256": harness.sha256_bytes(run_path.read_bytes()),
            "experiment_id": run.get("experiment_id"),
            "source_lock_id": run.get("source_lock_id"),
            "source_digests": run.get("source_digests"),
            "arm": run.get("arm"),
            "context": context,
            "runtime": run.get("runtime"),
            "generation": run.get("generation"),
            "usage": run.get("usage"),
            "timing": run.get("timing")
        },
        "canonicalization": canonicalization,
        "trust_boundary": {
            "canonicalization_after_retained_generation_artifact": True,
            "generation_visibility_of_canonicalization_contract": False,
            "commercial_target_identity_is_ai_extracted_leaf": False,
            "manufacturer_applicability_expression_is_ai_extracted": True,
            "identity_projection_is_deterministic": True,
            "identity_fuzzy_matching": False,
            "ai_emits_security_relationship": False,
            "ai_emits_option_relationship": False,
            "ai_emits_programming_relationship": False,
            "ai_emits_memory_geometry_relationship": False,
            "ai_emits_package_hardware_relationship": False,
            "destructive_security_operation_admission": False,
            "canonical_dataset_admission": False,
            "production_admission": False
        }
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonicalize one retained STM32F103C v9 semantic extraction run")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = canonicalize_run(args.run, args.contract)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = report["canonicalization"]
        print("IC v9 semantic run canonicalization COMPLETE")
        print(f"- status: {result['canonicalization_status']}")
        print(f"- transformations: {len(result['transformations'])}")
        print(f"- unresolved paths: {len(result['unresolved_paths'])}")
        return 0
    except (OSError, json.JSONDecodeError, CanonicalRunError, semantic.SemanticExtractionError, canonicalizer.CanonicalizationError, KeyError) as exc:
        print(f"IC v9 semantic run canonicalization FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import ab_benchmark as harness
import canonicalize_semantic_facts_v4 as canonicalizer
import semantic_extraction_v4 as semantic

HERE = Path(__file__).resolve().parent
DEFAULT_CONTRACT = HERE / "canonicalization-contract-v2.json"
PIPELINE_SCHEMA_VERSION = "0.3.0"
PIPELINE_ID = "stm32f103c-relationship-derived-semantic-to-canonical-v2"


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
    require(isinstance(response, dict), "semantic run response required")
    context = run.get("context")
    require(isinstance(context, dict), "semantic run context required")

    facts = response.get("semantic_facts")
    evidence = response.get("evidence")
    require(isinstance(facts, dict), "semantic_facts required")
    require(isinstance(evidence, dict), "evidence required")
    semantic.validate_semantic_facts(facts)
    semantic.validate_evidence(
        facts,
        evidence,
        allowed_pages=semantic.allowed_pages_from_run_context(context),
    )

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
            "timing": run.get("timing"),
        },
        "canonicalization": canonicalization,
        "trust_boundary": {
            "canonicalization_after_retained_generation_artifact": True,
            "generation_visibility_of_canonicalization_contract": False,
            "ai_emits_package_hardware_relationship": False,
            "package_hardware_relationship_is_deterministic": True,
            "pin_level_minimum_programming_hardware_admission": False,
            "canonical_dataset_admission": False,
            "production_admission": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Canonicalize one retained STM32F103C relationship-derivation semantic extraction run")
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--contract", type=Path, default=DEFAULT_CONTRACT)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = canonicalize_run(args.run, args.contract)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        result = report["canonicalization"]
        print("IC relationship-derived semantic run canonicalization COMPLETE")
        print(f"- status: {result['canonicalization_status']}")
        print(f"- package_hardware relationship: {result['canonical_spec']['profile_relationships']['package_hardware']}")
        print(f"- transformations: {len(result['transformations'])}")
        print(f"- unresolved paths: {len(result['unresolved_paths'])}")
        print("- package relationship emitted by AI: false")
        print("- pin-level programming-hardware admission: false")
        print("- canonical dataset admission: false")
        print("- production admission: false")
        return 0
    except (
        OSError,
        json.JSONDecodeError,
        CanonicalRunError,
        semantic.SemanticExtractionError,
        canonicalizer.CanonicalizationError,
        KeyError,
    ) as exc:
        print(f"IC relationship-derived semantic run canonicalization FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

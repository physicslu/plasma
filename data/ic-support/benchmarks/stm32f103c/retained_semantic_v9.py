#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import ab_benchmark as harness
import canonicalize_semantic_run_v9 as canonical_pipeline
import ollama_semantic_extraction_run_v9 as ollama_runner
import score_canonical_v8 as canonical_score
import score_semantic_extraction_v9 as semantic_score
import semantic_extraction_v9 as semantic

EXPECTED_MODEL = "qwen3.8:27b-mlx"
EXPECTED_ARM = "reduced_context"
EXPECTED_NUM_CTX = 65536
EXPECTED_TEMPERATURE = 0.0
EXPECTED_SEED = 7
BUNDLE_SCHEMA_VERSION = "0.2.0"
BUNDLE_ID = "stm32f103c-qwen-v9-device-identity-retained-model-proof-v0"
FILES = {
    "raw": "reduced_context.semantic-v9.raw.txt",
    "run": "reduced_context.semantic-v9.run.json",
    "semantic_score": "semantic-score.json",
    "canonical": "canonical.json",
    "canonical_score": "canonical-score.json"
}


class RetainedProofError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RetainedProofError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: JSON root must be object")
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _score_semantic(run: dict[str, Any], run_path: Path) -> dict[str, Any]:
    score = semantic_score.score_run(run)
    return {
        "schema_version": semantic_score.SCORE_SCHEMA_VERSION,
        "experiment_id": semantic.SEMANTIC_EXPERIMENT_ID,
        "run_file": run_path.name,
        "run_sha256": harness.sha256_bytes(run_path.read_bytes()),
        "score_authority": {
            "ground_truth_file": semantic_score.GROUND_TRUTH.name,
            "ground_truth_sha256": harness.sha256_bytes(semantic_score.GROUND_TRUTH.read_bytes()),
            "generation_reads_score_authority": False
        },
        "score": score
    }


def _score_canonical(report: dict[str, Any], canonical_path: Path) -> dict[str, Any]:
    score = canonical_score.score_report(report)
    return {
        "schema_version": canonical_score.SCORE_SCHEMA_VERSION,
        "pipeline_id": canonical_pipeline.PIPELINE_ID,
        "canonical_file": canonical_path.name,
        "canonical_sha256": harness.sha256_bytes(canonical_path.read_bytes()),
        "score_authority": {
            "ground_truth_file": canonical_score.GROUND_TRUTH.name,
            "ground_truth_sha256": harness.sha256_bytes(canonical_score.GROUND_TRUTH.read_bytes()),
            "generation_reads_ground_truth": False
        },
        "score": score
    }


def verify_bundle(output_dir: Path) -> dict[str, Any]:
    paths = {name: output_dir / filename for name, filename in FILES.items()}
    for name, path in paths.items():
        require(path.is_file(), f"retained artifact missing: {name}: {path}")

    run = load_json(paths["run"])
    semantic_report = load_json(paths["semantic_score"])
    canonical_report = load_json(paths["canonical"])
    canonical_score_report = load_json(paths["canonical_score"])

    require(run.get("status") == "success", "retained model run must be successful")
    require(run.get("experiment_id") == semantic.SEMANTIC_EXPERIMENT_ID, "v9 experiment ID mismatch")
    require(run.get("arm") == EXPECTED_ARM, "retained proof requires reduced_context")
    runtime = run.get("runtime")
    generation = run.get("generation")
    identity = run.get("identity_ontology")
    require(isinstance(runtime, dict), "runtime metadata required")
    require(isinstance(generation, dict), "generation metadata required")
    require(isinstance(identity, dict), "identity ontology metadata required")
    require(runtime.get("model_id") == EXPECTED_MODEL, f"retained proof requires model {EXPECTED_MODEL}")
    require(runtime.get("configured_context_tokens") == EXPECTED_NUM_CTX, "retained proof requires 64K context")
    require(generation.get("temperature") == EXPECTED_TEMPERATURE, "retained proof requires temperature 0")
    require(generation.get("seed") == EXPECTED_SEED, "retained proof requires seed 7")
    require(identity.get("commercial_target_identity_source") == "targets_map_key", "commercial identity source mismatch")
    require(identity.get("commercial_identity_is_ai_extracted_leaf") is False, "commercial identity must not be AI-extracted leaf")
    require(identity.get("fuzzy_identity_equivalence") is False, "identity fuzzy equivalence must remain disabled")

    response = run.get("response")
    require(isinstance(response, dict), "retained response required")
    facts = response.get("semantic_facts")
    require(isinstance(facts, dict), "retained semantic facts required")
    require(facts.get("profile_relationships") == {}, "v9 AI output must contain no profile relationships")
    targets = facts.get("targets")
    require(isinstance(targets, dict), "semantic targets required")
    require(set(targets) == {"STM32F103C8T6", "STM32F103CBT6"}, "commercial target map-key identity mismatch")

    sscore = semantic_report.get("score")
    require(isinstance(sscore, dict), "semantic score required")
    require(sscore.get("status") == "scored", "semantic score must be scored")
    require(sscore.get("semantic_accuracy") == 1.0, "semantic accuracy must be 1.0")
    for key in ("wrong_semantic_assertion_count", "missing_unknown_count", "uncited_assertion_count", "out_of_context_citation_count"):
        require(sscore.get(key) == 0, f"semantic proof requires {key}=0")

    canonicalization = canonical_report.get("canonicalization")
    require(isinstance(canonicalization, dict), "canonicalization report required")
    require(canonicalization.get("canonicalization_status") == "complete", "canonicalization must be complete")
    spec = canonicalization.get("canonical_spec")
    require(isinstance(spec, dict), "canonical spec required")
    expected_relationships = {
        "programming": "shared",
        "memory_geometry": "different",
        "package_hardware": "shared",
        "option": "shared",
        "security": "shared"
    }
    require(spec.get("profile_relationships") == expected_relationships, "canonical relationship set mismatch")

    cscore = canonical_score_report.get("score")
    require(isinstance(cscore, dict), "canonical score required")
    require(cscore.get("status") == "scored", "canonical score must be scored")
    require(cscore.get("exact_accuracy") == 1.0, "canonical exact accuracy must be 1.0")
    for key in ("wrong_assertion_count", "missing_unknown_count", "uncited_assertion_count", "out_of_context_citation_count"):
        require(cscore.get(key) == 0, f"canonical proof requires {key}=0")

    trust_sources = [run.get("trust_boundary"), canonical_report.get("trust_boundary"), canonicalization.get("trust_boundary")]
    for trust in trust_sources:
        require(isinstance(trust, dict), "trust boundary required")
        require(trust.get("canonical_dataset_admission") is False, "canonical dataset admission must remain false")
        require(trust.get("production_admission") is False, "production admission must remain false")
        require(trust.get("destructive_security_operation_admission") is False, "destructive security admission must remain false")

    return {
        "schema_version": BUNDLE_SCHEMA_VERSION,
        "bundle_id": BUNDLE_ID,
        "status": "verified_retained_model_proof",
        "model_id": EXPECTED_MODEL,
        "arm": EXPECTED_ARM,
        "generation": {"num_ctx": EXPECTED_NUM_CTX, "temperature": EXPECTED_TEMPERATURE, "seed": EXPECTED_SEED},
        "identity_ontology": {
            "commercial_target_identity_source": "targets_map_key",
            "manufacturer_applicability_expression": "evidence_backed_ai_extracted_fact",
            "commercial_identity_is_ai_extracted_leaf": False,
            "fuzzy_identity_equivalence": False
        },
        "semantic": {
            "accuracy": sscore["semantic_accuracy"],
            "wrong": sscore["wrong_semantic_assertion_count"],
            "missing_unknown": sscore["missing_unknown_count"]
        },
        "canonical": {
            "exact_accuracy": cscore["exact_accuracy"],
            "wrong": cscore["wrong_assertion_count"],
            "missing_unknown": cscore["missing_unknown_count"],
            "profile_relationships": expected_relationships
        },
        "trust_boundary": {
            "ai_emits_profile_relationships": False,
            "canonical_dataset_admission": False,
            "production_admission": False,
            "destructive_security_operation_admission": False,
            "hil_admission": False
        },
        "artifacts": {
            name: {"file": path.name, "sha256": harness.sha256_bytes(path.read_bytes())}
            for name, path in paths.items()
        }
    }


def execute(*, workspace: Path, output_dir: Path, ollama_url: str, runtime_label: str, timeout_seconds: float) -> dict[str, Any]:
    output_dir.mkdir(parents=True, exist_ok=True)
    run = ollama_runner.execute_arm(
        workspace=workspace, arm_name=EXPECTED_ARM, output_dir=output_dir,
        ollama_url=ollama_url, model=EXPECTED_MODEL, runtime_label=runtime_label,
        num_ctx=EXPECTED_NUM_CTX, max_tokens=4096, temperature=EXPECTED_TEMPERATURE,
        seed=EXPECTED_SEED, timeout_seconds=timeout_seconds
    )
    require(run.get("status") == "success", f"model run failed: {run.get('error')}")
    run_path = output_dir / FILES["run"]
    semantic_report = _score_semantic(run, run_path)
    _write_json(output_dir / FILES["semantic_score"], semantic_report)
    canonical_report = canonical_pipeline.canonicalize_run(run_path)
    canonical_path = output_dir / FILES["canonical"]
    _write_json(canonical_path, canonical_report)
    canonical_score_report = _score_canonical(canonical_report, canonical_path)
    _write_json(output_dir / FILES["canonical_score"], canonical_score_report)
    manifest = verify_bundle(output_dir)
    _write_json(output_dir / "retained-proof-manifest.json", manifest)
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Execute or verify the STM32F103C Qwen v9 device-identity retained model proof")
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--verify-only", action="store_true")
    parser.add_argument("--workspace", type=Path)
    parser.add_argument("--ollama-url", default="http://127.0.0.1:11434")
    parser.add_argument("--runtime-label", default="mac-m3max-48gb-ollama-qwen3.8-27b-mlx-64k-semantic-v9")
    parser.add_argument("--timeout-seconds", type=float, default=1800.0)
    args = parser.parse_args()
    try:
        if args.verify_only:
            manifest = verify_bundle(args.output_dir)
        else:
            require(args.workspace is not None, "--workspace is required unless --verify-only is used")
            manifest = execute(
                workspace=args.workspace, output_dir=args.output_dir,
                ollama_url=args.ollama_url, runtime_label=args.runtime_label,
                timeout_seconds=args.timeout_seconds
            )
        print("STM32F103C v9 retained model proof VERIFIED")
        print(f"- model: {manifest['model_id']}")
        print(f"- semantic accuracy: {manifest['semantic']['accuracy']}")
        print(f"- canonical exact accuracy: {manifest['canonical']['exact_accuracy']}")
        print("- commercial identity source: target map key")
        print("- identity fuzzy equivalence: false")
        print("- HIL / production / destructive security admission: false")
        return 0
    except (OSError, json.JSONDecodeError, RetainedProofError, semantic.SemanticExtractionError) as exc:
        print(f"STM32F103C v9 retained model proof FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

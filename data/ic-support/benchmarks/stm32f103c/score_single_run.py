#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import ab_benchmark as harness
import score_ab_benchmark as scorer

HERE = Path(__file__).resolve().parent
GROUND_TRUTH = HERE / "extraction-ground-truth.json"
SINGLE_SCORE_SCHEMA_VERSION = "0.1.0"


class SingleScoreError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SingleScoreError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def score_single(run_path: Path) -> dict[str, Any]:
    run = load_json(run_path)
    truth = load_json(GROUND_TRUTH)
    expected = truth.get("expected")
    require(isinstance(expected, dict), "extraction ground truth expected object required")

    score = scorer.score_run(run, expected)
    return {
        "schema_version": SINGLE_SCORE_SCHEMA_VERSION,
        "experiment_id": harness.EXPERIMENT_ID,
        "arm": run.get("arm"),
        "run_file": run_path.name,
        "run_sha256": harness.sha256_bytes(run_path.read_bytes()),
        "score_authority": {
            "ground_truth_file": GROUND_TRUTH.name,
            "ground_truth_sha256": harness.sha256_bytes(GROUND_TRUTH.read_bytes()),
            "generation_path_reads_ground_truth": False,
        },
        "runtime": run.get("runtime"),
        "generation": run.get("generation"),
        "usage": run.get("usage"),
        "timing": run.get("timing"),
        "score": score,
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Score one STM32F103C extraction run against the isolated benchmark answer key"
    )
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    try:
        report = score_single(args.run)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        score = report["score"]
        print("IC Evidence single-run score PASS" if score.get("status") == "scored" else "IC Evidence single-run score RUN_ERROR")
        print(f"- exact accuracy: {score.get('exact_accuracy')}")
        print(f"- wrong assertions: {score.get('wrong_assertion_count')}")
        print(f"- missing/unknown: {score.get('missing_unknown_count')}")
        print(f"- uncited assertions: {score.get('uncited_assertion_count')}")
        print(f"- unsupported-inference proxy: {score.get('unsupported_inference_proxy_count')}")
        return 0 if score.get("status") == "scored" else 1
    except (OSError, json.JSONDecodeError, SingleScoreError, scorer.ABScoreError, harness.ABBenchmarkError) as exc:
        print(f"IC Evidence single-run score FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

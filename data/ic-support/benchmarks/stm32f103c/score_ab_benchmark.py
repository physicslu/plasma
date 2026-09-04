#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path
from typing import Any

import ab_benchmark as harness

HERE = Path(__file__).resolve().parent
GROUND_TRUTH = HERE / "extraction-ground-truth.json"
SCORE_SCHEMA_VERSION = "0.1.0"


class ABScoreError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ABScoreError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: JSON root must be an object")
    return value


def flatten_leaves(value: Any, path: str = "$") -> dict[str, Any]:
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key in sorted(value):
            out.update(flatten_leaves(value[key], f"{path}.{key}"))
        return out
    return {path: value}


def is_missing_or_unknown(value: Any) -> bool:
    return value is None or value == "unknown"


def _allowed_pages(run: dict[str, Any]) -> dict[str, set[int]]:
    context = run.get("context")
    require(isinstance(context, dict), "run context required")
    ds_pages = context.get("datasheet_physical_pages")
    pm_pages = context.get("programming_manual_physical_pages")
    require(isinstance(ds_pages, list) and all(isinstance(v, int) for v in ds_pages), "datasheet pages invalid")
    require(isinstance(pm_pages, list) and all(isinstance(v, int) for v in pm_pages), "programming manual pages invalid")
    return {
        harness.DS_SOURCE_ID: set(ds_pages),
        harness.PM_SOURCE_ID: set(pm_pages),
    }


def score_run(run: dict[str, Any], expected: dict[str, Any]) -> dict[str, Any]:
    if run.get("status") != "success":
        return {
            "status": "run_error",
            "error": run.get("error"),
            "exact_field_count": 0,
            "total_field_count": len(flatten_leaves(expected)),
            "exact_accuracy": 0.0,
            "wrong_assertion_count": 0,
            "missing_unknown_count": len(flatten_leaves(expected)),
            "uncited_assertion_count": 0,
            "out_of_context_citation_count": 0,
            "unsupported_inference_proxy_count": 0,
            "paths": {},
        }

    response = run.get("response")
    require(isinstance(response, dict), "successful run requires response")
    observed = response.get("observed")
    evidence = response.get("evidence")
    require(isinstance(observed, dict), "successful run observed required")
    require(isinstance(evidence, dict), "successful run evidence required")

    expected_leaves = flatten_leaves(expected)
    observed_leaves = flatten_leaves(observed)
    require(set(observed_leaves) == set(expected_leaves), "observed leaf paths do not match score contract")
    allowed = _allowed_pages(run)

    exact_paths: list[str] = []
    wrong_paths: list[str] = []
    missing_paths: list[str] = []
    uncited_paths: list[str] = []
    out_of_context_paths: list[str] = []
    unsupported_proxy_paths: set[str] = set()

    for path, expected_value in expected_leaves.items():
        actual = observed_leaves[path]
        if actual == expected_value:
            exact_paths.append(path)
        elif is_missing_or_unknown(actual):
            missing_paths.append(path)
        else:
            wrong_paths.append(path)
            unsupported_proxy_paths.add(path)

        if is_missing_or_unknown(actual):
            continue
        citations = evidence.get(path)
        valid_citation = False
        invalid_citation = False
        if not isinstance(citations, list) or not citations:
            uncited_paths.append(path)
            unsupported_proxy_paths.add(path)
            continue
        for citation in citations:
            if not isinstance(citation, dict):
                invalid_citation = True
                continue
            source_id = citation.get("source_id")
            page_index = citation.get("physical_page_index")
            if (
                isinstance(source_id, str)
                and isinstance(page_index, int)
                and source_id in allowed
                and page_index in allowed[source_id]
            ):
                valid_citation = True
            else:
                invalid_citation = True
        if invalid_citation:
            out_of_context_paths.append(path)
        if not valid_citation:
            unsupported_proxy_paths.add(path)

    unexpected_evidence_paths = sorted(set(evidence) - set(expected_leaves))
    total = len(expected_leaves)
    return {
        "status": "scored",
        "exact_field_count": len(exact_paths),
        "total_field_count": total,
        "exact_accuracy": len(exact_paths) / total if total else 1.0,
        "wrong_assertion_count": len(wrong_paths),
        "missing_unknown_count": len(missing_paths),
        "uncited_assertion_count": len(uncited_paths),
        "out_of_context_citation_count": len(set(out_of_context_paths)),
        "unsupported_inference_proxy_count": len(unsupported_proxy_paths),
        "unexpected_evidence_path_count": len(unexpected_evidence_paths),
        "paths": {
            "wrong": sorted(wrong_paths),
            "missing_unknown": sorted(missing_paths),
            "uncited": sorted(uncited_paths),
            "out_of_context_citation": sorted(set(out_of_context_paths)),
            "unsupported_inference_proxy": sorted(unsupported_proxy_paths),
            "unexpected_evidence": unexpected_evidence_paths,
        },
    }


def _controlled_projection(run: dict[str, Any]) -> dict[str, Any]:
    context = run.get("context", {})
    prompt = run.get("prompt", {})
    return {
        "experiment_id": run.get("experiment_id"),
        "source_lock_id": run.get("source_lock_id"),
        "source_digests": run.get("source_digests"),
        "runtime": run.get("runtime"),
        "generation": run.get("generation"),
        "prompt_template_sha256": prompt.get("template_sha256"),
        "observed_schema_sha256": prompt.get("observed_schema_sha256"),
        "programming_manual_sha256": context.get("programming_manual_sha256"),
        "preprocessor": context.get("preprocessor"),
        "normalization": context.get("normalization"),
    }


def validate_pair(full: dict[str, Any], reduced: dict[str, Any]) -> None:
    require(full.get("arm") == "full_context", "full run arm mismatch")
    require(reduced.get("arm") == "reduced_context", "reduced run arm mismatch")
    require(full.get("trial_index") == reduced.get("trial_index"), "pair trial mismatch")
    require(_controlled_projection(full) == _controlled_projection(reduced), "controlled variables drift between A/B arms")
    full_context = full.get("context", {})
    reduced_context = reduced.get("context", {})
    require(full_context.get("datasheet_mode") == "FULL_LOCKED_SOURCE", "full datasheet mode mismatch")
    require(reduced_context.get("datasheet_mode") == "DETERMINISTIC_EVIDENCE_PACK", "reduced datasheet mode mismatch")
    require(
        full_context.get("programming_manual_sha256") == reduced_context.get("programming_manual_sha256"),
        "programming manual context drift",
    )


def _numeric(run: dict[str, Any], *path: str) -> float | None:
    value: Any = run
    for key in path:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    return None


def _median(values: list[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return statistics.median(known) if known else None


def _mean(values: list[float | None]) -> float | None:
    known = [value for value in values if value is not None]
    return statistics.mean(known) if known else None


def aggregate_arm(entries: list[tuple[dict[str, Any], dict[str, Any]]]) -> dict[str, Any]:
    runs = [entry[0] for entry in entries]
    scores = [entry[1] for entry in entries]
    successful_scores = [score for score in scores if score.get("status") == "scored"]
    return {
        "run_count": len(runs),
        "successful_run_count": len(successful_scores),
        "exact_accuracy_mean": _mean([float(score["exact_accuracy"]) for score in successful_scores]),
        "wrong_assertion_count_mean": _mean([float(score["wrong_assertion_count"]) for score in successful_scores]),
        "missing_unknown_count_mean": _mean([float(score["missing_unknown_count"]) for score in successful_scores]),
        "uncited_assertion_count_mean": _mean([float(score["uncited_assertion_count"]) for score in successful_scores]),
        "unsupported_inference_proxy_count_mean": _mean([
            float(score["unsupported_inference_proxy_count"]) for score in successful_scores
        ]),
        "ttft_ms_median": _median([_numeric(run, "timing", "ttft_ms") for run in runs]),
        "total_time_ms_median": _median([_numeric(run, "timing", "total_time_ms") for run in runs]),
        "input_tokens_median": _median([_numeric(run, "usage", "input_tokens") for run in runs]),
        "generation_tokens_median": _median([_numeric(run, "usage", "generation_tokens") for run in runs]),
        "rendered_prompt_bytes": _median([_numeric(run, "prompt", "rendered_byte_length") for run in runs]),
        "datasheet_input_bytes": _median([_numeric(run, "context", "datasheet_input_bytes") for run in runs]),
    }


def _reduction(full: float | None, reduced: float | None) -> dict[str, float | None]:
    if full is None or reduced is None:
        return {"delta_reduced_minus_full": None, "reduction_percent": None}
    percent = None if full == 0 else (full - reduced) / full * 100.0
    return {
        "delta_reduced_minus_full": reduced - full,
        "reduction_percent": percent,
    }


def score_results(results_dir: Path) -> dict[str, Any]:
    truth = load_json(GROUND_TRUTH)
    expected = truth.get("expected")
    require(isinstance(expected, dict), "extraction ground truth expected object required")

    trial_dirs = sorted(path for path in results_dir.glob("trial-*") if path.is_dir())
    require(trial_dirs, f"{results_dir}: no trial directories found")
    full_entries: list[tuple[dict[str, Any], dict[str, Any]]] = []
    reduced_entries: list[tuple[dict[str, Any], dict[str, Any]]] = []
    pair_reports: list[dict[str, Any]] = []
    baseline_control: dict[str, Any] | None = None

    for trial_dir in trial_dirs:
        full = load_json(trial_dir / "full_context.run.json")
        reduced = load_json(trial_dir / "reduced_context.run.json")
        validate_pair(full, reduced)
        control = _controlled_projection(full)
        if baseline_control is None:
            baseline_control = control
        else:
            require(control == baseline_control, "controlled variables drift across trials")
        full_score = score_run(full, expected)
        reduced_score = score_run(reduced, expected)
        full_entries.append((full, full_score))
        reduced_entries.append((reduced, reduced_score))

        pair_pass = (
            full_score["status"] == "scored"
            and reduced_score["status"] == "scored"
            and reduced_score["exact_accuracy"] >= full_score["exact_accuracy"]
            and reduced_score["wrong_assertion_count"] <= full_score["wrong_assertion_count"]
            and reduced_score["missing_unknown_count"] <= full_score["missing_unknown_count"]
            and reduced_score["unsupported_inference_proxy_count"]
            <= full_score["unsupported_inference_proxy_count"]
        )
        pair_reports.append({
            "trial_index": full.get("trial_index"),
            "execution_order": [
                arm
                for _, arm in sorted([
                    (full.get("order_position"), "full_context"),
                    (reduced.get("order_position"), "reduced_context"),
                ])
            ],
            "full_context": full_score,
            "reduced_context": reduced_score,
            "correctness_non_regression": pair_pass,
        })

    full_aggregate = aggregate_arm(full_entries)
    reduced_aggregate = aggregate_arm(reduced_entries)
    report = {
        "schema_version": SCORE_SCHEMA_VERSION,
        "experiment_id": harness.EXPERIMENT_ID,
        "score_authority": {
            "ground_truth_file": GROUND_TRUTH.name,
            "ground_truth_sha256": harness.sha256_bytes(GROUND_TRUTH.read_bytes()),
            "generation_path_reads_ground_truth": False,
        },
        "controlled_variables": baseline_control,
        "metric_definitions": {
            "exact_accuracy": "Exact field-level match against the source-locked extraction ground truth; arrays count as one leaf field.",
            "wrong_assertion_count": "Asserted non-null/non-unknown leaf values that differ from ground truth.",
            "missing_unknown_count": "Ground-truth leaf fields returned as null or unknown.",
            "uncited_assertion_count": "Asserted leaf fields without any citation entry.",
            "out_of_context_citation_count": "Asserted leaf fields containing at least one citation outside the arm's supplied source/page set.",
            "unsupported_inference_proxy_count": "Union of wrong asserted fields and asserted fields lacking any valid in-arm citation. This is a deterministic proxy, not semantic proof that a cited page entails the claim.",
        },
        "trials": pair_reports,
        "aggregate": {
            "full_context": full_aggregate,
            "reduced_context": reduced_aggregate,
        },
        "performance_delta": {
            "rendered_prompt_bytes": _reduction(
                full_aggregate["rendered_prompt_bytes"], reduced_aggregate["rendered_prompt_bytes"]
            ),
            "datasheet_input_bytes": _reduction(
                full_aggregate["datasheet_input_bytes"], reduced_aggregate["datasheet_input_bytes"]
            ),
            "input_tokens": _reduction(
                full_aggregate["input_tokens_median"], reduced_aggregate["input_tokens_median"]
            ),
            "ttft_ms": _reduction(full_aggregate["ttft_ms_median"], reduced_aggregate["ttft_ms_median"]),
            "total_time_ms": _reduction(
                full_aggregate["total_time_ms_median"], reduced_aggregate["total_time_ms_median"]
            ),
        },
        "acceptance": {
            "principle": "Reduced context must not reduce engineering correctness.",
            "correctness_non_regression_all_trials": all(
                report["correctness_non_regression"] for report in pair_reports
            ),
            "performance_is_reported_not_gate": True,
        },
    }
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Score STM32F103C full-vs-Evidence-Pack A/B benchmark runs")
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        report = score_results(args.results_dir)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        full = report["aggregate"]["full_context"]
        reduced = report["aggregate"]["reduced_context"]
        print("IC Evidence A/B score PASS")
        print(f"- full accuracy mean: {full['exact_accuracy_mean']}")
        print(f"- reduced accuracy mean: {reduced['exact_accuracy_mean']}")
        print(
            "- correctness non-regression all trials: "
            f"{report['acceptance']['correctness_non_regression_all_trials']}"
        )
        return 0
    except (OSError, json.JSONDecodeError, ABScoreError, harness.ABBenchmarkError) as exc:
        print(f"IC Evidence A/B score FAIL: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

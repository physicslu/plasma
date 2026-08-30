#!/usr/bin/env python3
"""Evaluate bounded STM32F4 browser evidence against the checked-in baseline."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32f4_admission_policy import TARGET_CONFIG

ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE = ROOT / "stm32f4-phase3.1-pilot-baseline.json"
BROWSER_TRANSPORT = "chromium_rendered_dom"
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


class PilotEvaluationError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise PilotEvaluationError(f"{path}: expected a JSON object")
    return value


def read_baseline(path: Path) -> dict[str, Any]:
    baseline = read_json(path)
    if baseline.get("schema_version") != 1 or baseline.get("canonical_dataset_admission") is not False:
        raise PilotEvaluationError("invalid STM32F4 baseline contract")
    targets = baseline.get("targets")
    if not isinstance(targets, list) or not targets:
        raise PilotEvaluationError("STM32F4 baseline requires targets")
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, dict):
            raise PilotEvaluationError("STM32F4 baseline target must be an object")
        base = target.get("base_device")
        values = target.get("exact_icpns")
        if not isinstance(base, str) or base in seen:
            raise PilotEvaluationError("STM32F4 baseline base_device is invalid or duplicate")
        if not isinstance(values, list) or not values or len(values) != len(set(values)):
            raise PilotEvaluationError(f"{base}: invalid baseline exact_icpns")
        if not all(isinstance(value, str) and value.startswith(base) for value in values):
            raise PilotEvaluationError(f"{base}: invalid baseline ICPN ownership")
        seen.add(base)
    return baseline


def _valid_st_url(value: object) -> bool:
    if not isinstance(value, str):
        return False
    try:
        validate_source_url(value)
    except AcquisitionError:
        return False
    return True


def evaluate_live_pilot(
    *,
    summary: dict[str, Any],
    baseline: dict[str, Any],
    run_metadata: dict[str, Any],
) -> dict[str, Any]:
    issues: list[str] = []
    expected = {
        target["base_device"]: set(target["exact_icpns"])
        for target in baseline["targets"]
    }
    target_count = len(expected)
    candidate_count = sum(len(values) for values in expected.values())

    if summary.get("pilot_id") != baseline.get("pilot_id"):
        issues.append("pilot_id mismatch")
    if summary.get("browser_scope") != "pilot":
        issues.append("browser scope must be pilot")
    if summary.get("acquisition_transport") != BROWSER_TRANSPORT:
        issues.append("pilot must use chromium_rendered_dom")
    if summary.get("attempted") != target_count or summary.get("acquisition_success") != target_count:
        issues.append("not all bounded targets acquired successfully")
    if summary.get("acquisition_failure") != 0 or summary.get("manual_intervention_required") != 0:
        issues.append("pilot contains failures or manual intervention")
    if summary.get("canonical_mapping") != {"unique": target_count, "ambiguous": 0, "unmapped": 0}:
        issues.append("target mapping is not uniquely clean")
    if summary.get("openocd_cfg_mapping") != {"mapped": target_count, "total": target_count}:
        issues.append("OpenOCD target mapping is incomplete")
    if summary.get("canonical_dataset_admission") is not False:
        issues.append("pilot must deny canonical admission")

    runtime = summary.get("browser_runtime")
    if not isinstance(runtime, dict) or runtime.get("engine") != "chromium" or runtime.get("headless") is not False:
        issues.append("retained pilot requires headed Chromium runtime")

    results = summary.get("results")
    if not isinstance(results, list):
        results = []
        issues.append("pilot results must be a list")
    by_base = {
        result.get("base_device"): result
        for result in results
        if isinstance(result, dict) and isinstance(result.get("base_device"), str)
    }
    if set(by_base) != set(expected):
        issues.append("pilot target set does not match baseline")

    drift: list[dict[str, Any]] = []
    observed_count = 0
    for base, expected_values in expected.items():
        result = by_base.get(base)
        if not isinstance(result, dict) or result.get("acquisition_status") != "success":
            issues.append(f"{base}: acquisition failed")
            continue
        mapping = result.get("canonical_mapping")
        if not isinstance(mapping, dict) or mapping.get("status") != "unique" or mapping.get("target_configs") != [TARGET_CONFIG]:
            issues.append(f"{base}: target ordering-pattern mapping is not unique")
        candidate_mappings = result.get("candidate_mappings")
        if not isinstance(candidate_mappings, list) or not candidate_mappings:
            issues.append(f"{base}: candidate mappings missing")
        elif any(
            not isinstance(item, dict)
            or item.get("status") != "unique"
            or item.get("target_configs") != [TARGET_CONFIG]
            or item.get("identifier_kind") != "ordering_pattern"
            for item in candidate_mappings
        ):
            issues.append(f"{base}: one or more exact ICPNs lack unique ordering-pattern mapping")

        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            issues.append(f"{base}: evidence missing")
            continue
        if evidence.get("acquisition_transport") != BROWSER_TRANSPORT:
            issues.append(f"{base}: wrong evidence transport")
        if evidence.get("base_device") != base:
            issues.append(f"{base}: evidence identity mismatch")
        if not _valid_st_url(evidence.get("source_url")) or not _valid_st_url(evidence.get("final_url")):
            issues.append(f"{base}: invalid ST source URL")
        if not isinstance(evidence.get("rendered_dom_sha256"), str) or SHA256_RE.fullmatch(evidence["rendered_dom_sha256"]) is None:
            issues.append(f"{base}: invalid rendered DOM SHA")
        if not isinstance(evidence.get("evidence_section_sha256"), str) or SHA256_RE.fullmatch(evidence["evidence_section_sha256"]) is None:
            issues.append(f"{base}: invalid evidence section SHA")
        if "raw_sha256" in evidence:
            issues.append(f"{base}: browser evidence must not claim raw_sha256")
        values = evidence.get("exact_icpns")
        if not isinstance(values, list) or not all(isinstance(value, str) for value in values):
            issues.append(f"{base}: exact_icpns must be strings")
            observed = set()
        else:
            observed = set(values)
            observed_count += len(values)
            if len(observed) != len(values):
                issues.append(f"{base}: duplicate exact ICPN")
        added = sorted(observed - expected_values)
        removed = sorted(expected_values - observed)
        if added or removed:
            drift.append({"base_device": base, "added": added, "removed": removed})

    if summary.get("exact_icpn_candidates") != observed_count or observed_count != candidate_count:
        issues.append("candidate count mismatch")
    if drift:
        issues.append("exact ICPN candidate drift detected")

    repository = run_metadata.get("repository")
    git_sha = run_metadata.get("git_sha")
    if repository != "physicslu/plasma":
        issues.append("run repository mismatch")
    if not isinstance(git_sha, str) or GIT_SHA_RE.fullmatch(git_sha) is None:
        issues.append("run requires full Git SHA")

    scale_ready = not issues
    return {
        "schema_version": 1,
        "pilot_id": baseline["pilot_id"],
        "run_metadata": dict(run_metadata),
        "target_count": target_count,
        "expected_exact_icpn_candidates": candidate_count,
        "observed_exact_icpn_candidates": observed_count,
        "candidate_baseline_match": not drift and observed_count == candidate_count,
        "candidate_drift": drift,
        "ordering_pattern_mapping": {
            "mapped": target_count if summary.get("canonical_mapping") == {"unique": target_count, "ambiguous": 0, "unmapped": 0} else 0,
            "target_config": TARGET_CONFIG,
        },
        "decision": "scale_ready" if scale_ready else "blocked",
        "scale_ready": scale_ready,
        "canonical_dataset_admission": False,
        "issues": issues,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--repository", default="physicslu/plasma")
    parser.add_argument("--git-sha", required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        evaluation = evaluate_live_pilot(
            summary=read_json(args.summary),
            baseline=read_baseline(args.baseline),
            run_metadata={"repository": args.repository, "git_sha": args.git_sha},
        )
        args.output.write_text(json.dumps(evaluation, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if evaluation["scale_ready"] else 1
    except (OSError, json.JSONDecodeError, PilotEvaluationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

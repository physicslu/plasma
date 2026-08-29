#!/usr/bin/env python3
"""Evaluate a live STM32F1 acquisition pilot against the Phase 2.5 research baseline.

This evaluator is intentionally separate from canonical commercial ICPN admission. It
consumes the live pilot summary, verifies transport/provenance evidence, detects exact
candidate drift, and emits a scale-readiness decision. It never writes the canonical
commercial ICPN dataset.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from st_product_page_acquisition import AcquisitionError, validate_source_url

EVALUATION_SCHEMA_VERSION = 1
BASELINE_SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")
ROOT = Path(__file__).resolve().parent
DEFAULT_BASELINE = ROOT / "stm32f1-acquisition-pilot-baseline.json"


class LivePilotEvaluationError(RuntimeError):
    pass


def read_json_object(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise LivePilotEvaluationError(f"{path}: expected a JSON object")
    return payload


def read_baseline(path: Path) -> dict[str, Any]:
    payload = read_json_object(path)
    if payload.get("schema_version") != BASELINE_SCHEMA_VERSION:
        raise LivePilotEvaluationError("unsupported live-pilot baseline schema_version")
    if payload.get("canonical_dataset_admission") is not False:
        raise LivePilotEvaluationError("live-pilot baseline must not be canonical dataset admission")
    pilot_id = payload.get("pilot_id")
    if not isinstance(pilot_id, str) or not pilot_id:
        raise LivePilotEvaluationError("live-pilot baseline requires pilot_id")
    raw_targets = payload.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        raise LivePilotEvaluationError("live-pilot baseline requires targets")

    seen: set[str] = set()
    for index, target in enumerate(raw_targets, start=1):
        if not isinstance(target, dict):
            raise LivePilotEvaluationError(f"baseline target {index} must be an object")
        base_device = target.get("base_device")
        exact_icpns = target.get("exact_icpns")
        if not isinstance(base_device, str) or not base_device:
            raise LivePilotEvaluationError(f"baseline target {index} requires base_device")
        if base_device in seen:
            raise LivePilotEvaluationError(f"duplicate baseline base_device: {base_device}")
        seen.add(base_device)
        if not isinstance(exact_icpns, list) or not exact_icpns:
            raise LivePilotEvaluationError(f"baseline target {base_device} requires exact_icpns")
        if len(exact_icpns) != len(set(exact_icpns)):
            raise LivePilotEvaluationError(f"baseline target {base_device} contains duplicate exact_icpns")
        if not all(isinstance(icpn, str) and icpn.startswith(base_device) for icpn in exact_icpns):
            raise LivePilotEvaluationError(f"baseline target {base_device} contains invalid exact_icpns")
    return payload


def _valid_sha256(value: object) -> bool:
    return isinstance(value, str) and SHA256_RE.fullmatch(value) is not None


def _valid_timestamp(value: object) -> bool:
    return isinstance(value, str) and len(value) >= 20 and value.endswith("Z") and "T" in value


def _validate_official_url(value: object) -> bool:
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
    run_metadata: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    issues: list[str] = []
    baseline_targets = baseline["targets"]
    expected_by_base = {
        target["base_device"]: set(target["exact_icpns"])
        for target in baseline_targets
    }
    expected_target_count = len(expected_by_base)
    expected_candidate_count = sum(len(values) for values in expected_by_base.values())

    if summary.get("schema_version") != 1:
        issues.append("unexpected pilot summary schema_version")
    if summary.get("pilot_id") != baseline.get("pilot_id"):
        issues.append("pilot_id does not match the checked-in baseline")
    if summary.get("attempted") != expected_target_count:
        issues.append("attempted target count does not match the checked-in baseline")
    if summary.get("acquisition_success") != expected_target_count:
        issues.append("not all pilot targets acquired successfully")
    if summary.get("acquisition_failure") != 0:
        issues.append("live pilot contains acquisition failures")
    if summary.get("manual_intervention_required") != 0:
        issues.append("pilot runner requires manual intervention")

    canonical_mapping = summary.get("canonical_mapping")
    if canonical_mapping != {"unique": expected_target_count, "ambiguous": 0, "unmapped": 0}:
        issues.append("canonical mapping is not uniquely clean for every pilot target")
    openocd_mapping = summary.get("openocd_cfg_mapping")
    if openocd_mapping != {"mapped": expected_target_count, "total": expected_target_count}:
        issues.append("OpenOCD CFG mapping is not complete for every pilot target")

    raw_results = summary.get("results")
    if not isinstance(raw_results, list):
        raw_results = []
        issues.append("pilot summary results must be a list")

    result_by_base: dict[str, dict[str, Any]] = {}
    for result in raw_results:
        if not isinstance(result, dict):
            issues.append("pilot summary contains a non-object result")
            continue
        base_device = result.get("base_device")
        if not isinstance(base_device, str):
            issues.append("pilot result is missing base_device")
            continue
        if base_device in result_by_base:
            issues.append(f"duplicate live result for {base_device}")
            continue
        result_by_base[base_device] = result

    unexpected_bases = sorted(set(result_by_base) - set(expected_by_base))
    if unexpected_bases:
        issues.append("unexpected live result base device(s): " + ", ".join(unexpected_bases))

    drift: list[dict[str, Any]] = []
    etag_present = 0
    last_modified_present = 0
    valid_transport_evidence = 0
    observed_candidate_count = 0

    for base_device, expected_candidates in expected_by_base.items():
        result = result_by_base.get(base_device)
        if result is None:
            issues.append(f"missing live result for {base_device}")
            continue
        if result.get("acquisition_status") != "success":
            issues.append(f"{base_device}: acquisition_status is not success")
            continue

        mapping = result.get("canonical_mapping")
        if not isinstance(mapping, dict) or mapping.get("status") != "unique" or not mapping.get("target_configs"):
            issues.append(f"{base_device}: canonical mapping is not uniquely executable")

        evidence = result.get("evidence")
        if not isinstance(evidence, dict):
            issues.append(f"{base_device}: missing evidence object")
            continue

        transport_ok = True
        if evidence.get("base_device") != base_device:
            issues.append(f"{base_device}: evidence base_device mismatch")
            transport_ok = False
        for field in ("source_url", "final_url"):
            if not _validate_official_url(evidence.get(field)):
                issues.append(f"{base_device}: {field} is not an approved ST product URL")
                transport_ok = False
        if not _valid_timestamp(evidence.get("retrieved_at_utc")):
            issues.append(f"{base_device}: invalid retrieved_at_utc")
            transport_ok = False
        if not _valid_sha256(evidence.get("raw_sha256")):
            issues.append(f"{base_device}: invalid raw_sha256")
            transport_ok = False
        if not _valid_sha256(evidence.get("evidence_section_sha256")):
            issues.append(f"{base_device}: invalid evidence_section_sha256")
            transport_ok = False
        if evidence.get("evidence_surface") != "quality_and_reliability_part_number":
            issues.append(f"{base_device}: unexpected evidence_surface")
            transport_ok = False
        if transport_ok:
            valid_transport_evidence += 1

        if evidence.get("http_etag"):
            etag_present += 1
        if evidence.get("http_last_modified"):
            last_modified_present += 1

        raw_candidates = evidence.get("exact_icpns")
        if not isinstance(raw_candidates, list) or not all(isinstance(value, str) for value in raw_candidates):
            issues.append(f"{base_device}: exact_icpns must be a string list")
            observed_candidates: set[str] = set()
        else:
            observed_candidates = set(raw_candidates)
            observed_candidate_count += len(raw_candidates)
            if len(raw_candidates) != len(observed_candidates):
                issues.append(f"{base_device}: live exact_icpns contain duplicates")

        added = sorted(observed_candidates - expected_candidates)
        removed = sorted(expected_candidates - observed_candidates)
        if added or removed:
            drift.append({"base_device": base_device, "added": added, "removed": removed})

    if summary.get("exact_icpn_candidates") != observed_candidate_count:
        issues.append("summary exact_icpn_candidates does not match evidence records")
    if observed_candidate_count != expected_candidate_count:
        issues.append("live candidate count differs from the checked-in baseline")
    if drift:
        issues.append("live exact ICPN candidate set differs from the checked-in baseline")

    transport_evidence_complete = valid_transport_evidence == expected_target_count
    candidate_baseline_match = not drift and observed_candidate_count == expected_candidate_count
    scale_ready = not issues and transport_evidence_complete and candidate_baseline_match

    return {
        "schema_version": EVALUATION_SCHEMA_VERSION,
        "pilot_id": baseline["pilot_id"],
        "decision": "scale_ready" if scale_ready else "manual_review_required",
        "scale_ready": scale_ready,
        "expected_targets": expected_target_count,
        "expected_exact_icpn_candidates": expected_candidate_count,
        "observed_exact_icpn_candidates": observed_candidate_count,
        "transport_evidence": {
            "valid_records": valid_transport_evidence,
            "total": expected_target_count,
            "complete": transport_evidence_complete,
            "etag_present": etag_present,
            "last_modified_present": last_modified_present,
            "headers_are_optional": True,
        },
        "candidate_baseline_match": candidate_baseline_match,
        "candidate_drift": drift,
        "issues": issues,
        "run_metadata": run_metadata or {},
        "canonical_dataset_admission": False,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--output", type=Path, help="Write evaluation JSON; stdout if omitted")
    parser.add_argument("--run-id")
    parser.add_argument("--run-attempt")
    parser.add_argument("--repository")
    parser.add_argument("--git-sha")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        summary = read_json_object(args.summary)
        baseline = read_baseline(args.baseline)
        report = evaluate_live_pilot(
            summary=summary,
            baseline=baseline,
            run_metadata={
                "run_id": args.run_id,
                "run_attempt": args.run_attempt,
                "repository": args.repository,
                "git_sha": args.git_sha,
            },
        )
        payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0 if report["scale_ready"] else 1
    except (OSError, json.JSONDecodeError, LivePilotEvaluationError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

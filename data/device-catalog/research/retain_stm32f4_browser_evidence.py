#!/usr/bin/env python3
"""Retain a successful STM32F4 browser pilot using the generic evidence framework."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path
from typing import Any

from device_catalog_evidence_framework import build_manifest, sha256
from evaluate_stm32f4_pilot import evaluate_live_pilot, read_baseline
from validate_stm32f4_retained_evidence import RetainedEvidenceError, validate_retained_evidence

RETAINED_FILES = {
    "control-summary.json",
    "pilot-summary.json",
    "evaluation.json",
    "provenance.json",
    "README.md",
}


class RetentionError(RuntimeError):
    pass


def read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RetentionError(f"{path}: expected a JSON object")
    return value


def _evidence_timestamp(summary: dict[str, Any], *, first: bool) -> str:
    results = summary.get("results")
    if not isinstance(results, list) or not results:
        raise RetentionError("summary has no results")
    values = []
    for result in results:
        if not isinstance(result, dict) or not isinstance(result.get("evidence"), dict):
            raise RetentionError("result lacks evidence")
        stamp = result["evidence"].get("retrieved_at_utc")
        if not isinstance(stamp, str) or not stamp:
            raise RetentionError("evidence lacks retrieved_at_utc")
        values.append(stamp)
    return min(values) if first else max(values)


def retain(
    *,
    control_path: Path,
    pilot_path: Path,
    evaluation_path: Path,
    baseline_path: Path,
    output_dir: Path,
    evidence_id: str | None = None,
) -> dict[str, Any]:
    if output_dir.exists():
        raise RetentionError(f"output directory already exists: {output_dir}")

    control = read_json(control_path)
    pilot = read_json(pilot_path)
    evaluation = read_json(evaluation_path)
    baseline = read_baseline(baseline_path)
    run_metadata = evaluation.get("run_metadata")
    if not isinstance(run_metadata, dict):
        raise RetentionError("evaluation requires run_metadata")
    if evaluation != evaluate_live_pilot(summary=pilot, baseline=baseline, run_metadata=run_metadata):
        raise RetentionError("evaluation is not reproducible")
    if evaluation.get("scale_ready") is not True:
        raise RetentionError("evaluation is not scale_ready")
    if control.get("browser_scope") != "control" or control.get("attempted") != 1 or control.get("acquisition_success") != 1:
        raise RetentionError("control summary is not a successful 1/1 browser control")
    if pilot.get("browser_scope") != "pilot" or pilot.get("canonical_dataset_admission") is not False:
        raise RetentionError("pilot summary is not eligible for retention")

    runtime = pilot.get("browser_runtime")
    if not isinstance(runtime, dict) or runtime != control.get("browser_runtime"):
        raise RetentionError("control/pilot browser runtime mismatch")
    if runtime.get("headless") is not False:
        raise RetentionError("retained STM32F4 evidence requires headed Chromium")
    repository = run_metadata.get("repository")
    git_sha = run_metadata.get("git_sha")
    if repository != "physicslu/plasma" or not isinstance(git_sha, str) or len(git_sha) != 40:
        raise RetentionError("evaluation run metadata is invalid")

    target_count = len(baseline["targets"])
    candidate_count = sum(len(target["exact_icpns"]) for target in baseline["targets"])
    first_stamp = _evidence_timestamp(pilot, first=True)
    last_stamp = _evidence_timestamp(pilot, first=False)
    control_stamp = _evidence_timestamp(control, first=True)
    if evidence_id is None:
        compact = first_stamp.replace("-", "").replace(":", "")
        evidence_id = f"{baseline['pilot_id']}-retained-{compact}-{git_sha[:7]}"
    if not evidence_id.strip():
        raise RetentionError("evidence_id must be non-empty")

    output_dir.mkdir(parents=True)
    try:
        shutil.copyfile(control_path, output_dir / "control-summary.json")
        shutil.copyfile(pilot_path, output_dir / "pilot-summary.json")
        shutil.copyfile(evaluation_path, output_dir / "evaluation.json")
        provenance = {
            "schema_version": 1,
            "manufacturer": "STMicroelectronics",
            "source_repository": repository,
            "executed_git_sha": git_sha,
            "evidence_id": evidence_id,
            "acquisition_transport": "chromium_rendered_dom",
            "headed": True,
            "playwright_version": runtime.get("playwright_requirement"),
            "chromium_version": runtime.get("browser_version"),
            "target_count": target_count,
            "acquisition_success": pilot.get("acquisition_success"),
            "acquisition_failure": pilot.get("acquisition_failure"),
            "exact_icpn_candidate_count": candidate_count,
            "evaluator_result": evaluation.get("decision"),
            "scale_ready": True,
            "canonical_dataset_admission": False,
            "acquisition_time_utc": {
                "control": control_stamp,
                "pilot_first": first_stamp,
                "pilot_last": last_stamp,
            },
            "baseline": {
                "pilot_id": baseline["pilot_id"],
                "schema_version": baseline["schema_version"],
                "sha256": sha256(baseline_path),
            },
        }
        (output_dir / "provenance.json").write_text(
            json.dumps(provenance, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        (output_dir / "README.md").write_text(
            "# Retained STM32F4 Phase 3.1 browser evidence\n\n"
            f"Evidence ID: `{evidence_id}`\n\n"
            f"- targets: {target_count}\n"
            f"- exact ICPN candidates: {candidate_count}\n"
            "- mapping: deterministic OpenOCD ordering patterns\n"
            "- acquisition transport: `chromium_rendered_dom`\n"
            "- canonical dataset admission: false\n",
            encoding="utf-8",
        )
        manifest = build_manifest(
            output_dir,
            evidence_id=evidence_id,
            retained_files=RETAINED_FILES,
        )
        (output_dir / "manifest.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        return validate_retained_evidence(output_dir, baseline_path=baseline_path)
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--control", type=Path, required=True)
    parser.add_argument("--pilot", type=Path, required=True)
    parser.add_argument("--evaluation", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--evidence-id")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = retain(
            control_path=args.control,
            pilot_path=args.pilot,
            evaluation_path=args.evaluation,
            baseline_path=args.baseline,
            output_dir=args.output_dir,
            evidence_id=args.evidence_id,
        )
    except (OSError, json.JSONDecodeError, RetentionError, RetainedEvidenceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

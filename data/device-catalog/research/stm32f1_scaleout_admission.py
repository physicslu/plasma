#!/usr/bin/env python3
"""Build a deterministic read-only STM32F1 scale-out admission plan.

STM32F1 owns evidence/policy adaptation. Generic evidence-to-admission composition is
owned by device_catalog_pipeline_framework, and canonical decision/write mechanics are
owned by device_catalog_admission_framework.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import AdmissionError, file_sha256, read_csv, read_json
from device_catalog_pipeline_framework import (
    AdmissionInputs,
    PipelineError,
    build_pipeline_plan,
    pipeline_plan_is_clean,
)
from evaluate_stm32f1_live_pilot import read_baseline
from stm32f1_admission_policy import build_candidate_inputs, build_canonical_row
from validate_stm32f1_retained_evidence import validate_retained_evidence

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_CANONICAL = HERE / "stm32f1-commercial-icpn.csv"


def expected_candidate_count(baseline: dict[str, Any]) -> int:
    return sum(len(target["exact_icpns"]) for target in baseline["targets"])


def build_scaleout_inputs(
    *,
    evidence_dir: Path,
    baseline_path: Path,
    catalog_path: Path,
) -> tuple[AdmissionInputs, dict[str, Any]]:
    """STM32F1 adapter: validated retained evidence -> normalized admission inputs."""

    retained = validate_retained_evidence(evidence_dir, baseline_path=baseline_path)
    baseline = read_baseline(baseline_path)
    provenance = read_json(evidence_dir / "provenance.json")
    summary = read_json(evidence_dir / "pilot-summary.json")
    _, catalog_rows = read_csv(catalog_path)

    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise AdmissionError("retained provenance requires evidence_id")
    if retained.get("scale_ready") is not True or retained.get("canonical_dataset_admission") is not False:
        raise AdmissionError("retained evidence is not eligible for scale-out admission planning")

    expected = expected_candidate_count(baseline)
    candidate_inputs = build_candidate_inputs(
        summary=summary,
        evidence_id=evidence_id,
        catalog_rows=catalog_rows,
    )
    if len(candidate_inputs) != expected:
        raise AdmissionError(
            f"retained candidate count {len(candidate_inputs)} does not match baseline {expected}"
        )

    return (
        AdmissionInputs(
            evidence_id=evidence_id,
            candidate_inputs=candidate_inputs,
            source_provenance={
                "repository": provenance.get("source_repository"),
                "executed_git_sha": provenance.get("executed_git_sha"),
                "evidence_manifest_sha256": file_sha256(evidence_dir / "manifest.json"),
            },
            input_bindings={
                "retained_evidence_directory": evidence_dir.name,
                "mapping_catalog": catalog_path.name,
                "mapping_catalog_sha256": file_sha256(catalog_path),
                "baseline": baseline_path.name,
                "baseline_sha256": file_sha256(baseline_path),
            },
            expected_candidate_count=expected,
        ),
        baseline,
    )


def build_scaleout_plan(
    *,
    evidence_dir: Path,
    baseline_path: Path,
    canonical_path: Path,
    catalog_path: Path,
) -> dict[str, Any]:
    admission_inputs, baseline = build_scaleout_inputs(
        evidence_dir=evidence_dir,
        baseline_path=baseline_path,
        catalog_path=catalog_path,
    )
    plan = build_pipeline_plan(
        canonical_path=canonical_path,
        row_builder=build_canonical_row,
        admission_inputs=admission_inputs,
    )
    plan["inputs"]["canonical_dataset"] = canonical_path.name
    # Historical Phase 2.9 keys remain as compatibility/audit aliases.
    plan["scaleout_expected_candidate_count"] = admission_inputs.expected_candidate_count
    plan["scaleout_baseline_pilot_id"] = baseline["pilot_id"]
    return plan


def scaleout_plan_is_clean(plan: dict[str, Any]) -> bool:
    expected = plan.get("scaleout_expected_candidate_count")
    return (
        isinstance(expected, int)
        and expected >= 0
        and plan.get("pipeline_expected_candidate_count") == expected
        and plan.get("candidate_count") == expected
        and pipeline_plan_is_clean(plan)
    )


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        plan = build_scaleout_plan(
            evidence_dir=args.evidence_dir,
            baseline_path=args.baseline,
            canonical_path=args.canonical,
            catalog_path=args.catalog,
        )
        if not scaleout_plan_is_clean(plan):
            print(json.dumps(plan, indent=2, sort_keys=True))
            print("ERROR: scale-out admission plan is not clean", file=sys.stderr)
            return 1
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(
            json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        print(json.dumps({
            "candidate_count": plan["candidate_count"],
            "decision_counts": plan["decision_counts"],
            "conflicts": plan["conflicts"],
            "canonical_rows_before": plan["canonical_rows_before"],
            "canonical_dataset_written": False,
        }, indent=2, sort_keys=True))
        return 0
    except (OSError, json.JSONDecodeError, AdmissionError, PipelineError, RuntimeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

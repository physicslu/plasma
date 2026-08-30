#!/usr/bin/env python3
"""Build a deterministic STM32F4 admission plan through the Phase 3.0 generic pipeline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from device_catalog_admission_framework import AdmissionError, file_sha256, read_csv, read_json
from device_catalog_pipeline_framework import (
    AdmissionInputs,
    PipelineError,
    build_pipeline_plan,
    pipeline_plan_is_clean,
)
from evaluate_stm32f4_pilot import read_baseline
from stm32f4_admission_policy import build_candidate_inputs, build_canonical_row
from validate_stm32f4_retained_evidence import validate_retained_evidence

HERE = Path(__file__).resolve().parent
DEFAULT_BASELINE = HERE / "stm32f4-phase3.1-pilot-baseline.json"
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_CANONICAL = HERE / "stm32f4-commercial-icpn.csv"


def build_admission_inputs(
    *,
    evidence_dir: Path,
    baseline_path: Path,
    catalog_path: Path,
    admission_base_devices: set[str] | None = None,
) -> AdmissionInputs:
    retained = validate_retained_evidence(evidence_dir, baseline_path=baseline_path)
    baseline = read_baseline(baseline_path)
    provenance = read_json(evidence_dir / "provenance.json")
    summary = read_json(evidence_dir / "pilot-summary.json")
    _, catalog_rows = read_csv(catalog_path)

    evidence_id = provenance.get("evidence_id")
    if not isinstance(evidence_id, str) or not evidence_id:
        raise AdmissionError("STM32F4 retained evidence requires evidence_id")
    if retained.get("scale_ready") is not True or retained.get("canonical_dataset_admission") is not False:
        raise AdmissionError("STM32F4 retained evidence is not eligible for admission planning")

    baseline_targets = baseline["targets"]
    baseline_bases = {target["base_device"] for target in baseline_targets}
    expected_all = sum(len(target["exact_icpns"]) for target in baseline_targets)
    candidates_all = build_candidate_inputs(
        summary=summary,
        evidence_id=evidence_id,
        catalog_rows=catalog_rows,
    )
    if len(candidates_all) != expected_all:
        raise AdmissionError(
            f"STM32F4 candidate count {len(candidates_all)} does not match baseline {expected_all}"
        )

    input_bindings = {
        "family_adapter": "stm32f4-phase3.1",
        "retained_evidence_directory": evidence_dir.name,
        "mapping_catalog": catalog_path.name,
        "mapping_catalog_sha256": file_sha256(catalog_path),
        "baseline": baseline_path.name,
        "baseline_sha256": file_sha256(baseline_path),
    }
    if admission_base_devices is None:
        candidates = candidates_all
        expected = expected_all
    else:
        if not admission_base_devices:
            raise AdmissionError("STM32F4 admission base-device selection must not be empty")
        unknown = admission_base_devices - baseline_bases
        if unknown:
            raise AdmissionError(
                "STM32F4 admission base-device selection is outside retained baseline: "
                + ", ".join(sorted(unknown))
            )
        candidates = [
            candidate
            for candidate in candidates_all
            if candidate.get("base_device") in admission_base_devices
        ]
        expected = sum(
            len(target["exact_icpns"])
            for target in baseline_targets
            if target["base_device"] in admission_base_devices
        )
        if len(candidates) != expected:
            raise AdmissionError(
                f"STM32F4 selected candidate count {len(candidates)} does not match baseline {expected}"
            )
        input_bindings["admission_base_devices"] = sorted(admission_base_devices)

    return AdmissionInputs(
        evidence_id=evidence_id,
        candidate_inputs=candidates,
        source_provenance={
            "repository": provenance.get("source_repository"),
            "executed_git_sha": provenance.get("executed_git_sha"),
            "evidence_manifest_sha256": file_sha256(evidence_dir / "manifest.json"),
        },
        input_bindings=input_bindings,
        expected_candidate_count=expected,
    )


def build_admission_plan(
    *,
    evidence_dir: Path,
    baseline_path: Path,
    catalog_path: Path,
    canonical_path: Path,
    admission_base_devices: set[str] | None = None,
) -> dict[str, object]:
    inputs = build_admission_inputs(
        evidence_dir=evidence_dir,
        baseline_path=baseline_path,
        catalog_path=catalog_path,
        admission_base_devices=admission_base_devices,
    )
    plan = build_pipeline_plan(
        canonical_path=canonical_path,
        row_builder=build_canonical_row,
        admission_inputs=inputs,
    )
    plan["inputs"]["canonical_dataset"] = canonical_path.name
    plan["family"] = "STM32F4"
    return plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument(
        "--admit-base",
        action="append",
        dest="admit_bases",
        help="Explicit retained base device to include in admission; repeat for scale-out batches",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        plan = build_admission_plan(
            evidence_dir=args.evidence_dir,
            baseline_path=args.baseline,
            catalog_path=args.catalog,
            canonical_path=args.canonical,
            admission_base_devices=set(args.admit_bases) if args.admit_bases else None,
        )
        if not pipeline_plan_is_clean(plan):
            print(json.dumps(plan, indent=2, sort_keys=True))
            print("ERROR: STM32F4 admission plan is not clean", file=sys.stderr)
            return 1
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")
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

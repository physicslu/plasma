#!/usr/bin/env python3
"""Validate a retained STM32F4 browser-evidence package entirely offline."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_evidence_framework import (
    EvidenceFrameworkError,
    read_json,
    require,
    sha256,
    validate_core_provenance,
    validate_manifest,
)
from evaluate_stm32f4_pilot import evaluate_live_pilot, read_baseline
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32f4_admission_policy import MANUFACTURER, TARGET_CONFIG

HERE = Path(__file__).resolve().parent
DEFAULT_BASELINE = HERE / "stm32f4-phase3.1-pilot-baseline.json"
EXPECTED_FILES = {
    "control-summary.json",
    "pilot-summary.json",
    "evaluation.json",
    "provenance.json",
    "README.md",
}
TRANSPORT = "chromium_rendered_dom"
RetainedEvidenceError = EvidenceFrameworkError


def _baseline_shape(baseline: dict[str, Any]) -> tuple[int, int, dict[str, set[str]]]:
    expected = {
        target["base_device"]: set(target["exact_icpns"])
        for target in baseline["targets"]
    }
    return len(expected), sum(len(values) for values in expected.values()), expected


def validate_retained_evidence(
    evidence_dir: Path,
    *,
    baseline_path: Path = DEFAULT_BASELINE,
) -> dict[str, Any]:
    manifest = validate_manifest(evidence_dir, expected_files=EXPECTED_FILES)
    control = read_json(evidence_dir / "control-summary.json")
    pilot = read_json(evidence_dir / "pilot-summary.json")
    evaluation = read_json(evidence_dir / "evaluation.json")
    provenance = read_json(evidence_dir / "provenance.json")
    core = validate_core_provenance(
        provenance,
        evidence_id=manifest["evidence_id"],
        expected_repository="physicslu/plasma",
        expected_manufacturer=MANUFACTURER,
    )
    baseline = read_baseline(baseline_path)
    target_count, candidate_count, expected = _baseline_shape(baseline)

    require(control.get("browser_scope") == "control", "control summary scope must be control")
    require(control.get("attempted") == 1 and control.get("acquisition_success") == 1, "control target must pass 1/1")
    require(control.get("acquisition_failure") == 0, "control target acquisition failed")
    require(pilot.get("browser_scope") == "pilot", "pilot summary scope must be pilot")
    require(pilot.get("attempted") == target_count, "pilot target count mismatch")
    require(pilot.get("acquisition_success") == target_count and pilot.get("acquisition_failure") == 0, "pilot must pass all targets")
    require(pilot.get("exact_icpn_candidates") == candidate_count, "pilot candidate count mismatch")
    require(pilot.get("canonical_mapping") == {"unique": target_count, "ambiguous": 0, "unmapped": 0}, "pilot ordering-pattern mapping is not clean")
    require(pilot.get("openocd_cfg_mapping") == {"mapped": target_count, "total": target_count}, "pilot OpenOCD mapping incomplete")
    require(pilot.get("manual_intervention_required") == 0, "pilot requires manual intervention")
    require(pilot.get("canonical_dataset_admission") is False, "pilot must deny canonical admission")

    results = pilot.get("results")
    require(isinstance(results, list) and len(results) == target_count, "pilot result set mismatch")
    observed: dict[str, set[str]] = {}
    for result in results:
        require(isinstance(result, dict), "pilot result must be an object")
        base = result.get("base_device")
        require(isinstance(base, str) and base in expected, "unexpected STM32F4 base device")
        require(result.get("acquisition_status") == "success", f"{base}: acquisition failed")
        mapping = result.get("canonical_mapping")
        require(
            isinstance(mapping, dict)
            and mapping.get("status") == "unique"
            and mapping.get("target_configs") == [TARGET_CONFIG],
            f"{base}: target mapping not unique",
        )
        candidate_mappings = result.get("candidate_mappings")
        require(isinstance(candidate_mappings, list) and candidate_mappings, f"{base}: candidate mappings missing")
        require(
            all(
                isinstance(item, dict)
                and item.get("status") == "unique"
                and item.get("identifier_kind") == "ordering_pattern"
                and item.get("target_configs") == [TARGET_CONFIG]
                for item in candidate_mappings
            ),
            f"{base}: exact ICPN mapping not uniquely clean",
        )
        evidence = result.get("evidence")
        require(isinstance(evidence, dict), f"{base}: evidence missing")
        require(evidence.get("base_device") == base, f"{base}: evidence identity mismatch")
        require(evidence.get("acquisition_transport") == TRANSPORT, f"{base}: wrong transport")
        require("raw_sha256" not in evidence, f"{base}: browser evidence must not contain raw_sha256")
        for field in ("rendered_dom_sha256", "evidence_section_sha256"):
            value = evidence.get(field)
            require(
                isinstance(value, str)
                and len(value) == 64
                and all(char in "0123456789abcdef" for char in value),
                f"{base}: invalid {field}",
            )
        for field in ("source_url", "final_url"):
            try:
                validate_source_url(evidence.get(field))
            except (AcquisitionError, TypeError) as exc:
                raise RetainedEvidenceError(f"{base}: invalid ST {field}") from exc
        values = evidence.get("exact_icpns")
        require(isinstance(values, list) and len(values) == len(set(values)), f"{base}: invalid exact_icpns")
        require(all(isinstance(value, str) and value.startswith(base) for value in values), f"{base}: ICPN ownership mismatch")
        observed[base] = set(values)
    require(observed == expected, "retained candidate set does not match baseline")

    run_metadata = evaluation.get("run_metadata")
    require(isinstance(run_metadata, dict), "evaluation requires run_metadata")
    require(evaluation == evaluate_live_pilot(summary=pilot, baseline=baseline, run_metadata=run_metadata), "retained evaluation is not deterministic")
    require(evaluation.get("scale_ready") is True and evaluation.get("candidate_drift") == [], "retained evaluation is not scale_ready")

    require(core["acquisition_transport"] == TRANSPORT and core["headed"] is True, "retained provenance must be headed Chromium")
    require(core["target_count"] == target_count and core["acquisition_success"] == target_count, "retained provenance target accounting mismatch")
    require(core["acquisition_failure"] == 0 and core["exact_icpn_candidate_count"] == candidate_count, "retained provenance candidate accounting mismatch")
    require(provenance.get("playwright_version"), "retained provenance requires Playwright version")
    require(provenance.get("chromium_version"), "retained provenance requires Chromium version")
    require(provenance.get("executed_git_sha") == run_metadata.get("git_sha"), "provenance/evaluation Git SHA mismatch")
    require(
        provenance.get("baseline") == {
            "pilot_id": baseline["pilot_id"],
            "schema_version": baseline["schema_version"],
            "sha256": sha256(baseline_path),
        },
        "baseline provenance mismatch",
    )

    return {
        "evidence_id": manifest["evidence_id"],
        "targets": target_count,
        "acquisition_success": target_count,
        "exact_icpn_candidates": candidate_count,
        "candidate_baseline_match": True,
        "candidate_drift": 0,
        "ordering_pattern_target": TARGET_CONFIG,
        "scale_ready": True,
        "canonical_dataset_admission": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = validate_retained_evidence(args.evidence_dir, baseline_path=args.baseline)
    except (OSError, json.JSONDecodeError, RetainedEvidenceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

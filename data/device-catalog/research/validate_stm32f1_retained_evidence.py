#!/usr/bin/env python3
"""Validate a checked-in STM32F1 browser evidence package entirely offline.

Generic package integrity/provenance is owned by device_catalog_evidence_framework.
This module owns only STM32F1/ST evidence semantics and deterministic reevaluation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_evidence_framework import (
    EvidenceFrameworkError,
    read_json as _read_json,
    require as _require,
    sha256 as _sha256,
    validate_core_provenance,
    validate_manifest,
)
from evaluate_stm32f1_live_pilot import evaluate_live_pilot, read_baseline
from st_product_page_acquisition import AcquisitionError, validate_source_url

HERE = Path(__file__).resolve().parent
DEFAULT_EVIDENCE_DIR = HERE / "evidence" / "stm32f1-phase2.6-browser-2026-08-29"
DEFAULT_BASELINE = HERE / "stm32f1-acquisition-pilot-baseline.json"
EXPECTED_FILES = {
    "control-summary.json",
    "pilot-summary.json",
    "evaluation.json",
    "provenance.json",
    "README.md",
}
TRANSPORT = "chromium_rendered_dom"
RetainedEvidenceError = EvidenceFrameworkError


def _baseline_shape(baseline: dict[str, Any]) -> tuple[int, int, set[str]]:
    targets = baseline.get("targets")
    _require(isinstance(targets, list) and targets, "baseline targets must be a non-empty list")
    bases: set[str] = set()
    candidate_count = 0
    for target in targets:
        _require(isinstance(target, dict), "baseline target must be an object")
        base_device = target.get("base_device")
        exact_icpns = target.get("exact_icpns")
        _require(isinstance(base_device, str) and base_device, "baseline target requires base_device")
        _require(isinstance(exact_icpns, list) and exact_icpns, f"{base_device}: baseline requires exact_icpns")
        bases.add(base_device)
        candidate_count += len(exact_icpns)
    return len(targets), candidate_count, bases


def validate_retained_evidence(
    evidence_dir: Path,
    *,
    baseline_path: Path = DEFAULT_BASELINE,
) -> dict[str, Any]:
    manifest = validate_manifest(evidence_dir, expected_files=EXPECTED_FILES)
    control = _read_json(evidence_dir / "control-summary.json")
    summary = _read_json(evidence_dir / "pilot-summary.json")
    evaluation = _read_json(evidence_dir / "evaluation.json")
    provenance = _read_json(evidence_dir / "provenance.json")
    validate_core_provenance(
        provenance,
        evidence_id=manifest["evidence_id"],
        expected_repository="physicslu/plasma",
        expected_manufacturer="STMicroelectronics",
    )

    baseline = read_baseline(baseline_path)
    expected_targets, expected_candidates, expected_bases = _baseline_shape(baseline)

    _require(control.get("browser_scope") == "control", "control summary scope must be control")
    _require(control.get("attempted") == 1 and control.get("acquisition_success") == 1, "control target must pass 1/1")
    _require(control.get("acquisition_failure") == 0, "control target contains an acquisition failure")
    _require(summary.get("browser_scope") == "pilot", "pilot summary scope must be pilot")
    _require(summary.get("attempted") == expected_targets, f"pilot must attempt exactly {expected_targets} targets")
    _require(summary.get("acquisition_success") == expected_targets and summary.get("acquisition_failure") == 0, f"pilot must pass {expected_targets}/{expected_targets}")
    _require(summary.get("exact_icpn_candidates") == expected_candidates, f"pilot must contain exactly {expected_candidates} candidates")
    _require(summary.get("canonical_mapping") == {"unique": expected_targets, "ambiguous": 0, "unmapped": 0}, "canonical mapping must be uniquely clean for every target")
    _require(summary.get("openocd_cfg_mapping") == {"mapped": expected_targets, "total": expected_targets}, "OpenOCD mapping must be complete for every target")
    _require(summary.get("manual_intervention_required") == 0, "pilot requires manual intervention")

    results = summary.get("results")
    _require(isinstance(results, list) and len(results) == expected_targets, f"pilot results must contain {expected_targets} targets")
    candidate_owner: dict[str, str] = {}
    observed_bases: set[str] = set()
    for result in results:
        _require(isinstance(result, dict), "pilot result must be an object")
        base_device = result.get("base_device")
        _require(isinstance(base_device, str) and base_device, "result requires base_device")
        observed_bases.add(base_device)
        _require(result.get("acquisition_status") == "success", f"{base_device}: acquisition failed")
        mapping = result.get("canonical_mapping")
        _require(isinstance(mapping, dict) and mapping.get("status") == "unique", f"{base_device}: canonical mapping is not unique")
        configs = mapping.get("target_configs")
        _require(isinstance(configs, list) and len(configs) == 1, f"{base_device}: OpenOCD mapping is not exactly one CFG")
        evidence = result.get("evidence")
        _require(isinstance(evidence, dict), f"{base_device}: missing evidence")
        _require(evidence.get("base_device") == base_device, f"{base_device}: evidence identity mismatch")
        _require(evidence.get("acquisition_transport") == TRANSPORT, f"{base_device}: wrong transport")
        _require("raw_sha256" not in evidence, f"{base_device}: browser evidence must not contain raw_sha256")
        for field in ("rendered_dom_sha256", "evidence_section_sha256"):
            value = evidence.get(field)
            _require(isinstance(value, str) and len(value) == 64 and all(ch in "0123456789abcdef" for ch in value), f"{base_device}: invalid {field}")
        for field in ("source_url", "final_url"):
            try:
                validate_source_url(evidence.get(field))
            except (AcquisitionError, TypeError) as exc:
                raise RetainedEvidenceError(f"{base_device}: invalid official ST {field}") from exc
        candidates = evidence.get("exact_icpns")
        _require(isinstance(candidates, list) and candidates, f"{base_device}: missing exact_icpns")
        _require(len(candidates) == len(set(candidates)), f"{base_device}: duplicate exact ICPN")
        for candidate in candidates:
            _require(isinstance(candidate, str) and candidate.startswith(base_device), f"{base_device}: candidate maps to wrong base")
            _require(candidate not in candidate_owner, f"duplicate exact ICPN across targets: {candidate}")
            candidate_owner[candidate] = base_device
    _require(observed_bases == expected_bases, "retained evidence target set does not match baseline")
    _require(len(candidate_owner) == expected_candidates, f"retained evidence must contain {expected_candidates} unique exact ICPNs")

    run_metadata = evaluation.get("run_metadata")
    _require(isinstance(run_metadata, dict), "evaluation requires run_metadata")
    reevaluated = evaluate_live_pilot(summary=summary, baseline=baseline, run_metadata=run_metadata)
    _require(evaluation == reevaluated, "retained evaluation does not match deterministic reevaluation")
    _require(evaluation.get("candidate_baseline_match") is True, "candidate baseline does not match")
    _require(evaluation.get("candidate_drift") == [], "candidate drift must be empty")
    _require(evaluation.get("decision") == "scale_ready" and evaluation.get("scale_ready") is True, "evaluator is not scale_ready")
    _require(evaluation.get("canonical_dataset_admission") is False, "evaluation must deny canonical admission")

    _require(provenance.get("acquisition_transport") == TRANSPORT, "provenance acquisition_transport mismatch")
    _require(provenance.get("headed") is True, "provenance headed mismatch")
    _require(provenance.get("target_count") == expected_targets, "provenance target_count mismatch")
    _require(provenance.get("acquisition_success") == expected_targets, "provenance acquisition_success mismatch")
    _require(provenance.get("acquisition_failure") == 0, "provenance acquisition_failure mismatch")
    _require(provenance.get("exact_icpn_candidate_count") == expected_candidates, "provenance exact_icpn_candidate_count mismatch")
    _require(provenance.get("evaluator_result") == "scale_ready", "provenance evaluator_result mismatch")
    _require(isinstance(provenance.get("acquisition_time_utc"), dict), "provenance requires acquisition_time_utc")
    _require(isinstance(provenance.get("playwright_version"), str), "provenance requires Playwright version")
    _require(isinstance(provenance.get("chromium_version"), str), "provenance requires Chromium version")
    _require(provenance.get("executed_git_sha") == run_metadata.get("git_sha"), "provenance/evaluation Git SHA mismatch")

    baseline_provenance = provenance.get("baseline")
    if baseline_provenance is None:
        baseline_provenance = provenance.get("phase2_5_baseline")
    _require(
        baseline_provenance == {
            "pilot_id": baseline["pilot_id"],
            "schema_version": baseline["schema_version"],
            "sha256": _sha256(baseline_path),
        },
        "baseline provenance mismatch",
    )

    return {
        "evidence_id": provenance["evidence_id"],
        "targets": expected_targets,
        "acquisition_success": expected_targets,
        "exact_icpn_candidates": expected_candidates,
        "candidate_baseline_match": True,
        "candidate_drift": 0,
        "scale_ready": True,
        "canonical_dataset_admission": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = validate_retained_evidence(args.evidence_dir, baseline_path=args.baseline)
    except (OSError, RetainedEvidenceError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    print("STM32F1 retained browser evidence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

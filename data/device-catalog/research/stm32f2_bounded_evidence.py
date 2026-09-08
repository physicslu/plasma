#!/usr/bin/env python3
"""Generic retained-evidence replay for registered bounded STM32F2 discovery batches."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_bounded_evidence import (
    BoundedEvidenceError,
    SHA256_RE,
    require,
    validate_baseline_result,
    validate_execution_binding,
    validate_fail_closed_claims,
)
from device_catalog_evidence_framework import (
    EvidenceFrameworkError,
    read_json,
    sha256,
    validate_core_provenance,
    validate_manifest,
)
from st_product_page_acquisition import validate_source_url
from stm32f2_bounded_discovery import (
    DEFAULT_CANONICAL,
    DEFAULT_CATALOG,
    EXPECTED_SUBFAMILIES,
    load_spec,
    read_catalog,
    read_manifest,
    read_production_bases,
)
from stm32f2_phase4_3b_discovery import TARGET_CONFIG, resolve_mapping

EXPECTED_FILES = {"README.md", "pilot-summary.json", "provenance.json"}
STM32F2EvidenceError = BoundedEvidenceError


def validate(
    *,
    phase: str,
    evidence_dir: Path | None = None,
    baseline_path: Path | None = None,
) -> dict[str, Any]:
    spec = load_spec(phase)
    evidence_dir = spec.evidence_dir if evidence_dir is None else evidence_dir
    baseline_path = spec.baseline_path if baseline_path is None else baseline_path

    baseline = read_json(baseline_path)
    require(baseline.get("schema_version") == 1, "baseline schema_version mismatch")
    require(baseline.get("phase") == phase, "baseline phase mismatch")

    inputs = baseline.get("inputs")
    require(isinstance(inputs, dict), "baseline inputs are missing")
    require(
        inputs.get("openocd_catalog_sha256") == sha256(DEFAULT_CATALOG),
        "OpenOCD catalog drifted",
    )
    require(
        inputs.get("discovery_manifest_sha256") == sha256(spec.manifest_path),
        "discovery manifest drifted",
    )
    production_manifest_digest = inputs.get("production_manifest_sha256_at_discovery")
    require(
        isinstance(production_manifest_digest, str)
        and SHA256_RE.fullmatch(production_manifest_digest) is not None,
        "historical Production manifest digest is invalid",
    )

    catalog = read_catalog(DEFAULT_CATALOG)
    production_bases = read_production_bases(DEFAULT_CANONICAL, spec=spec)
    pilot_id, manifest_targets = read_manifest(
        spec.manifest_path,
        catalog,
        production_bases,
        spec=spec,
    )
    require(pilot_id == baseline.get("pilot_id"), "manifest/baseline pilot_id mismatch")

    manifest = validate_manifest(evidence_dir, expected_files=EXPECTED_FILES)
    summary = read_json(evidence_dir / "pilot-summary.json")
    provenance = read_json(evidence_dir / "provenance.json")
    require(summary.get("phase") == phase, "retained summary phase mismatch")
    require(summary.get("pilot_id") == pilot_id, "retained summary pilot_id mismatch")
    require(
        summary.get("acquisition_transport") == "chromium_rendered_dom",
        "unexpected acquisition transport",
    )
    runtime = summary.get("browser_runtime")
    require(isinstance(runtime, dict), "retained browser runtime is missing")
    require(runtime.get("engine") == "chromium", "retained browser engine mismatch")
    require(runtime.get("playwright_requirement") == "1.62.0", "Playwright version mismatch")
    require(runtime.get("headless") is False, "retained evidence requires headed Chromium")

    from stm32f2_bounded_discovery import discovery_is_clean

    require(
        discovery_is_clean(summary, spec=spec),
        f"retained {phase} discovery is not clean",
    )
    validate_fail_closed_claims(baseline=baseline, summary=summary)

    target_keys = [
        (target.subfamily, target.base_device)
        for target in manifest_targets
    ]
    results, candidate_count, excluded_count = validate_baseline_result(
        baseline=baseline,
        summary=summary,
        target_keys=target_keys,
        validate_source_url=validate_source_url,
    )
    require(
        [result.get("subfamily") for result in results] == list(EXPECTED_SUBFAMILIES),
        "subfamily coverage drifted",
    )

    mapping_count = 0
    for result in results:
        mappings = result.get("candidate_mappings")
        require(isinstance(mappings, list), "retained candidate mappings are missing")
        evidence = result.get("evidence")
        require(isinstance(evidence, dict), "retained result lacks evidence")
        active = evidence.get("exact_icpns")
        require(isinstance(active, list), "retained exact ICPNs are missing")
        expected_mappings = [
            {"icpn": icpn, **resolve_mapping(icpn, catalog)}
            for icpn in active
        ]
        require(
            mappings == expected_mappings,
            "retained OpenOCD mapping is not reproducible",
        )
        require(
            result.get("canonical_mapping")
            == {
                "status": "unique",
                "candidate_count": len(active),
                "target_configs": [TARGET_CONFIG],
            },
            "retained target mapping is not uniquely bounded",
        )
        mapping_count += len(mappings)

    core = validate_core_provenance(
        provenance,
        evidence_id=manifest["evidence_id"],
        expected_repository="physicslu/plasma",
        expected_manufacturer="STMicroelectronics",
    )
    require(
        core["executed_git_sha"] == baseline.get("executed_git_sha"),
        "executed Git SHA drifted",
    )
    require(core["target_count"] == len(target_keys), "provenance target count mismatch")
    require(
        core["exact_icpn_candidate_count"] == candidate_count,
        "provenance candidate count mismatch",
    )
    require(
        provenance.get("excluded_non_active_part_number_count") == excluded_count,
        "lifecycle exclusion count mismatch",
    )
    require(
        provenance.get("production_admission_ready") is False,
        "retained evidence cannot authorize admission",
    )
    require(
        provenance.get("playwright_version") == runtime.get("playwright_requirement"),
        "Playwright provenance mismatch",
    )
    require(
        provenance.get("chromium_version") == runtime.get("browser_version"),
        "Chromium provenance mismatch",
    )
    require(
        provenance.get("baseline_sha256") == sha256(baseline_path),
        "provenance baseline digest mismatch",
    )
    require(
        provenance.get("pilot_summary_sha256") == sha256(evidence_dir / "pilot-summary.json"),
        "provenance pilot digest mismatch",
    )
    validate_execution_binding(baseline=baseline, provenance=provenance)
    require(mapping_count == candidate_count, "retained exact ICPN mapping count mismatch")

    return {
        "status": "valid",
        "phase": phase,
        "evidence_id": manifest["evidence_id"],
        "targets": len(target_keys),
        "subfamilies": list(EXPECTED_SUBFAMILIES),
        "active_exact_icpn_candidates": candidate_count,
        "excluded_non_active_part_numbers": excluded_count,
        "unique_openocd_mappings": mapping_count,
        "production_admission_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Validate one registered bounded STM32F2 retained-evidence batch."
    )
    parser.add_argument("--phase", required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--baseline", type=Path)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = validate(
            phase=args.phase,
            evidence_dir=args.evidence_dir,
            baseline_path=args.baseline,
        )
    except (EvidenceFrameworkError, BoundedEvidenceError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Validate immutable Phase 4.3B STM32F2 official-ST discovery evidence."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

from device_catalog_evidence_framework import (
    EvidenceFrameworkError,
    read_json,
    validate_core_provenance,
    validate_manifest,
)
from st_product_page_acquisition import validate_source_url
from stm32f2_phase4_3b_discovery import (
    DEFAULT_CATALOG,
    DEFAULT_MANIFEST,
    EXPECTED_SUBFAMILIES,
    TARGET_CONFIG,
    discovery_is_clean,
    read_catalog,
    read_manifest,
    resolve_mapping,
)

HERE = Path(__file__).resolve().parent
DEFAULT_BASELINE = HERE / "stm32f2-phase4.3b-discovery-baseline.json"
DEFAULT_EVIDENCE_DIR = (
    HERE / "evidence" / "stm32f2-phase4.3b-official-st-discovery-live-2026-09-06"
)
EXPECTED_FILES = {"README.md", "pilot-summary.json", "provenance.json"}
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


class STM32F2EvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise STM32F2EvidenceError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _target_snapshot(result: dict[str, Any]) -> dict[str, Any]:
    evidence = result.get("evidence")
    require(isinstance(evidence, dict), "retained result lacks evidence")
    source_url = evidence.get("source_url")
    final_url = evidence.get("final_url")
    require(isinstance(source_url, str), "retained evidence lacks source_url")
    validate_source_url(source_url)
    require(final_url == source_url, "official ST final URL drifted")
    active = evidence.get("exact_icpns")
    excluded = evidence.get("excluded_non_active_part_numbers")
    require(isinstance(active, list) and all(isinstance(value, str) for value in active), "invalid exact ICPN list")
    require(isinstance(excluded, list), "invalid excluded lifecycle list")
    records = evidence.get("part_number_records")
    require(isinstance(records, list), "retained evidence lacks lifecycle records")
    require(
        [record.get("icpn") for record in records if record.get("active") is True] == active,
        "Active lifecycle records do not match exact ICPNs",
    )
    require(
        [
            {"icpn": record.get("icpn"), "marketing_status": record.get("marketing_status")}
            for record in records
            if record.get("active") is not True
        ] == excluded,
        "excluded lifecycle records do not match retained evidence",
    )
    for field in ("rendered_dom_sha256", "evidence_section_sha256"):
        require(
            isinstance(evidence.get(field), str) and SHA256_RE.fullmatch(evidence[field]) is not None,
            f"invalid retained {field}",
        )
    return {
        "subfamily": result.get("subfamily"),
        "base_device": result.get("base_device"),
        "source_url": source_url,
        "retrieved_at_utc": evidence.get("retrieved_at_utc"),
        "rendered_dom_sha256": evidence.get("rendered_dom_sha256"),
        "evidence_section_sha256": evidence.get("evidence_section_sha256"),
        "active_exact_icpns": active,
        "excluded_non_active_part_numbers": excluded,
    }


def validate(*, evidence_dir: Path, baseline_path: Path) -> dict[str, Any]:
    baseline = read_json(baseline_path)
    require(baseline.get("schema_version") == 1, "baseline schema_version mismatch")
    require(baseline.get("phase") == "4.3B", "baseline phase mismatch")
    inputs = baseline.get("inputs")
    require(isinstance(inputs, dict), "baseline inputs are missing")
    require(inputs.get("openocd_catalog_sha256") == sha256(DEFAULT_CATALOG), "OpenOCD catalog drifted")
    require(inputs.get("discovery_manifest_sha256") == sha256(DEFAULT_MANIFEST), "discovery manifest drifted")
    require(
        isinstance(inputs.get("production_manifest_sha256_at_discovery"), str)
        and SHA256_RE.fullmatch(inputs["production_manifest_sha256_at_discovery"]) is not None,
        "historical Production manifest digest is invalid",
    )
    catalog = read_catalog(DEFAULT_CATALOG)
    pilot_id, manifest_targets = read_manifest(DEFAULT_MANIFEST, catalog)
    require(pilot_id == baseline.get("pilot_id"), "manifest/baseline pilot_id mismatch")

    manifest = validate_manifest(evidence_dir, expected_files=EXPECTED_FILES)
    summary = read_json(evidence_dir / "pilot-summary.json")
    provenance = read_json(evidence_dir / "provenance.json")
    require(summary.get("phase") == "4.3B", "retained summary phase mismatch")
    require(summary.get("pilot_id") == pilot_id, "retained summary pilot_id mismatch")
    require(summary.get("acquisition_transport") == "chromium_rendered_dom", "unexpected acquisition transport")
    runtime = summary.get("browser_runtime")
    require(isinstance(runtime, dict), "retained browser runtime is missing")
    require(runtime.get("engine") == "chromium", "retained browser engine mismatch")
    require(runtime.get("playwright_requirement") == "1.62.0", "Playwright version mismatch")
    require(runtime.get("headless") is False, "retained evidence requires headed Chromium")
    require(discovery_is_clean(summary), "retained Phase 4.3B discovery is not clean")
    require(summary.get("claims") == {key: False for key in summary.get("claims", {})}, "retained discovery overclaims authority")

    result_fields = (
        "attempted",
        "acquisition_success",
        "acquisition_failure",
        "active_exact_icpn_candidates",
        "excluded_non_active_part_numbers",
        "canonical_mapping",
        "manual_intervention_required",
    )
    observed_result = {field: summary.get(field) for field in result_fields}
    require(observed_result == baseline.get("result"), "retained aggregate result drifted")
    results = summary.get("results")
    require(isinstance(results, list) and len(results) == 4, "retained target result count mismatch")
    require([_target_snapshot(result) for result in results] == baseline.get("targets"), "retained target evidence drifted")
    require(
        [(result.get("subfamily"), result.get("base_device")) for result in results]
        == [(target.subfamily, target.base_device) for target in manifest_targets],
        "retained result target order drifted",
    )
    require([result.get("subfamily") for result in results] == list(EXPECTED_SUBFAMILIES), "subfamily coverage drifted")

    mapping_count = 0
    for result in results:
        mappings = result.get("candidate_mappings")
        require(isinstance(mappings, list), "retained candidate mappings are missing")
        active = result["evidence"]["exact_icpns"]
        expected_mappings = [{"icpn": icpn, **resolve_mapping(icpn, catalog)} for icpn in active]
        require(mappings == expected_mappings, "retained OpenOCD mapping is not reproducible")
        require(
            result.get("canonical_mapping")
            == {"status": "unique", "candidate_count": len(active), "target_configs": [TARGET_CONFIG]},
            "retained target mapping is not uniquely bounded",
        )
        mapping_count += len(mappings)

    core = validate_core_provenance(
        provenance,
        evidence_id=manifest["evidence_id"],
        expected_repository="physicslu/plasma",
        expected_manufacturer="STMicroelectronics",
    )
    require(core["executed_git_sha"] == baseline.get("executed_git_sha"), "executed Git SHA drifted")
    require(core["target_count"] == 4, "provenance target count mismatch")
    require(core["exact_icpn_candidate_count"] == 9, "provenance candidate count mismatch")
    require(provenance.get("workflow_run_id") == baseline.get("workflow_run_id"), "workflow run ID mismatch")
    require(provenance.get("baseline_sha256") == sha256(baseline_path), "provenance baseline digest mismatch")
    require(provenance.get("pilot_summary_sha256") == sha256(evidence_dir / "pilot-summary.json"), "provenance pilot digest mismatch")
    require(mapping_count == 9, "retained exact ICPN mapping count mismatch")

    claims = baseline.get("claims")
    require(isinstance(claims, dict) and claims and set(claims.values()) == {False}, "baseline claims must all fail closed")
    return {
        "status": "valid",
        "evidence_id": manifest["evidence_id"],
        "targets": 4,
        "subfamilies": list(EXPECTED_SUBFAMILIES),
        "active_exact_icpn_candidates": 9,
        "excluded_non_active_part_numbers": 0,
        "unique_openocd_mappings": 9,
        "production_admission_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = validate(evidence_dir=args.evidence_dir, baseline_path=args.baseline)
    except (EvidenceFrameworkError, STM32F2EvidenceError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

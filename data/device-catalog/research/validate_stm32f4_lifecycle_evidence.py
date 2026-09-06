#!/usr/bin/env python3
"""Validate a retained lifecycle-only STM32F4 evidence package offline."""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_evidence_framework import (
    EvidenceFrameworkError,
    read_json,
    require,
    sha256,
    validate_manifest,
)
from st_product_page_acquisition import AcquisitionError, validate_source_url

EXPECTED_FILES = {
    "README.md",
    "lifecycle-baseline.json",
    "pilot-summary.json",
    "provenance.json",
}
TRANSPORT = "chromium_rendered_dom"
MANUFACTURER = "STMicroelectronics"
REPOSITORY = "physicslu/plasma"
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def _status_class(marketing_status: str) -> str:
    if marketing_status.startswith("NRND"):
        return "NRND"
    if marketing_status.startswith("Proposal"):
        return "Proposal"
    raise EvidenceFrameworkError(f"unsupported lifecycle status: {marketing_status!r}")


def validate_lifecycle_evidence(evidence_dir: Path) -> dict[str, Any]:
    manifest = validate_manifest(evidence_dir, expected_files=EXPECTED_FILES)
    baseline = read_json(evidence_dir / "lifecycle-baseline.json")
    pilot = read_json(evidence_dir / "pilot-summary.json")
    provenance = read_json(evidence_dir / "provenance.json")

    require(provenance.get("schema_version") == 1, "provenance schema mismatch")
    require(provenance.get("evidence_id") == manifest["evidence_id"], "evidence ID mismatch")
    require(provenance.get("manufacturer") == MANUFACTURER, "manufacturer mismatch")
    require(provenance.get("source_repository") == REPOSITORY, "repository mismatch")
    executed_sha = provenance.get("executed_git_sha")
    require(isinstance(executed_sha, str) and GIT_SHA_RE.fullmatch(executed_sha), "invalid Git SHA")
    require(provenance.get("acquisition_transport") == TRANSPORT, "transport mismatch")
    require(provenance.get("headed") is True, "lifecycle evidence must use headed Chromium")
    require(provenance.get("target_count") == 5, "provenance target count mismatch")
    require(provenance.get("acquisition_success") == 5, "provenance success count mismatch")
    require(provenance.get("acquisition_failure") == 0, "provenance failure count mismatch")
    require(provenance.get("exact_icpn_candidate_count") == 0, "Active candidate count must be zero")
    require(provenance.get("lifecycle_exclusion_count") == 7, "exclusion count mismatch")
    require(provenance.get("lifecycle_status_counts") == {"NRND": 6, "Proposal": 1}, "status counts mismatch")
    require(provenance.get("canonical_dataset_admission") is False, "canonical admission must be denied")
    require(provenance.get("policy_change_authorized") is False, "policy change must be denied")
    require(provenance.get("production_write_authorized") is False, "Production write must be denied")
    require(provenance.get("evaluator_result") == "lifecycle_closed", "closure result mismatch")

    source = baseline.get("source_discovery")
    require(isinstance(source, dict), "baseline source discovery is missing")
    for field in ("artifact_zip_sha256", "pilot_summary_sha256"):
        digest = source.get(field)
        require(isinstance(digest, str) and SHA256_RE.fullmatch(digest), f"invalid {field}")
        require(provenance.get(field) == digest, f"provenance {field} mismatch")
    require(source.get("source_commit") == executed_sha, "source commit mismatch")
    require(source.get("workflow_run_id") == provenance.get("workflow_run_id"), "workflow run mismatch")
    require(source.get("artifact_id") == provenance.get("artifact_id"), "artifact ID mismatch")
    require(sha256(evidence_dir / "pilot-summary.json") == source["pilot_summary_sha256"], "pilot summary digest mismatch")
    require(baseline.get("canonical_dataset_admission") is False, "baseline canonical admission must be denied")
    require(baseline.get("policy_change_authorized") is False, "baseline policy change must be denied")
    require(baseline.get("production_write_authorized") is False, "baseline Production write must be denied")

    require(pilot.get("pilot_id") == baseline.get("pilot_id"), "pilot identity mismatch")
    require(pilot.get("browser_scope") == "pilot", "browser scope mismatch")
    require(pilot.get("acquisition_transport") == TRANSPORT, "pilot transport mismatch")
    require(pilot.get("canonical_dataset_admission") is False, "pilot canonical admission must be denied")
    require(pilot.get("attempted") == 5, "pilot target count mismatch")
    require(pilot.get("acquisition_success") == 5 and pilot.get("acquisition_failure") == 0, "pilot acquisition incomplete")
    require(pilot.get("exact_icpn_candidates") == 0, "pilot exposed an Active candidate")
    require(pilot.get("canonical_mapping") == {"unique": 0, "ambiguous": 0, "unmapped": 5}, "pilot mapping mismatch")
    require(pilot.get("openocd_cfg_mapping") == {"mapped": 0, "total": 5}, "pilot OpenOCD mapping mismatch")
    require(pilot.get("manual_intervention_required") == 5, "pilot manual-intervention accounting mismatch")

    expected_targets = baseline.get("targets")
    require(isinstance(expected_targets, list) and len(expected_targets) == 5, "baseline targets mismatch")
    expected = {
        item["base_device"]: item["excluded_non_active_part_numbers"]
        for item in expected_targets
    }
    results = pilot.get("results")
    require(isinstance(results, list) and len(results) == 5, "pilot result set mismatch")
    observed: dict[str, list[dict[str, str]]] = {}
    statuses: Counter[str] = Counter()
    for result in results:
        require(isinstance(result, dict), "pilot result must be an object")
        base = result.get("base_device")
        require(isinstance(base, str) and base in expected, "unexpected lifecycle base device")
        require(result.get("acquisition_status") == "success", f"{base}: acquisition failed")
        require(result.get("candidate_mappings") == [], f"{base}: candidate mapping must be empty")
        mapping = result.get("canonical_mapping")
        require(
            mapping == {"candidate_count": 0, "status": "unmapped", "target_configs": []},
            f"{base}: lifecycle-only mapping must remain unmapped",
        )
        evidence = result.get("evidence")
        require(isinstance(evidence, dict), f"{base}: evidence missing")
        require(evidence.get("base_device") == base, f"{base}: evidence identity mismatch")
        require(evidence.get("acquisition_transport") == TRANSPORT, f"{base}: evidence transport mismatch")
        require(evidence.get("exact_icpns") == [], f"{base}: Active candidate observed")
        require("raw_sha256" not in evidence, f"{base}: browser evidence claims raw HTTP")
        for field in ("rendered_dom_sha256", "evidence_section_sha256"):
            digest = evidence.get(field)
            require(isinstance(digest, str) and SHA256_RE.fullmatch(digest), f"{base}: invalid {field}")
        for field in ("source_url", "final_url"):
            try:
                validate_source_url(evidence.get(field))
            except (AcquisitionError, TypeError) as exc:
                raise EvidenceFrameworkError(f"{base}: invalid official ST URL") from exc
        records = evidence.get("part_number_records")
        excluded = evidence.get("excluded_non_active_part_numbers")
        require(isinstance(records, list) and records, f"{base}: lifecycle rows missing")
        require(isinstance(excluded, list) and excluded, f"{base}: exclusions missing")
        require(all(record.get("active") is False for record in records), f"{base}: record is not explicitly non-Active")
        normalized = [
            {"icpn": str(record.get("icpn")), "marketing_status": str(record.get("marketing_status"))}
            for record in records
        ]
        require(normalized == excluded, f"{base}: record/exclusion mismatch")
        for record in normalized:
            require(record["icpn"].startswith(base), f"{base}: ICPN ownership mismatch")
            statuses[_status_class(record["marketing_status"])] += 1
        observed[base] = normalized

    require(observed == expected, "retained lifecycle evidence differs from frozen baseline")
    require(dict(statuses) == {"NRND": 6, "Proposal": 1}, "observed lifecycle status counts mismatch")
    require(baseline.get("lifecycle_status_counts") == {"NRND": 6, "Proposal": 1, "total": 7}, "baseline lifecycle counts mismatch")
    return {
        "evidence_id": manifest["evidence_id"],
        "targets": 5,
        "acquisition_success": 5,
        "exact_icpn_candidates": 0,
        "lifecycle_exclusions": 7,
        "lifecycle_status_counts": dict(statuses),
        "canonical_dataset_admission": False,
        "policy_change_authorized": False,
        "production_write_authorized": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = validate_lifecycle_evidence(args.evidence_dir)
    except (EvidenceFrameworkError, OSError, json.JSONDecodeError) as exc:
        print(f"STM32F4 lifecycle evidence: FAIL: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    print("STM32F4 lifecycle evidence: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

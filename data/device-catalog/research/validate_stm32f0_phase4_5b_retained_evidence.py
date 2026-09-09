#!/usr/bin/env python3
"""Validate retained STM32F0 Phase 4.5B commercial-identity evidence offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_evidence_framework import (
    EvidenceFrameworkError,
    read_json,
    sha256,
    validate_core_provenance,
    validate_manifest,
)

HERE = Path(__file__).resolve().parent
DEFAULT_BASELINE = HERE / "stm32f0-phase4.5b-discovery-baseline.json"
DEFAULT_DISCOVERY_MANIFEST = HERE / "stm32f0-phase4.5b-discovery-manifest.json"
DEFAULT_EVIDENCE_DIR = HERE / "evidence/stm32f0-phase4.5b-official-st-discovery-live-2026-09-09"

EXPECTED_EVIDENCE_ID = (
    "stm32f0-phase4.5b-official-st-discovery-2026-09-09-"
    "retained-20260909T055900Z-1fcdf869"
)
EXPECTED_BASELINE_SHA256 = "2052ed71d159bd345fa9a718422558843ce0513c3e0f3ccfe6765f1edc79eadf"
EXPECTED_SUMMARY_SHA256 = "3077cc04ecba5dc19f0d74bf570b659fc7ba803d7356cc194cf0604e96dc6687"
EXPECTED_EXECUTED_GIT_SHA = "1fcdf8696bc4d334f6e5f092efc8200b65fc443e"
EXPECTED_CHECKOUT_SHA = "95276ea5af83819351c7f9f4a2f32db0638842b9"
EXPECTED_RUN_ID = 34315839031
EXPECTED_ARTIFACT_ID = 10090443968
EXPECTED_ARTIFACT_ZIP_SHA256 = "a3c02afd6a1295a612d25e35031d8623da86c0ea76777acaab4caaaab51cb1aa"
EXPECTED_LIVE_SUMMARY_SHA256 = "e96c9f09f4f57d2797cd9e3928664dcd67c72f3887eae3795df66aa1e75cbb76"
EXPECTED_PROFILE = "stm32f0_dual_surface_v1"
EXPECTED_DISCOVERY_MANIFEST_GIT_BLOB_SHA = "446969fb89f4bd6b8bd421eb0e4b2506d14c8a36"
EXPECTED_OPENOCD_GIT_BLOB_SHA = "0ef056e3363e20bb527590c4a4cc1cc0d7afb810"
EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB_SHA = "6fb6d103027fc3c7a949f0d4aa2d9c10828cc103"
EXPECTED_EXACT_COUNT = 42
ACTIVE_STATUS = "Active Product is in volume production."


class STM32F0RetainedEvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise STM32F0RetainedEvidenceError(message)


def git_blob_sha(path: Path) -> str:
    body = path.read_bytes()
    return hashlib.sha1(f"blob {len(body)}\0".encode("ascii") + body).hexdigest()


def all_false_claims(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}


def validate(
    *,
    evidence_dir: Path = DEFAULT_EVIDENCE_DIR,
    baseline_path: Path = DEFAULT_BASELINE,
    discovery_manifest_path: Path = DEFAULT_DISCOVERY_MANIFEST,
) -> dict[str, Any]:
    retained_manifest = validate_manifest(
        evidence_dir,
        expected_files=("README.md", "pilot-summary.json", "provenance.json"),
    )
    require(retained_manifest.get("evidence_id") == EXPECTED_EVIDENCE_ID, "evidence ID mismatch")

    baseline = read_json(baseline_path)
    summary = read_json(evidence_dir / "pilot-summary.json")
    provenance = read_json(evidence_dir / "provenance.json")
    discovery_manifest = read_json(discovery_manifest_path)
    core = validate_core_provenance(
        provenance,
        evidence_id=EXPECTED_EVIDENCE_ID,
        expected_repository="physicslu/plasma",
        expected_manufacturer="STMicroelectronics",
    )

    require(sha256(baseline_path) == EXPECTED_BASELINE_SHA256, "baseline byte digest mismatch")
    require(sha256(evidence_dir / "pilot-summary.json") == EXPECTED_SUMMARY_SHA256, "summary byte digest mismatch")
    require(provenance.get("baseline_sha256") == EXPECTED_BASELINE_SHA256, "provenance baseline digest mismatch")
    require(provenance.get("pilot_summary_sha256") == EXPECTED_SUMMARY_SHA256, "provenance summary digest mismatch")

    require(baseline.get("schema_version") == 1 and baseline.get("phase") == "4.5B", "baseline phase/schema mismatch")
    require(baseline.get("family") == "STM32F0", "baseline family mismatch")
    require(summary.get("schema_version") == 1 and summary.get("phase") == "4.5B", "summary phase/schema mismatch")
    require(summary.get("family") == "STM32F0", "summary family mismatch")
    require(summary.get("pilot_id") == baseline.get("pilot_id") == discovery_manifest.get("pilot_id"), "pilot identity mismatch")
    require(all_false_claims(baseline.get("claims")), "baseline claims must remain false")
    require(all_false_claims(summary.get("claims")), "summary claims must remain false")

    execution = baseline.get("discovery_execution")
    browser = baseline.get("browser")
    require(isinstance(execution, dict) and isinstance(browser, dict), "baseline execution/browser binding missing")
    require(execution == {
        "artifact_id": EXPECTED_ARTIFACT_ID,
        "artifact_zip_sha256": EXPECTED_ARTIFACT_ZIP_SHA256,
        "github_checkout_sha": EXPECTED_CHECKOUT_SHA,
        "head_git_sha": EXPECTED_EXECUTED_GIT_SHA,
        "workflow_run_id": EXPECTED_RUN_ID,
    }, "baseline live execution binding mismatch")
    require(browser == {
        "browser_version": "151.0.7922.34",
        "evidence_profile": EXPECTED_PROFILE,
        "headless": False,
        "playwright_version": "1.62.0",
    }, "baseline browser binding mismatch")

    require(core["executed_git_sha"] == EXPECTED_EXECUTED_GIT_SHA, "provenance head SHA mismatch")
    require(provenance.get("github_checkout_sha") == EXPECTED_CHECKOUT_SHA, "provenance checkout SHA mismatch")
    require(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "provenance run mismatch")
    require(provenance.get("artifact_id") == EXPECTED_ARTIFACT_ID, "provenance artifact mismatch")
    require(provenance.get("artifact_zip_sha256") == EXPECTED_ARTIFACT_ZIP_SHA256, "provenance artifact digest mismatch")
    require(provenance.get("live_artifact_summary_sha256") == EXPECTED_LIVE_SUMMARY_SHA256, "live summary digest mismatch")
    require(provenance.get("evidence_profile") == EXPECTED_PROFILE, "provenance profile mismatch")
    require(provenance.get("playwright_version") == "1.62.0", "provenance Playwright mismatch")
    require(provenance.get("chromium_version") == "151.0.7922.34", "provenance Chromium mismatch")
    require(core["headed"] is True, "retained run must be headed Chromium")
    require(core["target_count"] == 13, "provenance target count mismatch")
    require(core["acquisition_success"] == 13 and core["acquisition_failure"] == 0, "provenance acquisition accounting mismatch")
    require(core["exact_icpn_candidate_count"] == EXPECTED_EXACT_COUNT, "provenance ICPN count mismatch")
    require(provenance.get("excluded_non_active_part_number_count") == 0, "provenance lifecycle exclusion mismatch")
    require(provenance.get("routing_gates_commercial_identity") is False, "routing must not gate commercial identity")
    require(provenance.get("production_admission_ready") is False, "retained evidence must deny Production readiness")
    require(provenance.get("retained_pilot_summary_kind") == "normalized_decision_projection", "retained summary kind mismatch")
    require(provenance.get("acquisition_time_utc") == {
        "first": "2026-09-09T05:41:10Z",
        "last": "2026-09-09T05:59:00Z",
    }, "acquisition time boundary mismatch")

    expected_bindings = {
        "discovery_manifest_git_blob_sha": EXPECTED_DISCOVERY_MANIFEST_GIT_BLOB_SHA,
        "openocd_catalog_git_blob_sha": EXPECTED_OPENOCD_GIT_BLOB_SHA,
        "production_exact_icpn_count": 502,
        "production_family_counts": {"STM32F1": 75, "STM32F2": 33, "STM32F3": 10, "STM32F4": 384},
        "production_manifest_git_blob_sha": EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB_SHA,
        "stm32f0_production_prestate_count": 0,
    }
    require(baseline.get("source_bindings") == expected_bindings, "baseline historical source binding mismatch")
    require(provenance.get("source_bindings") == expected_bindings, "provenance historical source binding mismatch")

    # The Phase 4.5B target manifest is immutable input. Current Production and
    # current OpenOCD are intentionally NOT compared to historical blobs here.
    require(git_blob_sha(discovery_manifest_path) == EXPECTED_DISCOVERY_MANIFEST_GIT_BLOB_SHA, "Phase 4.5B discovery manifest drifted")
    require(discovery_manifest.get("schema_version") == 1 and discovery_manifest.get("phase") == "4.5B", "discovery manifest phase/schema mismatch")

    expected_aggregate = {
        "acquisition_failure": 0,
        "acquisition_success": 13,
        "active_exact_icpn_candidates": 42,
        "attempted": 13,
        "commercial_identity_clean": True,
        "excluded_non_active_part_numbers": 0,
        "identity_manual_intervention_required": 0,
        "openocd_routing": {"ambiguous": 0, "gates_commercial_identity": False, "unique": 13, "unmapped": 0},
        "routing_followup_required": 0,
    }
    require(baseline.get("aggregate") == expected_aggregate, "baseline aggregate mismatch")
    require(summary.get("aggregate") == {
        key: expected_aggregate[key]
        for key in (
            "acquisition_failure", "acquisition_success", "active_exact_icpn_candidates",
            "attempted", "commercial_identity_clean", "excluded_non_active_part_numbers",
            "identity_manual_intervention_required",
        )
    }, "summary aggregate mismatch")
    require(summary.get("lifecycle") == {
        "excluded_non_active_part_numbers": 0,
        "marketing_status_for_all_exact_icpns": ACTIVE_STATUS,
    }, "retained lifecycle projection mismatch")

    baseline_targets = baseline.get("targets")
    manifest_targets = discovery_manifest.get("targets")
    require(isinstance(baseline_targets, list) and len(baseline_targets) == 13, "baseline target list mismatch")
    require(isinstance(manifest_targets, list) and len(manifest_targets) == 13, "manifest target list mismatch")
    require(
        [(item.get("subfamily"), item.get("base_device")) for item in baseline_targets]
        == [(item.get("subfamily"), item.get("base_device")) for item in manifest_targets],
        "discovery target ordering drifted",
    )

    all_icpns: list[str] = []
    for baseline_target, manifest_target in zip(baseline_targets, manifest_targets):
        base = baseline_target.get("base_device")
        require(isinstance(base, str) and base.startswith("STM32F0"), "invalid baseline Base Device")
        require(manifest_target.get("source_url") == baseline_target.get("source_url"), f"{base}: source URL drifted")
        require(baseline_target.get("source_url") == f"https://www.st.com/en/microcontrollers-microprocessors/{base.lower()}.html", f"{base}: non-canonical ST source URL")
        exact = baseline_target.get("exact_icpns")
        require(isinstance(exact, list) and exact, f"{base}: exact ICPNs missing")
        require(all(isinstance(value, str) and value.startswith(base) for value in exact), f"{base}: foreign ICPN")
        require(baseline_target.get("routing_gates_commercial_identity") is False, f"{base}: routing gate boundary mismatch")
        require(baseline_target.get("historical_openocd_routing_status") == "unique", f"{base}: historical routing status mismatch")
        require(baseline_target.get("historical_openocd_target_configs") == ["tcl/target/stm32f0x.cfg"], f"{base}: historical target config mismatch")
        for field in ("evidence_section_sha256", "rendered_dom_sha256"):
            value = baseline_target.get(field)
            require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value), f"{base}: invalid {field}")
        require(isinstance(baseline_target.get("retrieved_at_utc"), str), f"{base}: retrieval timestamp missing")
        all_icpns.extend(exact)

    require(len(all_icpns) == EXPECTED_EXACT_COUNT, "aggregate exact ICPN count mismatch")
    require(len(set(all_icpns)) == EXPECTED_EXACT_COUNT, "duplicate exact ICPN across retained targets")
    require(summary.get("exact_icpns") == all_icpns, "retained exact ICPN projection drifted")

    return {
        "status": "valid",
        "phase": "4.5B",
        "family": "STM32F0",
        "target_count": 13,
        "active_exact_icpn_candidates": EXPECTED_EXACT_COUNT,
        "commercial_identity_clean": True,
        "routing_gates_commercial_identity": False,
        "canonical_dataset_admission": False,
        "production_admission_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--discovery-manifest", type=Path, default=DEFAULT_DISCOVERY_MANIFEST)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = validate(
            evidence_dir=args.evidence_dir,
            baseline_path=args.baseline,
            discovery_manifest_path=args.discovery_manifest,
        )
    except (EvidenceFrameworkError, STM32F0RetainedEvidenceError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

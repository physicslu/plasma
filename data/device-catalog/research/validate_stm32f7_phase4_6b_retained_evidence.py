#!/usr/bin/env python3
"""Validate retained STM32F7 Phase 4.6B disposition-aware evidence offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from collections import Counter
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
DEFAULT_BASELINE = HERE / "stm32f7-phase4.6b-discovery-baseline.json"
DEFAULT_DISCOVERY_MANIFEST = HERE / "stm32f7-phase4.6b-discovery-manifest.json"
DEFAULT_EVIDENCE_DIR = HERE / "evidence/stm32f7-phase4.6b-official-st-discovery-live-2026-09-09"

EXPECTED_EVIDENCE_ID = (
    "stm32f7-phase4.6b-official-st-discovery-2026-09-09-"
    "retained-20260909T080415Z-776ebeaf"
)
EXPECTED_BASELINE_SHA256 = "6e93a1b2ef0a91396bed08f6f3e6e87a427537bc6eb7b4bde5385e8191696e14"
EXPECTED_SUMMARY_SHA256 = "9cd87df3792ff85908bbe654fec0db06f72a0df7e619eb784e224f2d60a85ff0"
EXPECTED_PROVENANCE_SHA256 = "ee340be1dcdeda6eb3d10a27b42426574daa6b766782399d51db85a413da52e2"
EXPECTED_MANIFEST_SHA256 = "b45459347eaaaf16409f6ca12c75aa99696dbdacec260a387708a96725c0c9ca"
EXPECTED_LIVE_SUMMARY_SHA256 = "10fcae871a5d2a41f79a6b800c7425b607183fee3b1901de8f7c1947e1c515dc"
EXPECTED_EXECUTED_GIT_SHA = "776ebeafe2156a6cfdea5340dc2c8921e45725ed"
EXPECTED_RUN_ID = 34326658883
EXPECTED_ARTIFACT_ID = 10094200419
EXPECTED_ARTIFACT_ZIP_SHA256 = "998670e0d8fc6331d60a080dccd48f0dbeb2e967a0169af4e177d9e60f30bf3f"
EXPECTED_PRE_POLICY_FIX_RUN_ID = "34325627558"
EXPECTED_PRE_POLICY_FIX_ARTIFACT_ID = "10093847910"
EXPECTED_PROFILE = "stm32f7_dual_surface_v1"
EXPECTED_DISCOVERY_MANIFEST_GIT_BLOB_SHA = "706613e1894b88261d1769f14631655e76bce27c"
EXPECTED_OPENOCD_GIT_BLOB_SHA = "0ef056e3363e20bb527590c4a4cc1cc0d7afb810"
EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB_SHA = "8c9bf60bcbae81c145f647deabbcaf3af63c35e6"
EXPECTED_ACTIVE_COUNT = 19
EXPECTED_LIFECYCLE_EXCLUSION_COUNT = 11
EXPECTED_SOURCE_UNAVAILABLE_COUNT = 2
EXPECTED_TARGET_COUNT = 16
ACTIVE_STATUS = "Active Product is in volume production."

EXPECTED_AGGREGATE = {
    "acquisition_failure": 0,
    "acquisition_success": 14,
    "active_candidate_targets": 9,
    "active_exact_icpn_candidates": 19,
    "attempted": 16,
    "bounded_discovery_clean": True,
    "commercial_identity_clean": False,
    "commercial_identity_unresolved_targets": 2,
    "commercial_identity_verified_targets": 14,
    "dispositioned_targets": 16,
    "excluded_non_active_part_numbers": 11,
    "identity_manual_intervention_required": 0,
    "lifecycle_excluded_targets": 5,
    "openocd_routing": {
        "ambiguous": 0,
        "gates_commercial_identity": False,
        "not_applicable": 7,
        "unique": 9,
        "unmapped": 0,
    },
    "routing_followup_required": 0,
    "source_unavailable_exclusions": 2,
}

EXPECTED_SOURCE_BINDINGS = {
    "discovery_manifest_git_blob_sha": EXPECTED_DISCOVERY_MANIFEST_GIT_BLOB_SHA,
    "openocd_catalog_git_blob_sha": EXPECTED_OPENOCD_GIT_BLOB_SHA,
    "production_exact_icpn_count": 544,
    "production_family_counts": {
        "STM32F0": 42,
        "STM32F1": 75,
        "STM32F2": 33,
        "STM32F3": 10,
        "STM32F4": 384,
    },
    "production_manifest_git_blob_sha": EXPECTED_PRODUCTION_MANIFEST_GIT_BLOB_SHA,
    "stm32f7_production_prestate_count": 0,
}

EXPECTED_SOURCE_UNAVAILABLE = [
    ("STM32F768", "STM32F768AI"),
    ("STM32F769", "STM32F769AG"),
]


class STM32F7RetainedEvidenceError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise STM32F7RetainedEvidenceError(message)


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
    require(sha256(evidence_dir / "manifest.json") == EXPECTED_MANIFEST_SHA256, "retained manifest byte digest mismatch")

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
    require(sha256(evidence_dir / "provenance.json") == EXPECTED_PROVENANCE_SHA256, "provenance byte digest mismatch")
    require(provenance.get("baseline_sha256") == EXPECTED_BASELINE_SHA256, "provenance baseline digest mismatch")
    require(provenance.get("pilot_summary_sha256") == EXPECTED_SUMMARY_SHA256, "provenance summary digest mismatch")

    require(baseline.get("schema_version") == 1 and baseline.get("phase") == "4.6B", "baseline phase/schema mismatch")
    require(baseline.get("family") == "STM32F7", "baseline family mismatch")
    require(summary.get("schema_version") == 1 and summary.get("phase") == "4.6B", "summary phase/schema mismatch")
    require(summary.get("family") == "STM32F7", "summary family mismatch")
    require(summary.get("pilot_id") == baseline.get("pilot_id") == discovery_manifest.get("pilot_id"), "pilot identity mismatch")
    require(all_false_claims(baseline.get("claims")), "baseline claims must remain false")
    require(all_false_claims(summary.get("claims")), "summary claims must remain false")

    execution = baseline.get("discovery_execution")
    browser = baseline.get("browser")
    require(isinstance(execution, dict) and isinstance(browser, dict), "baseline execution/browser binding missing")
    require(execution == {
        "artifact_id": EXPECTED_ARTIFACT_ID,
        "artifact_zip_sha256": EXPECTED_ARTIFACT_ZIP_SHA256,
        "github_checkout_sha": EXPECTED_EXECUTED_GIT_SHA,
        "head_git_sha": EXPECTED_EXECUTED_GIT_SHA,
        "pre_policy_fix_artifact_id": EXPECTED_PRE_POLICY_FIX_ARTIFACT_ID,
        "pre_policy_fix_run_id": EXPECTED_PRE_POLICY_FIX_RUN_ID,
        "workflow_run_id": EXPECTED_RUN_ID,
    }, "baseline live execution binding mismatch")
    require(browser == {
        "browser_version": "151.0.7922.34",
        "evidence_profile": EXPECTED_PROFILE,
        "headless": False,
        "playwright_version": "1.62.0",
    }, "baseline browser binding mismatch")

    require(core["executed_git_sha"] == EXPECTED_EXECUTED_GIT_SHA, "provenance execution SHA mismatch")
    require(provenance.get("github_checkout_sha") == EXPECTED_EXECUTED_GIT_SHA, "provenance checkout SHA mismatch")
    require(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "provenance run mismatch")
    require(provenance.get("artifact_id") == EXPECTED_ARTIFACT_ID, "provenance artifact mismatch")
    require(provenance.get("artifact_zip_sha256") == EXPECTED_ARTIFACT_ZIP_SHA256, "provenance artifact digest mismatch")
    require(provenance.get("live_artifact_summary_sha256") == EXPECTED_LIVE_SUMMARY_SHA256, "live summary digest mismatch")
    require(provenance.get("evidence_profile") == EXPECTED_PROFILE, "provenance profile mismatch")
    require(provenance.get("playwright_version") == "1.62.0", "provenance Playwright mismatch")
    require(provenance.get("chromium_version") == "151.0.7922.34", "provenance Chromium mismatch")
    require(core["headed"] is True, "retained execution must be headed Chromium")
    require(core["target_count"] == EXPECTED_TARGET_COUNT, "provenance target count mismatch")
    require(core["acquisition_success"] == 14 and core["acquisition_failure"] == 0, "provenance acquisition accounting mismatch")
    require(core["exact_icpn_candidate_count"] == EXPECTED_ACTIVE_COUNT, "provenance Active ICPN count mismatch")
    require(provenance.get("excluded_non_active_part_number_count") == EXPECTED_LIFECYCLE_EXCLUSION_COUNT, "provenance lifecycle exclusion mismatch")
    require(provenance.get("source_unavailable_exclusion_count") == EXPECTED_SOURCE_UNAVAILABLE_COUNT, "provenance source-unavailable mismatch")
    require(provenance.get("bounded_discovery_clean") is True, "bounded discovery must remain clean")
    require(provenance.get("commercial_identity_clean") is False, "commercial identity must remain explicitly incomplete")
    require(provenance.get("routing_gates_commercial_identity") is False, "routing must not gate commercial identity")
    require(provenance.get("production_admission_ready") is False, "retained evidence must deny Production readiness")
    require(provenance.get("evaluator_result") == "phase4_6b_bounded_discovery_clean", "evaluator result mismatch")
    require(provenance.get("retained_pilot_summary_kind") == "normalized_decision_projection", "retained projection kind mismatch")
    require(provenance.get("acquisition_time_utc") == {
        "first": "2026-09-09T07:59:46Z",
        "last": "2026-09-09T08:04:15Z",
    }, "acquisition time boundary mismatch")
    require(provenance.get("source_bindings") == EXPECTED_SOURCE_BINDINGS, "provenance historical source binding mismatch")
    require(baseline.get("source_bindings") == EXPECTED_SOURCE_BINDINGS, "baseline historical source binding mismatch")

    # The retained historical snapshots are not compared with future mutable
    # Production/OpenOCD state. Only the Phase 4.6B target manifest itself is
    # immutable input and must remain byte-identical by Git-blob identity.
    require(git_blob_sha(discovery_manifest_path) == EXPECTED_DISCOVERY_MANIFEST_GIT_BLOB_SHA, "Phase 4.6B discovery manifest drifted")
    require(discovery_manifest.get("schema_version") == 1 and discovery_manifest.get("phase") == "4.6B", "discovery manifest phase/schema mismatch")

    require(baseline.get("aggregate") == EXPECTED_AGGREGATE, "baseline aggregate mismatch")
    require(summary.get("aggregate") == EXPECTED_AGGREGATE, "summary aggregate mismatch")
    require(summary.get("lifecycle", {}).get("marketing_status_for_all_exact_icpns") == ACTIVE_STATUS, "Active lifecycle projection mismatch")

    baseline_targets = baseline.get("targets")
    manifest_targets = discovery_manifest.get("targets")
    require(isinstance(baseline_targets, list) and len(baseline_targets) == EXPECTED_TARGET_COUNT, "baseline target list mismatch")
    require(isinstance(manifest_targets, list) and len(manifest_targets) == EXPECTED_TARGET_COUNT, "manifest target list mismatch")
    require(
        [(item.get("subfamily"), item.get("base_device")) for item in baseline_targets]
        == [(item.get("subfamily"), item.get("base_device")) for item in manifest_targets],
        "retained target ordering drifted",
    )

    disposition_counts: Counter[str] = Counter()
    active_icpns: list[str] = []
    lifecycle_exclusions: list[dict[str, str]] = []
    source_unavailable_pairs: list[tuple[str, str]] = []

    for retained, manifest_target in zip(baseline_targets, manifest_targets):
        require(isinstance(retained, dict) and isinstance(manifest_target, dict), "target entry must be an object")
        base = retained.get("base_device")
        subfamily = retained.get("subfamily")
        source_url = retained.get("source_url")
        require(isinstance(base, str) and base.startswith("STM32F7"), "invalid retained Base Device")
        require(manifest_target.get("source_url") == source_url, f"{base}: source URL drifted")
        require(source_url == f"https://www.st.com/en/microcontrollers-microprocessors/{base.lower()}.html", f"{base}: non-canonical ST URL")
        require(retained.get("routing_gates_commercial_identity") is False, f"{base}: routing gate boundary mismatch")
        disposition = retained.get("disposition")
        require(isinstance(disposition, str), f"{base}: disposition missing")
        disposition_counts[disposition] += 1

        if disposition == "source_unavailable_excluded":
            require(retained.get("commercial_identity_status") == "unverified", f"{base}: unavailable identity status mismatch")
            require(retained.get("source_unavailable_status") == "http_404", f"{base}: unavailable reason mismatch")
            require("exact_icpns" not in retained, f"{base}: unavailable source must not fabricate exact ICPNs")
            require("evidence_section_sha256" not in retained and "rendered_dom_sha256" not in retained, f"{base}: unavailable source must not fabricate evidence digests")
            source_unavailable_pairs.append((str(subfamily), base))
            continue

        exact = retained.get("exact_icpns")
        excluded = retained.get("excluded_non_active_part_numbers")
        require(isinstance(exact, list) and isinstance(excluded, list), f"{base}: retained identity lists missing")
        require(all(isinstance(value, str) and value.startswith(base) for value in exact), f"{base}: foreign Active exact ICPN")
        for item in excluded:
            require(isinstance(item, dict), f"{base}: invalid lifecycle exclusion")
            require(isinstance(item.get("icpn"), str) and item["icpn"].startswith(base), f"{base}: foreign lifecycle exclusion")
            require(isinstance(item.get("marketing_status"), str) and item["marketing_status"], f"{base}: exclusion status missing")
            lifecycle_exclusions.append({"base_device": base, "icpn": item["icpn"], "marketing_status": item["marketing_status"]})
        for field in ("evidence_section_sha256", "rendered_dom_sha256"):
            value = retained.get(field)
            require(isinstance(value, str) and len(value) == 64 and all(c in "0123456789abcdef" for c in value), f"{base}: invalid {field}")
        require(isinstance(retained.get("retrieved_at_utc"), str), f"{base}: retrieval timestamp missing")

        if disposition == "active_candidates":
            require(retained.get("commercial_identity_status") == "verified_active", f"{base}: Active identity status mismatch")
            require(bool(exact), f"{base}: Active disposition lacks exact ICPN")
            require(retained.get("historical_openocd_routing_status") == "unique", f"{base}: Active routing status mismatch")
            require(retained.get("historical_openocd_target_configs") == ["tcl/target/stm32f7x.cfg"], f"{base}: Active target config mismatch")
            active_icpns.extend(exact)
        elif disposition == "lifecycle_excluded":
            require(retained.get("commercial_identity_status") == "verified_non_active_only", f"{base}: lifecycle identity status mismatch")
            require(exact == [] and bool(excluded), f"{base}: lifecycle-only disposition inconsistent")
            require(retained.get("historical_openocd_routing_status") == "not_applicable", f"{base}: lifecycle routing must be not_applicable")
            require(retained.get("historical_openocd_target_configs") == [], f"{base}: lifecycle target configs must be empty")
        else:
            raise STM32F7RetainedEvidenceError(f"{base}: unknown disposition {disposition!r}")

    require(disposition_counts == Counter({
        "active_candidates": 9,
        "lifecycle_excluded": 5,
        "source_unavailable_excluded": 2,
    }), f"disposition counts mismatch: {dict(disposition_counts)}")
    require(source_unavailable_pairs == EXPECTED_SOURCE_UNAVAILABLE, "source-unavailable target set drifted")
    require(len(active_icpns) == EXPECTED_ACTIVE_COUNT and len(set(active_icpns)) == EXPECTED_ACTIVE_COUNT, "Active exact ICPN aggregate mismatch")
    require(len(lifecycle_exclusions) == EXPECTED_LIFECYCLE_EXCLUSION_COUNT, "lifecycle exclusion aggregate mismatch")
    require(set(active_icpns).isdisjoint({item["icpn"] for item in lifecycle_exclusions}), "Active and excluded ICPN sets overlap")
    require(summary.get("exact_icpns") == active_icpns, "retained Active ICPN projection drifted")
    require(summary.get("lifecycle", {}).get("excluded_non_active_part_numbers") == lifecycle_exclusions, "retained lifecycle projection drifted")
    require(
        [(item.get("subfamily"), item.get("base_device")) for item in summary.get("source_unavailable_exclusions", [])]
        == EXPECTED_SOURCE_UNAVAILABLE,
        "retained source-unavailable projection drifted",
    )
    require(all(item.get("reason") == "canonical_product_page_http_404" for item in summary.get("source_unavailable_exclusions", [])), "source-unavailable reason drifted")

    return {
        "status": "valid",
        "phase": "4.6B",
        "family": "STM32F7",
        "target_count": EXPECTED_TARGET_COUNT,
        "disposition_counts": dict(disposition_counts),
        "active_exact_icpn_candidates": EXPECTED_ACTIVE_COUNT,
        "excluded_non_active_part_numbers": EXPECTED_LIFECYCLE_EXCLUSION_COUNT,
        "source_unavailable_exclusions": EXPECTED_SOURCE_UNAVAILABLE_COUNT,
        "bounded_discovery_clean": True,
        "commercial_identity_clean": False,
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
    except (EvidenceFrameworkError, STM32F7RetainedEvidenceError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

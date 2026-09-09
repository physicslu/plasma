#!/usr/bin/env python3
"""Validate retained STM32F7 Phase 4.6B disposition-aware evidence offline."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from device_catalog_evidence_framework import (
    EvidenceFrameworkError,
    read_json,
    sha256,
    validate_manifest,
)

HERE = Path(__file__).resolve().parent
DEFAULT_BASELINE = HERE / "stm32f7-phase4.6b-discovery-baseline.json"
DEFAULT_DISCOVERY_MANIFEST = HERE / "stm32f7-phase4.6b-discovery-manifest.json"
DEFAULT_EVIDENCE_DIR = HERE / "evidence/stm32f7-phase4.6b-official-st-discovery-live-2026-09-09"

EXPECTED_EVIDENCE_ID = "stm32f7-phase4.6b-official-st-discovery-2026-09-09-retained-20260909T080415Z-776ebeaf"
EXPECTED_BASELINE_SHA256 = "6e93a1b2ef0a91396bed08f6f3e6e87a427537bc6eb7b4bde5385e8191696e14"
EXPECTED_SUMMARY_SHA256 = "9cd87df3792ff85908bbe654fec0db06f72a0df7e619eb784e224f2d60a85ff0"
EXPECTED_PROVENANCE_SHA256 = "ee340be1dcdeda6eb3d10a27b42426574daa6b766782399d51db85a413da52e2"
EXPECTED_MANIFEST_SHA256 = "b45459347eaaaf16409f6ca12c75aa99696dbdacec260a387708a96725c0c9ca"
EXPECTED_LIVE_SUMMARY_SHA256 = "10fcae871a5d2a41f79a6b800c7425b607183fee3b1901de8f7c1947e1c515dc"
EXPECTED_EXECUTED_GIT_SHA = "776ebeafe2156a6cfdea5340dc2c8921e45725ed"
EXPECTED_RUN_ID = 34326658883
EXPECTED_ARTIFACT_ID = 10094200419
EXPECTED_ARTIFACT_ZIP_SHA256 = "998670e0d8fc6331d60a080dccd48f0dbeb2e967a0169af4e177d9e60f30bf3f"
EXPECTED_DISCOVERY_MANIFEST_BLOB = "706613e1894b88261d1769f14631655e76bce27c"
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
    "discovery_manifest_git_blob_sha": EXPECTED_DISCOVERY_MANIFEST_BLOB,
    "openocd_catalog_git_blob_sha": "0ef056e3363e20bb527590c4a4cc1cc0d7afb810",
    "production_exact_icpn_count": 544,
    "production_family_counts": {
        "STM32F0": 42, "STM32F1": 75, "STM32F2": 33, "STM32F3": 10, "STM32F4": 384,
    },
    "production_manifest_git_blob_sha": "8c9bf60bcbae81c145f647deabbcaf3af63c35e6",
    "stm32f7_production_prestate_count": 0,
}
EXPECTED_SOURCE_UNAVAILABLE = [("STM32F768", "STM32F768AI"), ("STM32F769", "STM32F769AG")]
GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


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


def validate(*, evidence_dir: Path = DEFAULT_EVIDENCE_DIR, baseline_path: Path = DEFAULT_BASELINE,
             discovery_manifest_path: Path = DEFAULT_DISCOVERY_MANIFEST) -> dict[str, Any]:
    retained_manifest = validate_manifest(
        evidence_dir, expected_files=("README.md", "pilot-summary.json", "provenance.json")
    )
    require(retained_manifest.get("evidence_id") == EXPECTED_EVIDENCE_ID, "evidence ID mismatch")
    require(sha256(evidence_dir / "manifest.json") == EXPECTED_MANIFEST_SHA256, "retained manifest digest mismatch")

    baseline = read_json(baseline_path)
    summary = read_json(evidence_dir / "pilot-summary.json")
    provenance = read_json(evidence_dir / "provenance.json")
    discovery_manifest = read_json(discovery_manifest_path)

    require(sha256(baseline_path) == EXPECTED_BASELINE_SHA256, "baseline byte digest mismatch")
    require(sha256(evidence_dir / "pilot-summary.json") == EXPECTED_SUMMARY_SHA256, "summary byte digest mismatch")
    require(sha256(evidence_dir / "provenance.json") == EXPECTED_PROVENANCE_SHA256, "provenance byte digest mismatch")
    require(provenance.get("baseline_sha256") == EXPECTED_BASELINE_SHA256, "provenance baseline digest mismatch")
    require(provenance.get("pilot_summary_sha256") == EXPECTED_SUMMARY_SHA256, "provenance summary digest mismatch")
    require(provenance.get("live_artifact_summary_sha256") == EXPECTED_LIVE_SUMMARY_SHA256, "live summary digest mismatch")

    require(baseline.get("schema_version") == summary.get("schema_version") == provenance.get("schema_version") == 1, "schema mismatch")
    require(baseline.get("phase") == summary.get("phase") == "4.6B", "phase mismatch")
    require(baseline.get("family") == summary.get("family") == "STM32F7", "family mismatch")
    require(baseline.get("pilot_id") == summary.get("pilot_id") == discovery_manifest.get("pilot_id"), "pilot identity mismatch")
    require(provenance.get("evidence_id") == EXPECTED_EVIDENCE_ID, "provenance evidence ID mismatch")
    require(provenance.get("source_repository") == "physicslu/plasma", "source repository mismatch")
    require(provenance.get("manufacturer") == "STMicroelectronics", "manufacturer mismatch")
    require(provenance.get("acquisition_transport") == "chromium_rendered_dom", "transport mismatch")
    require(provenance.get("headed") is True, "headed-browser provenance mismatch")
    require(all_false_claims(baseline.get("claims")) and all_false_claims(summary.get("claims")), "claims must remain false")

    execution = baseline.get("discovery_execution")
    require(execution == {
        "artifact_id": EXPECTED_ARTIFACT_ID,
        "artifact_zip_sha256": EXPECTED_ARTIFACT_ZIP_SHA256,
        "github_checkout_sha": EXPECTED_EXECUTED_GIT_SHA,
        "head_git_sha": EXPECTED_EXECUTED_GIT_SHA,
        "pre_policy_fix_artifact_id": "10093847910",
        "pre_policy_fix_run_id": "34325627558",
        "workflow_run_id": EXPECTED_RUN_ID,
    }, "live execution binding mismatch")
    require(provenance.get("executed_git_sha") == EXPECTED_EXECUTED_GIT_SHA and GIT_SHA_RE.fullmatch(EXPECTED_EXECUTED_GIT_SHA), "execution SHA mismatch")
    require(provenance.get("github_checkout_sha") == EXPECTED_EXECUTED_GIT_SHA, "checkout SHA mismatch")
    require(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "workflow run mismatch")
    require(provenance.get("artifact_id") == EXPECTED_ARTIFACT_ID, "artifact ID mismatch")
    require(provenance.get("artifact_zip_sha256") == EXPECTED_ARTIFACT_ZIP_SHA256, "artifact digest mismatch")
    require(provenance.get("evidence_profile") == "stm32f7_dual_surface_v1", "evidence profile mismatch")
    require(provenance.get("playwright_version") == "1.62.0", "Playwright mismatch")
    require(provenance.get("chromium_version") == "151.0.7922.34", "Chromium mismatch")
    require(provenance.get("acquisition_time_utc") == {"first": "2026-09-09T07:59:46Z", "last": "2026-09-09T08:04:15Z"}, "acquisition time mismatch")

    # Disposition-aware accounting intentionally supersedes the generic two-state
    # success+failure==target_count invariant. HTTP-404 exclusions are neither a
    # successful manufacturer acquisition nor a technical acquisition failure.
    require(provenance.get("target_count") == 16, "provenance target count mismatch")
    require(provenance.get("acquisition_success") == 14, "provenance manufacturer acquisition count mismatch")
    require(provenance.get("acquisition_failure") == 0, "provenance technical failure count mismatch")
    require(provenance.get("source_unavailable_exclusion_count") == 2, "provenance source-unavailable count mismatch")
    require(14 + 0 + 2 == 16, "disposition acquisition accounting invariant broken")
    require(provenance.get("exact_icpn_candidate_count") == 19, "provenance Active ICPN count mismatch")
    require(provenance.get("excluded_non_active_part_number_count") == 11, "provenance lifecycle exclusion count mismatch")
    require(provenance.get("bounded_discovery_clean") is True, "bounded discovery must remain clean")
    require(provenance.get("commercial_identity_clean") is False, "commercial identity must remain incomplete")
    require(provenance.get("routing_gates_commercial_identity") is False, "routing must not gate identity")
    require(provenance.get("canonical_dataset_admission") is False and provenance.get("production_admission_ready") is False, "retained evidence cannot authorize admission")
    require(provenance.get("evaluator_result") == "phase4_6b_bounded_discovery_clean", "evaluator result mismatch")
    require(provenance.get("source_bindings") == EXPECTED_SOURCE_BINDINGS, "provenance historical source bindings mismatch")
    require(baseline.get("source_bindings") == EXPECTED_SOURCE_BINDINGS, "baseline historical source bindings mismatch")

    require(git_blob_sha(discovery_manifest_path) == EXPECTED_DISCOVERY_MANIFEST_BLOB, "Phase 4.6B target manifest drifted")
    require(baseline.get("aggregate") == EXPECTED_AGGREGATE, "baseline aggregate mismatch")
    require(summary.get("aggregate") == EXPECTED_AGGREGATE, "summary aggregate mismatch")
    require(summary.get("lifecycle", {}).get("marketing_status_for_all_exact_icpns") == ACTIVE_STATUS, "Active lifecycle projection mismatch")

    baseline_targets = baseline.get("targets")
    manifest_targets = discovery_manifest.get("targets")
    require(isinstance(baseline_targets, list) and isinstance(manifest_targets, list), "target lists missing")
    require(len(baseline_targets) == len(manifest_targets) == 16, "target count mismatch")
    require([(x.get("subfamily"), x.get("base_device")) for x in baseline_targets] ==
            [(x.get("subfamily"), x.get("base_device")) for x in manifest_targets], "target ordering drifted")

    dispositions: Counter[str] = Counter()
    active_icpns: list[str] = []
    lifecycle_exclusions: list[dict[str, str]] = []
    unavailable: list[tuple[str, str]] = []
    for retained, source in zip(baseline_targets, manifest_targets):
        base = retained.get("base_device")
        subfamily = retained.get("subfamily")
        require(isinstance(base, str) and base.startswith("STM32F7"), "invalid Base Device")
        require(retained.get("source_url") == source.get("source_url") == f"https://www.st.com/en/microcontrollers-microprocessors/{base.lower()}.html", f"{base}: source URL mismatch")
        require(retained.get("routing_gates_commercial_identity") is False, f"{base}: routing boundary mismatch")
        disposition = retained.get("disposition")
        require(isinstance(disposition, str), f"{base}: disposition missing")
        dispositions[disposition] += 1

        if disposition == "source_unavailable_excluded":
            require(retained.get("commercial_identity_status") == "unverified", f"{base}: unresolved identity status mismatch")
            require(retained.get("source_unavailable_status") == "http_404", f"{base}: source exclusion reason mismatch")
            require("exact_icpns" not in retained and "evidence_section_sha256" not in retained and "rendered_dom_sha256" not in retained, f"{base}: unavailable source fabricated evidence")
            unavailable.append((str(subfamily), base))
            continue

        exact = retained.get("exact_icpns")
        excluded = retained.get("excluded_non_active_part_numbers")
        require(isinstance(exact, list) and isinstance(excluded, list), f"{base}: identity lists missing")
        require(all(isinstance(x, str) and x.startswith(base) for x in exact), f"{base}: foreign Active ICPN")
        for item in excluded:
            require(isinstance(item, dict) and isinstance(item.get("icpn"), str) and item["icpn"].startswith(base), f"{base}: invalid lifecycle exclusion")
            require(isinstance(item.get("marketing_status"), str) and item["marketing_status"], f"{base}: missing lifecycle status")
            lifecycle_exclusions.append({"base_device": base, "icpn": item["icpn"], "marketing_status": item["marketing_status"]})
        for digest_field in ("evidence_section_sha256", "rendered_dom_sha256"):
            digest = retained.get(digest_field)
            require(isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest), f"{base}: invalid {digest_field}")

        if disposition == "active_candidates":
            require(retained.get("commercial_identity_status") == "verified_active" and bool(exact), f"{base}: Active disposition inconsistent")
            require(retained.get("historical_openocd_routing_status") == "unique", f"{base}: Active routing mismatch")
            require(retained.get("historical_openocd_target_configs") == ["tcl/target/stm32f7x.cfg"], f"{base}: Active target config mismatch")
            active_icpns.extend(exact)
        elif disposition == "lifecycle_excluded":
            require(retained.get("commercial_identity_status") == "verified_non_active_only", f"{base}: lifecycle identity mismatch")
            require(exact == [] and bool(excluded), f"{base}: lifecycle-only disposition inconsistent")
            require(retained.get("historical_openocd_routing_status") == "not_applicable" and retained.get("historical_openocd_target_configs") == [], f"{base}: lifecycle routing must be not_applicable")
        else:
            raise STM32F7RetainedEvidenceError(f"{base}: unknown disposition {disposition!r}")

    require(dispositions == Counter({"active_candidates": 9, "lifecycle_excluded": 5, "source_unavailable_excluded": 2}), f"disposition counts mismatch: {dict(dispositions)}")
    require(unavailable == EXPECTED_SOURCE_UNAVAILABLE, "source-unavailable target set drifted")
    require(len(active_icpns) == len(set(active_icpns)) == 19, "Active ICPN aggregate mismatch")
    require(len(lifecycle_exclusions) == 11, "lifecycle exclusion aggregate mismatch")
    require(set(active_icpns).isdisjoint({x["icpn"] for x in lifecycle_exclusions}), "Active/excluded identity sets overlap")
    require(summary.get("exact_icpns") == active_icpns, "Active ICPN projection drifted")
    require(summary.get("lifecycle", {}).get("excluded_non_active_part_numbers") == lifecycle_exclusions, "lifecycle exclusion projection drifted")
    source_unavailable = summary.get("source_unavailable_exclusions")
    require(isinstance(source_unavailable, list), "source-unavailable projection missing")
    require([(x.get("subfamily"), x.get("base_device")) for x in source_unavailable] == EXPECTED_SOURCE_UNAVAILABLE, "source-unavailable projection drifted")
    require(all(x.get("reason") == "canonical_product_page_http_404" for x in source_unavailable), "source-unavailable reason drifted")

    return {
        "status": "valid", "phase": "4.6B", "family": "STM32F7", "target_count": 16,
        "disposition_counts": dict(dispositions), "active_exact_icpn_candidates": 19,
        "excluded_non_active_part_numbers": 11, "source_unavailable_exclusions": 2,
        "bounded_discovery_clean": True, "commercial_identity_clean": False,
        "canonical_dataset_admission": False, "production_admission_ready": False,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-dir", type=Path, default=DEFAULT_EVIDENCE_DIR)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--discovery-manifest", type=Path, default=DEFAULT_DISCOVERY_MANIFEST)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        report = validate(evidence_dir=args.evidence_dir, baseline_path=args.baseline,
                          discovery_manifest_path=args.discovery_manifest)
    except (EvidenceFrameworkError, STM32F7RetainedEvidenceError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

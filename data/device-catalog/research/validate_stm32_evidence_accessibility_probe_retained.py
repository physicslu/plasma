#!/usr/bin/env python3
"""Hard-lock and semantically replay retained STM32 U0/C0/L1 accessibility evidence."""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
BASELINE = HERE / "stm32-evidence-accessibility-probe-baseline.json"
DISCOVERY = HERE / "stm32-evidence-accessibility-probe-manifest.json"
EVIDENCE = HERE / "evidence/stm32-u0-c0-l1-evidence-accessibility-probe-live-2026-09-10"

EXPECTED_EVIDENCE_ID = "stm32-u0-c0-l1-evidence-accessibility-probe-retained-20260910T042026Z-e30c2aca"
EXPECTED_BASELINE_SHA = "473e979818770fda2661e963d064f3a0cfbd7cbcad920203e7f358b5b6e140b6"
EXPECTED_SUMMARY_SHA = "d4339d85a7565f4be731de863ee7db0c1301a335bb5b2777e84a1089aae2769d"
EXPECTED_PROVENANCE_SHA = "8c5751803719449ed0be345c2a1b264f7dfa4341faf41c22cbefc2a8aca3d1d7"
EXPECTED_MANIFEST_SHA = "26ea41db9defd509fb2cfed1a0efa253f4587c395f35310c58055b93b8e5c35e"
EXPECTED_README_SHA = "04d4c6200f048744acdadde8703687488ca65c8d8f2a2ba0a9a730e49c2df9ba"
EXPECTED_LIVE_SHA = "7ba273a501fd98d8bd74d180229c7413849390be27b18acd21d3537d39bf9d3d"
EXPECTED_EXEC_SHA = "e30c2aca6a3f4e3ede3b40e6352aa9d8dbe2d163"
EXPECTED_RUN = 34436667425
EXPECTED_ARTIFACT = 10136442964
EXPECTED_ARTIFACT_SHA = "4423e91a1c5eec5491084e6fedd7afc5a53f1701ec583f86163d2ddf64c16d4b"
EXPECTED_TARGETS = [
    "STM32U031C6", "STM32U073C8", "STM32U083CC",
    "STM32C011F4", "STM32C031C4", "STM32C051C6", "STM32C071C8", "STM32C091CB", "STM32C092CB",
    "STM32L100C6", "STM32L151C6", "STM32L152C6", "STM32L162QC",
]
EXPECTED_LIFECYCLE_ONLY = {"STM32L100C6", "STM32L151C6", "STM32L152C6"}
EXPECTED_SERIES = {
    "STM32U0": {"attempted_targets": 3, "dispositioned_targets": 3, "verified_identity_targets": 3, "active_candidate_targets": 3, "lifecycle_excluded_targets": 0, "source_unavailable_404": 0, "manual_review": 0, "active_exact_icpns": 8, "excluded_non_active_part_numbers": 0, "verified_identity_fraction": 1.0, "disposition_fraction": 1.0, "commercial_identity_access_clean": True},
    "STM32C0": {"attempted_targets": 6, "dispositioned_targets": 6, "verified_identity_targets": 6, "active_candidate_targets": 6, "lifecycle_excluded_targets": 0, "source_unavailable_404": 0, "manual_review": 0, "active_exact_icpns": 21, "excluded_non_active_part_numbers": 0, "verified_identity_fraction": 1.0, "disposition_fraction": 1.0, "commercial_identity_access_clean": True},
    "STM32L1": {"attempted_targets": 4, "dispositioned_targets": 4, "verified_identity_targets": 4, "active_candidate_targets": 1, "lifecycle_excluded_targets": 3, "source_unavailable_404": 0, "manual_review": 0, "active_exact_icpns": 1, "excluded_non_active_part_numbers": 8, "verified_identity_fraction": 1.0, "disposition_fraction": 1.0, "commercial_identity_access_clean": True},
}
EXPECTED_BINDINGS = {
    "cross_family_prioritization_git_blob_sha": "f445bc7938eee1a0453fcebe6bf81d77879aeaca",
    "cross_family_prioritization_sha256": "9a99865865f048e6a7636efd82cb17958fdc593240a329e18e3b68d8b0f862f9",
    "openocd_catalog_git_blob_sha": "0ef056e3363e20bb527590c4a4cc1cc0d7afb810",
    "openocd_catalog_sha256": "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3",
    "probe_family_production_prestate_counts": {"STM32C0": 0, "STM32L1": 0, "STM32U0": 0},
    "probe_manifest_git_blob_sha": "52d412d874edd13e7e2b4b63c0509c0e99a8f781",
    "probe_manifest_sha256": "b30acc44a6beceff3a4f4e3bd50162e78b5e42909af1de06ff00380114b0bab3",
    "production_exact_icpn_count": 635,
    "production_family_counts": {"STM32F0": 42, "STM32F1": 75, "STM32F2": 33, "STM32F3": 10, "STM32F4": 384, "STM32F7": 19, "STM32G0": 47, "STM32G4": 25},
    "production_manifest_git_blob_sha": "34ad9299ff0c063a8c8b5de1c253dfee47b63428",
    "production_manifest_sha256": "93c2a4541daeb1d4aa1dcc57edef54042862eb6d9da03e3a6b401e4b8481b11d",
}

class Error(RuntimeError):
    pass

def req(value: bool, message: str) -> None:
    if not value:
        raise Error(message)

def readj(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path}: object required")
    return value

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def all_false(value: object) -> bool:
    return isinstance(value, dict) and bool(value) and set(value.values()) == {False}

def main() -> int:
    baseline = readj(BASELINE)
    summary = readj(EVIDENCE / "probe-summary.json")
    provenance = readj(EVIDENCE / "provenance.json")
    manifest = readj(EVIDENCE / "manifest.json")
    discovery = readj(DISCOVERY)

    req(sha(BASELINE) == EXPECTED_BASELINE_SHA, "baseline byte drift")
    req(sha(EVIDENCE / "probe-summary.json") == EXPECTED_SUMMARY_SHA, "summary byte drift")
    req(sha(EVIDENCE / "provenance.json") == EXPECTED_PROVENANCE_SHA, "provenance byte drift")
    req(sha(EVIDENCE / "manifest.json") == EXPECTED_MANIFEST_SHA, "manifest byte drift")
    req(sha(EVIDENCE / "README.md") == EXPECTED_README_SHA, "README byte drift")
    req(manifest.get("evidence_id") == EXPECTED_EVIDENCE_ID, "evidence ID drift")
    req(provenance.get("evidence_id") == EXPECTED_EVIDENCE_ID, "provenance evidence ID drift")
    req(manifest.get("files") == {"README.md": EXPECTED_README_SHA, "probe-summary.json": EXPECTED_SUMMARY_SHA, "provenance.json": EXPECTED_PROVENANCE_SHA}, "retained manifest bindings drift")

    req(baseline.get("by_series") == EXPECTED_SERIES, "baseline series metrics drift")
    req(summary.get("by_series") == EXPECTED_SERIES, "summary series metrics drift")
    req(baseline.get("attempted_targets") == 13 and baseline.get("dispositioned_targets") == 13, "target accounting drift")
    req(baseline.get("manual_review_targets") == 0 and baseline.get("bounded_probe_clean") is True, "probe clean-state drift")
    req(baseline.get("selected_next_research_family") is None, "probe must not select next family")
    req(summary.get("selected_next_research_family") is None, "summary must not select next family")
    req(all_false(baseline.get("claims")) and all_false(summary.get("claims")), "probe claims must remain false")

    req(baseline.get("source_bindings") == EXPECTED_BINDINGS, "baseline source bindings drift")
    req(provenance.get("source_bindings") == EXPECTED_BINDINGS, "provenance source bindings drift")
    req(baseline.get("discovery_execution") == {"artifact_id": EXPECTED_ARTIFACT, "artifact_zip_sha256": EXPECTED_ARTIFACT_SHA, "executed_git_sha": EXPECTED_EXEC_SHA, "live_summary_sha256": EXPECTED_LIVE_SHA, "workflow_run_id": EXPECTED_RUN}, "execution binding drift")
    req(provenance.get("workflow_run_id") == EXPECTED_RUN and provenance.get("artifact_id") == EXPECTED_ARTIFACT, "workflow/artifact binding drift")
    req(provenance.get("artifact_zip_sha256") == EXPECTED_ARTIFACT_SHA, "artifact digest drift")
    req(provenance.get("executed_git_sha") == EXPECTED_EXEC_SHA, "execution SHA drift")
    req(provenance.get("live_artifact_summary_sha256") == EXPECTED_LIVE_SHA, "live summary digest drift")
    req(provenance.get("baseline_sha256") == EXPECTED_BASELINE_SHA, "provenance baseline digest drift")
    req(provenance.get("acquisition_time_utc") == {"first": "2026-09-10T04:19:02Z", "last": "2026-09-10T04:20:26Z"}, "acquisition time drift")
    req(provenance.get("evidence_profile") == "stm32_cross_family_accessibility_probe_v1", "evidence profile drift")
    req(provenance.get("playwright_version") == "1.62.0" and provenance.get("chromium_version") == "151.0.7922.34", "browser toolchain drift")
    req(provenance.get("headed") is True and provenance.get("target_count") == 13, "browser/target provenance drift")
    req(provenance.get("selected_next_research_family") is None, "provenance must not select next family")
    req(provenance.get("production_write_authorized") is False and provenance.get("programming_policy_defined") is False and provenance.get("runtime_support_claimed") is False, "authority boundary drift")

    source_targets = discovery.get("targets")
    targets = baseline.get("targets")
    req(isinstance(source_targets, list) and isinstance(targets, list), "target lists missing")
    req([x.get("base_device") for x in source_targets] == EXPECTED_TARGETS, "source target ordering drift")
    req([x.get("base_device") for x in targets] == EXPECTED_TARGETS, "retained target ordering drift")

    active: list[str] = []
    excluded: list[str] = []
    lifecycle_only: set[str] = set()
    for target in targets:
        req(isinstance(target, dict), "target must be an object")
        base = target.get("base_device")
        series = target.get("series")
        req(isinstance(base, str) and isinstance(series, str), "target identity missing")
        exact = target.get("exact_icpns")
        non_active = target.get("excluded_non_active_part_numbers")
        req(isinstance(exact, list) and isinstance(non_active, list), f"{base}: identity lists missing")
        req(all(isinstance(v, str) and v.startswith(base) for v in exact), f"{base}: foreign Active identity")
        active.extend(exact)
        for item in non_active:
            req(isinstance(item, dict), f"{base}: lifecycle exclusion must be object")
            icpn = item.get("icpn"); status = item.get("marketing_status")
            req(isinstance(icpn, str) and icpn.startswith(base), f"{base}: foreign excluded identity")
            req(isinstance(status, str) and status.startswith("NRND"), f"{base}: unexpected lifecycle state")
            excluded.append(icpn)
        if base in EXPECTED_LIFECYCLE_ONLY:
            req(target.get("disposition") == "lifecycle_excluded" and not exact and non_active, f"{base}: lifecycle-only disposition drift")
            lifecycle_only.add(base)
        else:
            req(target.get("disposition") == "active_candidates" and exact and not non_active, f"{base}: Active disposition drift")
        for key in ("evidence_section_sha256", "rendered_dom_sha256"):
            req(re.fullmatch(r"[0-9a-f]{64}", str(target.get(key, ""))) is not None, f"{base}: invalid {key}")

    req(lifecycle_only == EXPECTED_LIFECYCLE_ONLY, "lifecycle-only target set drift")
    req(len(active) == len(set(active)) == 30, "Active exact identity count/uniqueness drift")
    req(len(excluded) == len(set(excluded)) == 8, "excluded identity count/uniqueness drift")
    req("STM32C071C8T6N" in active and "STM32C071C8U6N" in active, "C071 N commercial variants lost")
    req(baseline.get("source_unavailable") == [], "unexpected source-unavailable target")

    print("STM32 U0/C0/L1 retained accessibility evidence validation: PASS")
    print(json.dumps({"active_exact_icpns": len(active), "lifecycle_excluded_icpns": len(excluded), "lifecycle_only_bases": sorted(lifecycle_only), "selected_next_research_family": None}, indent=2, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

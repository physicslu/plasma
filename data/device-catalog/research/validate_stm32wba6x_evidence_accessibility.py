#!/usr/bin/env python3
"""Fail-closed validation for blocked STM32WBA6X official-ST accessibility evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from stm32wba6x_evidence_accessibility_probe import (
    EXPECTED_SERIES,
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    PROBE_ID,
    deterministic_targets,
    target_manifest,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE_DIR = HERE / "evidence" / "stm32wba6x-accessibility-live-2026-09-22"
TARGETS_PATH = EVIDENCE_DIR / "targets.json"
SUMMARY_PATH = EVIDENCE_DIR / "probe-summary.json"
PROVENANCE_PATH = EVIDENCE_DIR / "provenance.json"
GATE_PATH = HERE / "stm32wba6x-evidence-accessibility-gate.json"
PRODUCTION_PATH = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_BASES = (
    "STM32WBA62CG",
    "STM32WBA63CG",
    "STM32WBA64CG",
    "STM32WBA65CG",
    "STM32WBA6MOI",
)
EXPECTED_ACTIVE = {
    "STM32WBA62CG": ["STM32WBA62CGU6"],
    "STM32WBA63CG": ["STM32WBA63CGU6", "STM32WBA63CGU7"],
    "STM32WBA64CG": ["STM32WBA64CGU6", "STM32WBA64CGU7"],
    "STM32WBA65CG": ["STM32WBA65CGU6", "STM32WBA65CGU7"],
}
EXPECTED_BROWSER = "151.0.7922.34"
EXPECTED_SOURCE_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_SELECTION_SHA256 = "6243c80f97b2c159bc964935fc2f87371a596ee9f2d2e397e1c7ee9c3b6a178d"

def req(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit(message)

def load(path: Path) -> dict[str, Any]:
    req(path.is_file(), f"missing retained file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected object")
    return value

def validate() -> None:
    targets = load(TARGETS_PATH)
    summary = load(SUMMARY_PATH)
    provenance = load(PROVENANCE_PATH)
    gate = load(GATE_PATH)

    req(targets == target_manifest(deterministic_targets()), "target manifest is not deterministic replay")
    req(targets.get("probe_id") == PROBE_ID, "probe id drifted")
    req(targets.get("target_count") == 5, "target count drifted")
    req(targets.get("candidate_source_sha256") == EXPECTED_SOURCE_SHA256, "candidate source digest drifted")
    req(targets.get("selection_sha256") == EXPECTED_SELECTION_SHA256, "selection digest drifted")
    trows = targets.get("targets")
    req(isinstance(trows, list) and len(trows) == 5, "target list drifted")
    req(tuple(row.get("subfamily") for row in trows) == EXPECTED_SUBFAMILIES, "subfamily target order drifted")
    req(tuple(row.get("base_device") for row in trows) == EXPECTED_BASES, "representative Base Device order drifted")

    req(summary.get("probe_id") == PROBE_ID, "summary probe id drifted")
    req(summary.get("selected_wireless_frontier") == EXPECTED_SERIES, "summary series drifted")
    req(summary.get("target_config") == EXPECTED_TARGET_CONFIG, "summary target config drifted")
    req(summary.get("attempted_targets") == 5, "attempted target count drifted")
    req(summary.get("successful_targets") == 4, "successful target count drifted")
    req(summary.get("manual_review_targets") == 1, "manual review count drifted")
    req(summary.get("active_exact_icpns_observed_on_representative_pages") == 7, "Active observation count drifted")
    req(summary.get("excluded_non_active_part_numbers_observed") == 1, "excluded lifecycle count drifted")
    req(summary.get("bounded_probe_complete") is False, "blocked probe unexpectedly became complete")
    req(summary.get("official_st_evidence_accessible_for_all_subfamilies") is False, "all-subfamily accessibility unexpectedly opened")
    req(summary.get("status") == "blocked_manual_review", "blocked status drifted")
    req(summary.get("next_gate") is None, "blocked acquisition unexpectedly opened a next gate")

    claims = summary.get("claims")
    req(isinstance(claims, dict) and claims, "summary claims missing")
    req(all(value is False for value in claims.values()), "summary fail-closed claim escaped")
    req(claims.get("stm32wba6x_admission_ready") is False, "WBA6X admission unexpectedly ready")

    results = summary.get("results")
    req(isinstance(results, list) and len(results) == 5, "result list drifted")
    observed = {row.get("base_device"): row for row in results if isinstance(row, dict)}
    req(set(observed) == set(EXPECTED_BASES), "representative result set drifted")

    for base, exact in EXPECTED_ACTIVE.items():
        row = observed[base]
        req(row.get("acquisition_status") == "success", f"{base}: acquisition no longer successful")
        req(row.get("commercial_identity_status") == "verified_active", f"{base}: identity not verified Active")
        req(row.get("manual_intervention_required") is False, f"{base}: manual intervention opened")
        evidence = row.get("evidence")
        req(isinstance(evidence, dict), f"{base}: evidence missing")
        req(evidence.get("acquisition_transport") == BROWSER_TRANSPORT, f"{base}: transport drifted")
        req(evidence.get("base_device") == base, f"{base}: evidence identity mismatch")
        req(evidence.get("exact_icpns") == exact, f"{base}: Active exact identities drifted")
        retained = load(EVIDENCE_DIR / f"{base.lower()}.json")
        req(retained == evidence, f"{base}: standalone evidence differs from summary")

    excluded = observed["STM32WBA63CG"]["evidence"].get("excluded_non_active_part_numbers")
    req(isinstance(excluded, list) and len(excluded) == 1, "WBA63 exclusion count drifted")
    req(excluded[0].get("icpn") == "STM32WBA63CGU6TR", "WBA63 excluded identity drifted")
    req(str(excluded[0].get("marketing_status", "")).startswith("Proposal"), "WBA63 exclusion is no longer Proposal")

    blocked = observed["STM32WBA6MOI"]
    req(blocked.get("subfamily") == "STM32WBA6M", "blocked subfamily drifted")
    req(blocked.get("acquisition_status") == "failure", "WBA6M acquisition unexpectedly succeeded")
    req(blocked.get("commercial_identity_status") == "unverified", "WBA6M identity unexpectedly verified")
    req(blocked.get("manual_intervention_required") is True, "WBA6M manual review boundary closed")
    req(blocked.get("error_type") == "AcquisitionError", "WBA6M error type drifted")
    req(blocked.get("error") == "browser navigation returned HTTP 404", "WBA6M HTTP blocker drifted")
    req(blocked.get("source_url") == "https://www.st.com/en/microcontrollers-microprocessors/stm32wba6moi.html", "WBA6M source URL drifted")

    req(provenance.get("browser_version") == EXPECTED_BROWSER, "browser version drifted")
    req(provenance.get("candidate_source_sha256") == EXPECTED_SOURCE_SHA256, "provenance source digest drifted")
    req(provenance.get("selection_sha256") == EXPECTED_SELECTION_SHA256, "provenance selection digest drifted")
    req(provenance.get("acquisition_transport") == BROWSER_TRANSPORT, "provenance transport drifted")

    req(gate.get("gate_id") == "stm32wba6x-bounded-official-st-evidence-accessibility-v1", "gate id drifted")
    req(gate.get("scope") == "research_only", "gate scope drifted")
    req(gate.get("decision") == "defer_frontier_pending_official_product_evidence", "gate decision drifted")
    req(gate.get("catalog_admission_ready") is False, "blocked WBA6X became admission-ready")
    req(gate.get("next_gate") == "stm32-post-wba6x-evidence-block-wireless-frontier-reselection-gate", "reselection gate drifted")
    live = gate.get("live_acquisition") or {}
    req(live.get("workflow_run_id") == 35694311469, "workflow run provenance drifted")
    req(live.get("executed_head") == "3982be122a43be062054f0be25f6f897e3b2a498", "executed head drifted")
    req(live.get("artifact_id") == 10680295411, "artifact id drifted")
    req(live.get("artifact_zip_sha256") == "7f5db9ce0fceecd670cdcefc41f491aa56328ae8aaf5f198082a01254474b317", "artifact digest drifted")
    req(all(value is False for value in (gate.get("claims") or {}).values()), "gate fail-closed claim escaped")

    production = load(PRODUCTION_PATH)
    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(source.get("row_count", 0)) for source in sources) == 2554, "Production exact ICPN count changed")
    req(len(sources) == 20, "Production family count changed")
    req(all(source.get("family") != "STM32WBA6X" for source in sources), "blocked WBA6X leaked into Production")

def main() -> int:
    validate()
    print("STM32WBA6X official-ST evidence accessibility: BLOCKED (validated fail-closed)")
    print("targets=5 success=4 manual_review=1 active_observed=7 excluded_proposal=1")
    print("blocker=STM32WBA6MOI HTTP 404")
    print("Production unchanged at 2554 / 20; next=reselection")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

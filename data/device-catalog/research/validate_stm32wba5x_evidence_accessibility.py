#!/usr/bin/env python3
"""Fail-closed validation for blocked STM32WBA5X official-ST accessibility evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from stm32wba5x_evidence_accessibility_probe import (
    EXPECTED_SERIES,
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    PROBE_ID,
    deterministic_targets,
    target_manifest,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE_DIR = HERE / "evidence" / "stm32wba5x-accessibility-live-2026-09-23"
TARGETS_PATH = EVIDENCE_DIR / "targets.json"
SUMMARY_PATH = EVIDENCE_DIR / "probe-summary.json"
PROVENANCE_PATH = EVIDENCE_DIR / "provenance.json"
GATE_PATH = HERE / "stm32wba5x-evidence-accessibility-gate.json"
PRODUCTION_PATH = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_BASES = (
    "STM32WBA50KE",
    "STM32WBA52CE",
    "STM32WBA54CE",
    "STM32WBA55CE",
    "STM32WBA5MMG",
)
EXPECTED_ACTIVE = {
    "STM32WBA52CE": ["STM32WBA52CEU6", "STM32WBA52CEU6TR"],
    "STM32WBA54CE": ["STM32WBA54CEU6", "STM32WBA54CEU7", "STM32WBA54CEU7TR"],
    "STM32WBA55CE": ["STM32WBA55CEU6", "STM32WBA55CEU6TR", "STM32WBA55CEU7"],
    "STM32WBA5MMG": ["STM32WBA5MMGH6TR"],
}
EXPECTED_BROWSER = "151.0.7922.34"
EXPECTED_SOURCE_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_SELECTION_SHA256 = "6cc5a67f3bac67ee6633c206620af487a65301214b60dd62e35dfef48c395b43"

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
    req(summary.get("active_exact_icpns_observed_on_representative_pages") == 9, "Active observation count drifted")
    req(summary.get("excluded_non_active_part_numbers_observed") == 0, "excluded lifecycle count drifted")
    req(summary.get("bounded_probe_complete") is False, "blocked probe unexpectedly became complete")
    req(summary.get("official_st_evidence_accessible_for_all_subfamilies") is False, "all-subfamily accessibility unexpectedly opened")
    req(summary.get("status") == "blocked_manual_review", "blocked status drifted")
    req(summary.get("next_gate") is None, "blocked acquisition unexpectedly opened a next gate")

    claims = summary.get("claims")
    req(isinstance(claims, dict) and claims, "summary claims missing")
    req(all(value is False for value in claims.values()), "summary fail-closed claim escaped")
    req(claims.get("stm32wba5x_admission_ready") is False, "WBA6X admission unexpectedly ready")

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

    for base in EXPECTED_ACTIVE:
        excluded = observed[base]["evidence"].get("excluded_non_active_part_numbers")
        req(excluded == [], f"{base}: unexpected non-Active lifecycle exclusion")

    blocked = observed["STM32WBA50KE"]
    req(blocked.get("subfamily") == "STM32WBA50", "blocked subfamily drifted")
    req(blocked.get("acquisition_status") == "failure", "WBA50 acquisition unexpectedly succeeded")
    req(blocked.get("commercial_identity_status") == "unverified", "WBA50 identity unexpectedly verified")
    req(blocked.get("manual_intervention_required") is True, "WBA50 manual review boundary closed")
    req(blocked.get("error_type") == "AcquisitionError", "WBA50 error type drifted")
    req(blocked.get("error") == "browser navigation returned HTTP 404", "WBA50 HTTP blocker drifted")
    req(blocked.get("source_url") == "https://www.st.com/en/microcontrollers-microprocessors/stm32wba50ke.html", "WBA50 source URL drifted")

    req(provenance.get("browser_version") == EXPECTED_BROWSER, "browser version drifted")
    req(provenance.get("candidate_source_sha256") == EXPECTED_SOURCE_SHA256, "provenance source digest drifted")
    req(provenance.get("selection_sha256") == EXPECTED_SELECTION_SHA256, "provenance selection digest drifted")
    req(provenance.get("acquisition_transport") == BROWSER_TRANSPORT, "provenance transport drifted")

    req(gate.get("gate_id") == "stm32wba5x-bounded-official-st-evidence-accessibility-v1", "gate id drifted")
    req(gate.get("scope") == "research_only", "gate scope drifted")
    req(gate.get("decision") == "defer_frontier_pending_official_product_evidence", "gate decision drifted")
    req(gate.get("catalog_admission_ready") is False, "blocked WBA6X became admission-ready")
    req(gate.get("next_gate") == "stm32-post-wba5x-evidence-block-wireless-frontier-reselection-gate", "reselection gate drifted")
    live = gate.get("live_acquisition") or {}
    req(live.get("workflow_run_id") == 35803914407, "workflow run provenance drifted")
    req(live.get("executed_head") == "0ddc6143360a254d1d3d2e22cdbf57b5329c1002", "executed head drifted")
    req(live.get("artifact_id") == 10726794785, "artifact id drifted")
    req(live.get("artifact_zip_sha256") == "bb1c69502581bfe4a992053b61b2ae3795a1a1fb572eaf98e7032528fc429b9a", "artifact digest drifted")
    req(all(value is False for value in (gate.get("claims") or {}).values()), "gate fail-closed claim escaped")

    production = load(PRODUCTION_PATH)
    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(source.get("row_count", 0)) for source in sources) == 2604, "Production exact ICPN count changed")
    req(len(sources) == 21, "Production family count changed")
    req(all(source.get("family") != "STM32WBA5X" for source in sources), "blocked WBA6X leaked into Production")

def main() -> int:
    validate()
    print("STM32WBA5X official-ST evidence accessibility: BLOCKED (validated fail-closed)")
    print("targets=5 success=4 manual_review=1 active_observed=9 excluded_non_active=0")
    print("blocker=STM32WBA50KE HTTP 404")
    print("Production unchanged at 2604 / 21; next=reselection")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

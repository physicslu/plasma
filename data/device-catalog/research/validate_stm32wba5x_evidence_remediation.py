#!/usr/bin/env python3
"""Validate successful STM32WBA5X official-ST evidence remediation."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from stm32wba5x_evidence_remediation_probe import (
    EXPECTED_SERIES,
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    PROBE_ID,
    deterministic_targets,
    target_manifest,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE_DIR = HERE / "evidence" / "stm32wba5x-remediation-live-2026-09-23"
TARGETS_PATH = EVIDENCE_DIR / "targets.json"
SUMMARY_PATH = EVIDENCE_DIR / "probe-summary.json"
PROVENANCE_PATH = EVIDENCE_DIR / "provenance.json"
GATE_PATH = HERE / "stm32wba5x-evidence-remediation-gate.json"
PRODUCTION_PATH = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_BASES = (
    "STM32WBA50KG",
    "STM32WBA52CE",
    "STM32WBA54CE",
    "STM32WBA55CE",
    "STM32WBA5MMG",
)
EXPECTED_ACTIVE = {
    "STM32WBA50KG": ["STM32WBA50KGU6", "STM32WBA50KGU6TR"],
    "STM32WBA52CE": ["STM32WBA52CEU6", "STM32WBA52CEU6TR"],
    "STM32WBA54CE": ["STM32WBA54CEU6", "STM32WBA54CEU7", "STM32WBA54CEU7TR"],
    "STM32WBA55CE": ["STM32WBA55CEU6", "STM32WBA55CEU6TR", "STM32WBA55CEU7"],
    "STM32WBA5MMG": ["STM32WBA5MMGH6TR"],
}
EXPECTED_BROWSER = "151.0.7922.34"
EXPECTED_SOURCE_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_SELECTION_SHA256 = "6cc5a67f3bac67ee6633c206620af487a65301214b60dd62e35dfef48c395b43"
EXPECTED_SELECTION_BLOB = "849488b36d398a7e8f8da83b3aa93fbe320f8dc3"
EXPECTED_BLOCKED_GATE_BLOB = "26c0d55a4d0e1f85025134b0c9bda38049b5b3a4"
EXPECTED_EXHAUSTION_BLOB = "3345ead0c1f5fb0b103fc8fb2da84c24533b5a67"

def req(ok: bool, message: str) -> None:
    if not ok:
        raise SystemExit(message)

def load(path: Path) -> dict[str, Any]:
    req(path.is_file(), f"missing retained file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected object")
    return value

def main() -> int:
    targets = load(TARGETS_PATH)
    summary = load(SUMMARY_PATH)
    provenance = load(PROVENANCE_PATH)
    gate = load(GATE_PATH)

    req(targets == target_manifest(deterministic_targets()), "target manifest is not deterministic remediation replay")
    req(targets.get("probe_id") == PROBE_ID, "probe id drifted")
    req(targets.get("target_count") == 5, "target count drifted")
    req(targets.get("candidate_source_sha256") == EXPECTED_SOURCE_SHA256, "candidate source digest drifted")
    req(targets.get("selection_sha256") == EXPECTED_SELECTION_SHA256, "selection digest drifted")
    req(targets.get("selection_git_blob_sha") == EXPECTED_SELECTION_BLOB, "selection blob drifted")
    req(targets.get("blocked_gate_git_blob_sha") == EXPECTED_BLOCKED_GATE_BLOB, "blocked gate blob drifted")
    req(targets.get("wireless_exhaustion_git_blob_sha") == EXPECTED_EXHAUSTION_BLOB, "exhaustion blob drifted")
    trows = targets.get("targets")
    req(isinstance(trows, list) and len(trows) == 5, "target list drifted")
    req(tuple(row.get("subfamily") for row in trows) == EXPECTED_SUBFAMILIES, "subfamily order drifted")
    req(tuple(row.get("base_device") for row in trows) == EXPECTED_BASES, "representative Base Devices drifted")
    req("retained STM32WBA50KE official-ST HTTP 404 blocker" in str(trows[0].get("selection_reason")), "WBA50 remediation reason drifted")

    req(summary.get("probe_id") == PROBE_ID, "summary probe id drifted")
    req(summary.get("selected_wireless_frontier") == EXPECTED_SERIES, "summary series drifted")
    req(summary.get("target_config") == EXPECTED_TARGET_CONFIG, "summary target config drifted")
    req(summary.get("attempted_targets") == 5, "attempted target count drifted")
    req(summary.get("successful_targets") == 5, "not all remediation targets succeeded")
    req(summary.get("manual_review_targets") == 0, "manual review remains after remediation")
    req(summary.get("active_exact_icpns_observed_on_representative_pages") == 11, "Active observation count drifted")
    req(summary.get("excluded_non_active_part_numbers_observed") == 0, "lifecycle exclusion count drifted")
    req(summary.get("bounded_probe_complete") is True, "remediation probe incomplete")
    req(summary.get("official_st_evidence_accessible_for_all_subfamilies") is True, "all-subfamily accessibility not restored")
    req(summary.get("status") == "accessible", "remediation status drifted")
    req(summary.get("next_gate") == "stm32wba5x-bounded-exact-icpn-discovery-gate", "exact discovery gate not opened")

    claims = summary.get("claims")
    req(isinstance(claims, dict) and claims and all(value is False for value in claims.values()), "summary fail-closed claim escaped")

    results = summary.get("results")
    req(isinstance(results, list) and len(results) == 5, "result list drifted")
    observed = {row.get("base_device"): row for row in results if isinstance(row, dict)}
    req(set(observed) == set(EXPECTED_BASES), "representative result set drifted")
    for base, exact in EXPECTED_ACTIVE.items():
        row = observed[base]
        req(row.get("acquisition_status") == "success", f"{base}: acquisition no longer successful")
        req(row.get("commercial_identity_status") == "verified_active", f"{base}: identity not verified Active")
        req(row.get("manual_intervention_required") is False, f"{base}: manual intervention reopened")
        evidence = row.get("evidence")
        req(isinstance(evidence, dict), f"{base}: evidence missing")
        req(evidence.get("acquisition_transport") == BROWSER_TRANSPORT, f"{base}: transport drifted")
        req(evidence.get("exact_icpns") == exact, f"{base}: Active exact identities drifted")
        req(evidence.get("excluded_non_active_part_numbers") == [], f"{base}: unexpected lifecycle exclusion")
        req(load(EVIDENCE_DIR / f"{base.lower()}.json") == evidence, f"{base}: retained evidence differs from summary")

    req(provenance.get("browser_version") == EXPECTED_BROWSER, "browser version drifted")
    req(provenance.get("candidate_source_sha256") == EXPECTED_SOURCE_SHA256, "provenance source digest drifted")
    req(provenance.get("selection_sha256") == EXPECTED_SELECTION_SHA256, "provenance selection digest drifted")
    req(provenance.get("selection_git_blob_sha") == EXPECTED_SELECTION_BLOB, "provenance selection blob drifted")
    req(provenance.get("blocked_gate_git_blob_sha") == EXPECTED_BLOCKED_GATE_BLOB, "provenance blocked gate blob drifted")
    req(provenance.get("wireless_exhaustion_git_blob_sha") == EXPECTED_EXHAUSTION_BLOB, "provenance exhaustion blob drifted")
    req(provenance.get("acquisition_transport") == BROWSER_TRANSPORT, "provenance transport drifted")

    req(gate.get("gate_id") == "stm32wba5x-bounded-official-st-evidence-remediation-v1", "gate id drifted")
    req(gate.get("remediation_of") == "stm32wba5x-bounded-official-st-evidence-accessibility-v1", "historical blocker binding drifted")
    req(gate.get("evidence_accessibility_ready") is True, "evidence accessibility not restored")
    req(gate.get("catalog_admission_ready") is False, "remediation prematurely admitted catalog")
    req(gate.get("decision") == "remediation_success_exact_discovery_reopened", "remediation decision drifted")
    req(gate.get("next_gate") == "stm32wba5x-bounded-exact-icpn-discovery-gate", "gate next step drifted")
    live = gate.get("live_acquisition") or {}
    req(live.get("workflow_run_id") == 35814598613, "workflow run provenance drifted")
    req(live.get("executed_head") == "063069425ebf4710c019b8a171476636c6443533", "executed head drifted")
    req(live.get("artifact_id") == 10731375509, "artifact id drifted")
    req(live.get("artifact_zip_sha256") == "dc4d244c3e86def6790fa0f7ad08b21b89a826204d1c4abf7a4212935d568d15", "artifact digest drifted")
    req(all(value is False for value in (gate.get("claims") or {}).values()), "gate fail-closed claim escaped")

    production = load(PRODUCTION_PATH)
    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(source.get("row_count", 0)) for source in sources) == 2604, "Production exact ICPN count changed")
    req(len(sources) == 21, "Production family count changed")
    req(all(source.get("family") != "STM32WBA5X" for source in sources), "WBA5X leaked into Production")

    print("STM32WBA5X official-ST evidence remediation: PASS")
    print("targets=5 success=5 manual_review=0 active_observed=11 excluded_non_active=0")
    print("alternate=STM32WBA50KG exact_discovery_gate=open")
    print("Production unchanged at 2604 / 21")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

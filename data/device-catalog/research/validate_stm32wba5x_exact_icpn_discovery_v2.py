#!/usr/bin/env python3
"""Fail-closed validator for retained STM32WBA5X exact ICPN discovery v2."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from stm32wba5x_exact_icpn_discovery_v2 import (
    DISCOVERY_ID,
    EXPECTED_BASE_DEVICE_COUNT,
    EXPECTED_BASES,
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    EXPECTED_SERIES,
    deterministic_targets,
    target_manifest,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE = HERE / "evidence" / "stm32wba5x-exact-icpn-live-2026-09-23"
TARGETS = EVIDENCE / "targets.json"
SUMMARY = EVIDENCE / "discovery-summary.json"
EXACT = EVIDENCE / "exact-icpns.json"
PROVENANCE = EVIDENCE / "provenance.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_COUNT = 40
EXPECTED_EXCLUDED = 0
EXPECTED_SHA256 = "de7b479493688ad5ac4417682f384da64af391850e876b45a649823fbe395485"
EXPECTED_NEXT = "stm32wba5x-bounded-exact-icpn-admission-readiness-gate"
EXPECTED_PRODUCTION_COUNT = 2604
EXPECTED_PRODUCTION_FAMILIES = 21
EXPECTED_RUN_ID = 35830764037
EXPECTED_EXECUTED_SHA = "392b0d796c33ad659527eb16a378c7ac9817971b"
EXPECTED_BROWSER_VERSION = "151.0.7922.34"
EXPECTED_ARTIFACT_ID = 10737358304
EXPECTED_ARTIFACT_SHA256 = "bd1f5f6fe74662951d062a4b233b55e5bb2267820c3fa5b3e5de4422cb306e57"

EXPECTED_ACTIVE_COUNTS = {
    "STM32WBA50KG": 2,
    "STM32WBA52CE": 2,
    "STM32WBA52CG": 3,
    "STM32WBA52KE": 1,
    "STM32WBA52KG": 1,
    "STM32WBA54CE": 3,
    "STM32WBA54CG": 4,
    "STM32WBA54KE": 4,
    "STM32WBA54KG": 4,
    "STM32WBA55CE": 3,
    "STM32WBA55CG": 4,
    "STM32WBA55HG": 2,
    "STM32WBA55UE": 2,
    "STM32WBA55UG": 4,
    "STM32WBA5MMG": 1,
}

FALSE_CLAIMS = {
    "production_write_authorized",
    "icpn_admission_authorized",
    "programming_algorithm_equivalence_claimed",
    "runtime_programming_support_claimed",
    "wireless_radio_operation_authorized",
    "wireless_security_operation_authorized",
    "security_mutation_authorized",
    "debug_attach_supported",
    "target_execution_authorized",
    "physical_validation_claimed",
    "hil_required_for_catalog_admission",
    "remaining_wireless_families_rejected",
    "stm32wba6x_rejected",
    "stm32wba5x_admission_ready",
    "cmsis_bridge_authorizes_production_route",
}

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise SystemExit(msg)

def load(path: Path) -> dict[str, Any]:
    req(path.is_file(), f"missing retained file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected JSON object")
    return value

def validate_documents(
    targets: dict[str, Any],
    summary: dict[str, Any],
    exact_snapshot: dict[str, Any],
    provenance: dict[str, Any],
    production: dict[str, Any],
) -> None:
    expected_manifest = target_manifest(deterministic_targets())
    req(targets == expected_manifest, "retained target manifest is not deterministic replay")
    req(targets.get("discovery_id") == DISCOVERY_ID, "target discovery id drifted")
    req(targets.get("selected_wireless_frontier") == EXPECTED_SERIES, "target frontier drifted")
    req(targets.get("base_device_count") == EXPECTED_BASE_DEVICE_COUNT == 15, "target Base Device count drifted")
    req(targets.get("target_config") == EXPECTED_TARGET_CONFIG, "target config drifted")
    manifest_targets = targets.get("targets")
    req(isinstance(manifest_targets, list) and len(manifest_targets) == 15, "target list malformed")
    req(tuple(item.get("base_device") for item in manifest_targets) == EXPECTED_BASES, "target Base Device order/coverage drifted")
    req("STM32WBA55HE" not in EXPECTED_BASES, "stale STM32WBA55HE target reopened")
    req({item.get("subfamily") for item in manifest_targets} == set(EXPECTED_SUBFAMILIES), "target subfamily coverage drifted")

    req(summary.get("discovery_id") == DISCOVERY_ID, "summary discovery id drifted")
    req(summary.get("selected_wireless_frontier") == EXPECTED_SERIES, "summary frontier drifted")
    req(summary.get("target_config") == EXPECTED_TARGET_CONFIG, "summary target config drifted")
    req(summary.get("base_device_count") == 15, "summary Base Device count drifted")
    req(summary.get("attempted_targets") == 15, "attempted target count drifted")
    req(summary.get("successful_targets") == 15, "successful target count drifted")
    req(summary.get("manual_review_targets") == 0, "manual review opened")
    req(summary.get("active_exact_icpn_count") == EXPECTED_COUNT, "Active exact ICPN count drifted")
    req(summary.get("excluded_non_active_part_number_count") == 0, "excluded lifecycle count drifted")
    req(summary.get("excluded_non_active_part_numbers") == [], "excluded identity set drifted")
    req(summary.get("active_exact_icpn_set_sha256") == EXPECTED_SHA256, "exact-set digest drifted")
    req(summary.get("bounded_exact_discovery_complete") is True, "bounded discovery incomplete")
    req(summary.get("status") == "discovered", "discovery status drifted")
    req(summary.get("next_gate") == EXPECTED_NEXT, "next gate drifted")
    req(summary.get("browser_version") == EXPECTED_BROWSER_VERSION, "browser version drifted")

    claims = summary.get("claims")
    req(isinstance(claims, dict), "claims missing")
    req(claims.get("exact_icpn_discovery_completed") is True, "discovery completion claim must be true")
    for key in FALSE_CLAIMS:
        req(claims.get(key) is False, f"{key} must remain false")
    req(set(claims) == FALSE_CLAIMS | {"exact_icpn_discovery_completed"}, "claims surface drifted")

    exact = summary.get("active_exact_icpns")
    req(isinstance(exact, list) and len(exact) == EXPECTED_COUNT, "Active exact set malformed")
    req(exact == sorted(set(exact)), "Active exact set is not sorted unique")
    digest = hashlib.sha256(("\n".join(exact) + "\n").encode("utf-8")).hexdigest()
    req(digest == EXPECTED_SHA256, "recomputed exact-set digest mismatch")

    req(exact_snapshot.get("discovery_id") == DISCOVERY_ID, "exact snapshot discovery id drifted")
    req(exact_snapshot.get("exact_icpn_count") == EXPECTED_COUNT, "exact snapshot count drifted")
    req(exact_snapshot.get("exact_icpn_set_sha256") == EXPECTED_SHA256, "exact snapshot digest drifted")
    req(exact_snapshot.get("exact_icpns") == exact, "exact snapshot differs from summary")

    results = summary.get("results")
    req(isinstance(results, list) and len(results) == 15, "result count drifted")
    req([item.get("base_device") for item in results] == list(EXPECTED_BASES), "result Base Device order drifted")
    active_owner: dict[str, str] = {}

    for item in results:
        req(isinstance(item, dict), "result entry is not an object")
        base = item.get("base_device")
        req(isinstance(base, str) and base in EXPECTED_ACTIVE_COUNTS, "unexpected Base Device")
        req(item.get("series") == EXPECTED_SERIES, f"{base}: series drifted")
        req(item.get("acquisition_status") == "success", f"{base}: acquisition failure retained")
        req(item.get("manual_intervention_required") is False, f"{base}: manual intervention retained")
        req(item.get("commercial_identity_status") == "verified_active", f"{base}: identity not verified Active")
        evidence = item.get("evidence")
        req(isinstance(evidence, dict), f"{base}: evidence missing")
        req(evidence.get("base_device") == base, f"{base}: evidence Base Device mismatch")
        req(evidence.get("acquisition_transport") == BROWSER_TRANSPORT, f"{base}: transport drifted")
        req(evidence.get("evidence_surface") == "quality_and_reliability_part_number", f"{base}: evidence surface drifted")
        active = evidence.get("exact_icpns")
        nonactive = evidence.get("excluded_non_active_part_numbers")
        req(isinstance(active, list) and len(active) == EXPECTED_ACTIVE_COUNTS[base], f"{base}: Active count drifted")
        req(nonactive == [], f"{base}: unexpected non-Active identities")
        req(item.get("active_exact_icpns") == active, f"{base}: result Active set differs from evidence")
        req(item.get("excluded_non_active_icpns") == [], f"{base}: result excluded set drifted")
        for icpn in active:
            req(isinstance(icpn, str) and icpn.startswith(base), f"{base}: foreign Active ICPN")
            req(icpn not in active_owner, f"{icpn}: duplicate Active identity")
            active_owner[icpn] = base
        req(load(EVIDENCE / f"{base.lower()}.json") == evidence, f"{base}: standalone evidence differs from summary")

    req(sorted(active_owner) == exact, "summary Active set differs from per-Base evidence")

    req(provenance.get("discovery_id") == DISCOVERY_ID, "provenance discovery id drifted")
    req(provenance.get("workflow_role") == "authoritative_exact_icpn_discovery", "workflow role drifted")
    req(provenance.get("source_repository") == "physicslu/plasma", "source repository drifted")
    req(provenance.get("executed_git_sha") == EXPECTED_EXECUTED_SHA, "authoritative executed SHA drifted")
    req(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "authoritative workflow run id drifted")
    req(provenance.get("workflow_run_attempt") == 1, "workflow run attempt drifted")
    req(provenance.get("acquisition_transport") == BROWSER_TRANSPORT, "provenance transport drifted")
    req(provenance.get("browser_version") == EXPECTED_BROWSER_VERSION, "provenance browser version drifted")
    req(provenance.get("candidate_source_sha256") == targets.get("candidate_source_sha256"), "candidate source digest mismatch")
    req(provenance.get("selection_sha256") == targets.get("selection_sha256"), "selection digest mismatch")
    req(provenance.get("accessibility_summary_sha256") == targets.get("accessibility_summary_sha256"), "accessibility digest mismatch")

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    req(sum(int(src.get("row_count", 0)) for src in sources if isinstance(src, dict)) == EXPECTED_PRODUCTION_COUNT, "Production exact count changed")
    req(len(sources) == EXPECTED_PRODUCTION_FAMILIES, "Production family count changed")
    req(all(not (isinstance(src, dict) and src.get("family") == "STM32WBA5X") for src in sources), "STM32WBA5X leaked into Production during research-only discovery")

def main() -> None:
    t, s, e, p, d = load(TARGETS), load(SUMMARY), load(EXACT), load(PROVENANCE), load(PRODUCTION)
    validate_documents(t, s, e, p, d)
    print(
        "STM32WBA5X exact ICPN discovery v2 validation: PASS "
        f"({EXPECTED_BASE_DEVICE_COUNT} Base Devices / {EXPECTED_COUNT} Active / 0 excluded)"
    )
    print(f"run={EXPECTED_RUN_ID} artifact={EXPECTED_ARTIFACT_ID} artifact_sha256={EXPECTED_ARTIFACT_SHA256}")

if __name__ == "__main__":
    main()

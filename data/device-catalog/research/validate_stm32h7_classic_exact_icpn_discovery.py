#!/usr/bin/env python3
"""Fail-closed validator for retained STM32H7-classic exact ICPN discovery."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from stm32h7_classic_exact_icpn_discovery import (
    DISCOVERY_ID,
    EXPECTED_BASE_DEVICE_COUNT,
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    deterministic_targets,
    target_manifest,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE = HERE / "evidence" / "stm32h7-classic-exact-icpn-live-2026-09-18"
TARGETS = EVIDENCE / "targets.json"
SUMMARY = EVIDENCE / "discovery-summary.json"
EXACT = EVIDENCE / "exact-icpns.json"
PROVENANCE = EVIDENCE / "provenance.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_COUNT = 191
EXPECTED_EXCLUDED = 19
EXPECTED_SHA256 = "7ac4feb19ef5a7c75d2eeaf3cc1334b89d28862aceb2702d59fecc71ae0dd6c7"
EXPECTED_NEXT = "stm32h7-classic-bounded-exact-icpn-admission-readiness-gate"
EXPECTED_PRODUCTION_COUNT = 2318
EXPECTED_SHARDS = 6
EXPECTED_RUN_ID = 35302905725
EXPECTED_EXECUTED_SHA = "e0d2dd1ad22ac47b793d46a712ca0e8c16869a87"

FALSE_CLAIMS = {
    "production_write_authorized",
    "icpn_admission_authorized",
    "programming_algorithm_equivalence_claimed",
    "runtime_programming_support_claimed",
    "security_mutation_authorized",
    "debug_attach_supported",
    "physical_validation_claimed",
    "hil_required_for_catalog_admission",
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
    req(targets.get("base_device_count") == EXPECTED_BASE_DEVICE_COUNT, "target Base Device count drifted")
    req(targets.get("target_config") == EXPECTED_TARGET_CONFIG, "target config drifted")

    manifest_targets = targets.get("targets")
    req(isinstance(manifest_targets, list) and len(manifest_targets) == EXPECTED_BASE_DEVICE_COUNT, "target list malformed")
    req(len({item.get("base_device") for item in manifest_targets if isinstance(item, dict)}) == EXPECTED_BASE_DEVICE_COUNT, "target Base Devices are not unique")
    req({item.get("subfamily") for item in manifest_targets if isinstance(item, dict)} == set(EXPECTED_SUBFAMILIES), "target subfamily coverage drifted")

    req(summary.get("discovery_id") == DISCOVERY_ID, "summary discovery id drifted")
    req(summary.get("selected_partition") == "STM32H7-classic", "partition drifted")
    req(summary.get("target_config") == EXPECTED_TARGET_CONFIG, "summary target config drifted")
    req(summary.get("base_device_count") == EXPECTED_BASE_DEVICE_COUNT, "summary Base Device count drifted")
    req(summary.get("attempted_targets") == EXPECTED_BASE_DEVICE_COUNT, "attempted target count drifted")
    req(summary.get("successful_targets") == EXPECTED_BASE_DEVICE_COUNT, "success target count drifted")
    req(summary.get("manual_review_targets") == 0, "manual review opened")
    req(summary.get("active_exact_icpn_count") == EXPECTED_COUNT, "Active exact ICPN count drifted")
    req(summary.get("excluded_non_active_part_number_count") == EXPECTED_EXCLUDED, "non-active exclusion count drifted")
    req(summary.get("active_exact_icpn_set_sha256") == EXPECTED_SHA256, "exact-set digest drifted")
    req(summary.get("bounded_exact_discovery_complete") is True, "bounded discovery incomplete")
    req(summary.get("status") == "discovered", "discovery status drifted")
    req(summary.get("next_gate") == EXPECTED_NEXT, "next gate drifted or bypassed")

    parallel = summary.get("parallel_shards")
    req(isinstance(parallel, dict), "parallel shard provenance missing")
    req(parallel.get("count") == EXPECTED_SHARDS, "shard count drifted")
    req(parallel.get("indices") == list(range(EXPECTED_SHARDS)), "shard index coverage drifted")
    req(parallel.get("base_device_partition") == "deterministic target index modulo shard_count", "shard partition rule drifted")
    req(parallel.get("base_device_is_atomic") is True, "Base Device atomicity drifted")

    browsers = summary.get("browser_shards")
    req(isinstance(browsers, list) and len(browsers) == EXPECTED_SHARDS, "browser shard provenance drifted")
    req([item.get("shard_index") for item in browsers if isinstance(item, dict)] == list(range(EXPECTED_SHARDS)), "browser shard indices drifted")
    req(sum(int(item.get("base_device_count", 0)) for item in browsers if isinstance(item, dict)) == EXPECTED_BASE_DEVICE_COUNT, "browser shard target total drifted")
    req(all(isinstance(item.get("browser_version"), str) and item["browser_version"].strip() for item in browsers if isinstance(item, dict)), "browser version missing")

    claims = summary.get("claims")
    req(isinstance(claims, dict), "claims missing")
    req(claims.get("exact_icpn_discovery_completed") is True, "discovery completion claim must be true")
    for key in FALSE_CLAIMS:
        req(claims.get(key) is False, f"{key} must remain false")
    req(set(claims) == FALSE_CLAIMS | {"exact_icpn_discovery_completed"}, "claims surface drifted")

    exact = summary.get("active_exact_icpns")
    excluded = summary.get("excluded_non_active_part_numbers")
    req(isinstance(exact, list) and len(exact) == EXPECTED_COUNT, "Active exact set malformed")
    req(exact == sorted(set(exact)), "Active exact set not sorted unique")
    req(isinstance(excluded, list) and len(excluded) == EXPECTED_EXCLUDED, "excluded set malformed")
    req(excluded == sorted(set(excluded)), "excluded set not sorted unique")
    req(not (set(exact) & set(excluded)), "Active/excluded exact identity overlap")
    digest = hashlib.sha256(("\n".join(exact) + "\n").encode("utf-8")).hexdigest()
    req(digest == EXPECTED_SHA256, "recomputed exact-set digest mismatch")

    req(exact_snapshot.get("discovery_id") == DISCOVERY_ID, "exact snapshot discovery id drifted")
    req(exact_snapshot.get("exact_icpn_count") == EXPECTED_COUNT, "exact snapshot count drifted")
    req(exact_snapshot.get("exact_icpn_set_sha256") == EXPECTED_SHA256, "exact snapshot digest drifted")
    req(exact_snapshot.get("exact_icpns") == exact, "exact snapshot differs from summary")

    results = summary.get("results")
    req(isinstance(results, list) and len(results) == EXPECTED_BASE_DEVICE_COUNT, "result count drifted")
    target_bases = [item.get("base_device") for item in manifest_targets if isinstance(item, dict)]
    result_bases = [item.get("base_device") for item in results if isinstance(item, dict)]
    req(result_bases == target_bases, "result Base Device order/coverage drifted")

    active_owner: dict[str, str] = {}
    excluded_owner: dict[str, str] = {}
    for item in results:
        req(isinstance(item, dict), "result entry is not an object")
        base = item.get("base_device")
        req(isinstance(base, str), "result Base Device missing")
        req(item.get("acquisition_status") == "success", f"{base}: acquisition failure retained")
        req(item.get("manual_intervention_required") is False, f"{base}: manual intervention retained")
        req(item.get("commercial_identity_status") in {"verified_active", "verified_non_active_only"}, f"{base}: identity disposition unverified")
        evidence = item.get("evidence")
        req(isinstance(evidence, dict), f"{base}: evidence missing")
        req(evidence.get("base_device") == base, f"{base}: evidence Base Device mismatch")
        req(evidence.get("acquisition_transport") == BROWSER_TRANSPORT, f"{base}: acquisition transport drifted")
        req(evidence.get("source_url") == item.get("source_url"), f"{base}: source URL mismatch")
        active = evidence.get("exact_icpns")
        nonactive = evidence.get("excluded_non_active_part_numbers")
        req(isinstance(active, list) and isinstance(nonactive, list), f"{base}: identity lists missing")
        req(active or nonactive, f"{base}: no exact identity disposition")
        req(item.get("active_exact_icpns") == active, f"{base}: result Active set differs from evidence")
        req(item.get("excluded_non_active_icpns") == [row.get("icpn") for row in nonactive if isinstance(row, dict)], f"{base}: result exclusion set differs from evidence")

        for icpn in active:
            req(isinstance(icpn, str) and icpn.startswith(base), f"{base}: foreign Active ICPN")
            req(icpn not in active_owner, f"{icpn}: duplicate Active identity")
            active_owner[icpn] = base
        for row in nonactive:
            req(isinstance(row, dict), f"{base}: malformed lifecycle exclusion")
            icpn = row.get("icpn")
            status = row.get("marketing_status")
            req(isinstance(icpn, str) and icpn.startswith(base), f"{base}: foreign excluded ICPN")
            req(isinstance(status, str) and status.strip(), f"{base}: missing marketing status")
            req(icpn not in excluded_owner, f"{icpn}: duplicate excluded identity")
            excluded_owner[icpn] = base

        retained = load(EVIDENCE / f"{base.lower()}.json")
        req(retained == evidence, f"{base}: standalone evidence differs from summary")

    req(sorted(active_owner) == exact, "summary Active set differs from per-Base evidence")
    req(sorted(excluded_owner) == excluded, "summary excluded set differs from per-Base evidence")

    req(provenance.get("discovery_id") == DISCOVERY_ID, "provenance discovery id drifted")
    req(provenance.get("workflow_role") == "authoritative_sharded_exact_icpn_discovery", "workflow role drifted")
    req(provenance.get("source_repository") == "physicslu/plasma", "source repository drifted")
    req(provenance.get("executed_git_sha") == EXPECTED_EXECUTED_SHA, "authoritative executed SHA drifted")
    req(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "authoritative workflow run id drifted")
    req(provenance.get("workflow_run_attempt") == 1, "workflow run attempt drifted")
    req(provenance.get("acquisition_transport") == BROWSER_TRANSPORT, "provenance transport drifted")
    req(provenance.get("shard_count") == EXPECTED_SHARDS, "provenance shard count drifted")
    req(provenance.get("partition_source_sha256") == targets.get("partition_source_sha256"), "partition source digest mismatch")
    req(provenance.get("selection_sha256") == targets.get("selection_sha256"), "selection digest mismatch")
    req(provenance.get("accessibility_summary_sha256") == targets.get("accessibility_summary_sha256"), "accessibility digest mismatch")

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    prod_count = sum(int(src.get("row_count", 0)) for src in sources if isinstance(src, dict))
    req(prod_count == EXPECTED_PRODUCTION_COUNT, "Production Catalog changed during research-only discovery")
    req(all("stm32h7-classic" not in str(src).casefold() for src in sources), "STM32H7-classic leaked into Production")


def expect_reject(name: str, mutator) -> None:
    t = load(TARGETS)
    s = load(SUMMARY)
    e = load(EXACT)
    p = load(PROVENANCE)
    prod = load(PRODUCTION)
    mutator(t, s, e, p, prod)
    try:
        validate_documents(t, s, e, p, prod)
    except SystemExit:
        return
    raise SystemExit(f"negative control accepted: {name}")


def main() -> None:
    t = load(TARGETS)
    s = load(SUMMARY)
    e = load(EXACT)
    p = load(PROVENANCE)
    prod = load(PRODUCTION)
    validate_documents(t, s, e, p, prod)

    controls = [
        ("Production authorization", lambda t,s,e,p,d: s["claims"].__setitem__("production_write_authorized", True)),
        ("ICPN admission authorization", lambda t,s,e,p,d: s["claims"].__setitem__("icpn_admission_authorized", True)),
        ("runtime programming support", lambda t,s,e,p,d: s["claims"].__setitem__("runtime_programming_support_claimed", True)),
        ("programming equivalence", lambda t,s,e,p,d: s["claims"].__setitem__("programming_algorithm_equivalence_claimed", True)),
        ("security mutation", lambda t,s,e,p,d: s["claims"].__setitem__("security_mutation_authorized", True)),
        ("debug attach", lambda t,s,e,p,d: s["claims"].__setitem__("debug_attach_supported", True)),
        ("HIL coupling", lambda t,s,e,p,d: s["claims"].__setitem__("hil_required_for_catalog_admission", True)),
        ("manual review", lambda t,s,e,p,d: s.__setitem__("manual_review_targets", 1)),
        ("skip admission-readiness gate", lambda t,s,e,p,d: s.__setitem__("next_gate", "stm32h7-classic-production-publication-gate")),
        ("exact-set mutation", lambda t,s,e,p,d: s["active_exact_icpns"].pop()),
        ("nondeterministic targets", lambda t,s,e,p,d: t["targets"].reverse()),
        ("incomplete shard coverage", lambda t,s,e,p,d: s["parallel_shards"].__setitem__("indices", [0,1,2,3,4])),
        ("wrong authoritative SHA", lambda t,s,e,p,d: p.__setitem__("executed_git_sha", "0"*40)),
        ("Production count mutation", lambda t,s,e,p,d: d["sources"][0].__setitem__("row_count", int(d["sources"][0]["row_count"])+1)),
    ]
    for name, mutate in controls:
        expect_reject(name, mutate)

    print(
        "STM32H7-classic exact ICPN discovery validation: PASS "
        f"({EXPECTED_BASE_DEVICE_COUNT} Base Devices / {EXPECTED_COUNT} Active / "
        f"{EXPECTED_EXCLUDED} excluded / {len(controls)} negative controls)"
    )


if __name__ == "__main__":
    main()

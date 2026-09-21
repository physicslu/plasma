#!/usr/bin/env python3
"""Fail-closed validator for retained STM32WLX exact ICPN discovery."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from stm32wlx_exact_icpn_discovery import (
    DISCOVERY_ID,
    EXPECTED_BASE_DEVICE_COUNT,
    EXPECTED_BASES,
    EXPECTED_NON_PREFIX_BASE,
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    EXPECTED_SERIES,
    deterministic_targets,
    target_manifest,
)

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
EVIDENCE = HERE / "evidence" / "stm32wlx-exact-icpn-live-2026-09-21"
TARGETS = EVIDENCE / "targets.json"
SUMMARY = EVIDENCE / "discovery-summary.json"
EXACT = EVIDENCE / "exact-icpns.json"
PROVENANCE = EVIDENCE / "provenance.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_COUNT = 31
EXPECTED_EXCLUDED = 2
EXPECTED_EXCLUDED_IDENTITIES = ["STM32WLE4CCU7", "STM32WLE4JCI7"]
EXPECTED_SHA256 = "928a6d292a524d7fbf1834af17446e2ad801c09c7daacc693b18d24020a7b7c2"
EXPECTED_NEXT = "stm32wlx-bounded-exact-icpn-admission-readiness-gate"
EXPECTED_PRODUCTION_COUNT = 2523
EXPECTED_PRODUCTION_FAMILIES = 19
EXPECTED_RUN_ID = 35566559922
EXPECTED_EXECUTED_SHA = "43f1b14be4bb12174a689dfd43cb74b2c28ad442"
EXPECTED_BROWSER_VERSION = "151.0.7922.34"

EXPECTED_ACTIVE_COUNTS = {
    "STM32WL54CC": 2,
    "STM32WL54JC": 2,
    "STM32WL55CC": 3,
    "STM32WL55JC": 3,
    "STM32WL5MOC": 2,
    "STM32WLE4C8": 2,
    "STM32WLE4CB": 1,
    "STM32WLE4CC": 2,
    "STM32WLE4J8": 1,
    "STM32WLE4JB": 1,
    "STM32WLE4JC": 1,
    "STM32WLE5C8": 1,
    "STM32WLE5CB": 2,
    "STM32WLE5CC": 2,
    "STM32WLE5J8": 1,
    "STM32WLE5JB": 2,
    "STM32WLE5JC": 3,
}
EXPECTED_EXCLUDED_BY_BASE = {
    "STM32WLE4CC": ["STM32WLE4CCU7"],
    "STM32WLE4JC": ["STM32WLE4JCI7"],
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
    "stm32wlx_admission_ready",
    "wl5m_alias_normalized",
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
    req(targets.get("selected_wireless_frontier") == EXPECTED_SERIES, "target wireless frontier drifted")
    req(targets.get("base_device_count") == EXPECTED_BASE_DEVICE_COUNT, "target Base Device count drifted")
    req(targets.get("target_config") == EXPECTED_TARGET_CONFIG, "target config drifted")

    anomalies = targets.get("known_non_prefix_ordering_targets")
    req(isinstance(anomalies, list) and len(anomalies) == 1, "WL5M anomaly manifest drifted")
    anomaly = anomalies[0]
    req(anomaly.get("frozen_subfamily") == "STM32WL55", "WL5M frozen subfamily drifted")
    req(anomaly.get("base_device") == EXPECTED_NON_PREFIX_BASE, "WL5M Base Device drifted")
    req(anomaly.get("alias_normalized") is False, "WL5M alias normalization unexpectedly opened")
    req(anomaly.get("included_in_exact_discovery") is True, "WL5M exact discovery coverage lost")

    manifest_targets = targets.get("targets")
    req(
        isinstance(manifest_targets, list)
        and len(manifest_targets) == EXPECTED_BASE_DEVICE_COUNT,
        "target list malformed",
    )
    req(
        tuple(item.get("base_device") for item in manifest_targets if isinstance(item, dict))
        == EXPECTED_BASES,
        "target Base Device order/coverage drifted",
    )
    req(
        {item.get("subfamily") for item in manifest_targets if isinstance(item, dict)}
        == set(EXPECTED_SUBFAMILIES),
        "target subfamily coverage drifted",
    )
    non_prefix_targets = [
        item for item in manifest_targets
        if isinstance(item, dict)
        and item.get("prefix_consistent_with_frozen_subfamily") is False
    ]
    req(len(non_prefix_targets) == 1, "non-prefix exact-discovery target cardinality drifted")
    req(
        non_prefix_targets[0].get("base_device") == EXPECTED_NON_PREFIX_BASE
        and non_prefix_targets[0].get("subfamily") == "STM32WL55",
        "non-prefix exact-discovery target identity drifted",
    )

    req(summary.get("discovery_id") == DISCOVERY_ID, "summary discovery id drifted")
    req(summary.get("selected_wireless_frontier") == EXPECTED_SERIES, "summary wireless frontier drifted")
    req(summary.get("target_config") == EXPECTED_TARGET_CONFIG, "summary target config drifted")
    req(summary.get("base_device_count") == EXPECTED_BASE_DEVICE_COUNT, "summary Base Device count drifted")
    req(summary.get("attempted_targets") == EXPECTED_BASE_DEVICE_COUNT, "attempted target count drifted")
    req(summary.get("successful_targets") == EXPECTED_BASE_DEVICE_COUNT, "success target count drifted")
    req(summary.get("manual_review_targets") == 0, "manual review opened")
    req(summary.get("active_exact_icpn_count") == EXPECTED_COUNT, "Active exact ICPN count drifted")
    req(
        summary.get("excluded_non_active_part_number_count") == EXPECTED_EXCLUDED,
        "non-active exclusion count drifted",
    )
    req(
        summary.get("excluded_non_active_part_numbers") == EXPECTED_EXCLUDED_IDENTITIES,
        "non-active exclusion identity set drifted",
    )
    req(summary.get("active_exact_icpn_set_sha256") == EXPECTED_SHA256, "exact-set digest drifted")
    req(summary.get("bounded_exact_discovery_complete") is True, "bounded discovery incomplete")
    req(summary.get("status") == "discovered", "discovery status drifted")
    req(summary.get("next_gate") == EXPECTED_NEXT, "next gate drifted or bypassed")
    req(summary.get("browser_version") == EXPECTED_BROWSER_VERSION, "browser version drifted")
    req(summary.get("known_non_prefix_base_device") == EXPECTED_NON_PREFIX_BASE, "summary WL5M anomaly drifted")

    claims = summary.get("claims")
    req(isinstance(claims, dict), "claims missing")
    req(claims.get("exact_icpn_discovery_completed") is True, "discovery completion claim must be true")
    for key in FALSE_CLAIMS:
        req(claims.get(key) is False, f"{key} must remain false")
    req(
        set(claims) == FALSE_CLAIMS | {"exact_icpn_discovery_completed"},
        "claims surface drifted",
    )

    exact = summary.get("active_exact_icpns")
    excluded = summary.get("excluded_non_active_part_numbers")
    req(isinstance(exact, list) and len(exact) == EXPECTED_COUNT, "Active exact set malformed")
    req(exact == sorted(set(exact)), "Active exact set is not sorted unique")
    req(isinstance(excluded, list) and excluded == EXPECTED_EXCLUDED_IDENTITIES, "excluded set drifted")
    req(not (set(exact) & set(excluded)), "Active/non-active identity overlap")
    digest = hashlib.sha256(("\n".join(exact) + "\n").encode("utf-8")).hexdigest()
    req(digest == EXPECTED_SHA256, "recomputed exact-set digest mismatch")

    req(exact_snapshot.get("discovery_id") == DISCOVERY_ID, "exact snapshot discovery id drifted")
    req(exact_snapshot.get("exact_icpn_count") == EXPECTED_COUNT, "exact snapshot count drifted")
    req(exact_snapshot.get("exact_icpn_set_sha256") == EXPECTED_SHA256, "exact snapshot digest drifted")
    req(exact_snapshot.get("exact_icpns") == exact, "exact snapshot differs from summary")

    results = summary.get("results")
    req(
        isinstance(results, list)
        and len(results) == EXPECTED_BASE_DEVICE_COUNT,
        "result count drifted",
    )
    target_bases = [
        item.get("base_device")
        for item in manifest_targets
        if isinstance(item, dict)
    ]
    result_bases = [
        item.get("base_device")
        for item in results
        if isinstance(item, dict)
    ]
    req(result_bases == target_bases, "result Base Device order/coverage drifted")

    active_owner: dict[str, str] = {}
    excluded_owner: dict[str, str] = {}
    for item in results:
        req(isinstance(item, dict), "result entry is not an object")
        base = item.get("base_device")
        req(isinstance(base, str) and base in EXPECTED_ACTIVE_COUNTS, "unexpected result Base Device")
        req(item.get("series") == EXPECTED_SERIES, f"{base}: series drifted")
        req(item.get("acquisition_status") == "success", f"{base}: acquisition failure retained")
        req(item.get("manual_intervention_required") is False, f"{base}: manual intervention retained")
        req(item.get("commercial_identity_status") == "verified_active", f"{base}: identity is not verified Active")
        if base == EXPECTED_NON_PREFIX_BASE:
            req(item.get("subfamily") == "STM32WL55", "WL5M frozen cohort drifted")
            req(item.get("prefix_consistent_with_frozen_subfamily") is False, "WL5M prefix anomaly disappeared")
        else:
            req(item.get("prefix_consistent_with_frozen_subfamily") is True, f"{base}: unexpected prefix anomaly")

        evidence = item.get("evidence")
        req(isinstance(evidence, dict), f"{base}: evidence missing")
        req(evidence.get("base_device") == base, f"{base}: evidence Base Device mismatch")
        req(evidence.get("acquisition_transport") == BROWSER_TRANSPORT, f"{base}: acquisition transport drifted")
        req(evidence.get("source_url") == item.get("source_url"), f"{base}: source URL mismatch")
        req(evidence.get("evidence_surface") == "quality_and_reliability_part_number", f"{base}: evidence surface drifted")

        active = evidence.get("exact_icpns")
        nonactive_records = evidence.get("excluded_non_active_part_numbers")
        records = evidence.get("part_number_records")
        expected_excluded = EXPECTED_EXCLUDED_BY_BASE.get(base, [])
        req(isinstance(active, list), f"{base}: Active list missing")
        req(len(active) == EXPECTED_ACTIVE_COUNTS[base], f"{base}: Active exact identity count drifted")
        req(
            isinstance(nonactive_records, list)
            and [row.get("icpn") for row in nonactive_records if isinstance(row, dict)] == expected_excluded,
            f"{base}: non-active exclusion identities drifted",
        )
        for row in nonactive_records:
            req(
                isinstance(row, dict)
                and isinstance(row.get("marketing_status"), str)
                and row["marketing_status"].startswith("Proposal"),
                f"{base}: non-active lifecycle status is no longer Proposal",
            )
        req(
            isinstance(records, list)
            and len(records) == EXPECTED_ACTIVE_COUNTS[base] + len(expected_excluded),
            f"{base}: part-number record surface drifted",
        )
        req(item.get("active_exact_icpns") == active, f"{base}: result Active set differs from evidence")
        req(item.get("excluded_non_active_icpns") == expected_excluded, f"{base}: result exclusion set drifted")

        for icpn in active:
            req(isinstance(icpn, str) and icpn.startswith(base), f"{base}: foreign Active ICPN")
            req(icpn not in active_owner, f"{icpn}: duplicate Active identity")
            active_owner[icpn] = base
        for icpn in expected_excluded:
            req(icpn.startswith(base), f"{base}: foreign excluded identity")
            req(icpn not in excluded_owner, f"{icpn}: duplicate excluded identity")
            excluded_owner[icpn] = base

        retained = load(EVIDENCE / f"{base.lower()}.json")
        req(retained == evidence, f"{base}: standalone evidence differs from summary")

    req(sorted(active_owner) == exact, "summary Active set differs from per-Base evidence")
    req(sorted(excluded_owner) == EXPECTED_EXCLUDED_IDENTITIES, "summary excluded set differs from per-Base evidence")

    req(provenance.get("discovery_id") == DISCOVERY_ID, "provenance discovery id drifted")
    req(provenance.get("workflow_role") == "authoritative_exact_icpn_discovery", "workflow role drifted")
    req(provenance.get("source_repository") == "physicslu/plasma", "source repository drifted")
    req(provenance.get("executed_git_sha") == EXPECTED_EXECUTED_SHA, "authoritative executed SHA drifted")
    req(provenance.get("workflow_run_id") == EXPECTED_RUN_ID, "authoritative workflow run id drifted")
    req(provenance.get("workflow_run_attempt") == 1, "workflow run attempt drifted")
    req(provenance.get("acquisition_transport") == BROWSER_TRANSPORT, "provenance transport drifted")
    req(provenance.get("browser_version") == EXPECTED_BROWSER_VERSION, "provenance browser version drifted")
    req(
        provenance.get("candidate_source_sha256") == targets.get("candidate_source_sha256"),
        "candidate source digest mismatch",
    )
    req(
        provenance.get("selection_sha256") == targets.get("selection_sha256"),
        "selection digest mismatch",
    )
    req(
        provenance.get("accessibility_summary_sha256")
        == targets.get("accessibility_summary_sha256"),
        "accessibility digest mismatch",
    )

    sources = production.get("sources")
    req(isinstance(sources, list), "Production sources missing")
    prod_count = sum(
        int(src.get("row_count", 0))
        for src in sources
        if isinstance(src, dict)
    )
    req(prod_count == EXPECTED_PRODUCTION_COUNT, "Production Catalog exact count changed")
    req(len(sources) == EXPECTED_PRODUCTION_FAMILIES, "Production family count changed")
    req(
        all(
            not (isinstance(src, dict) and src.get("family") == "STM32WLX")
            for src in sources
        ),
        "STM32WLX leaked into Production during research-only discovery",
    )


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
        ("discovery completion loss", lambda t,s,e,p,d: s["claims"].__setitem__("exact_icpn_discovery_completed", False)),
        ("runtime programming support", lambda t,s,e,p,d: s["claims"].__setitem__("runtime_programming_support_claimed", True)),
        ("programming equivalence", lambda t,s,e,p,d: s["claims"].__setitem__("programming_algorithm_equivalence_claimed", True)),
        ("radio operation", lambda t,s,e,p,d: s["claims"].__setitem__("wireless_radio_operation_authorized", True)),
        ("wireless security operation", lambda t,s,e,p,d: s["claims"].__setitem__("wireless_security_operation_authorized", True)),
        ("security mutation", lambda t,s,e,p,d: s["claims"].__setitem__("security_mutation_authorized", True)),
        ("debug attach", lambda t,s,e,p,d: s["claims"].__setitem__("debug_attach_supported", True)),
        ("target execution", lambda t,s,e,p,d: s["claims"].__setitem__("target_execution_authorized", True)),
        ("HIL coupling", lambda t,s,e,p,d: s["claims"].__setitem__("hil_required_for_catalog_admission", True)),
        ("reject remaining wireless", lambda t,s,e,p,d: s["claims"].__setitem__("remaining_wireless_families_rejected", True)),
        ("open WLX admission", lambda t,s,e,p,d: s["claims"].__setitem__("stm32wlx_admission_ready", True)),
        ("normalize WL5M alias", lambda t,s,e,p,d: s["claims"].__setitem__("wl5m_alias_normalized", True)),
        ("drop WL5M exact coverage", lambda t,s,e,p,d: t["known_non_prefix_ordering_targets"][0].__setitem__("included_in_exact_discovery", False)),
        ("manual review", lambda t,s,e,p,d: s.__setitem__("manual_review_targets", 1)),
        ("skip admission-readiness gate", lambda t,s,e,p,d: s.__setitem__("next_gate", "stm32wlx-production-publication-gate")),
        ("exact-set mutation", lambda t,s,e,p,d: s["active_exact_icpns"].pop()),
        ("excluded-set mutation", lambda t,s,e,p,d: s["excluded_non_active_part_numbers"].pop()),
        ("nondeterministic targets", lambda t,s,e,p,d: t["targets"].reverse()),
        ("wrong authoritative SHA", lambda t,s,e,p,d: p.__setitem__("executed_git_sha", "0"*40)),
        ("Production count mutation", lambda t,s,e,p,d: d["sources"][0].__setitem__("row_count", int(d["sources"][0]["row_count"])+1)),
    ]
    for name, mutate in controls:
        expect_reject(name, mutate)

    print(
        "STM32WLX exact ICPN discovery validation: PASS "
        f"({EXPECTED_BASE_DEVICE_COUNT} Base Devices / {EXPECTED_COUNT} Active / "
        f"{EXPECTED_EXCLUDED} excluded / {len(controls)} negative controls)"
    )


if __name__ == "__main__":
    main()

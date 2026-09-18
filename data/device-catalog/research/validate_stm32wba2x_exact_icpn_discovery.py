#!/usr/bin/env python3
"""Fail-closed validator for retained STM32WBA2X exact ICPN discovery."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from stm32wba2x_exact_icpn_discovery import (
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
EVIDENCE = HERE / "evidence" / "stm32wba2x-exact-icpn-live-2026-09-18"
TARGETS = EVIDENCE / "targets.json"
SUMMARY = EVIDENCE / "discovery-summary.json"
EXACT = EVIDENCE / "exact-icpns.json"
PROVENANCE = EVIDENCE / "provenance.json"
PRODUCTION = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_COUNT = 14
EXPECTED_EXCLUDED = 0
EXPECTED_SHA256 = "56efc2b0fe64354ba9bdb626e592aae0cc2f2ae4208cadd7cbe6e08f9585887e"
EXPECTED_NEXT = "stm32wba2x-bounded-exact-icpn-admission-readiness-gate"
EXPECTED_PRODUCTION_COUNT = 2509
EXPECTED_PRODUCTION_FAMILIES = 18
EXPECTED_RUN_ID = 35319117740
EXPECTED_EXECUTED_SHA = "afb94361c10029ef3894f3ae18500c427e87bb94"
EXPECTED_BROWSER_VERSION = "151.0.7922.34"

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
    "stm32wba2x_admission_ready",
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
    req(summary.get("active_exact_icpn_set_sha256") == EXPECTED_SHA256, "exact-set digest drifted")
    req(summary.get("bounded_exact_discovery_complete") is True, "bounded discovery incomplete")
    req(summary.get("status") == "discovered", "discovery status drifted")
    req(summary.get("next_gate") == EXPECTED_NEXT, "next gate drifted or bypassed")
    req(summary.get("browser_version") == EXPECTED_BROWSER_VERSION, "browser version drifted")

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
    req(isinstance(excluded, list) and excluded == [], "excluded set drifted")
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
    target_bases = [item.get("base_device") for item in manifest_targets if isinstance(item, dict)]
    result_bases = [item.get("base_device") for item in results if isinstance(item, dict)]
    req(result_bases == target_bases, "result Base Device order/coverage drifted")

    expected_active_counts = {
        "STM32WBA23CE": 4,
        "STM32WBA23KE": 4,
        "STM32WBA25CE": 4,
        "STM32WBA25HE": 2,
    }
    active_owner: dict[str, str] = {}
    for item in results:
        req(isinstance(item, dict), "result entry is not an object")
        base = item.get("base_device")
        req(isinstance(base, str) and base in expected_active_counts, "unexpected result Base Device")
        req(item.get("series") == EXPECTED_SERIES, f"{base}: series drifted")
        req(item.get("acquisition_status") == "success", f"{base}: acquisition failure retained")
        req(item.get("manual_intervention_required") is False, f"{base}: manual intervention retained")
        req(item.get("commercial_identity_status") == "verified_active", f"{base}: identity is not verified Active")

        evidence = item.get("evidence")
        req(isinstance(evidence, dict), f"{base}: evidence missing")
        req(evidence.get("base_device") == base, f"{base}: evidence Base Device mismatch")
        req(evidence.get("acquisition_transport") == BROWSER_TRANSPORT, f"{base}: acquisition transport drifted")
        req(evidence.get("source_url") == item.get("source_url"), f"{base}: source URL mismatch")
        req(evidence.get("evidence_surface") == "quality_and_reliability_part_number", f"{base}: evidence surface drifted")

        active = evidence.get("exact_icpns")
        nonactive = evidence.get("excluded_non_active_part_numbers")
        records = evidence.get("part_number_records")
        req(isinstance(active, list), f"{base}: Active list missing")
        req(isinstance(nonactive, list) and nonactive == [], f"{base}: non-active exclusions drifted")
        req(
            len(active) == expected_active_counts[base],
            f"{base}: Active exact identity count drifted",
        )
        req(
            isinstance(records, list)
            and len(records) == expected_active_counts[base]
            and all(isinstance(row, dict) and row.get("active") is True for row in records),
            f"{base}: part-number record surface drifted",
        )
        req(item.get("active_exact_icpns") == active, f"{base}: result Active set differs from evidence")
        req(item.get("excluded_non_active_icpns") == [], f"{base}: result exclusion set drifted")

        for icpn in active:
            req(isinstance(icpn, str) and icpn.startswith(base), f"{base}: foreign Active ICPN")
            req(icpn not in active_owner, f"{icpn}: duplicate Active identity")
            active_owner[icpn] = base

        retained = load(EVIDENCE / f"{base.lower()}.json")
        req(retained == evidence, f"{base}: standalone evidence differs from summary")

    req(sorted(active_owner) == exact, "summary Active set differs from per-Base evidence")

    req(provenance.get("discovery_id") == DISCOVERY_ID, "provenance discovery id drifted")
    req(
        provenance.get("workflow_role") == "authoritative_exact_icpn_discovery",
        "workflow role drifted",
    )
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
    prod_count = sum(int(src.get("row_count", 0)) for src in sources if isinstance(src, dict))
    req(prod_count == EXPECTED_PRODUCTION_COUNT, "Production Catalog exact count changed")
    req(len(sources) == EXPECTED_PRODUCTION_FAMILIES, "Production family count changed")
    req(
        all(
            "wba2x" not in str(src).casefold()
            for src in sources
        ),
        "STM32WBA2X leaked into Production during research-only discovery",
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
        ("open WBA2X admission", lambda t,s,e,p,d: s["claims"].__setitem__("stm32wba2x_admission_ready", True)),
        ("manual review", lambda t,s,e,p,d: s.__setitem__("manual_review_targets", 1)),
        ("skip admission-readiness gate", lambda t,s,e,p,d: s.__setitem__("next_gate", "stm32wba2x-production-publication-gate")),
        ("exact-set mutation", lambda t,s,e,p,d: s["active_exact_icpns"].pop()),
        ("nondeterministic targets", lambda t,s,e,p,d: t["targets"].reverse()),
        ("wrong authoritative SHA", lambda t,s,e,p,d: p.__setitem__("executed_git_sha", "0"*40)),
        ("Production count mutation", lambda t,s,e,p,d: d["sources"][0].__setitem__("row_count", int(d["sources"][0]["row_count"])+1)),
    ]
    for name, mutate in controls:
        expect_reject(name, mutate)

    print(
        "STM32WBA2X exact ICPN discovery validation: PASS "
        f"({EXPECTED_BASE_DEVICE_COUNT} Base Devices / {EXPECTED_COUNT} Active / "
        f"{EXPECTED_EXCLUDED} excluded / {len(controls)} negative controls)"
    )


if __name__ == "__main__":
    main()

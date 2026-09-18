#!/usr/bin/env python3
"""Fail-closed validator for retained STM32H7-classic official-ST accessibility evidence."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from stm32h7_classic_evidence_accessibility_probe import (
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    PROBE_ID,
    deterministic_targets,
    target_manifest,
)

HERE = Path(__file__).resolve().parent
EVIDENCE_DIR = HERE / "evidence" / "stm32h7-classic-accessibility-live-2026-09-18"
TARGETS_PATH = EVIDENCE_DIR / "targets.json"
SUMMARY_PATH = EVIDENCE_DIR / "probe-summary.json"
PROVENANCE_PATH = EVIDENCE_DIR / "provenance.json"
EXPECTED_NEXT_GATE = "stm32h7-classic-bounded-exact-icpn-discovery-gate"
EXPECTED_TARGETS = len(EXPECTED_SUBFAMILIES)
EXPECTED_FALSE_CLAIMS = {
    "production_write_authorized",
    "icpn_admission_authorized",
    "full_exact_icpn_discovery_completed",
    "representative_probe_is_full_family_enumeration",
    "programming_algorithm_equivalence_claimed",
    "runtime_programming_support_claimed",
    "security_mutation_authorized",
    "debug_attach_supported",
    "physical_validation_claimed",
    "hil_required_for_catalog_admission",
}


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load(path: Path) -> dict[str, Any]:
    req(path.is_file(), f"missing retained evidence file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected JSON object")
    return value


def validate_documents(targets: dict[str, Any], summary: dict[str, Any], provenance: dict[str, Any]) -> None:
    expected_manifest = target_manifest(deterministic_targets())
    req(targets == expected_manifest, "retained STM32H7-classic target manifest is not deterministic replay")
    req(targets.get("probe_id") == PROBE_ID, "target manifest probe id drifted")
    req(targets.get("target_count") == EXPECTED_TARGETS, "STM32H7-classic target count drifted")

    manifest_targets = targets.get("targets")
    req(isinstance(manifest_targets, list) and len(manifest_targets) == EXPECTED_TARGETS, "invalid target list")
    observed_subfamilies = tuple(item.get("subfamily") for item in manifest_targets if isinstance(item, dict))
    req(observed_subfamilies == EXPECTED_SUBFAMILIES, "STM32H7-classic deterministic subfamily order drifted")
    for item in manifest_targets:
        req(isinstance(item, dict), "target manifest entry is not an object")
        base = item.get("base_device")
        subfamily = item.get("subfamily")
        url = item.get("source_url")
        req(isinstance(base, str) and isinstance(subfamily, str) and base.startswith(subfamily), "target escaped subfamily boundary")
        req(isinstance(url, str) and url == f"https://www.st.com/en/microcontrollers-microprocessors/{base.lower()}.html", "target source URL is not canonical ST product page")

    req(summary.get("probe_id") == PROBE_ID, "summary probe id drifted")
    req(summary.get("selected_partition") == "STM32H7-classic", "summary partition drifted")
    req(summary.get("target_config") == EXPECTED_TARGET_CONFIG, "summary target config drifted")
    req(summary.get("attempted_targets") == EXPECTED_TARGETS, "summary attempted target count drifted")
    req(summary.get("successful_targets") == EXPECTED_TARGETS, "not all STM32H7-classic representative targets succeeded")
    req(summary.get("manual_review_targets") == 0, "manual review remains in STM32H7-classic accessibility probe")
    req(summary.get("bounded_probe_complete") is True, "bounded probe is incomplete")
    req(summary.get("official_st_evidence_accessible_for_all_subfamilies") is True, "official ST evidence is not accessible for all subfamilies")
    req(summary.get("status") == "accessible", "accessibility status drifted")
    req(summary.get("next_gate") == EXPECTED_NEXT_GATE, "next gate drifted or bypassed")

    active_total = summary.get("active_exact_icpns_observed_on_representative_pages")
    excluded_total = summary.get("excluded_non_active_part_numbers_observed")
    req(isinstance(active_total, int) and active_total >= 0, "invalid aggregate active exact-ICPN count")
    req(isinstance(excluded_total, int) and excluded_total >= 0, "invalid aggregate lifecycle-exclusion count")

    claims = summary.get("claims")
    req(isinstance(claims, dict), "summary claims missing")
    req(set(claims) == EXPECTED_FALSE_CLAIMS, "summary claims surface drifted")
    req(all(claims[name] is False for name in EXPECTED_FALSE_CLAIMS), "accessibility probe escaped fail-closed claims")

    results = summary.get("results")
    req(isinstance(results, list) and len(results) == EXPECTED_TARGETS, "summary results target count drifted")
    result_by_subfamily: dict[str, dict[str, Any]] = {}
    counted_active = 0
    counted_excluded = 0
    for item in results:
        req(isinstance(item, dict), "summary result is not an object")
        subfamily = item.get("subfamily")
        req(isinstance(subfamily, str) and subfamily in EXPECTED_SUBFAMILIES, "unexpected summary subfamily")
        req(subfamily not in result_by_subfamily, "duplicate summary subfamily")
        result_by_subfamily[subfamily] = item

        req(item.get("acquisition_status") == "success", f"{subfamily}: acquisition did not succeed")
        req(item.get("manual_intervention_required") is False, f"{subfamily}: manual intervention remains")
        req(item.get("commercial_identity_status") in {"verified_active", "verified_non_active_only"}, f"{subfamily}: commercial identity was not verified")
        active_count = item.get("active_exact_icpn_count")
        excluded_count = item.get("excluded_non_active_count")
        req(isinstance(active_count, int) and active_count >= 0, f"{subfamily}: invalid active count")
        req(isinstance(excluded_count, int) and excluded_count >= 0, f"{subfamily}: invalid excluded count")
        req(active_count + excluded_count > 0, f"{subfamily}: no commercial identity disposition")
        counted_active += active_count
        counted_excluded += excluded_count

        evidence = item.get("evidence")
        req(isinstance(evidence, dict), f"{subfamily}: evidence missing")
        req(evidence.get("acquisition_transport") == BROWSER_TRANSPORT, f"{subfamily}: evidence transport drifted")
        base = item.get("base_device")
        req(evidence.get("base_device") == base, f"{subfamily}: evidence Base Device mismatch")
        req(evidence.get("source_url") == item.get("source_url"), f"{subfamily}: evidence source URL mismatch")
        exact = evidence.get("exact_icpns")
        excluded = evidence.get("excluded_non_active_part_numbers")
        req(isinstance(exact, list) and isinstance(excluded, list), f"{subfamily}: evidence identity lists missing")
        req(len(exact) == active_count and len(excluded) == excluded_count, f"{subfamily}: evidence disposition counts mismatch")
        req(all(isinstance(value, str) and value.startswith(str(base)) for value in exact), f"{subfamily}: foreign active ICPN")
        for row in excluded:
            req(isinstance(row, dict), f"{subfamily}: malformed lifecycle exclusion")
            req(isinstance(row.get("icpn"), str) and row["icpn"].startswith(str(base)), f"{subfamily}: foreign excluded ICPN")
            req(isinstance(row.get("marketing_status"), str) and row["marketing_status"].strip(), f"{subfamily}: missing lifecycle status")
        retained = load(EVIDENCE_DIR / f"{str(base).lower()}.json")
        req(retained == evidence, f"{subfamily}: standalone evidence JSON differs from summary")

    req(tuple(result_by_subfamily) == EXPECTED_SUBFAMILIES, "summary result order drifted")
    req(counted_active == active_total, "aggregate active exact-ICPN count differs from per-target evidence")
    req(counted_excluded == excluded_total, "aggregate lifecycle-exclusion count differs from per-target evidence")

    req(provenance.get("probe_id") == PROBE_ID, "provenance probe id drifted")
    req(provenance.get("acquisition_transport") == BROWSER_TRANSPORT, "provenance transport drifted")
    req(isinstance(provenance.get("browser_version"), str) and provenance["browser_version"].strip(), "browser version missing")
    req(provenance.get("partition_source_sha256") == targets.get("partition_source_sha256"), "partition source digest mismatch")
    req(provenance.get("selection_sha256") == targets.get("selection_sha256"), "selection digest mismatch")


def expect_reject(name: str, mutator) -> None:
    targets = load(TARGETS_PATH)
    summary = load(SUMMARY_PATH)
    provenance = load(PROVENANCE_PATH)
    mutator(targets, summary, provenance)
    try:
        validate_documents(targets, summary, provenance)
    except SystemExit:
        return
    raise SystemExit(f"negative control accepted: {name}")


def main() -> None:
    targets = load(TARGETS_PATH)
    summary = load(SUMMARY_PATH)
    provenance = load(PROVENANCE_PATH)
    validate_documents(targets, summary, provenance)

    controls = [
        ("Production authorization", lambda t, s, p: s["claims"].__setitem__("production_write_authorized", True)),
        ("ICPN admission authorization", lambda t, s, p: s["claims"].__setitem__("icpn_admission_authorized", True)),
        ("representative equals full enumeration", lambda t, s, p: s["claims"].__setitem__("representative_probe_is_full_family_enumeration", True)),
        ("programming equivalence", lambda t, s, p: s["claims"].__setitem__("programming_algorithm_equivalence_claimed", True)),
        ("runtime programming support", lambda t, s, p: s["claims"].__setitem__("runtime_programming_support_claimed", True)),
        ("security mutation", lambda t, s, p: s["claims"].__setitem__("security_mutation_authorized", True)),
        ("debug attach", lambda t, s, p: s["claims"].__setitem__("debug_attach_supported", True)),
        ("HIL coupling", lambda t, s, p: s["claims"].__setitem__("hil_required_for_catalog_admission", True)),
        ("skip directly to Production", lambda t, s, p: s.__setitem__("next_gate", "stm32h7-classic-production-publication-gate")),
        ("missing subfamily success", lambda t, s, p: s.__setitem__("successful_targets", EXPECTED_TARGETS - 1)),
        ("wrong transport", lambda t, s, p: p.__setitem__("acquisition_transport", "raw_http")),
        ("nondeterministic target manifest", lambda t, s, p: t["targets"].reverse()),
    ]
    for name, mutate in controls:
        expect_reject(name, mutate)

    print("STM32H7-classic bounded official-ST evidence accessibility validation: PASS")
    print(f"targets={EXPECTED_TARGETS} negative_controls={len(controls)} rejected")


if __name__ == "__main__":
    main()

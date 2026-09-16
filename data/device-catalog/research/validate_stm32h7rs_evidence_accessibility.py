#!/usr/bin/env python3
"""Fail-closed validator for retained STM32H7RS official-ST accessibility evidence."""
from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from stm32h7rs_evidence_accessibility_probe import (
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    PROBE_ID,
    deterministic_targets,
    target_manifest,
)

HERE = Path(__file__).resolve().parent
EVIDENCE_DIR = HERE / "evidence" / "stm32h7rs-accessibility-live-2026-09-16"
TARGETS_PATH = EVIDENCE_DIR / "targets.json"
SUMMARY_PATH = EVIDENCE_DIR / "probe-summary.json"
PROVENANCE_PATH = EVIDENCE_DIR / "provenance.json"
EXPECTED_NEXT_GATE = "stm32h7rs-bounded-exact-icpn-discovery-gate"
EXPECTED_FALSE_CLAIMS = {
    "production_write_authorized",
    "icpn_admission_authorized",
    "full_exact_icpn_discovery_completed",
    "representative_probe_is_full_family_enumeration",
    "programming_algorithm_equivalence_claimed",
    "runtime_programming_support_claimed",
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
    req(targets == expected_manifest, "retained STM32H7RS target manifest is not deterministic replay")
    req(targets.get("probe_id") == PROBE_ID, "target manifest probe id drifted")
    req(targets.get("target_count") == 4, "STM32H7RS target count must remain 4")

    manifest_targets = targets.get("targets")
    req(isinstance(manifest_targets, list) and len(manifest_targets) == 4, "invalid target list")
    observed_subfamilies = tuple(item.get("subfamily") for item in manifest_targets if isinstance(item, dict))
    req(observed_subfamilies == EXPECTED_SUBFAMILIES, "STM32H7RS deterministic subfamily order drifted")
    for item in manifest_targets:
        req(isinstance(item, dict), "target manifest entry is not an object")
        base = item.get("base_device")
        subfamily = item.get("subfamily")
        url = item.get("source_url")
        req(isinstance(base, str) and isinstance(subfamily, str) and base.startswith(subfamily), "target escaped subfamily")
        req(url == f"https://www.st.com/en/microcontrollers-microprocessors/{base.lower()}.html", "target source URL is not canonical ST product page")

    req(summary.get("probe_id") == PROBE_ID, "summary probe id drifted")
    req(summary.get("selected_partition") == "STM32H7RS", "summary partition drifted")
    req(summary.get("target_config") == EXPECTED_TARGET_CONFIG, "summary target config drifted")
    req(summary.get("attempted_targets") == 4, "summary attempted target count drifted")
    req(summary.get("successful_targets") == 4, "not all STM32H7RS representative targets succeeded")
    req(summary.get("manual_review_targets") == 0, "manual review remains in STM32H7RS accessibility probe")
    req(summary.get("bounded_probe_complete") is True, "bounded probe is incomplete")
    req(summary.get("official_st_evidence_accessible_for_all_subfamilies") is True, "official ST evidence is not cleanly accessible for all subfamilies")
    req(summary.get("status") == "accessible", "accessibility status drifted")
    req(summary.get("next_gate") == EXPECTED_NEXT_GATE, "next gate drifted or bypassed")

    claims = summary.get("claims")
    req(isinstance(claims, dict), "summary claims missing")
    req(set(claims) == EXPECTED_FALSE_CLAIMS, "summary claims surface drifted")
    req(all(claims[name] is False for name in EXPECTED_FALSE_CLAIMS), "accessibility probe escaped fail-closed claims")

    results = summary.get("results")
    req(isinstance(results, list) and len(results) == 4, "summary results must contain 4 targets")
    result_by_subfamily: dict[str, dict[str, Any]] = {}
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
        req(isinstance(active_count, int) and isinstance(excluded_count, int) and active_count + excluded_count > 0, f"{subfamily}: no identity disposition")
        evidence = item.get("evidence")
        req(isinstance(evidence, dict), f"{subfamily}: evidence missing")
        req(evidence.get("acquisition_transport") == BROWSER_TRANSPORT, f"{subfamily}: evidence transport drifted")
        base = item.get("base_device")
        req(evidence.get("base_device") == base, f"{subfamily}: evidence Base Device mismatch")
        req(evidence.get("source_url") == item.get("source_url"), f"{subfamily}: evidence source URL mismatch")
        exact = evidence.get("exact_icpns")
        excluded = evidence.get("excluded_non_active_part_numbers")
        req(isinstance(exact, list) and isinstance(excluded, list), f"{subfamily}: evidence identity lists missing")
        req(all(isinstance(value, str) and value.startswith(str(base)) for value in exact), f"{subfamily}: foreign active ICPN")
        for row in excluded:
            req(isinstance(row, dict), f"{subfamily}: malformed lifecycle exclusion")
            req(isinstance(row.get("icpn"), str) and row["icpn"].startswith(str(base)), f"{subfamily}: foreign excluded ICPN")
            req(isinstance(row.get("marketing_status"), str) and row["marketing_status"].strip(), f"{subfamily}: missing lifecycle status")
        retained = load(EVIDENCE_DIR / f"{str(base).lower()}.json")
        req(retained == evidence, f"{subfamily}: standalone evidence JSON differs from summary")

    req(tuple(result_by_subfamily) == EXPECTED_SUBFAMILIES, "summary result order drifted")
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

    expect_reject("Production authorization", lambda t, s, p: s["claims"].__setitem__("production_write_authorized", True))
    expect_reject("ICPN admission authorization", lambda t, s, p: s["claims"].__setitem__("icpn_admission_authorized", True))
    expect_reject("representative equals full enumeration", lambda t, s, p: s["claims"].__setitem__("representative_probe_is_full_family_enumeration", True))
    expect_reject("HIL coupling", lambda t, s, p: s["claims"].__setitem__("hil_required_for_catalog_admission", True))
    expect_reject("skip directly to Production", lambda t, s, p: s.__setitem__("next_gate", "stm32h7rs-production-publication-gate"))
    expect_reject("missing subfamily success", lambda t, s, p: s.__setitem__("successful_targets", 3))
    expect_reject("wrong transport", lambda t, s, p: p.__setitem__("acquisition_transport", "raw_http"))
    expect_reject("nondeterministic target manifest", lambda t, s, p: t["targets"].reverse())

    print("STM32H7RS bounded official-ST evidence accessibility validation: PASS")


if __name__ == "__main__":
    main()

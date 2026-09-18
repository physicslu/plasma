#!/usr/bin/env python3
"""Fail-closed validator for retained STM32WBA2X official-ST accessibility evidence."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from stm32wba2x_evidence_accessibility_probe import (
    EXPECTED_SUBFAMILIES,
    EXPECTED_TARGET_CONFIG,
    EXPECTED_SERIES,
    PROBE_ID,
    deterministic_targets,
    target_manifest,
)

HERE = Path(__file__).resolve().parent
EVIDENCE_DIR = HERE / "evidence" / "stm32wba2x-accessibility-live-2026-09-18"
TARGETS_PATH = EVIDENCE_DIR / "targets.json"
SUMMARY_PATH = EVIDENCE_DIR / "probe-summary.json"
PROVENANCE_PATH = EVIDENCE_DIR / "provenance.json"

EXPECTED_TARGETS = 2
EXPECTED_ACTIVE_OBSERVED = 8
EXPECTED_EXCLUDED_OBSERVED = 0
EXPECTED_BASES = ("STM32WBA23CE", "STM32WBA25CE")
EXPECTED_NEXT_GATE = "stm32wba2x-bounded-exact-icpn-discovery-gate"
EXPECTED_SOURCE_SHA256 = "43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_FALSE_CLAIMS = {
    "production_write_authorized",
    "icpn_admission_authorized",
    "full_exact_icpn_discovery_completed",
    "representative_probe_is_full_family_enumeration",
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


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def load(path: Path) -> dict[str, Any]:
    req(path.is_file(), f"missing retained evidence file: {path}")
    value = json.loads(path.read_text(encoding="utf-8"))
    req(isinstance(value, dict), f"{path.name}: expected JSON object")
    return value


def validate_documents(
    targets: dict[str, Any],
    summary: dict[str, Any],
    provenance: dict[str, Any],
) -> None:
    expected_manifest = target_manifest(deterministic_targets())
    req(targets == expected_manifest, "retained STM32WBA2X target manifest is not deterministic replay")
    req(targets.get("probe_id") == PROBE_ID, "target manifest probe id drifted")
    req(targets.get("target_count") == EXPECTED_TARGETS, "STM32WBA2X target count drifted")
    req(targets.get("candidate_source_sha256") == EXPECTED_SOURCE_SHA256, "candidate source digest drifted")

    manifest_targets = targets.get("targets")
    req(isinstance(manifest_targets, list) and len(manifest_targets) == EXPECTED_TARGETS, "invalid target list")
    req(
        tuple(item.get("subfamily") for item in manifest_targets if isinstance(item, dict))
        == EXPECTED_SUBFAMILIES,
        "STM32WBA2X deterministic subfamily order drifted",
    )
    req(
        tuple(item.get("base_device") for item in manifest_targets if isinstance(item, dict))
        == EXPECTED_BASES,
        "STM32WBA2X deterministic representative Base Devices drifted",
    )
    for item in manifest_targets:
        req(isinstance(item, dict), "target manifest entry is not an object")
        base = item.get("base_device")
        subfamily = item.get("subfamily")
        url = item.get("source_url")
        req(item.get("series") == EXPECTED_SERIES, "target series drifted")
        req(
            isinstance(base, str)
            and isinstance(subfamily, str)
            and base.startswith(subfamily),
            "target escaped subfamily boundary",
        )
        req(
            isinstance(url, str)
            and url
            == f"https://www.st.com/en/microcontrollers-microprocessors/{base.lower()}.html",
            "target source URL is not canonical ST product page",
        )

    req(summary.get("probe_id") == PROBE_ID, "summary probe id drifted")
    req(summary.get("selected_wireless_frontier") == EXPECTED_SERIES, "summary wireless frontier drifted")
    req(summary.get("target_config") == EXPECTED_TARGET_CONFIG, "summary target config drifted")
    req(summary.get("attempted_targets") == EXPECTED_TARGETS, "summary attempted target count drifted")
    req(summary.get("successful_targets") == EXPECTED_TARGETS, "not all STM32WBA2X representative targets succeeded")
    req(summary.get("manual_review_targets") == 0, "manual review remains in STM32WBA2X accessibility probe")
    req(summary.get("bounded_probe_complete") is True, "bounded probe is incomplete")
    req(
        summary.get("official_st_evidence_accessible_for_all_subfamilies") is True,
        "official ST evidence is not accessible for all STM32WBA2X subfamilies",
    )
    req(summary.get("status") == "accessible", "accessibility status drifted")
    req(summary.get("next_gate") == EXPECTED_NEXT_GATE, "next gate drifted or bypassed")
    req(
        summary.get("active_exact_icpns_observed_on_representative_pages")
        == EXPECTED_ACTIVE_OBSERVED,
        "representative Active exact-ICPN observation count drifted",
    )
    req(
        summary.get("excluded_non_active_part_numbers_observed")
        == EXPECTED_EXCLUDED_OBSERVED,
        "representative lifecycle exclusion count drifted",
    )

    claims = summary.get("claims")
    req(isinstance(claims, dict), "summary claims missing")
    req(set(claims) == EXPECTED_FALSE_CLAIMS, "summary claims surface drifted")
    req(
        all(claims[name] is False for name in EXPECTED_FALSE_CLAIMS),
        "accessibility probe escaped fail-closed claims",
    )

    results = summary.get("results")
    req(isinstance(results, list) and len(results) == EXPECTED_TARGETS, "summary results target count drifted")
    counted_active = 0
    counted_excluded = 0
    observed_bases: list[str] = []
    for expected_subfamily, item in zip(EXPECTED_SUBFAMILIES, results, strict=True):
        req(isinstance(item, dict), "summary result is not an object")
        req(item.get("subfamily") == expected_subfamily, f"{expected_subfamily}: result order drifted")
        req(item.get("series") == EXPECTED_SERIES, f"{expected_subfamily}: result series drifted")
        req(item.get("acquisition_status") == "success", f"{expected_subfamily}: acquisition did not succeed")
        req(item.get("manual_intervention_required") is False, f"{expected_subfamily}: manual intervention remains")
        req(item.get("commercial_identity_status") == "verified_active", f"{expected_subfamily}: representative identity is not verified Active")

        active_count = item.get("active_exact_icpn_count")
        excluded_count = item.get("excluded_non_active_count")
        req(active_count == 4, f"{expected_subfamily}: representative Active count drifted")
        req(excluded_count == 0, f"{expected_subfamily}: representative exclusion count drifted")
        counted_active += active_count
        counted_excluded += excluded_count

        evidence = item.get("evidence")
        req(isinstance(evidence, dict), f"{expected_subfamily}: evidence missing")
        req(evidence.get("acquisition_transport") == BROWSER_TRANSPORT, f"{expected_subfamily}: evidence transport drifted")
        base = item.get("base_device")
        req(isinstance(base, str), f"{expected_subfamily}: Base Device missing")
        observed_bases.append(base)
        req(evidence.get("base_device") == base, f"{expected_subfamily}: evidence Base Device mismatch")
        req(evidence.get("source_url") == item.get("source_url"), f"{expected_subfamily}: evidence source URL mismatch")
        req(evidence.get("evidence_surface") == "quality_and_reliability_part_number", f"{expected_subfamily}: evidence surface drifted")

        exact = evidence.get("exact_icpns")
        excluded = evidence.get("excluded_non_active_part_numbers")
        req(isinstance(exact, list) and isinstance(excluded, list), f"{expected_subfamily}: evidence identity lists missing")
        req(len(exact) == 4 and excluded == [], f"{expected_subfamily}: retained identity disposition drifted")
        req(
            all(isinstance(value, str) and value.startswith(base) for value in exact),
            f"{expected_subfamily}: foreign Active ICPN",
        )
        records = evidence.get("part_number_records")
        req(isinstance(records, list) and len(records) == 4, f"{expected_subfamily}: part-number record surface drifted")
        req(all(isinstance(row, dict) and row.get("active") is True for row in records), f"{expected_subfamily}: non-Active record retained")

        retained = load(EVIDENCE_DIR / f"{base.lower()}.json")
        req(retained == evidence, f"{expected_subfamily}: standalone evidence JSON differs from summary")

    req(tuple(observed_bases) == EXPECTED_BASES, "summary representative Base Devices drifted")
    req(counted_active == EXPECTED_ACTIVE_OBSERVED, "aggregate Active count differs from per-target evidence")
    req(counted_excluded == EXPECTED_EXCLUDED_OBSERVED, "aggregate exclusion count differs from per-target evidence")

    req(provenance.get("probe_id") == PROBE_ID, "provenance probe id drifted")
    req(provenance.get("acquisition_transport") == BROWSER_TRANSPORT, "provenance transport drifted")
    req(
        isinstance(provenance.get("browser_version"), str)
        and provenance["browser_version"].strip(),
        "browser version missing",
    )
    req(provenance.get("candidate_source_sha256") == EXPECTED_SOURCE_SHA256, "provenance candidate source digest drifted")
    req(
        provenance.get("candidate_source_sha256") == targets.get("candidate_source_sha256"),
        "candidate source digest mismatch",
    )
    req(
        provenance.get("selection_sha256") == targets.get("selection_sha256"),
        "selection digest mismatch",
    )


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
        ("Production authorization", lambda t,s,p: s["claims"].__setitem__("production_write_authorized", True)),
        ("ICPN admission authorization", lambda t,s,p: s["claims"].__setitem__("icpn_admission_authorized", True)),
        ("full exact discovery", lambda t,s,p: s["claims"].__setitem__("full_exact_icpn_discovery_completed", True)),
        ("representative equals full enumeration", lambda t,s,p: s["claims"].__setitem__("representative_probe_is_full_family_enumeration", True)),
        ("programming equivalence", lambda t,s,p: s["claims"].__setitem__("programming_algorithm_equivalence_claimed", True)),
        ("runtime programming support", lambda t,s,p: s["claims"].__setitem__("runtime_programming_support_claimed", True)),
        ("radio operation", lambda t,s,p: s["claims"].__setitem__("wireless_radio_operation_authorized", True)),
        ("wireless security operation", lambda t,s,p: s["claims"].__setitem__("wireless_security_operation_authorized", True)),
        ("security mutation", lambda t,s,p: s["claims"].__setitem__("security_mutation_authorized", True)),
        ("debug attach", lambda t,s,p: s["claims"].__setitem__("debug_attach_supported", True)),
        ("target execution", lambda t,s,p: s["claims"].__setitem__("target_execution_authorized", True)),
        ("HIL coupling", lambda t,s,p: s["claims"].__setitem__("hil_required_for_catalog_admission", True)),
        ("reject remaining wireless", lambda t,s,p: s["claims"].__setitem__("remaining_wireless_families_rejected", True)),
        ("open WBA2X admission", lambda t,s,p: s["claims"].__setitem__("stm32wba2x_admission_ready", True)),
        ("skip exact discovery gate", lambda t,s,p: s.__setitem__("next_gate", "stm32wba2x-production-publication-gate")),
        ("missing representative success", lambda t,s,p: s.__setitem__("successful_targets", 1)),
        ("wrong Active observation count", lambda t,s,p: s.__setitem__("active_exact_icpns_observed_on_representative_pages", 7)),
        ("wrong transport", lambda t,s,p: p.__setitem__("acquisition_transport", "raw_http")),
        ("nondeterministic target manifest", lambda t,s,p: t["targets"].reverse()),
    ]
    for name, mutate in controls:
        expect_reject(name, mutate)

    print("STM32WBA2X bounded official-ST evidence accessibility validation: PASS")
    print(
        f"targets={EXPECTED_TARGETS} active_observed={EXPECTED_ACTIVE_OBSERVED} "
        f"excluded_observed={EXPECTED_EXCLUDED_OBSERVED} "
        f"negative_controls={len(controls)} rejected"
    )


if __name__ == "__main__":
    main()

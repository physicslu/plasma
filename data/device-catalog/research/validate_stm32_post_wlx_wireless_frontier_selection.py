#!/usr/bin/env python3
"""Fail-closed validation for post-WLX STM32 wireless frontier reselection."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from stm32_post_wba2x_wireless_frontier_selection import (
    NEXT_GATE,
    SELECTED,
    WIRELESS_IDS,
    build_selection,
)

HERE = Path(__file__).resolve().parent
SELECTION = HERE / "stm32-post-wlx-wireless-frontier-selection.json"


def req(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)


def validate(value: dict) -> None:
    req(value.get("schema_version") == 1, "schema version drifted")
    req(value.get("selection_id") == "stm32-post-wlx-wireless-frontier-selection-v1", "selection id drifted")
    req(value.get("scope") == "wireless_frontier_reselection_research_only", "scope drifted")
    req(value.get("status") == "selected_for_bounded_manufacturer_evidence_only", "status drifted")

    prod = value.get("production_boundary") or {}
    req(prod.get("exact_icpns") == 2554, "Production exact count drifted")
    req(prod.get("families") == 20, "Production family count drifted")
    req(prod.get("published_wireless_families") == {"STM32WBA2X": 14, "STM32WLX": 31}, "published wireless boundary drifted")
    req(prod.get("standard_nonwireless_frontier_exhausted") is True, "non-wireless frontier reopened")
    req(prod.get("frozen_manifest_git_blob_sha") == "4174f665a1a8ef7801dec7785c7d3853850cad4a", "Production blob drifted")

    upstream = value.get("upstream") or {}
    req(upstream.get("prior_wireless_selection_id") == "stm32-post-h7-wireless-frontier-selection-v1", "prior selection id drifted")
    req(upstream.get("prior_wireless_selection_git_blob_sha") == "3397b44d97216625ce3fcf5235f6ae05e260ac59", "prior selection blob drifted")
    req(upstream.get("cross_family_prioritization_git_blob_sha") == "f445bc7938eee1a0453fcebe6bf81d77879aeaca", "prioritization blob drifted")
    req(upstream.get("original_wireless_backlog_count") == 6, "wireless backlog count drifted")
    req(upstream.get("published_wireless_count") == 2, "published wireless count drifted")
    req(upstream.get("remaining_structurally_eligible_count") == 3, "remaining eligible count drifted")
    req(upstream.get("deferred_wireless_count") == 1, "deferred wireless count drifted")

    published = value.get("already_published_wireless_frontiers")
    req(isinstance(published, list) and len(published) == 2, "published wireless list drifted")
    req(published[0].get("plasma_series") == "STM32WBA2X", "published WBA2X identity drifted")
    req(published[0].get("production_row_count") == 14, "published WBA2X row count drifted")
    req(published[1].get("plasma_series") == "STM32WLX", "published WLX identity drifted")
    req(published[1].get("production_row_count") == 31, "published WLX row count drifted")

    eligible = value.get("eligible_wireless_frontiers")
    req(isinstance(eligible, list), "remaining eligible list missing")
    req(
        [item.get("plasma_series") for item in eligible]
        == ["STM32WBA6X", "STM32WBX", "STM32WBA5X"],
        "remaining eligible order drifted",
    )
    req(
        [(item.get("row_count"), item.get("subfamily_count")) for item in eligible]
        == [(19, 5), (23, 8), (34, 5)],
        "remaining eligible sizing drifted",
    )

    deferred = value.get("deferred_wireless_frontiers")
    req(isinstance(deferred, list) and len(deferred) == 1, "deferred wireless list drifted")
    req(deferred[0].get("plasma_series") == "STM32W108", "STM32W108 deferred identity drifted")
    req(deferred[0].get("structural_gate_pass") is False, "STM32W108 structural boundary opened")
    req(
        deferred[0].get("defer_reasons")
        == ["structural_gate_fail", "no_bounded_subfamilies", "no_ordering_pattern_rows"],
        "STM32W108 defer reasons drifted",
    )

    req(value.get("selected_wireless_frontier") == SELECTED, "selected frontier drifted")
    req(value.get("selected_target_config") == "tcl/target/stm32wba6x.cfg", "selected target config drifted")
    req(value.get("selected_row_count") == 19, "selected row count drifted")
    req(value.get("selected_subfamily_count") == 5, "selected subfamily count drifted")
    req(
        value.get("selected_subfamilies")
        == ["STM32WBA62", "STM32WBA63", "STM32WBA64", "STM32WBA65", "STM32WBA6M"],
        "selected subfamilies drifted",
    )
    req(value.get("selected_identifier_kind_counts") == {"ordering_pattern": 19}, "selected identifier mix drifted")
    req(value.get("next_gate") == NEXT_GATE, "next gate drifted")

    policy = value.get("selection_policy") or {}
    req(policy.get("sequencing_only") is True, "selection ceased to be sequencing-only")
    req(
        policy.get("sequencing")
        == ["fewest row_count", "then fewest subfamily_count", "then lexical plasma_series"],
        "sequencing policy drifted",
    )

    claims = value.get("claims") or {}
    expected_claims = {
        "production_write_authorized",
        "exact_icpn_discovery_completed",
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
        "stm32w108_rejected",
        "stm32wba6x_admission_ready",
    }
    req(set(claims) == expected_claims, "claim surface drifted")
    req(all(claims[k] is False for k in expected_claims), "fail-closed claim opened")

    covered = {
        item.get("plasma_series") for item in eligible
    } | {
        item.get("plasma_series") for item in deferred
    } | {
        item.get("plasma_series") for item in published
    }
    req(covered == set(WIRELESS_IDS), "wireless frontier coverage drifted")


def expect_rejected(name: str, mutate) -> None:
    candidate = copy.deepcopy(json.loads(SELECTION.read_text(encoding="utf-8")))
    mutate(candidate)
    try:
        validate(candidate)
    except AssertionError:
        return
    raise AssertionError(f"negative control accepted: {name}")


def main() -> int:
    frozen = json.loads(SELECTION.read_text(encoding="utf-8"))
    validate(frozen)
    req(build_selection() == frozen, "post-WLX wireless selection is not deterministic replay")

    controls = [
        ("reselect-published-wba2x", lambda v: v.__setitem__("selected_wireless_frontier", "STM32WBA2X")),
        ("reselect-published-wlx", lambda v: v.__setitem__("selected_wireless_frontier", "STM32WLX")),
        ("select-w108", lambda v: v.__setitem__("selected_wireless_frontier", "STM32W108")),
        ("wrong-target", lambda v: v.__setitem__("selected_target_config", "tcl/target/stm32wbx.cfg")),
        ("drop-wlx-publication", lambda v: v["production_boundary"].__setitem__("published_wireless_families", {"STM32WBA2X": 14})),
        ("mark-w108-eligible", lambda v: v["deferred_wireless_frontiers"][0].__setitem__("structural_gate_pass", True)),
        ("authorize-production", lambda v: v["claims"].__setitem__("production_write_authorized", True)),
        ("claim-exact-discovery", lambda v: v["claims"].__setitem__("exact_icpn_discovery_completed", True)),
        ("authorize-admission", lambda v: v["claims"].__setitem__("icpn_admission_authorized", True)),
        ("authorize-radio", lambda v: v["claims"].__setitem__("wireless_radio_operation_authorized", True)),
        ("authorize-security", lambda v: v["claims"].__setitem__("wireless_security_operation_authorized", True)),
        ("authorize-target", lambda v: v["claims"].__setitem__("target_execution_authorized", True)),
        ("reject-remaining", lambda v: v["claims"].__setitem__("remaining_wireless_families_rejected", True)),
        ("reject-w108", lambda v: v["claims"].__setitem__("stm32w108_rejected", True)),
        ("open-wba6x-admission", lambda v: v["claims"].__setitem__("stm32wba6x_admission_ready", True)),
        ("skip-accessibility", lambda v: v.__setitem__("next_gate", "stm32wba6x-bounded-exact-icpn-discovery-gate")),
    ]
    for name, mutate in controls:
        expect_rejected(name, mutate)

    print("STM32 post-WLX wireless frontier selection: PASS")
    print("published=2 eligible=3 deferred=1 selected=STM32WBA6X")
    print(f"negative_controls={len(controls)} rejected")
    print(f"next_gate={NEXT_GATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

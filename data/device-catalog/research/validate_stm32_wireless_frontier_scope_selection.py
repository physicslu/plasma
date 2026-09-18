#!/usr/bin/env python3
"""Fail-closed validation for post-H7 STM32 wireless frontier selection."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from stm32_wireless_frontier_scope_selection import (
    NEXT_GATE,
    SELECTED,
    WIRELESS_IDS,
    build_selection,
)

HERE = Path(__file__).resolve().parent
SELECTION = HERE / "stm32-post-h7-wireless-frontier-selection.json"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def validate(value: dict) -> None:
    req(value.get("schema_version") == 1, "schema version drifted")
    req(
        value.get("selection_id") == "stm32-post-h7-wireless-frontier-selection-v1",
        "selection id drifted",
    )
    req(
        value.get("scope") == "wireless_frontier_scope_selection_research_only",
        "scope drifted",
    )
    req(
        value.get("status") == "selected_for_bounded_manufacturer_evidence_only",
        "status drifted",
    )

    production = value.get("production_boundary") or {}
    req(production.get("exact_icpns") == 2509, "post-H7 Production exact count drifted")
    req(production.get("families") == 18, "post-H7 Production family count drifted")
    req(production.get("stm32h7rs_published") is True, "STM32H7RS publication missing")
    req(production.get("stm32h7_published") is True, "STM32H7 publication missing")
    req(production.get("stm32h7rs_exact_icpns") == 36, "STM32H7RS Production rows drifted")
    req(production.get("stm32h7_exact_icpns") == 191, "STM32H7 Production rows drifted")
    req(
        production.get("standard_nonwireless_frontier_exhausted") is True,
        "non-wireless frontier unexpectedly reopened",
    )
    req(
        production.get("frozen_manifest_git_blob_sha")
        == "3b59475ad7a45710e9015a8d1cfbb38d8dee7ece",
        "frozen post-H7 Production blob drifted",
    )

    upstream = value.get("upstream") or {}
    req(
        upstream.get("post_u5_frontier_selection_id")
        == "stm32-post-u5-frontier-selection-v1",
        "post-U5 frontier identity drifted",
    )
    req(
        upstream.get("post_u5_frontier_git_blob_sha")
        == "712e1162fba526d88d92e61e3b979e0b1a69f876",
        "post-U5 frontier blob drifted",
    )
    req(
        upstream.get("cross_family_prioritization_id")
        == "stm32-cross-family-prioritization-v1",
        "cross-family prioritization identity drifted",
    )
    req(
        upstream.get("cross_family_prioritization_git_blob_sha")
        == "f445bc7938eee1a0453fcebe6bf81d77879aeaca",
        "cross-family prioritization blob drifted",
    )
    req(upstream.get("wireless_backlog_count") == 6, "wireless backlog count drifted")

    policy = value.get("selection_policy") or {}
    req(policy.get("sequencing_only") is True, "wireless selection ceased to be sequencing-only")
    req(
        policy.get("sequencing")
        == [
            "fewest row_count",
            "then fewest subfamily_count",
            "then lexical plasma_series",
        ],
        "wireless sequencing policy drifted",
    )

    eligible = value.get("eligible_wireless_frontiers")
    req(isinstance(eligible, list), "eligible wireless frontier list missing")
    req(
        [item.get("plasma_series") for item in eligible]
        == ["STM32WBA2X", "STM32WLX", "STM32WBA6X", "STM32WBX", "STM32WBA5X"],
        "eligible wireless order drifted",
    )
    req(
        [(item.get("row_count"), item.get("subfamily_count")) for item in eligible]
        == [(8, 2), (17, 4), (19, 5), (23, 8), (34, 5)],
        "eligible wireless sizing drifted",
    )
    req(
        all(item.get("structural_gate_pass") is True for item in eligible),
        "structurally ineligible wireless family admitted to eligible list",
    )
    req(
        all(item.get("complete_mapping_metadata") is True for item in eligible),
        "wireless mapping metadata completeness drifted",
    )
    req(
        all(len(item.get("target_configs") or []) == 1 for item in eligible),
        "wireless target-config cardinality drifted",
    )

    deferred = value.get("deferred_wireless_frontiers")
    req(isinstance(deferred, list) and len(deferred) == 1, "deferred wireless list drifted")
    w108 = deferred[0]
    req(w108.get("plasma_series") == "STM32W108", "STM32W108 deferred identity drifted")
    req(w108.get("structural_gate_pass") is False, "STM32W108 structural boundary opened")
    req(
        w108.get("defer_reasons")
        == ["structural_gate_fail", "no_bounded_subfamilies", "no_ordering_pattern_rows"],
        "STM32W108 defer reasons drifted",
    )

    req(value.get("selected_wireless_frontier") == SELECTED, "selected wireless frontier drifted")
    req(value.get("selected_target_config") == "tcl/target/stm32wba2x.cfg", "selected target config drifted")
    req(value.get("selected_row_count") == 8, "selected row count drifted")
    req(value.get("selected_subfamily_count") == 2, "selected subfamily count drifted")
    req(
        value.get("selected_subfamilies") == ["STM32WBA23", "STM32WBA25"],
        "selected subfamilies drifted",
    )
    req(
        value.get("selected_identifier_kind_counts")
        == {"cmsis_device_name": 4, "ordering_pattern": 4},
        "selected identifier mix drifted",
    )
    req(value.get("next_gate") == NEXT_GATE, "next gate drifted")

    claims = value.get("claims") or {}
    expected_claims = (
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
        "stm32wba2x_admission_ready",
    )
    req(set(claims) == set(expected_claims), "wireless claim surface drifted")
    for key in expected_claims:
        req(claims.get(key) is False, f"fail-closed wireless claim opened: {key}")

    all_ids = {
        item.get("plasma_series") for item in eligible
    } | {
        item.get("plasma_series") for item in deferred
    }
    req(all_ids == set(WIRELESS_IDS), "wireless frontier coverage drifted")


def expect_rejected(name: str, mutate) -> None:
    candidate = copy.deepcopy(json.loads(SELECTION.read_text(encoding="utf-8")))
    mutate(candidate)
    try:
        validate(candidate)
    except AssertionError:
        return
    raise AssertionError(f"negative control was accepted: {name}")


def main() -> int:
    frozen = json.loads(SELECTION.read_text(encoding="utf-8"))
    validate(frozen)
    req(build_selection() == frozen, "wireless frontier selection does not deterministically replay")

    controls = [
        ("select-wlx", lambda v: v.__setitem__("selected_wireless_frontier", "STM32WLX")),
        ("select-w108", lambda v: v.__setitem__("selected_wireless_frontier", "STM32W108")),
        ("wrong-target-config", lambda v: v.__setitem__("selected_target_config", "tcl/target/stm32wlx.cfg")),
        ("inflate-selected-rows", lambda v: v.__setitem__("selected_row_count", 17)),
        ("drop-h7-publication", lambda v: v["production_boundary"].__setitem__("stm32h7_published", False)),
        ("reopen-nonwireless", lambda v: v["production_boundary"].__setitem__("standard_nonwireless_frontier_exhausted", False)),
        ("mark-w108-structural-pass", lambda v: v["deferred_wireless_frontiers"][0].__setitem__("structural_gate_pass", True)),
        ("authorize-production", lambda v: v["claims"].__setitem__("production_write_authorized", True)),
        ("claim-exact-discovery", lambda v: v["claims"].__setitem__("exact_icpn_discovery_completed", True)),
        ("authorize-admission", lambda v: v["claims"].__setitem__("icpn_admission_authorized", True)),
        ("authorize-radio", lambda v: v["claims"].__setitem__("wireless_radio_operation_authorized", True)),
        ("authorize-security", lambda v: v["claims"].__setitem__("wireless_security_operation_authorized", True)),
        ("authorize-target-execution", lambda v: v["claims"].__setitem__("target_execution_authorized", True)),
        ("reject-remaining-wireless", lambda v: v["claims"].__setitem__("remaining_wireless_families_rejected", True)),
        ("reject-w108", lambda v: v["claims"].__setitem__("stm32w108_rejected", True)),
        ("open-wba2x-admission", lambda v: v["claims"].__setitem__("stm32wba2x_admission_ready", True)),
        ("skip-accessibility-gate", lambda v: v.__setitem__("next_gate", "stm32wba2x-bounded-exact-icpn-discovery-gate")),
    ]
    for name, mutate in controls:
        expect_rejected(name, mutate)

    print("STM32 post-H7 wireless frontier selection: PASS")
    print("wireless_backlog=6 eligible=5 deferred=1")
    print("selected=STM32WBA2X rows=8 subfamilies=2 target=tcl/target/stm32wba2x.cfg")
    print(f"negative_controls={len(controls)} rejected")
    print(f"next_gate={NEXT_GATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

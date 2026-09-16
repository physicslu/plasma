#!/usr/bin/env python3
"""Validate the frozen post-U5 STM32 frontier selection."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from stm32_post_u5_frontier_selection import NEXT_GATE, build_selection

HERE = Path(__file__).resolve().parent
SELECTION = HERE / "stm32-post-u5-frontier-selection.json"


def req(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def validate(value: dict) -> None:
    req(value.get("schema_version") == 1, "schema version drifted")
    req(value.get("selection_id") == "stm32-post-u5-frontier-selection-v1", "selection id drifted")
    req(value.get("scope") == "next_frontier_research_only", "scope drifted")
    req(value.get("status") == "selected_for_partitioning_only", "selection status drifted")
    req(value.get("selected_next_research_frontier") == "STM32H7", "next frontier drifted")
    req(value.get("next_gate") == NEXT_GATE, "next gate drifted")

    production = value.get("production_boundary") or {}
    req(production.get("exact_icpns") == 2282, "post-U5 Production exact count drifted")
    req(production.get("families") == 16, "post-U5 Production family count drifted")
    req(production.get("stm32u5_published") is True, "STM32U5 publication boundary missing")
    req(production.get("source_production_manifest_sha256") == "3fbab3198e813580e29c3388a9027d1993a44a6d66ec73349ad20da708cc66af", "source Production digest drifted")

    policy = value.get("upstream_policy") or {}
    req(policy.get("policy_id") == "stm32-cross-family-prioritization-v1", "upstream policy drifted")
    req(policy.get("standard_nonwireless_shortlist_exhausted") is True, "standard shortlist unexpectedly open")

    h7 = value.get("stm32h7_frontier") or {}
    req(h7.get("row_count") == 200, "STM32H7 row count drifted")
    req(h7.get("ordering_pattern_rows") == 168, "STM32H7 ordering-pattern count drifted")
    req(h7.get("cmsis_device_name_rows") == 32, "STM32H7 CMSIS count drifted")
    req(h7.get("subfamily_count") == 20, "STM32H7 subfamily count drifted")
    req(h7.get("target_configs") == ["tcl/target/stm32h7rsx.cfg", "tcl/target/stm32h7x.cfg"], "STM32H7 target-config partition drifted")
    req(h7.get("cohort") == "high_complexity_requires_partitioned_scope", "STM32H7 cohort drifted")
    req(h7.get("structural_gate_pass") is False, "STM32H7 incorrectly became structurally admission-ready")
    req(h7.get("shortlist_eligible") is False, "STM32H7 incorrectly entered standard shortlist")

    wireless = value.get("wireless_frontier_backlog") or []
    req(len(wireless) == 6, "wireless frontier count drifted")
    req([item.get("plasma_series") for item in wireless] == ["STM32W108", "STM32WBA2X", "STM32WBA5X", "STM32WBA6X", "STM32WBX", "STM32WLX"], "wireless frontier identity drifted")
    req(all(item.get("cohort") == "wireless_requires_dedicated_scope" for item in wireless), "wireless scope classification drifted")

    claims = value.get("claims") or {}
    for key in (
        "production_write_authorized",
        "icpn_admission_authorized",
        "exact_icpn_claimed_from_openocd",
        "programming_algorithm_equivalence_claimed",
        "runtime_programming_support_claimed",
        "physical_validation_claimed",
        "hil_required_for_catalog_admission",
        "wireless_family_rejected",
        "stm32h7_admission_ready",
    ):
        req(claims.get(key) is False, f"unsafe frontier claim enabled: {key}")


def expect_rejected(name: str, value: dict) -> None:
    try:
        validate(value)
    except SystemExit:
        return
    raise SystemExit(f"negative control admitted: {name}")


def main() -> int:
    rendered = build_selection()
    checked = json.loads(SELECTION.read_text(encoding="utf-8"))
    req(checked == rendered, "checked-in post-U5 frontier selection differs from deterministic replay")
    validate(checked)

    controls = []
    x = copy.deepcopy(checked); x["selected_next_research_frontier"] = "STM32WBA5X"; controls.append(("wireless selected as standard frontier", x))
    x = copy.deepcopy(checked); x["stm32h7_frontier"]["structural_gate_pass"] = True; controls.append(("H7 structural fail-open", x))
    x = copy.deepcopy(checked); x["claims"]["icpn_admission_authorized"] = True; controls.append(("premature ICPN admission", x))
    x = copy.deepcopy(checked); x["claims"]["runtime_programming_support_claimed"] = True; controls.append(("premature runtime support", x))
    x = copy.deepcopy(checked); x["claims"]["hil_required_for_catalog_admission"] = True; controls.append(("HIL catalog coupling", x))
    x = copy.deepcopy(checked); x["claims"]["wireless_family_rejected"] = True; controls.append(("wireless incorrectly rejected", x))
    x = copy.deepcopy(checked); x["next_gate"] = "stm32h7-production-publication-gate"; controls.append(("partition gate bypass", x))
    for name, mutated in controls:
        expect_rejected(name, mutated)

    print("STM32 post-U5 frontier selection validation: PASS")
    print("production_exact_icpns=2282")
    print("production_families=16")
    print("standard_nonwireless_shortlist_exhausted=true")
    print("selected_next_research_frontier=STM32H7")
    print("stm32h7_target_configs=2")
    print("wireless_frontier_backlog=6")
    print("negative_controls_rejected=7")
    print(f"next_gate={NEXT_GATE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

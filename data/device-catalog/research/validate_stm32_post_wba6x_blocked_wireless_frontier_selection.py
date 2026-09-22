#!/usr/bin/env python3
"""Fail-closed validator for wireless reselection after blocked STM32WBA6X evidence."""
from __future__ import annotations

import copy
import json
from pathlib import Path

from stm32_post_wba6x_blocked_wireless_frontier_selection import NEXT_GATE, SELECTED, build_selection

HERE = Path(__file__).resolve().parent
SELECTION = HERE / "stm32-post-wba6x-blocked-wireless-frontier-selection.json"

def req(ok: bool, message: str) -> None:
    if not ok:
        raise AssertionError(message)

def validate(v: dict) -> None:
    req(v.get("selection_id") == "stm32-post-wba6x-evidence-block-wireless-frontier-selection-v1", "selection id drifted")
    req(v.get("scope") == "wireless_frontier_reselection_research_only", "scope drifted")
    prod = v.get("production_boundary") or {}
    req(prod.get("exact_icpns") == 2554 and prod.get("families") == 20, "Production boundary drifted")
    req(prod.get("published_wireless_families") == {"STM32WBA2X": 14, "STM32WLX": 31}, "published wireless boundary drifted")

    upstream = v.get("upstream") or {}
    req(upstream.get("blocked_frontier") == "STM32WBA6X", "blocked frontier drifted")
    req(upstream.get("blocked_evidence_decision") == "defer_frontier_pending_official_product_evidence", "block decision drifted")
    req(upstream.get("remaining_structurally_eligible_count") == 2, "remaining eligible count drifted")
    req(upstream.get("deferred_wireless_count") == 2, "deferred count drifted")

    eligible = v.get("eligible_wireless_frontiers")
    req(isinstance(eligible, list), "eligible list missing")
    req([x.get("plasma_series") for x in eligible] == ["STM32WBX", "STM32WBA5X"], "eligible order drifted")
    req([(x.get("row_count"), x.get("subfamily_count")) for x in eligible] == [(23, 8), (34, 5)], "eligible sizing drifted")

    deferred = v.get("deferred_wireless_frontiers")
    req(isinstance(deferred, list) and len(deferred) == 2, "deferred list drifted")
    by_id = {x.get("plasma_series"): x for x in deferred}
    req(set(by_id) == {"STM32W108", "STM32WBA6X"}, "deferred identities drifted")
    req(by_id["STM32WBA6X"].get("defer_reasons") == ["official_st_evidence_incomplete", "stm32wba6m_product_page_http_404"], "WBA6X defer reasons drifted")
    req(by_id["STM32WBA6X"].get("evidence_gate_decision") == "defer_frontier_pending_official_product_evidence", "WBA6X gate link drifted")
    req(by_id["STM32W108"].get("structural_gate_pass") is False, "W108 defer boundary opened")

    req(v.get("selected_wireless_frontier") == SELECTED == "STM32WBX", "selected frontier drifted")
    req(v.get("selected_target_config") == "tcl/target/stm32wbx.cfg", "selected target drifted")
    req(v.get("selected_row_count") == 23, "selected row count drifted")
    req(v.get("selected_subfamily_count") == 8, "selected subfamily count drifted")
    req(v.get("selected_subfamilies") == ["STM32WB10","STM32WB15","STM32WB1M","STM32WB30","STM32WB35","STM32WB50","STM32WB55","STM32WB5M"], "selected subfamilies drifted")
    req(v.get("selected_identifier_kind_counts") == {"cmsis_device_name": 4, "ordering_pattern": 19}, "selected identifier mix drifted")
    req(v.get("next_gate") == NEXT_GATE, "next gate drifted")

    claims = v.get("claims") or {}
    req(claims.get("stm32wba6x_rejected") is False, "deferred WBA6X was rejected")
    req(claims.get("stm32w108_rejected") is False, "deferred W108 was rejected")
    req(claims.get("stm32wbx_admission_ready") is False, "WBX admission prematurely opened")
    req(all(value is False for value in claims.values()), "fail-closed claim escaped")

def expect_reject(name: str, mutate) -> None:
    v = copy.deepcopy(json.loads(SELECTION.read_text(encoding="utf-8")))
    mutate(v)
    try:
        validate(v)
    except AssertionError:
        return
    raise AssertionError(f"negative control accepted: {name}")

def main() -> int:
    frozen = json.loads(SELECTION.read_text(encoding="utf-8"))
    validate(frozen)
    req(build_selection() == frozen, "selection is not deterministic replay")
    controls = [
        ("reselect-blocked-wba6x", lambda v: v.__setitem__("selected_wireless_frontier", "STM32WBA6X")),
        ("select-wba5x", lambda v: v.__setitem__("selected_wireless_frontier", "STM32WBA5X")),
        ("drop-wba6x-defer", lambda v: v.__setitem__("deferred_wireless_frontiers", [v["deferred_wireless_frontiers"][0]])),
        ("reject-wba6x", lambda v: v["claims"].__setitem__("stm32wba6x_rejected", True)),
        ("authorize-production", lambda v: v["claims"].__setitem__("production_write_authorized", True)),
        ("open-wbx-admission", lambda v: v["claims"].__setitem__("stm32wbx_admission_ready", True)),
        ("skip-accessibility", lambda v: v.__setitem__("next_gate", "stm32wbx-bounded-exact-icpn-discovery-gate")),
    ]
    for name, mutate in controls:
        expect_reject(name, mutate)
    print("STM32 post-WBA6X-block wireless frontier selection: PASS")
    print("published=2 eligible=2 deferred=2 selected=STM32WBX")
    print(f"negative_controls={len(controls)} rejected")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

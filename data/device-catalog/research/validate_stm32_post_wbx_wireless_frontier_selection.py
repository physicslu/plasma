#!/usr/bin/env python3
"""Validate post-STM32WBX wireless frontier selection."""
from __future__ import annotations
import json
from pathlib import Path
from stm32_post_wbx_wireless_frontier_selection import render, SELECTED, NEXT_GATE

HERE=Path(__file__).resolve().parent
OUT=HERE/"stm32-post-wbx-wireless-frontier-selection.json"

def req(ok: bool, msg: str) -> None:
    if not ok: raise SystemExit(msg)

def validate(v: dict) -> None:
    prod=v.get("production_boundary") or {}
    req(prod.get("exact_icpns")==2604 and prod.get("families")==21, "Production boundary drifted")
    req(prod.get("published_wireless_families")=={"STM32WBA2X":14,"STM32WLX":31,"STM32WBX":50}, "published wireless boundary drifted")
    upstream=v.get("upstream") or {}
    req(upstream.get("published_wireless_count")==3, "published count drifted")
    req(upstream.get("remaining_structurally_eligible_count")==1, "remaining eligible count drifted")
    req(upstream.get("deferred_wireless_count")==2, "deferred count drifted")
    eligible=v.get("eligible_wireless_frontiers")
    req(isinstance(eligible,list) and len(eligible)==1 and eligible[0].get("plasma_series")=="STM32WBA5X", "eligible frontier drifted")
    req((eligible[0].get("row_count"),eligible[0].get("subfamily_count"))==(34,5), "eligible sizing drifted")
    deferred=v.get("deferred_wireless_frontiers")
    req(isinstance(deferred,list) and {x.get("plasma_series") for x in deferred}=={"STM32W108","STM32WBA6X"}, "deferred identities drifted")
    published=v.get("already_published_wireless_frontiers")
    req(isinstance(published,list) and [x.get("plasma_series") for x in published]==["STM32WBA2X","STM32WLX","STM32WBX"], "published frontier list drifted")
    req(published[-1].get("production_row_count")==50, "WBX production count drifted")
    req(v.get("selected_wireless_frontier")==SELECTED=="STM32WBA5X", "selected frontier drifted")
    req(v.get("selected_target_config")=="tcl/target/stm32wba5x.cfg", "selected target drifted")
    req(v.get("selected_row_count")==34 and v.get("selected_subfamily_count")==5, "selected sizing drifted")
    req(v.get("selected_subfamilies")==["STM32WBA50","STM32WBA52","STM32WBA54","STM32WBA55","STM32WBA5M"], "selected subfamilies drifted")
    req(v.get("selected_identifier_kind_counts")=={"cmsis_device_name":17,"ordering_pattern":17}, "identifier mix drifted")
    req(v.get("next_gate")==NEXT_GATE, "next gate drifted")
    claims=v.get("claims") or {}
    req(claims.get("stm32wba6x_rejected") is False and claims.get("stm32w108_rejected") is False, "deferred frontier rejection escaped")
    req(claims.get("stm32wba5x_admission_ready") is False, "WBA5X admission prematurely opened")
    req(all(value is False for value in claims.values()), "fail-closed claim escaped")

def main() -> int:
    checked=json.loads(OUT.read_text(encoding="utf-8"))
    expected=render()
    req(checked==expected, "checked-in selection differs from deterministic renderer")
    validate(checked)
    print("STM32 post-WBX wireless frontier selection: PASS")
    print("published=3 eligible=1 deferred=2 selected=STM32WBA5X")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

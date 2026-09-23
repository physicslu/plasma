#!/usr/bin/env python3
"""Validate current STM32 wireless frontier exhaustion state."""
from __future__ import annotations
import json
from pathlib import Path
from stm32_wireless_frontier_exhaustion import render

HERE=Path(__file__).resolve().parent
OUT=HERE/"stm32-wireless-frontier-exhaustion.json"

def req(ok: bool,msg: str)->None:
    if not ok: raise SystemExit(msg)

def main()->int:
    checked=json.loads(OUT.read_text(encoding="utf-8"))
    expected=render()
    req(checked==expected,"checked-in exhaustion report differs from deterministic renderer")
    req(checked.get("status")=="no_currently_eligible_wireless_frontier","status drifted")
    prod=checked.get("production_boundary") or {}
    req(prod.get("exact_icpns")==2604 and prod.get("families")==21,"Production boundary drifted")
    req(prod.get("published_wireless_families")=={"STM32WBA2X":14,"STM32WLX":31,"STM32WBX":50},"published wireless boundary drifted")
    req(checked.get("eligible_wireless_frontiers")==[],"eligible frontier unexpectedly reopened")
    req(checked.get("selected_wireless_frontier") is None,"frontier unexpectedly selected")
    req(checked.get("next_gate") is None,"next gate unexpectedly opened")
    deferred=checked.get("deferred_wireless_frontiers")
    req(isinstance(deferred,list) and {x.get("plasma_series") for x in deferred}=={"STM32W108","STM32WBA6X","STM32WBA5X"},"deferred frontier set drifted")
    blockers=checked.get("current_blockers")
    req(isinstance(blockers,list) and len(blockers)==3,"blocker set drifted")
    req(any(x.get("base_device")=="STM32WBA50KE" and x.get("blocker")=="official_st_product_page_http_404" for x in blockers),"WBA5X blocker drifted")
    req(any(x.get("base_device")=="STM32WBA6MOI" and x.get("blocker")=="official_st_product_page_http_404" for x in blockers),"WBA6X blocker drifted")
    claims=checked.get("claims") or {}
    req(claims and all(v is False for v in claims.values()),"fail-closed claim escaped")
    print("STM32 wireless frontier exhaustion validation: PASS")
    print("Production=2604/21 published_wireless=3 eligible=0 deferred=3")
    print("blockers=STM32WBA50KE:404,STM32WBA6MOI:404,STM32W108:structural")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

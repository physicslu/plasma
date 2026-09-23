#!/usr/bin/env python3
"""Validate STM32WBA5X current commercial-scope reconciliation."""
from __future__ import annotations
import json
from pathlib import Path
from stm32wba5x_commercial_scope_reconciliation import render

HERE=Path(__file__).resolve().parent
OUT=HERE/"stm32wba5x-commercial-scope-reconciliation.json"

def req(ok: bool,msg: str)->None:
    if not ok: raise SystemExit(msg)

def main()->int:
    checked=json.loads(OUT.read_text(encoding="utf-8"))
    expected=render()
    req(checked==expected,"checked-in reconciliation differs from deterministic renderer")
    req(checked.get("decision")=="current_commercial_scope_reconciled","decision drifted")
    source=checked.get("source_surface") or {}
    reconciled=checked.get("reconciled_surface") or {}
    req(source.get("source_rows")==34,"source row count drifted")
    req(reconciled.get("retained_rows")==32,"retained row count drifted")
    req(reconciled.get("ordering_pattern_rows")==16 and reconciled.get("cmsis_device_name_rows")==16,"reconciled identifier mix drifted")
    req(reconciled.get("base_device_count")==16,"Base Device count drifted")
    excluded=checked.get("excluded_research_candidates")
    req(isinstance(excluded,list) and {(x.get("part_number"),x.get("identifier_kind")) for x in excluded}=={
        ("STM32WBA50KEUx","ordering_pattern"),("STM32WBA50KEUxT","cmsis_device_name")
    },"excluded candidate set drifted")
    evidence=checked.get("official_manufacturer_evidence") or {}
    req(evidence.get("document")=="DS14688" and evidence.get("revision")=="Rev 2","datasheet authority drifted")
    req(evidence.get("ordering_example")=="STM32 WBA50 K G U 6 TR","ordering semantics drifted")
    req(evidence.get("observed_active_exact_icpns")==["STM32WBA50KGU6","STM32WBA50KGU6TR"],"WBA50KG exact identities drifted")
    req(checked.get("next_gate")=="stm32wba5x-bounded-exact-icpn-discovery-gate","discovery gate drifted")
    claims=checked.get("claims") or {}
    req(claims and all(v is False for v in claims.values()),"fail-closed claim escaped")
    print("STM32WBA5X current commercial-scope reconciliation: PASS")
    print("source=34 retained=32 excluded=2 ordering=16 cmsis=16 bases=16")
    print("excluded=STM32WBA50KEUx,STM32WBA50KEUxT next=exact-discovery")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

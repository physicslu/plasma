#!/usr/bin/env python3
"""Exact-scope backend evolution helper for the v6.30 STM32L4 tail closure."""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

HERE=Path(__file__).resolve().parent
POLICY=HERE/"openocd-tier-a-tail-write-v6.30.json"
BACKEND_FIELDS=(
    "cmsis_device_name","existing_identifier","existing_identifier_kind",
    "mapping_status","openocd_target_config",
)

class BackendEvolutionError(RuntimeError):
    pass

def _policy()->dict:
    p=json.loads(POLICY.read_text(encoding="utf-8"))
    if p["transaction_id"]!="openocd-tier-a-tail-write-v6.30":
        raise BackendEvolutionError("v6.30 policy identity drift")
    if p["l4"]["exact_icpns"]!=["STM32L496WGY6PST","STM32L496WGY6PTR"]:
        raise BackendEvolutionError("v6.30 L4 exact scope drift")
    return p

def bindings()->dict[str,dict[str,str]]:
    p=_policy()["l4"]
    out={}
    for icpn in p["exact_icpns"]:
        out[icpn]={
            "family":"STM32L4",
            "cmsis_device_name":p["route_identifier"],
            "existing_identifier":p["route_identifier"],
            "existing_identifier_kind":p["route_identifier_kind"],
            "mapping_status":p["mapping_status"],
            "openocd_target_config":p["target_config"],
        }
    return out

def _is_pre(row:Mapping[str,str])->bool:
    return (
        row.get("cmsis_device_name","")=="" and
        row.get("existing_identifier","")=="" and
        row.get("existing_identifier_kind","")=="" and
        row.get("mapping_status","")=="no_mapping" and
        row.get("openocd_target_config","")==""
    )

def _is_post(row:Mapping[str,str],binding:Mapping[str,str])->bool:
    return row.get("family")==binding["family"] and all(
        row.get(field,"")==binding[field] for field in BACKEND_FIELDS
    )

def backend_state(rows:Iterable[Mapping[str,str]],family:str)->str:
    if family!="STM32L4":
        return "not_applicable"
    current=[dict(r) for r in rows]
    by={r.get("icpn",""):r for r in current}
    expected=bindings()
    missing=set(expected)-set(by)
    if missing:
        raise BackendEvolutionError(f"STM32L4 v6.30 rows missing: {sorted(missing)}")
    states=set()
    for icpn,binding in expected.items():
        row=by[icpn]
        if _is_pre(row):
            states.add("pre")
        elif _is_post(row,binding):
            states.add("post")
        else:
            raise BackendEvolutionError(f"{icpn}: invalid partial/non-frozen v6.30 backend state")
    if len(states)!=1:
        raise BackendEvolutionError(f"v6.30 mixed application detected: {sorted(states)}")
    return states.pop()

def rewind_v630_backend(rows:Iterable[Mapping[str,str]],family:str)->list[dict[str,str]]:
    current=[dict(r) for r in rows]
    state=backend_state(current,family)
    if state in ("pre","not_applicable"):
        return current
    exact=set(bindings())
    out=[]
    for row in current:
        historical=dict(row)
        if historical.get("icpn") in exact:
            historical["cmsis_device_name"]=""
            historical["existing_identifier"]=""
            historical["existing_identifier_kind"]=""
            historical["mapping_status"]="no_mapping"
            historical["openocd_target_config"]=""
        out.append(historical)
    return out

#!/usr/bin/env python3
"""Exact-scope compatibility helper for v6.31 backend evolution.

The v6.31 transaction promotes exactly 103 current no_mapping rows across
STM32F3/STM32F7/STM32G4. Historical validators may rewind these backend-only
fields after first validating that the current state is either the complete
pre-v6.31 state or the complete frozen v6.31 poststate for that family.
"""
from __future__ import annotations

import csv,hashlib
from collections import Counter
from collections.abc import Iterable,Mapping
from pathlib import Path

HERE=Path(__file__).resolve().parent
BINDINGS=HERE/"openocd-final-safe-bindings-v6.31.csv"

BACKEND_FIELDS=(
    "cmsis_device_name","existing_identifier","existing_identifier_kind",
    "mapping_status","openocd_target_config",
)
EXPECTED_EXACT_COUNT=103
EXPECTED_FAMILY_COUNTS={"STM32F3":10,"STM32F7":92,"STM32G4":1}
EXPECTED_EXACT_SET_SHA256="fb6de43b35e386c68cb9d903f57758f928006e733bf8feb7f036fb69c105aec8"
EXPECTED_BINDINGS_SHA256="47dce542995d32ec5472b9bb46d632751aeb37835c21504f06e13f8a54c8917c"

class BackendEvolutionError(RuntimeError):
    pass

def _load()->dict[str,dict[str,str]]:
    raw=BINDINGS.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=EXPECTED_BINDINGS_SHA256:
        raise BackendEvolutionError("v6.31 binding CSV SHA drift")
    with BINDINGS.open(newline="",encoding="utf-8") as h:
        rows=list(csv.DictReader(h))
    if len(rows)!=EXPECTED_EXACT_COUNT:
        raise BackendEvolutionError("v6.31 binding cardinality drift")
    if dict(sorted(Counter(r["family"] for r in rows).items()))!=EXPECTED_FAMILY_COUNTS:
        raise BackendEvolutionError("v6.31 family partition drift")
    digest=hashlib.sha256(("\n".join(sorted(r["icpn"] for r in rows))+"\n").encode()).hexdigest()
    if digest!=EXPECTED_EXACT_SET_SHA256:
        raise BackendEvolutionError("v6.31 exact-set digest drift")
    out={}
    for r in rows:
        out[r["icpn"]]={
            "family":r["family"],
            "cmsis_device_name":"",
            "existing_identifier":r["existing_identifier"],
            "existing_identifier_kind":r["existing_identifier_kind"],
            "mapping_status":r["mapping_status"],
            "openocd_target_config":r["openocd_target_config"],
        }
    return out

def bindings()->dict[str,dict[str,str]]:
    return _load()

def family_bindings(family:str)->dict[str,dict[str,str]]:
    return {i:b for i,b in bindings().items() if b["family"]==family}

def _is_pre(row:Mapping[str,str])->bool:
    return (
        row.get("cmsis_device_name","")=="" and
        row.get("existing_identifier","")=="" and
        row.get("existing_identifier_kind","")=="" and
        row.get("mapping_status","")=="no_mapping" and
        row.get("openocd_target_config","")==""
    )

def _is_post(row:Mapping[str,str],binding:Mapping[str,str])->bool:
    return all(row.get(f,"")==binding[f] for f in BACKEND_FIELDS)

def backend_state(rows:Iterable[Mapping[str,str]],family:str)->str:
    fb=family_bindings(family)
    if not fb:
        return "not_applicable"
    current=[dict(r) for r in rows]
    by={r.get("icpn",""):r for r in current}
    missing=set(fb)-set(by)
    if missing:
        raise BackendEvolutionError(f"{family}: missing v6.31 scoped rows: {sorted(missing)}")
    states=set()
    for icpn,b in fb.items():
        row=by[icpn]
        if row.get("family")!=family:
            raise BackendEvolutionError(f"{icpn}: family drift")
        if _is_pre(row):
            states.add("pre")
        elif _is_post(row,b):
            states.add("post")
        else:
            raise BackendEvolutionError(f"{icpn}: invalid partial/non-frozen v6.31 backend state")
    if len(states)!=1:
        raise BackendEvolutionError(f"{family}: mixed v6.31 application: {sorted(states)}")
    return states.pop()

def rewind_v631_backend(rows:Iterable[Mapping[str,str]],family:str)->list[dict[str,str]]:
    current=[dict(r) for r in rows]
    state=backend_state(current,family)
    if state in ("not_applicable","pre"):
        return current
    scoped=set(family_bindings(family))
    out=[]
    for row in current:
        historical=dict(row)
        if historical.get("icpn") in scoped:
            historical["cmsis_device_name"]=""
            historical["existing_identifier"]=""
            historical["existing_identifier_kind"]=""
            historical["mapping_status"]="no_mapping"
            historical["openocd_target_config"]=""
        out.append(historical)
    return out

#!/usr/bin/env python3
from __future__ import annotations

import csv,hashlib,io,json
from copy import deepcopy
from pathlib import Path

from openocd_backend_evolution_v631 import (
    BACKEND_FIELDS,
    backend_state,
    bindings,
    rewind_v631_backend,
)

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
POLICY=HERE/"openocd-final-production-dry-run-v6.31.json"
SAFE=HERE/"openocd-final-safe-bindings-v6.31.csv"
BLOCKED=HERE/"openocd-final-runtime-blocked-v6.31.csv"
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
ROUTE_PRE=HERE/"openocd-parts-canonical-v627.csv"
ROUTE_POST=HERE/"openocd-parts-canonical-v631.csv"

FAMILY_PATHS={
    "STM32F3":HERE/"stm32f3-commercial-icpn.csv",
    "STM32F7":HERE/"stm32f7-commercial-icpn.csv",
    "STM32G4":HERE/"stm32g4-commercial-icpn.csv",
}

def req(ok:bool,msg:str)->None:
    if not ok: raise RuntimeError(msg)

def sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()

def blob(raw:bytes)->str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii")+raw,usedforsecurity=False).hexdigest()

def parse(raw:bytes):
    with io.StringIO(raw.decode("utf-8")) as h:
        r=csv.DictReader(h);fields=list(r.fieldnames or []);rows=list(r)
    req(bool(fields),"CSV header missing")
    return fields,rows

def render(fields,rows)->bytes:
    s=io.StringIO(newline="")
    w=csv.DictWriter(s,fieldnames=fields,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return s.getvalue().encode("utf-8")

def validate()->dict:
    p=json.loads(POLICY.read_text(encoding="utf-8"))
    pre=p["production_preimages"]
    post=p["frozen_postimages"]
    req(post["lock_state"]=="FROZEN","v6.31 postimage lock lost")
    req(p["scope"]["exact_count"]==103,"v6.31 scope cardinality drift")
    req(p["scope"]["family_counts"]=={"STM32F3":10,"STM32F7":92,"STM32G4":1},
        "v6.31 family partition drift")

    safe_raw=SAFE.read_bytes()
    blocked_raw=BLOCKED.read_bytes()
    req(sha(safe_raw)==p["evidence_files"]["safe_bindings"]["sha256"],
        "safe binding evidence SHA drift")
    req(blob(safe_raw)==p["evidence_files"]["safe_bindings"]["git_blob_sha"],
        "safe binding evidence blob drift")
    req(sha(blocked_raw)==p["evidence_files"]["runtime_blocked"]["sha256"],
        "blocked evidence SHA drift")
    req(blob(blocked_raw)==p["evidence_files"]["runtime_blocked"]["git_blob_sha"],
        "blocked evidence blob drift")

    with SAFE.open(newline="",encoding="utf-8") as h:
        safe_rows=list(csv.DictReader(h))
    with BLOCKED.open(newline="",encoding="utf-8") as h:
        blocked_rows=list(csv.DictReader(h))
    req(len(safe_rows)==103,"safe binding cardinality drift")
    req(len(blocked_rows)==465,"blocked cardinality drift")
    safe_by={r["icpn"]:r for r in safe_rows}
    blocked_set={r["icpn"] for r in blocked_rows}
    req(len(safe_by)==103 and len(blocked_set)==465,"duplicate closure identities")
    req(set(safe_by).isdisjoint(blocked_set),"safe/blocked sets overlap")

    family_current={}
    family_rows={}
    family_fields={}
    states={}
    for family,path in FAMILY_PATHS.items():
        raw=path.read_bytes()
        fields,rows=parse(raw)
        family_current[family]=raw
        family_rows[family]=rows
        family_fields[family]=fields
        states[family]=backend_state(rows,family)

    req(len(set(states.values()))==1,f"cross-family partial v6.31 state: {states}")
    state=next(iter(states.values()))
    req(state in {"pre","post"},f"unexpected v6.31 state: {state}")

    # For every family, rewinding current state must reproduce exact frozen preimage bytes.
    for family in FAMILY_PATHS:
        rewound=rewind_v631_backend(family_rows[family],family)
        raw=render(family_fields[family],rewound)
        cfg=pre[family]
        req(blob(raw)==cfg["git_blob_sha"],f"{family}: inverse preimage blob drift")
        req(sha(raw)==cfg["sha256"],f"{family}: inverse preimage SHA drift")
        req(len(rewound)==cfg["row_count"],f"{family}: inverse row-count drift")

    manifest_raw=MANIFEST.read_bytes()
    manifest=json.loads(manifest_raw)
    req(len(manifest["sources"])==28,"Production source-count drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"])==4629,
        "Production exact-total drift")

    route_pre_raw=ROUTE_PRE.read_bytes()
    req(blob(route_pre_raw)==pre["ROUTE_INVENTORY"]["git_blob_sha"],
        "v627 route preimage blob drift")
    req(sha(route_pre_raw)==pre["ROUTE_INVENTORY"]["sha256"],
        "v627 route preimage SHA drift")

    if state=="pre":
        for family,raw in family_current.items():
            cfg=pre[family]
            req(blob(raw)==cfg["git_blob_sha"],f"{family}: current preimage blob drift")
            req(sha(raw)==cfg["sha256"],f"{family}: current preimage SHA drift")
        req(blob(manifest_raw)==pre["MANIFEST"]["git_blob_sha"],
            "manifest preimage blob drift")
        req(sha(manifest_raw)==pre["MANIFEST"]["sha256"],
            "manifest preimage SHA drift")
        req(not ROUTE_POST.exists(),
            "versioned v631 route successor exists before owner-authorized write")
        req(p["approval"]["owner_approval_received"] is False,
            "prewrite policy unexpectedly records owner approval")
        req(p["approval"]["route_inventory_write_authorized"] is False,
            "prewrite route write unexpectedly authorized")
        req(p["approval"]["production_write_authorized"] is False,
            "prewrite Production write unexpectedly authorized")
        req(p["write_state"]["route_inventory_write_applied"] is False,
            "prewrite policy claims route write")
        req(p["write_state"]["production_write_applied"] is False,
            "prewrite policy claims Production write")
    else:
        for family,raw in family_current.items():
            cfg=post[family]
            req(blob(raw)==cfg["git_blob_sha"],f"{family}: postimage blob drift")
            req(sha(raw)==cfg["sha256"],f"{family}: postimage SHA drift")
            req(len(raw)==cfg["byte_count"],f"{family}: postimage byte-count drift")
        req(blob(manifest_raw)==post["MANIFEST"]["git_blob_sha"],
            "manifest postimage blob drift")
        req(sha(manifest_raw)==post["MANIFEST"]["sha256"],
            "manifest postimage SHA drift")
        req(len(manifest_raw)==post["MANIFEST"]["byte_count"],
            "manifest postimage byte-count drift")
        req(ROUTE_POST.exists(),"v631 route successor missing after postwrite")
        route_post_raw=ROUTE_POST.read_bytes()
        req(blob(route_post_raw)==post["ROUTE_INVENTORY"]["git_blob_sha"],
            "v631 route successor blob drift")
        req(sha(route_post_raw)==post["ROUTE_INVENTORY"]["sha256"],
            "v631 route successor SHA drift")
        req(len(route_post_raw)==post["ROUTE_INVENTORY"]["byte_count"],
            "v631 route successor byte-count drift")
        req(p["approval"]["owner_approval_received"] is True,
            "postwrite owner approval missing")
        req(p["approval"]["route_inventory_write_authorized"] is True,
            "postwrite route authorization missing")
        req(p["approval"]["production_write_authorized"] is True,
            "postwrite Production authorization missing")
        req(p["approval"]["merge_after_green_ci_authorized"] is True,
            "postwrite merge authorization missing")
        req(p["write_state"]["route_inventory_write_applied"] is True,
            "postwrite route write receipt missing")
        req(p["write_state"]["production_write_applied"] is True,
            "postwrite Production write receipt missing")
        req(isinstance(p["write_state"]["applied_commit"],str)
            and len(p["write_state"]["applied_commit"])==40,
            "postwrite applied commit missing")

        # Invert manifest integrity updates and reproduce the exact pre-v6.31 manifest.
        old_manifest=deepcopy(manifest)
        for family in FAMILY_PATHS:
            source=next(s for s in old_manifest["sources"] if s["family"]==family)
            source["git_blob_sha"]=pre[family]["git_blob_sha"]
            source["sha256"]=pre[family]["sha256"]
        old_raw=(json.dumps(old_manifest,indent=2)+"\n").encode("utf-8")
        req(blob(old_raw)==pre["MANIFEST"]["git_blob_sha"],
            "manifest inverse preimage blob drift")
        req(sha(old_raw)==pre["MANIFEST"]["sha256"],
            "manifest inverse preimage SHA drift")

    # Manifest must bind every source to its actual current file.
    rows_by_icpn={}
    mapped=no_mapping=0
    for source in manifest["sources"]:
        path=(MANIFEST.parent/source["path"]).resolve()
        raw=path.read_bytes()
        req(blob(raw)==source["git_blob_sha"],f"{source['family']}: manifest blob binding drift")
        req(sha(raw)==source["sha256"],f"{source['family']}: manifest SHA binding drift")
        with path.open(newline="",encoding="utf-8") as h:
            rows=list(csv.DictReader(h))
        req(len(rows)==int(source["row_count"]),f"{source['family']}: row-count drift")
        for row in rows:
            req(row["icpn"] not in rows_by_icpn,f"{row['icpn']}: duplicate Production ICPN")
            rows_by_icpn[row["icpn"]]=row
            if row["mapping_status"]=="no_mapping": no_mapping+=1
            else: mapped+=1

    if state=="pre":
        req((mapped,no_mapping)==(4061,568),
            f"prewrite backend partition drift: {(mapped,no_mapping)}")
    else:
        req((mapped,no_mapping)==(4164,465),
            f"postwrite backend partition drift: {(mapped,no_mapping)}")
        expected=bindings()
        for icpn,b in expected.items():
            row=rows_by_icpn[icpn]
            for field in BACKEND_FIELDS:
                req(row[field]==b[field],f"{icpn}: {field} postwrite drift")

    # Every runtime-blocked identity must remain completely unbound in both states.
    for icpn in blocked_set:
        row=rows_by_icpn[icpn]
        req(row["mapping_status"]=="no_mapping",f"{icpn}: blocked identity became mapped")
        req(not row["cmsis_device_name"]
            and not row["existing_identifier"]
            and not row["existing_identifier_kind"]
            and not row["openocd_target_config"],
            f"{icpn}: blocked identity acquired backend fields")

    # Every safe identity is pre-unbound or exact post-bound according to the global state.
    for icpn,binding in safe_by.items():
        row=rows_by_icpn[icpn]
        if state=="pre":
            req(row["mapping_status"]=="no_mapping",f"{icpn}: prewrite safe row already mapped")
        else:
            req(row["mapping_status"]==binding["mapping_status"],f"{icpn}: mapping status drift")
            req(row["existing_identifier"]==binding["existing_identifier"],f"{icpn}: identifier drift")
            req(row["existing_identifier_kind"]==binding["existing_identifier_kind"],
                f"{icpn}: identifier kind drift")
            req(row["openocd_target_config"]==binding["openocd_target_config"],
                f"{icpn}: target config drift")

    projected=p["projected_poststate"]
    req(projected=={
        "exact_total":4629,"source_count":28,"mapped":4164,"no_mapping":465,
        "active_openocd_route":4085,"active_denominator":4550,
        "coverage_percent":89.7802,
    },"projected poststate drift")
    req(all(value is False for value in p["claims"].values()),
        "v6.31 capability overclaim")

    summary={
        "transaction_id":p["transaction_id"],
        "repository_write_state":state,
        "family_states":states,
        "safe_exact_count":103,
        "blocked_exact_count":465,
        "mapped":mapped,
        "no_mapping":no_mapping,
        "active_openocd_route":3982 if state=="pre" else 4085,
        "active_denominator":4550,
        "coverage_percent":87.5165 if state=="pre" else 89.7802,
        "approval":p["approval"],
        "write_state":p["write_state"],
        "claims":p["claims"],
    }
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_FINAL_WRITE_V631_PREWRITE_PASS" if state=="pre"
          else "OPENOCD_FINAL_WRITE_V631_POSTWRITE_PASS")
    return summary

if __name__=="__main__":
    validate()

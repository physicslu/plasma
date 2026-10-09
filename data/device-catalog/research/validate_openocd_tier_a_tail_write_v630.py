#!/usr/bin/env python3
from __future__ import annotations

import csv,hashlib,io,json
from copy import deepcopy
from pathlib import Path

from openocd_backend_evolution_v630 import BACKEND_FIELDS,backend_state,bindings,rewind_v630_backend

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
POLICY=HERE/"openocd-tier-a-tail-write-v6.30.json"
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
L4=HERE/"stm32l4-commercial-icpn.csv"
G4=HERE/"stm32g4-commercial-icpn.csv"

def req(ok:bool,msg:str)->None:
    if not ok: raise RuntimeError(msg)

def sha(raw:bytes)->str: return hashlib.sha256(raw).hexdigest()
def blob(raw:bytes)->str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw,usedforsecurity=False).hexdigest()

def parse(raw:bytes):
    with io.StringIO(raw.decode()) as s:
        r=csv.DictReader(s);fields=list(r.fieldnames or []);rows=list(r)
    return fields,rows

def render(fields,rows)->bytes:
    s=io.StringIO(newline="");w=csv.DictWriter(s,fieldnames=fields,lineterminator="\n")
    w.writeheader();w.writerows(rows);return s.getvalue().encode()

def validate()->dict:
    p=json.loads(POLICY.read_text(encoding="utf-8"))
    l4p=p["l4"];pre=p["manifest_preimage"];post=p["frozen_postimages"]
    req(post["lock_state"]=="FROZEN","v6.30 postimage lock lost")

    l4_raw=L4.read_bytes();fields,rows=parse(l4_raw)
    req(len(rows)==449,"L4 row-count drift")
    state=backend_state(rows,"STM32L4")
    historical=rewind_v630_backend(rows,"STM32L4")
    historical_raw=render(fields,historical)
    req(blob(historical_raw)==l4p["preimage_git_blob_sha"],"L4 inverse preimage blob drift")
    req(sha(historical_raw)==l4p["preimage_sha256"],"L4 inverse preimage SHA drift")

    manifest_raw=MANIFEST.read_bytes();manifest=json.loads(manifest_raw)
    src=next(s for s in manifest["sources"] if s["family"]=="STM32L4")
    req(src["row_count"]==449,"manifest L4 row-count drift")

    if state=="pre":
        req(blob(l4_raw)==l4p["preimage_git_blob_sha"],"L4 preimage blob drift")
        req(sha(l4_raw)==l4p["preimage_sha256"],"L4 preimage SHA drift")
        req(blob(manifest_raw)==pre["git_blob_sha"],"manifest preimage blob drift")
        req(p["approval"]["owner_approval_received"] is False,"prewrite approval state drift")
        req(p["write_state"]["production_write_applied"] is False,"prewrite receipt claims write")
    else:
        req(state=="post","unexpected v6.30 backend state")
        req(blob(l4_raw)==post["l4_git_blob_sha"],"L4 postimage blob drift")
        req(sha(l4_raw)==post["l4_sha256"],"L4 postimage SHA drift")
        req(len(l4_raw)==post["l4_byte_count"],"L4 postimage byte-count drift")
        req(blob(manifest_raw)==post["manifest_git_blob_sha"],"manifest postimage blob drift")
        req(sha(manifest_raw)==post["manifest_sha256"],"manifest postimage SHA drift")
        req(len(manifest_raw)==post["manifest_byte_count"],"manifest postimage byte-count drift")
        req(p["approval"]["owner_approval_received"] is True,"postwrite owner approval missing")
        req(p["approval"]["l4_production_write_authorized"] is True,"postwrite authorization missing")
        req(p["approval"]["merge_after_green_ci_authorized"] is True,"postwrite merge authorization missing")
        req(p["write_state"]["production_write_applied"] is True,"postwrite receipt missing")
        req(isinstance(p["write_state"]["applied_commit"],str) and len(p["write_state"]["applied_commit"])==40,
            "postwrite commit missing")

        inv=deepcopy(manifest)
        inv_src=next(s for s in inv["sources"] if s["family"]=="STM32L4")
        inv_src["git_blob_sha"]=l4p["preimage_git_blob_sha"]
        inv_src["sha256"]=l4p["preimage_sha256"]
        inv_raw=(json.dumps(inv,indent=2)+"\n").encode()
        req(blob(inv_raw)==pre["git_blob_sha"],"manifest inverse preimage blob drift")

    current={r["icpn"]:r for r in rows};old={r["icpn"]:r for r in historical}
    changed=[]
    for icpn,row in current.items():
        diffs={f for f in fields if row[f]!=old[icpn][f]}
        if diffs:
            req(diffs<=set(BACKEND_FIELDS),f"{icpn}: non-backend mutation: {sorted(diffs)}")
            changed.append(icpn)
    if state=="post": req(set(changed)==set(bindings()),"L4 changed exact-set drift")
    else: req(not changed,"prewrite L4 unexpectedly changed")

    # G4 must remain blocked in both states.
    _,g4rows=parse(G4.read_bytes())
    g4=next(r for r in g4rows if r["icpn"]==p["g4"]["exact_icpn"])
    req(g4["mapping_status"]=="no_mapping","G4 ambiguity escaped no_mapping")
    req(all(g4.get(f,"")=="" for f in ("cmsis_device_name","existing_identifier","existing_identifier_kind","openocd_target_config")),
        "G4 ambiguity acquired backend binding")

    mapped=no_mapping=0
    for source in manifest["sources"]:
        path=(MANIFEST.parent/source["path"]).resolve();raw=path.read_bytes()
        req(blob(raw)==source["git_blob_sha"],f"{source['family']}: manifest blob binding drift")
        req(sha(raw)==source["sha256"],f"{source['family']}: manifest SHA binding drift")
        with path.open(newline="",encoding="utf-8") as h:
            family_rows=list(csv.DictReader(h))
        req(len(family_rows)==source["row_count"],f"{source['family']}: row count drift")
        for row in family_rows:
            if row["mapping_status"]=="no_mapping": no_mapping+=1
            else: mapped+=1

    expected=p["projected_poststate_if_l4_approved"]
    if state=="pre":
        req((mapped,no_mapping)==(4059,570),f"prestate partition drift: {(mapped,no_mapping)}")
    else:
        req((mapped,no_mapping)==(4061,568),f"poststate partition drift: {(mapped,no_mapping)}")
        for icpn,b in bindings().items():
            row=current[icpn]
            for f in BACKEND_FIELDS: req(row[f]==b[f],f"{icpn}: {f} drift")

    req(sum(int(s["row_count"]) for s in manifest["sources"])==4629,"Production exact total drift")
    req(len(manifest["sources"])==28,"Production source count drift")

    summary={
      "transaction_id":p["transaction_id"],"repository_write_state":state,
      "l4_changed_exact_count":len(changed),"mapped":mapped,"no_mapping":no_mapping,
      "l4_current_git_blob_sha":blob(l4_raw),"manifest_current_git_blob_sha":blob(manifest_raw),
      "inverse_l4_preimage_git_blob_sha":blob(historical_raw),
      "g4_state":"BLOCKED_NO_CANONICAL_PACKAGE_ROUTE",
      "poststate_if_l4_approved":expected,"approval":p["approval"],"write_state":p["write_state"],
      "claims":p["claims"],
    }
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_TIER_A_TAIL_V630_PREWRITE_PASS" if state=="pre" else "OPENOCD_TIER_A_TAIL_V630_POSTWRITE_PASS")
    return summary

if __name__=="__main__": validate()

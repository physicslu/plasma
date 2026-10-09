#!/usr/bin/env python3
from __future__ import annotations

import argparse,csv,hashlib,io,json,re
from copy import deepcopy
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
POLICY=HERE/"openocd-tier-a-tail-write-v6.30.json"
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
L4=HERE/"stm32l4-commercial-icpn.csv"
G4=HERE/"stm32g4-commercial-icpn.csv"
ROUTES=HERE/"openocd-parts-canonical-v627.csv"
G4_AUTH=HERE/"stm32g4-ordering-authority-v2.0.json"

BACKEND_FIELDS=(
    "cmsis_device_name","existing_identifier","existing_identifier_kind",
    "mapping_status","openocd_target_config",
)

def req(ok:bool,msg:str)->None:
    if not ok: raise RuntimeError(msg)

def sha256(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()

def blob(raw:bytes)->str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode()+raw,usedforsecurity=False).hexdigest()

def read_csv(path:Path):
    raw=path.read_bytes()
    with io.StringIO(raw.decode("utf-8")) as s:
        r=csv.DictReader(s); fields=list(r.fieldnames or []); rows=list(r)
    req(bool(fields),f"{path.name}: missing CSV header")
    return raw,fields,rows

def render(fields:list[str],rows:list[dict[str,str]])->bytes:
    s=io.StringIO(newline="")
    w=csv.DictWriter(s,fieldnames=fields,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return s.getvalue().encode()

def match(pattern:str,value:str)->bool:
    expr="".join("[A-Z0-9]" if c=="x" else re.escape(c) for c in pattern)
    return re.fullmatch(expr,value) is not None

def normalize_exact(icpn:str)->str:
    allowed={
        "STM32L496WGY6PTR":"TR",
        "STM32L496WGY6PST":"ST",
    }
    suffix=allowed.get(icpn)
    req(suffix is not None,f"{icpn}: outside bounded normalization scope")
    req(icpn.endswith(suffix),f"{icpn}: bounded packing suffix drift")
    return icpn[:-len(suffix)]

def build():
    p=json.loads(POLICY.read_text(encoding="utf-8"))
    l4p=p["l4"];g4p=p["g4"];pre=p["manifest_preimage"]

    route_raw,route_fields,routes=read_csv(ROUTES)
    req(blob(route_raw)==l4p["route_inventory_git_blob_sha"],"route inventory blob drift")
    req(sha256(route_raw)==l4p["route_inventory_sha256"],"route inventory SHA drift")
    matches=[r for r in routes if r["vendor"]=="STMicroelectronics" and r["part_number"]==l4p["route_identifier"]]
    req(len(matches)==1,"L4 route identifier missing/duplicated")
    route=matches[0]
    req(route["identifier_kind"]==l4p["route_identifier_kind"],"L4 route kind drift")
    req(route["target_config"]==l4p["target_config"],"L4 target drift")

    l4_raw,l4_fields,l4_rows=read_csv(L4)
    req(blob(l4_raw)==l4p["preimage_git_blob_sha"],"L4 preimage blob drift")
    req(sha256(l4_raw)==l4p["preimage_sha256"],"L4 preimage SHA drift")
    req(len(l4_rows)==l4p["row_count"]==449,"L4 row-count drift")

    before={r["icpn"]:dict(r) for r in l4_rows}
    seen=set()
    for row in l4_rows:
        icpn=row["icpn"]
        if icpn not in set(l4p["exact_icpns"]): continue
        req(row["mapping_status"]=="no_mapping",f"{icpn}: no longer no_mapping")
        for f in ("cmsis_device_name","existing_identifier","existing_identifier_kind","openocd_target_config"):
            req(row.get(f,"")=="",f"{icpn}: backend preimage field dirty: {f}")
        core=normalize_exact(icpn)
        req(core=="STM32L496WGY6P",f"{icpn}: normalized core drift")
        req(match(l4p["route_identifier"],core),f"{icpn}: bounded nonterminal-x match failed")
        old=dict(row)
        row["cmsis_device_name"]=l4p["route_identifier"]
        row["existing_identifier"]=l4p["route_identifier"]
        row["existing_identifier_kind"]=l4p["route_identifier_kind"]
        row["mapping_status"]=l4p["mapping_status"]
        row["openocd_target_config"]=l4p["target_config"]
        for f in l4_fields:
            if f not in BACKEND_FIELDS:
                req(row[f]==old[f],f"{icpn}: immutable field changed: {f}")
        seen.add(icpn)
    req(seen==set(l4p["exact_icpns"]),"L4 exact-set application drift")
    after={r["icpn"]:r for r in l4_rows}
    for icpn,row in before.items():
        if icpn not in seen: req(row==after[icpn],f"{icpn}: out-of-scope L4 row changed")
    l4_post=render(l4_fields,l4_rows)
    req(blob(l4_post)==p["frozen_postimages"]["l4_git_blob_sha"],"L4 projected Git blob drift")

    manifest_raw=MANIFEST.read_bytes()
    req(blob(manifest_raw)==pre["git_blob_sha"],"manifest preimage blob drift")
    manifest=json.loads(manifest_raw)
    req(len(manifest["sources"])==28,"Production source count drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"])==4629,"Production exact count drift")
    src=next(s for s in manifest["sources"] if s["family"]=="STM32L4")
    req(src["git_blob_sha"]==l4p["preimage_git_blob_sha"],"manifest L4 preimage binding drift")
    req(src["sha256"]==l4p["preimage_sha256"],"manifest L4 preimage SHA binding drift")
    manifest_after=deepcopy(manifest)
    dst=next(s for s in manifest_after["sources"] if s["family"]=="STM32L4")
    dst["git_blob_sha"]=blob(l4_post);dst["sha256"]=sha256(l4_post)
    manifest_post=(json.dumps(manifest_after,indent=2)+"\n").encode()

    mapped=no_mapping=0
    for s in manifest["sources"]:
        path=(MANIFEST.parent/s["path"]).resolve()
        with path.open(newline="",encoding="utf-8") as h:
            for row in csv.DictReader(h):
                if row["mapping_status"]=="no_mapping": no_mapping+=1
                else: mapped+=1
    req((mapped,no_mapping)==(4059,570),f"Production pre-partition drift: {(mapped,no_mapping)}")

    # G4 stays fail-closed.
    g4_auth_raw=G4_AUTH.read_bytes()
    req(blob(g4_auth_raw)==g4p["ordering_authority_blob_sha"],"G4 ordering authority blob drift")
    auth=json.loads(g4_auth_raw)
    rec=next(r for r in auth["records"] if r["series"]=="STM32G491")
    req(rec["package"]["Y"]=="WLCSP","G4 Y package authority drift")
    _,_,g4_rows=read_csv(G4)
    g4=next(r for r in g4_rows if r["icpn"]==g4p["exact_icpn"])
    req(g4["mapping_status"]=="no_mapping","G4 ambiguity unexpectedly mapped")
    req(g4["package"]=="WLCSP" and g4["option_suffix"]=="TR","G4 exact metadata drift")
    same=[r for r in routes if r["vendor"]=="STMicroelectronics" and r["part_number"] in {"STM32G491RCIx","STM32G491RCTx"}]
    req({r["part_number"] for r in same}=={"STM32G491RCIx","STM32G491RCTx"},"G4 sibling route inventory drift")
    req({r["target_config"] for r in same}=={"tcl/target/stm32g4x.cfg"},"G4 sibling target drift")
    req(not any(r["part_number"]=="STM32G491RCYx" for r in routes),"G4 exact package route now exists; rebaseline required")
    req(g4p["production_write_authorized"] is False,"G4 write unexpectedly authorized")

    projected=p["projected_poststate_if_l4_approved"]
    req(projected["mapped"]==mapped+2==4061,"L4 mapped projection drift")
    req(projected["no_mapping"]==no_mapping-2==568,"L4 no_mapping projection drift")
    req(projected["active_openocd_route"]==pre["active_openocd_route"]+2==3982,"active route projection drift")

    frozen=p["frozen_postimages"]
    values={
      "l4_git_blob_sha":blob(l4_post),"l4_sha256":sha256(l4_post),"l4_byte_count":len(l4_post),
      "manifest_git_blob_sha":blob(manifest_post),"manifest_sha256":sha256(manifest_post),"manifest_byte_count":len(manifest_post),
    }
    if frozen["lock_state"]=="FROZEN":
        for k,v in values.items(): req(frozen[k]==v,f"frozen postimage drift: {k}")
    else:
        req(frozen["lock_state"]=="DISCOVERY_PENDING","unknown postimage lock state")
        for k in ("l4_sha256","l4_byte_count","manifest_git_blob_sha","manifest_sha256","manifest_byte_count"):
            req(frozen[k] is None,f"partial discovery lock: {k}")

    summary={
      "transaction_id":p["transaction_id"],
      "postimage_lock_state":frozen["lock_state"],
      "l4_exact_count":2,
      "l4_route_identifier":l4p["route_identifier"],
      "l4_route_kind":l4p["route_identifier_kind"],
      "l4_normalized_core":"STM32L496WGY6P",
      "l4_postimage":values,
      "g4":{
        "icpn":g4p["exact_icpn"],
        "state":"BLOCKED_NO_CANONICAL_PACKAGE_ROUTE",
        "package":"WLCSP",
        "same_base_candidate_identifiers":["STM32G491RCIx","STM32G491RCTx"],
        "common_target_config":"tcl/target/stm32g4x.cfg",
        "production_write_authorized":False,
      },
      "prestate":{"mapped":mapped,"no_mapping":no_mapping,"active_openocd_route":3980},
      "poststate_if_l4_approved":projected,
      "claims":p["claims"],
    }
    return summary,{"STM32L4":l4_raw,"MANIFEST":manifest_raw},{"STM32L4":l4_post,"MANIFEST":manifest_post}

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--summary",type=Path)
    ap.add_argument("--package-dir",type=Path)
    args=ap.parse_args()
    summary,before,after=build()
    if args.summary: args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if args.package_dir:
        for side,data in (("before",before),("after",after)):
            d=args.package_dir/side;d.mkdir(parents=True,exist_ok=True)
            d.joinpath("STM32L4.csv").write_bytes(data["STM32L4"])
            d.joinpath("icpn-v1-manifest.json").write_bytes(data["MANIFEST"])
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_TIER_A_TAIL_V630_DRY_RUN_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

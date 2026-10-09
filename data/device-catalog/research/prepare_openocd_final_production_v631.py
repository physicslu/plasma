#!/usr/bin/env python3
from __future__ import annotations

import argparse,csv,hashlib,io,json
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
POLICY=HERE/"openocd-final-production-dry-run-v6.31.json"
SAFE=HERE/"openocd-final-safe-bindings-v6.31.csv"
BLOCKED=HERE/"openocd-final-runtime-blocked-v6.31.csv"
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
ROUTES=HERE/"openocd-parts-canonical-v627.csv"

BACKEND_FIELDS=(
    "cmsis_device_name","existing_identifier","existing_identifier_kind",
    "mapping_status","openocd_target_config",
)

def req(ok:bool,msg:str)->None:
    if not ok: raise RuntimeError(msg)

def sha(raw:bytes)->str:
    return hashlib.sha256(raw).hexdigest()

def blob(raw:bytes)->str:
    return hashlib.sha1(f"blob {len(raw)}\0".encode("ascii")+raw,usedforsecurity=False).hexdigest()

def read_csv(path:Path):
    raw=path.read_bytes()
    with io.StringIO(raw.decode("utf-8")) as s:
        r=csv.DictReader(s);fields=list(r.fieldnames or []);rows=list(r)
    req(bool(fields),f"{path.name}: missing header")
    return raw,fields,rows

def render_csv(fields,rows)->bytes:
    s=io.StringIO(newline="")
    w=csv.DictWriter(s,fieldnames=fields,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return s.getvalue().encode("utf-8")

def info(raw:bytes)->dict:
    return {"git_blob_sha":blob(raw),"sha256":sha(raw),"byte_count":len(raw)}

def build():
    p=json.loads(POLICY.read_text(encoding="utf-8"))
    pre=p["production_preimages"]

    safe_raw,safe_fields,safe_rows=read_csv(SAFE)
    blocked_raw,_,blocked_rows=read_csv(BLOCKED)
    req(blob(safe_raw)==p["evidence_files"]["safe_bindings"]["git_blob_sha"],"safe bindings blob drift")
    req(blob(blocked_raw)==p["evidence_files"]["runtime_blocked"]["git_blob_sha"],"blocked evidence blob drift")
    req(len(safe_rows)==103 and len(blocked_rows)==465,"closure evidence cardinality drift")
    safe_exact=sorted(r["icpn"] for r in safe_rows)
    blocked_exact=sorted(r["icpn"] for r in blocked_rows)
    req(sha(("\n".join(safe_exact)+"\n").encode())==p["source_closure"]["safe_exact_set_sha256"],
        "safe exact-set digest drift")
    req(sha(("\n".join(blocked_exact)+"\n").encode())==p["source_closure"]["blocked_exact_set_sha256"],
        "blocked exact-set digest drift")
    req(dict(sorted(Counter(r["family"] for r in safe_rows).items()))==
        {"STM32F3":10,"STM32F7":92,"STM32G4":1},"safe family partition drift")

    bindings={r["icpn"]:r for r in safe_rows}
    after={}
    before={}
    family_paths={
        "STM32F3":HERE/"stm32f3-commercial-icpn.csv",
        "STM32F7":HERE/"stm32f7-commercial-icpn.csv",
        "STM32G4":HERE/"stm32g4-commercial-icpn.csv",
    }
    changed_all=[]
    for family,path in family_paths.items():
        raw,fields,rows=read_csv(path)
        cfg=pre[family]
        req(blob(raw)==cfg["git_blob_sha"],f"{family}: preimage blob drift")
        req(sha(raw)==cfg["sha256"],f"{family}: preimage SHA drift")
        req(len(rows)==cfg["row_count"],f"{family}: preimage row-count drift")
        before[family]=raw
        original={r["icpn"]:dict(r) for r in rows}
        changed=[]
        for row in rows:
            binding=bindings.get(row["icpn"])
            if binding is None: continue
            req(row["family"]==family,f"{row['icpn']}: binding family mismatch")
            req(row["mapping_status"]=="no_mapping",f"{row['icpn']}: no longer no_mapping")
            req(all(row.get(f,"")=="" for f in (
                "cmsis_device_name","existing_identifier","existing_identifier_kind","openocd_target_config"
            )),f"{row['icpn']}: backend preimage dirty")
            row["cmsis_device_name"]=""
            row["existing_identifier"]=binding["existing_identifier"]
            row["existing_identifier_kind"]=binding["existing_identifier_kind"]
            row["mapping_status"]=binding["mapping_status"]
            row["openocd_target_config"]=binding["openocd_target_config"]
            changed.append(row["icpn"])
        expected=sorted(r["icpn"] for r in safe_rows if r["family"]==family)
        req(sorted(changed)==expected,f"{family}: changed exact-set drift")
        now={r["icpn"]:r for r in rows}
        for icpn,old in original.items():
            diffs={f for f in fields if old[f]!=now[icpn][f]}
            if icpn in changed:
                req(diffs<=set(BACKEND_FIELDS) and diffs,
                    f"{icpn}: non-backend or empty mutation {sorted(diffs)}")
            else:
                req(not diffs,f"{icpn}: out-of-scope row mutated")
        raw_after=render_csv(fields,rows)
        after[family]=raw_after
        changed_all.extend(changed)

    req(sorted(changed_all)==safe_exact,"global 103 exact-set application drift")

    # Route successor = exact v6.27 successor plus exactly the two bounded rows.
    route_raw,route_fields,route_rows=read_csv(ROUTES)
    rcfg=pre["ROUTE_INVENTORY"]
    req(blob(route_raw)==rcfg["git_blob_sha"],"route preimage blob drift")
    req(sha(route_raw)==rcfg["sha256"],"route preimage SHA drift")
    req(len(route_rows)==rcfg["row_count"]==7661,"route preimage row-count drift")
    before["ROUTE_INVENTORY"]=route_raw

    delta=[
        {
          "vendor":"STMicroelectronics","family":"STM32F3 Series","subfamily":"STM32F3x8",
          "plasma_series":"STM32F3","part_number":"STM32F378VCHx",
          "identifier_kind":"ordering_pattern","cpu_architectures":'["ARM Cortex-M"]',
          "target_config":"tcl/target/stm32f3x.cfg","openocd_distribution":"upstream-openocd",
          "mapping_status":"mapping_candidate","validation_status":"not_verified",
          "catalog_origin":"openocd-final-route-delta-v6.31.csv",
        },
        {
          "vendor":"STMicroelectronics","family":"STM32G4 Series","subfamily":"STM32G491",
          "plasma_series":"STM32G4","part_number":"STM32G491RCYx",
          "identifier_kind":"ordering_pattern","cpu_architectures":'["ARM Cortex-M"]',
          "target_config":"tcl/target/stm32g4x.cfg","openocd_distribution":"upstream-openocd",
          "mapping_status":"mapping_candidate","validation_status":"not_verified",
          "catalog_origin":"openocd-final-route-delta-v6.31.csv",
        },
    ]
    keys={(r["vendor"],r["part_number"],r["identifier_kind"]) for r in route_rows}
    for r in delta:
        req((r["vendor"],r["part_number"],r["identifier_kind"]) not in keys,
            f"{r['part_number']}: route already exists")
    route_after=render_csv(route_fields,route_rows+delta)
    req(len(route_rows)+len(delta)==7663,"route successor cardinality drift")
    req(sha(route_after)==p["source_closure"]["route_successor_csv_sha256"],
        "route successor SHA differs from discovery artifact")
    after["ROUTE_INVENTORY"]=route_after

    # Manifest only updates integrity bindings for the three family CSVs.
    manifest_raw=MANIFEST.read_bytes()
    mcfg=pre["MANIFEST"]
    req(blob(manifest_raw)==mcfg["git_blob_sha"],"manifest preimage blob drift")
    req(sha(manifest_raw)==mcfg["sha256"],"manifest preimage SHA drift")
    manifest=json.loads(manifest_raw)
    req(len(manifest["sources"])==mcfg["source_count"]==28,"manifest source-count drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"])==mcfg["exact_total"]==4629,
        "manifest exact-total drift")
    before["MANIFEST"]=manifest_raw
    for family in ("STM32F3","STM32F7","STM32G4"):
        source=next(s for s in manifest["sources"] if s["family"]==family)
        source["git_blob_sha"]=blob(after[family])
        source["sha256"]=sha(after[family])
    manifest_after=(json.dumps(manifest,indent=2)+"\n").encode("utf-8")
    after["MANIFEST"]=manifest_after

    frozen=p["frozen_postimages"]
    discovered={k:info(v) for k,v in after.items()}
    if frozen["lock_state"]=="FROZEN":
        for k,v in discovered.items():
            req(frozen[k]==v,f"{k}: frozen postimage drift")
    else:
        req(frozen["lock_state"]=="DISCOVERY_PENDING","unknown postimage lock state")
        req(all(frozen[k] is None for k in discovered),"partial frozen postimage state")

    summary={
        "transaction_id":p["transaction_id"],
        "safe_bindings_sha256":sha(safe_raw),
        "blocked_evidence_sha256":sha(blocked_raw),
        "safe_exact_count":len(safe_rows),
        "blocked_exact_count":len(blocked_rows),
        "family_changed_counts":dict(sorted(Counter(bindings[x]["family"] for x in changed_all).items())),
        "postimages":discovered,
        "projected_poststate":p["projected_poststate"],
        "approval":p["approval"],
        "claims":p["claims"],
    }
    req(all(v is False for v in p["claims"].values()),"capability overclaim")
    return summary,before,after,delta

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--summary",type=Path)
    ap.add_argument("--package-dir",type=Path)
    args=ap.parse_args()
    summary,before,after,delta=build()
    if args.summary:
        args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if args.package_dir:
        for side,data in (("before",before),("after",after)):
            d=args.package_dir/side;d.mkdir(parents=True,exist_ok=True)
            for key,raw in data.items():
                suffix=".json" if key=="MANIFEST" else ".csv"
                d.joinpath(key+suffix).write_bytes(raw)
        fields=("vendor","family","subfamily","plasma_series","part_number","identifier_kind",
                "cpu_architectures","target_config","openocd_distribution","mapping_status",
                "validation_status","catalog_origin")
        s=io.StringIO(newline="");w=csv.DictWriter(s,fieldnames=fields,lineterminator="\n")
        w.writeheader();w.writerows(delta)
        args.package_dir.joinpath("openocd-final-route-delta-v6.31.csv").write_text(s.getvalue(),encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_FINAL_PRODUCTION_DRY_RUN_V631_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

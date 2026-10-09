#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
CATALOG=HERE/"openocd-parts-canonical.csv"
DELTA=HERE/"openocd-c0-bounded-route-inventory-v6.25.csv"
RECEIPT=HERE/"openocd-c0-canonical-route-write-v6.27.json"
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"

FIELDS=(
    "vendor","family","subfamily","plasma_series","part_number","identifier_kind",
    "cpu_architectures","target_config","openocd_distribution","mapping_status",
    "validation_status","catalog_origin",
)

EXACT=(
    "STM32C011D6Y6TR",
    "STM32C051D8Y6TR",
    "STM32C091ECY6TR",
    "STM32C092ECY3TR",
    "STM32C092ECY6TR",
)

def req(ok:bool,msg:str)->None:
    if not ok:
        raise RuntimeError(msg)

def git_blob_sha(data:bytes)->str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii")+data,
        usedforsecurity=False,
    ).hexdigest()

def parse(raw:bytes)->list[dict[str,str]]:
    with io.StringIO(raw.decode("utf-8")) as s:
        r=csv.DictReader(s)
        req(tuple(r.fieldnames or ())==FIELDS,f"schema drift: {r.fieldnames}")
        return list(r)

def render(rows:list[dict[str,str]])->bytes:
    b=io.StringIO(newline="")
    w=csv.DictWriter(b,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader(); w.writerows(rows)
    return b.getvalue().encode()

def validate()->dict:
    receipt=json.loads(RECEIPT.read_text(encoding="utf-8"))
    scope=receipt["approved_scope"]

    cat_raw=CATALOG.read_bytes()
    delta_raw=DELTA.read_bytes()

    req(git_blob_sha(cat_raw)==scope["postimage_git_blob_sha"],"canonical postimage blob mismatch")
    req(hashlib.sha256(cat_raw).hexdigest()==scope["postimage_sha256"],"canonical postimage sha256 mismatch")
    req(hashlib.sha256(delta_raw).hexdigest()==scope["source_delta_sha256"],"delta sha256 mismatch")

    cat=parse(cat_raw)
    delta=parse(delta_raw)
    req(len(cat)==scope["postimage_rows"]==7661,"postimage row-count drift")
    req(len(delta)==scope["delta_rows"]==4,"delta row-count drift")

    delta_keys={(r["vendor"],r["part_number"].upper()) for r in delta}
    req(len(delta_keys)==4,"delta duplicate keys")
    by_key={(r["vendor"],r["part_number"].upper()):r for r in cat}
    req(len(by_key)==len(cat),"canonical duplicate keys")
    req(delta_keys <= set(by_key),"delta rows missing from canonical")
    for r in delta:
        req(by_key[(r["vendor"],r["part_number"].upper())]==r,
            f"canonical row differs from provenance row: {r['part_number']}")

    inverse=[r for r in cat if (r["vendor"],r["part_number"].upper()) not in delta_keys]
    req(len(inverse)==scope["preimage_rows"]==7657,"inverse preimage row-count drift")
    inverse_raw=render(inverse)
    req(git_blob_sha(inverse_raw)==scope["preimage_git_blob_sha"],
        "inverse reconstruction did not reproduce frozen preimage")

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    prod={}
    mapped=no_mapping=0
    for source in manifest["sources"]:
        path=(MANIFEST.parent/source["path"]).resolve()
        with path.open(newline="",encoding="utf-8") as h:
            for row in csv.DictReader(h):
                prod[row["icpn"]]=row
                if row["mapping_status"]=="no_mapping": no_mapping+=1
                else: mapped+=1
    exp=receipt["production_state_expected_unchanged"]
    req(mapped==exp["mapped"]==4054,f"Production mapped drift: {mapped}")
    req(no_mapping==exp["no_mapping"]==575,f"Production no_mapping drift: {no_mapping}")
    for icpn in EXACT:
        req(prod[icpn]["mapping_status"]=="no_mapping",f"{icpn}: Production changed during canonical-only write")

    patterns={r["part_number"] for r in delta}
    req(patterns=={
        "STM32C011D6Yx","STM32C051D8Yx","STM32C091ECYx","STM32C092ECYx"
    },"delta pattern set drift")

    summary={
        "transaction_id":receipt["transaction_id"],
        "canonical_postimage_git_blob_sha":git_blob_sha(cat_raw),
        "canonical_postimage_sha256":hashlib.sha256(cat_raw).hexdigest(),
        "canonical_rows":len(cat),
        "delta_rows":len(delta),
        "delta_sha256":hashlib.sha256(delta_raw).hexdigest(),
        "inverse_preimage_git_blob_sha":git_blob_sha(inverse_raw),
        "inverse_preimage_rows":len(inverse),
        "production_mapped":mapped,
        "production_no_mapping":no_mapping,
        "production_exact_scope_still_no_mapping":len(EXACT),
        "active_openocd_route_exact_count":exp["active_openocd_route_exact_count"],
        "active_openocd_route_denominator":exp["active_openocd_route_denominator"],
        "active_openocd_route_coverage_percent":exp["active_openocd_route_coverage_percent"],
        "next_gate":receipt["next_gate"],
        "claims":receipt["claims"],
    }
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_C0_CANONICAL_WRITE_V627_PASS")
    return summary

if __name__=="__main__":
    validate()

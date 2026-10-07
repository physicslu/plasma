#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import qualify_openocd_tier_a_identifiers_v65 as v65

HERE = Path(__file__).resolve().parent

FIELDS = (
    "manufacturer","icpn","family","series","base_device",
    "candidate_openocd_target_config","blocked_reason",
    "structural_gap_class","same_series_route_rows",
    "same_base_route_rows","candidate_option_suffix",
    "programming_profile_state","production_write_authorized",
)

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)

def read_production_index() -> dict[str,dict[str,str]]:
    manifest=json.loads((HERE.parent/"production/icpn-v1-manifest.json").read_text(encoding="utf-8"))
    out={}
    for src in manifest["sources"]:
        path=(HERE.parent/"production"/src["path"]).resolve()
        with path.open(newline="",encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                out[row["icpn"]]=row
    return out

def literal_prefix(pattern: str) -> str:
    pos=min([i for i,c in enumerate(pattern) if c.lower()=="x"] or [len(pattern)])
    return pattern[:pos]

def build() -> tuple[list[dict[str,str]],str,dict[str,Any]]:
    _,blocked,_,_,v65_summary=v65.build()
    req(len(blocked)==69, "v6.5 blocked cardinality drift")
    routes=v65.read_routes()
    prod=read_production_index()

    rows=[]
    classes=Counter()
    family_classes=defaultdict(Counter)
    suffixes=Counter()

    for b in blocked:
        icpn=b["icpn"]
        p=prod[icpn]
        family=b["family"]
        target=b["candidate_openocd_target_config"]
        kinds=v65.allowed_kinds(family)
        pool=[
            r for r in routes
            if r.get("plasma_series")==family
            and r.get("identifier_kind") in kinds
            and r.get("target_config")==target
        ]
        same_series=[r for r in pool if r.get("subfamily")==b["series"]]
        same_base=[
            r for r in same_series
            if r.get("part_number","").startswith(b["base_device"])
            or b["base_device"].startswith(literal_prefix(r.get("part_number","")))
        ]

        suffix=p.get("option_suffix","")
        suffixes[suffix]+=1
        if same_base:
            gap="same_base_route_inventory_present_but_no_policy_match"
        elif same_series:
            gap="same_series_route_inventory_present_but_base_variant_absent"
        else:
            gap="no_same_series_route_inventory_row"

        classes[gap]+=1
        family_classes[family][gap]+=1
        rows.append({
            "manufacturer":b["manufacturer"],
            "icpn":icpn,
            "family":family,
            "series":b["series"],
            "base_device":b["base_device"],
            "candidate_openocd_target_config":target,
            "blocked_reason":b["blocked_reason"],
            "structural_gap_class":gap,
            "same_series_route_rows":str(len(same_series)),
            "same_base_route_rows":str(len(same_base)),
            "candidate_option_suffix":suffix,
            "programming_profile_state":"unresolved",
            "production_write_authorized":"false",
        })

    rows.sort(key=lambda r:r["icpn"])
    req(len(rows)==69 and len({r["icpn"] for r in rows})==69, "blocked classification cardinality drift")
    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader(); w.writerows(rows)
    csv_text=buf.getvalue()
    summary={
        "schema_version":1,
        "classification_id":"openocd-tier-a-blocked-classification-v6.6",
        "record_state":"RESEARCH_ONLY",
        "input_blocked_exact_count":69,
        "blocked_exact_set_sha256":v65_summary["blocked_exact_set_sha256"],
        "classification_csv_sha256":hashlib.sha256(csv_text.encode()).hexdigest(),
        "structural_gap_counts":dict(sorted(classes.items())),
        "family_structural_gap_counts":{
            fam:dict(sorted(cnt.items()))
            for fam,cnt in sorted(family_classes.items())
        },
        "option_suffix_counts":dict(sorted(suffixes.items())),
        "next_gate":"decide whether each structural class needs route-inventory expansion, explicit suffix normalization, or new manufacturer/OpenOCD evidence",
        "claims":{
            "production_write_authorized":False,
            "identifier_inferred_for_blocked_rows":False,
            "programming_profile_binding_claimed":False,
            "programming_verified_claimed":False,
            "engineering_verified_claimed":False,
            "hil_verified_claimed":False,
        }
    }
    return rows,csv_text,summary

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--classified",type=Path)
    p.add_argument("--summary",type=Path)
    args=p.parse_args()
    _,csv_text,summary=build()
    if args.classified:
        args.classified.write_text(csv_text,encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_TIER_A_BLOCKED_CLASSIFICATION_V66_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

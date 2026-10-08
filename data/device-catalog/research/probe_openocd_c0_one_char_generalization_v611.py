#!/usr/bin/env python3
from __future__ import annotations

import argparse,csv,hashlib,io,json
from collections import Counter
from pathlib import Path
from typing import Any

import analyze_openocd_c0_g0_residual_v69 as v69
import qualify_openocd_tier_a_identifiers_v65 as v65

FIELDS=(
    "icpn","series","base_device","option_suffix","candidate_openocd_target_config",
    "normalized_core","probe_state","resolved_identifier","resolved_identifier_kind",
    "match_count","production_write_authorized"
)

def req(ok:bool,msg:str)->None:
    if not ok:
        raise ValueError(msg)

def generalize_one(core:str, route:str)->bool:
    if not route.endswith("x"):
        return False
    prefix=route[:-1]
    if len(prefix)<=1 or len(core)<len(prefix):
        return False
    return core.startswith(prefix[:-1])

def build()->tuple[list[dict[str,str]],str,dict[str,Any]]:
    rows69,_,summary69=v69.build()
    req(summary69["family_counts"]=={"STM32C0":16,"STM32G0":12},"v6.9 family partition drift")
    c0=[
        r for r in rows69
        if r["family"]=="STM32C0"
        and r["analysis_class"]=="route_inventory_present_policy_shape_gap"
    ]
    req(len(c0)==11,"C0 policy-shape residual cardinality drift")

    routes=v65.read_routes()
    out=[]
    states=Counter()
    for r in c0:
        pool=[
            x for x in routes
            if x.get("plasma_series")=="STM32C0"
            and x.get("subfamily")==r["series"]
            and x.get("identifier_kind")=="ordering_pattern"
            and x.get("target_config")==r["candidate_openocd_target_config"]
        ]
        matches=[x for x in pool if generalize_one(r["normalized_core"],x["part_number"])]
        uniq={(x["part_number"],x["identifier_kind"],x["target_config"]):x for x in matches}
        matches=list(uniq.values())

        if len(matches)==1:
            state="unique_under_one_char_generalization"
            ident=matches[0]["part_number"]
            kind=matches[0]["identifier_kind"]
        elif len(matches)==0:
            state="still_unmapped_under_one_char_generalization"
            ident=kind=""
        else:
            state="ambiguous_under_one_char_generalization"
            ident=kind=""
        states[state]+=1
        out.append({
            "icpn":r["icpn"],
            "series":r["series"],
            "base_device":r["base_device"],
            "option_suffix":r["option_suffix"],
            "candidate_openocd_target_config":r["candidate_openocd_target_config"],
            "normalized_core":r["normalized_core"],
            "probe_state":state,
            "resolved_identifier":ident,
            "resolved_identifier_kind":kind,
            "match_count":str(len(matches)),
            "production_write_authorized":"false",
        })

    out.sort(key=lambda x:x["icpn"])
    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader();w.writerows(out)
    csv_text=buf.getvalue()
    unique=states["unique_under_one_char_generalization"]
    summary={
        "schema_version":1,
        "probe_id":"openocd-c0-one-char-generalization-v6.11",
        "record_state":"RESEARCH_ONLY_NOT_POLICY_CHANGE",
        "input_c0_policy_shape_gap_exact_count":11,
        "probe_state_counts":dict(sorted(states.items())),
        "unique_under_one_char_generalization_exact_count":unique,
        "probe_csv_sha256":hashlib.sha256(csv_text.encode()).hexdigest(),
        "potential_total_identifier_qualified_or_normalizable_if_later_authorized":353+unique,
        "potential_active_openocd_route_exact_count_if_later_promoted":3947+unique,
        "scoped_active_denominator":4550,
        "potential_coverage_percent_if_later_promoted":round((3947+unique)/4550*100,4),
        "c0_base_variant_inventory_gap_exact_count":5,
        "claims":{
            "c0_one_char_policy_authorized":False,
            "identifier_promoted":False,
            "route_inventory_modified":False,
            "production_write_authorized":False,
            "programming_verified":False,
            "hil_verified":False,
        }
    }
    return out,csv_text,summary

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--output",type=Path)
    p.add_argument("--summary",type=Path)
    a=p.parse_args()
    _,csv_text,summary=build()
    if a.output:a.output.write_text(csv_text,encoding="utf-8")
    if a.summary:a.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_C0_ONE_CHAR_GENERALIZATION_V611_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

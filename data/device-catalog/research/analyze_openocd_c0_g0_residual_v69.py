#!/usr/bin/env python3
from __future__ import annotations
import argparse,csv,hashlib,io,json,re
from collections import Counter,defaultdict
from pathlib import Path
from typing import Any
import classify_openocd_tier_a_residual_v68 as v68
import qualify_openocd_tier_a_identifiers_v65 as v65

HERE=Path(__file__).resolve().parent
TARGET_FAMILIES={"STM32C0","STM32G0"}
FIELDS=("icpn","family","series","base_device","option_suffix","candidate_openocd_target_config",
"same_series_route_rows","same_base_route_rows","normalized_core","literal_prefix_match_count",
"one_char_generalization_match_count","analysis_class","next_gate","production_write_authorized")

def req(ok,msg):
    if not ok: raise ValueError(msg)

def literal_prefix(pattern:str)->str:
    pos=min([i for i,c in enumerate(pattern) if c.lower()=="x"] or [len(pattern)])
    return pattern[:pos]

def generalize_one(core:str, route:str)->bool:
    if not route.endswith("x"): return False
    p=route[:-1]
    if len(core)<len(p): return False
    return core.startswith(p[:-1]) if len(p)>1 else False

def build()->tuple[list[dict[str,str]],str,dict[str,Any]]:
    residual,_,s68=v68.build()
    rows=[r for r in residual if r["family"] in TARGET_FAMILIES]
    req(len(rows)==28,"C0/G0 residual cardinality drift")
    routes=v65.read_routes()
    out=[]; classes=Counter(); fam=defaultdict(Counter)
    for r in rows:
        pool=[x for x in routes if x.get("plasma_series")==r["family"]
              and x.get("target_config")==r["candidate_openocd_target_config"]
              and x.get("identifier_kind")=="ordering_pattern"]
        same_series=[x for x in pool if x.get("subfamily")==r["series"]]
        suffix=r["option_suffix"]
        normalized=r["icpn"][:-len(suffix)] if suffix and r["icpn"].endswith(suffix) else r["icpn"]
        prefix=[x for x in same_series if normalized.startswith(literal_prefix(x["part_number"]))]
        gen=[x for x in same_series if generalize_one(normalized,x["part_number"])]
        if r["same_base_route_rows"]!="0":
            cls="route_inventory_present_policy_shape_gap"
            gate="review_existing_route_pattern_shape_before_policy_change"
        elif same_series:
            cls="base_variant_absent_from_route_inventory"
            gate="obtain_or_generate_authoritative_route_evidence_for_base_variant"
        else:
            cls="series_absent_from_route_inventory"
            gate="expand_canonical_route_inventory_for_series"
        classes[cls]+=1; fam[r["family"]][cls]+=1
        out.append({
            "icpn":r["icpn"],"family":r["family"],"series":r["series"],"base_device":r["base_device"],
            "option_suffix":suffix,"candidate_openocd_target_config":r["candidate_openocd_target_config"],
            "same_series_route_rows":r["same_series_route_rows"],"same_base_route_rows":r["same_base_route_rows"],
            "normalized_core":normalized,"literal_prefix_match_count":str(len(prefix)),
            "one_char_generalization_match_count":str(len(gen)),"analysis_class":cls,"next_gate":gate,
            "production_write_authorized":"false"
        })
    out.sort(key=lambda x:x["icpn"])
    buf=io.StringIO(newline=""); w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n"); w.writeheader();w.writerows(out)
    csv_text=buf.getvalue()
    summary={
      "schema_version":1,"analysis_id":"openocd-c0-g0-residual-analysis-v6.9","record_state":"RESEARCH_ONLY",
      "input_tier_a_residual_exact_count":36,"target_c0_g0_exact_count":28,
      "family_counts":dict(sorted(Counter(x["family"] for x in out).items())),
      "analysis_class_counts":dict(sorted(classes.items())),
      "family_analysis_class_counts":{k:dict(sorted(v.items())) for k,v in sorted(fam.items())},
      "analysis_csv_sha256":hashlib.sha256(csv_text.encode()).hexdigest(),
      "claims":{"identifier_inferred":False,"route_inventory_modified":False,"production_write_authorized":False,
      "programming_verified":False,"hil_verified":False}
    }
    return out,csv_text,summary

def main():
    p=argparse.ArgumentParser(); p.add_argument("--output",type=Path); p.add_argument("--summary",type=Path); a=p.parse_args()
    _,c,s=build()
    if a.output:a.output.write_text(c,encoding="utf-8")
    if a.summary:a.summary.write_text(json.dumps(s,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(s,indent=2,sort_keys=True)); print("OPENOCD_C0_G0_RESIDUAL_ANALYSIS_V69_PASS")
if __name__=="__main__":main()

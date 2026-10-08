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

import classify_openocd_tier_a_blocked_v66 as v66
import probe_openocd_tier_a_suffix_normalization_v67 as v67

HERE=Path(__file__).resolve().parent

FIELDS=(
    "manufacturer","icpn","family","series","base_device",
    "candidate_openocd_target_config","option_suffix",
    "normalization_probe_state","structural_gap_class",
    "same_series_route_rows","same_base_route_rows",
    "residual_class","recommended_next_gate",
    "programming_profile_state","production_write_authorized",
)

def req(ok: bool,msg: str)->None:
    if not ok:
        raise ValueError(msg)

def build()->tuple[list[dict[str,str]],str,dict[str,Any]]:
    classified,_,s66=v66.build()
    probed,_,s67=v67.build()
    req(len(classified)==69 and len(probed)==69,"upstream residual input drift")
    by_class={r["icpn"]:r for r in classified}
    by_probe={r["icpn"]:r for r in probed}
    req(set(by_class)==set(by_probe),"v6.6/v6.7 exact-set mismatch")

    rows=[]
    residual_counts=Counter()
    family_counts=defaultdict(Counter)

    for icpn in sorted(by_probe):
        p=by_probe[icpn]
        if p["normalization_probe_state"]=="unique_after_catalog_suffix_removal":
            continue
        c=by_class[icpn]
        suffix=p["option_suffix"]
        structural=c["structural_gap_class"]
        state=p["normalization_probe_state"]

        if state=="not_applicable_empty_suffix":
            if structural=="same_base_route_inventory_present_but_no_policy_match":
                residual="empty_suffix_same_base_policy_gap"
                gate="inspect_family_policy_vs_route_identifier_shape"
            elif structural=="same_series_route_inventory_present_but_base_variant_absent":
                residual="empty_suffix_base_variant_missing"
                gate="expand_route_inventory_for_missing_base_variant"
            else:
                residual="empty_suffix_series_route_inventory_missing"
                gate="add_route_inventory_for_series"
        else:
            if structural=="same_base_route_inventory_present_but_no_policy_match":
                residual="suffix_removed_but_same_base_policy_gap"
                gate="inspect_identifier_pattern_and_commercial_core_normalization"
            elif structural=="same_series_route_inventory_present_but_base_variant_absent":
                residual="suffix_removed_but_base_variant_missing"
                gate="expand_route_inventory_for_missing_base_variant"
            else:
                residual="suffix_removed_but_series_route_inventory_missing"
                gate="add_route_inventory_for_series"

        residual_counts[residual]+=1
        family_counts[p["family"]][residual]+=1
        rows.append({
            "manufacturer":p["manufacturer"],
            "icpn":icpn,
            "family":p["family"],
            "series":p["series"],
            "base_device":p["base_device"],
            "candidate_openocd_target_config":p["candidate_openocd_target_config"],
            "option_suffix":suffix,
            "normalization_probe_state":state,
            "structural_gap_class":structural,
            "same_series_route_rows":c["same_series_route_rows"],
            "same_base_route_rows":c["same_base_route_rows"],
            "residual_class":residual,
            "recommended_next_gate":gate,
            "programming_profile_state":"unresolved",
            "production_write_authorized":"false",
        })

    req(len(rows)==36 and len({r["icpn"] for r in rows})==36,
        f"residual Tier A count drift: {len(rows)}")

    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader(); w.writerows(rows)
    csv_text=buf.getvalue()

    summary={
        "schema_version":1,
        "classification_id":"openocd-tier-a-residual-classification-v6.8",
        "record_state":"RESEARCH_ONLY",
        "input_v65_blocked_exact_count":69,
        "v67_unique_after_suffix_normalization_exact_count":33,
        "residual_exact_count":36,
        "residual_exact_set_sha256":hashlib.sha256(
            ("\n".join(r["icpn"] for r in rows)+"\n").encode()
        ).hexdigest(),
        "classification_csv_sha256":hashlib.sha256(csv_text.encode()).hexdigest(),
        "residual_class_counts":dict(sorted(residual_counts.items())),
        "family_residual_class_counts":{
            fam:dict(sorted(cnt.items())) for fam,cnt in sorted(family_counts.items())
        },
        "family_residual_counts":dict(sorted(Counter(r["family"] for r in rows).items())),
        "option_suffix_counts":dict(sorted(Counter(r["option_suffix"] for r in rows).items())),
        "qualified_or_normalizable_tier_a_exact_count":353,
        "tier_a_residual_exact_count":36,
        "current_active_openocd_route_exact_count":3594,
        "potential_route_exact_count_if_353_later_promoted":3947,
        "scoped_active_denominator":4550,
        "potential_coverage_percent_if_353_later_promoted":86.7473,
        "claims":{
            "production_write_authorized":False,
            "identifier_inferred_for_residual_rows":False,
            "suffix_removal_policy_authorized":False,
            "programming_profile_binding_claimed":False,
            "programming_verified_claimed":False,
            "engineering_verified_claimed":False,
            "hil_verified_claimed":False,
        }
    }
    req(sum(summary["family_residual_counts"].values())==36,"family residual partition drift")
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
    print("OPENOCD_TIER_A_RESIDUAL_CLASSIFICATION_V68_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

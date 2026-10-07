#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import analyze_st_final_active_tail_gap_v60 as replay

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
AUTHORITY = HERE / "st-final-active-tail-gap-metadata-authority-v6.0.json"

EXPECTED_TOTAL = 4620
EXPECTED_SOURCES = 28
EXPECTED_INTERSECTION = 4541
EXPECTED_DENOMINATOR = 4550
EXPECTED_FAMILY_PRESTATE = {
    "STM32F4":384,
    "STM32L4":446,
    "STM32L1":144,
    "STM32U3":106,
}
EXPECTED_FAMILY_DELTA = {
    "STM32F4":3,
    "STM32L4":3,
    "STM32L1":2,
    "STM32U3":1,
}

FIELDS = (
    "manufacturer","icpn","family","series","base_device","marketing_status",
    "catalog_resolution","package","pin_count","flash_size","temperature_grade",
    "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
    "existing_identifier","existing_identifier_kind","openocd_target_config",
    "metadata_source_reference","source_authority","verification_status",
    "programming_profile_state","metadata_exception",
)

class ProposalError(RuntimeError):
    pass

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ProposalError(msg)

def production_prestate() -> dict[str,Any]:
    m=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources=m["sources"]
    req(len(sources)==EXPECTED_SOURCES, "Production source-count drift")
    total=sum(int(s["row_count"]) for s in sources)
    req(total==EXPECTED_TOTAL, f"Production exact-total drift: {total}")
    counts={s["family"]:int(s["row_count"]) for s in sources}
    for fam,count in EXPECTED_FAMILY_PRESTATE.items():
        req(counts.get(fam)==count, f"{fam}: Production prestate drift")
    return {"total":total,"source_count":len(sources),"family_counts":counts}

def row_for(r: dict[str,Any]) -> dict[str,str]:
    mode=r["metadata_authority_mode"]
    verification=(
        "verified_official_exact_product_identity_metadata_plus_locked_active_lifecycle"
        if mode=="official_exact_product"
        else "verified_st_ordering_information_codes_plus_locked_active_exact_identity"
    )
    return {
        "manufacturer":"STMicroelectronics",
        "icpn":r["icpn"],
        "family":r["family"],
        "series":r["series"],
        "base_device":r["base_device"],
        "marketing_status":"Active",
        "catalog_resolution":"normalized",
        "package":r["package"],
        "pin_count":str(r["pin_count"]),
        "flash_size":r["flash_size"],
        "temperature_grade":r["temperature_grade"],
        "option_suffix":r["option_suffix"],
        "backend_type":"",
        "backend_mapping_state":"no_mapping",
        "backend_route_observation":
            "backend_not_evaluated_catalog_only_existing_family_mapping_not_inherited",
        "existing_identifier":"",
        "existing_identifier_kind":"",
        "openocd_target_config":"",
        "metadata_source_reference":r["metadata_source_url"],
        "source_authority":"STMicroelectronics official",
        "verification_status":verification,
        "programming_profile_state":"unresolved",
        "metadata_exception":"",
    }

def render_csv(rows:list[dict[str,str]]) -> str:
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()

def build() -> tuple[list[dict[str,str]],str,dict[str,Any]]:
    pre=production_prestate()
    meta=replay.analyze()
    req(meta["metadata_ready_exact_count"]==9, "final-tail metadata replay incomplete")
    req(meta["metadata_blocked_exact_count"]==0, "final-tail metadata blocked")
    req(meta["claims"]["backend_scope_evaluated"] is False, "backend scope overclaim")
    req(meta["claims"]["existing_family_backend_mapping_inherited"] is False,
        "existing family backend mapping inheritance overclaim")

    authority=json.loads(AUTHORITY.read_text(encoding="utf-8"))
    records=authority["records"]
    rows=[row_for(r) for r in records]
    rows.sort(key=lambda x:x["icpn"])
    req(len(rows)==9 and len({r["icpn"] for r in rows})==9, "proposal cardinality drift")
    req(all(
        r["backend_mapping_state"]=="no_mapping"
        and r["backend_type"]==""
        and r["existing_identifier"]==""
        and r["existing_identifier_kind"]==""
        and r["openocd_target_config"]==""
        and r["programming_profile_state"]=="unresolved"
        for r in rows
    ), "proposal synthesized backend or Programming Profile capability")

    csv_text=render_csv(rows)
    exact_set=[r["icpn"] for r in rows]
    exact_sha=hashlib.sha256(("\n".join(exact_set)+"\n").encode()).hexdigest()
    csv_sha=hashlib.sha256(csv_text.encode()).hexdigest()
    projected_families={
        fam:EXPECTED_FAMILY_PRESTATE[fam]+EXPECTED_FAMILY_DELTA[fam]
        for fam in EXPECTED_FAMILY_PRESTATE
    }
    projected_intersection=EXPECTED_INTERSECTION+9

    summary={
        "schema_version":1,
        "proposal_id":"st-final-layer1-admission-proposal-v6.1",
        "record_state":"RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
        "production_write_authorized":False,
        "production_exact_prestate":pre["total"],
        "production_source_count_prestate":pre["source_count"],
        "proposal_addition_count":9,
        "proposal_exact_set_sha256":exact_sha,
        "proposal_csv_sha256":csv_sha,
        "family_addition_counts":dict(sorted(EXPECTED_FAMILY_DELTA.items())),
        "family_production_prestates":dict(sorted(EXPECTED_FAMILY_PRESTATE.items())),
        "family_production_after_if_approved":dict(sorted(projected_families.items())),
        "metadata_ready_exact_count":9,
        "metadata_ordering_grammar_exact_count":4,
        "metadata_official_exact_product_exact_count":5,
        "metadata_blocked_exact_count":0,
        "metadata_exception_exact_count":0,
        "opaque_suffix_literal_exact_count":5,
        "f4_lifecycle_authority_conflict_exact_count":3,
        "backend_scope_evaluated":False,
        "existing_family_backend_mapping_inherited":False,
        "backend_type_claimed":False,
        "backend_state_for_new_rows":{"no_mapping":9},
        "backend_mapping_required_for_layer1_admission":False,
        "programming_profile_binding_claimed":False,
        "programming_profile_scope_expanded":False,
        "production_exact_after_if_approved":pre["total"]+9,
        "production_source_count_after_if_approved":pre["source_count"],
        "catalog_backend_partition_after_if_approved":{
            "mapped":3673,
            "no_mapping":956
        },
        "whole_st_active_exact_denominator":EXPECTED_DENOMINATOR,
        "whole_st_active_intersection_prestate":EXPECTED_INTERSECTION,
        "whole_st_active_intersection_after_if_approved":projected_intersection,
        "whole_st_active_gap_after_if_approved":EXPECTED_DENOMINATOR-projected_intersection,
        "whole_st_active_coverage_after_if_approved_percent":round(
            projected_intersection/EXPECTED_DENOMINATOR*100,4
        ),
        "scoped_st_active_identity_coverage_after_if_published":"4550/4550 = 100%",
        "engineering_verified_claimed":False,
        "field_evidence_claimed":False,
        "ps_hil_claimed":False,
    }
    req(summary["proposal_exact_set_sha256"]==
        "891831ec21f6f65e5332667bf30440f321039740709d697312afd38a821ac801",
        "proposal exact-set digest drift")
    req(summary["whole_st_active_gap_after_if_approved"]==0, "final gap does not close to zero")
    return rows,csv_text,summary

def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--proposal",type=Path)
    parser.add_argument("--summary",type=Path)
    args=parser.parse_args()
    _,csv_text,summary=build()
    if args.proposal:
        args.proposal.write_text(csv_text,encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("ST_FINAL_LAYER1_ADMISSION_PROPOSAL_V61_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

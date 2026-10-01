#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json
from pathlib import Path

import replay_stm32g0_ordering_authority_v17 as metadata
from stm32g0_foundation import read_catalog
from stm32g0_phase4_8b_discovery import resolve_mapping

HERE=Path(__file__).resolve().parent
PRODUCTION=HERE/"stm32g0-commercial-icpn.csv"

FIELDS=(
 "manufacturer","icpn","family","series","base_device","marketing_status",
 "catalog_resolution","package","pin_count","flash_size","temperature_grade",
 "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
 "existing_identifier","openocd_target_config","metadata_source_reference",
 "source_authority","verification_status"
)

def req(ok,msg):
    if not ok: raise ValueError(msg)

def proposal_rows():
    rows,summary=metadata.build()
    req(summary["fully_metadata_decoded_exact"]==359,"metadata replay drift")
    catalog=read_catalog()
    out=[]
    unique=unmapped=0
    for row in rows:
        m=resolve_mapping(row["icpn"],catalog)
        status=m.get("status")
        if status=="unique":
            unique+=1
            backend_state="mapping_candidate"
            route="unique_ordering_pattern"
            existing=m.get("existing_identifier","")
            configs=m.get("target_configs") or []
            req(configs==["tcl/target/stm32g0x.cfg"],f'{row["icpn"]}: target config drift')
            target=configs[0]
        elif status=="unmapped":
            unmapped+=1
            backend_state="no_mapping"
            route="unmapped"
            existing=target=""
        else:
            raise ValueError(f'{row["icpn"]}: unexpected route status {status}')
        out.append({
          "manufacturer":row["manufacturer"],"icpn":row["icpn"],"family":row["family"],
          "series":row["series"],"base_device":row["base_device"],
          "marketing_status":"Active","catalog_resolution":"normalized",
          "package":row["package"],"pin_count":row["pin_count"],"flash_size":row["flash_size"],
          "temperature_grade":row["temperature_grade"],"option_suffix":row["option_suffix"],
          "backend_type":"openocd","backend_mapping_state":backend_state,
          "backend_route_observation":route,"existing_identifier":existing,
          "openocd_target_config":target,
          "metadata_source_reference":row["source_reference"],
          "source_authority":row["source_authority"],
          "verification_status":row["verification_status"],
        })
    req((unique,unmapped)==(317,42),"route partition drift")
    return out

def render_csv(rows):
    from io import StringIO
    s=StringIO()
    w=csv.DictWriter(s,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader(); w.writerows(rows)
    return s.getvalue()

def build():
    rows=proposal_rows()
    text=render_csv(rows)
    exact_hash=hashlib.sha256(
      ("\n".join(r["icpn"] for r in rows)+"\n").encode()).hexdigest()
    csv_hash=hashlib.sha256(text.encode()).hexdigest()
    mapped=sum(r["backend_mapping_state"]=="mapping_candidate" for r in rows)
    no_mapping=sum(r["backend_mapping_state"]=="no_mapping" for r in rows)
    return rows,text,{
      "proposal_id":"stm32g0-layer1-catalog-admission-proposal-v1.8",
      "record_state":"RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
      "candidate_exact_count":359,
      "candidate_exact_set_sha256":exact_hash,
      "candidate_csv_sha256":csv_hash,
      "layer1_catalog_resolution":{"normalized":359},
      "layer2_backend_state":{"mapping_candidate":mapped,"no_mapping":no_mapping},
      "current_g0_active_exact":406,
      "current_g0_production_exact":47,
      "proposed_g0_catalog_exact_after":406,
      "g0_active_coverage_after_percent":100.0,
      "whole_st_active_exact_denominator":4550,
      "whole_st_current_active_intersection":2604,
      "whole_st_proposed_active_intersection_after":2963,
      "whole_st_active_gap_after":1587,
      "whole_st_active_coverage_after_percent":round(2963/4550*100,4),
      "production_exact_total_before":2683,
      "production_exact_total_after_if_approved":3042,
      "production_write_authorized":False,
      "backend_mapping_required_for_layer1_admission":False,
      "engineering_verified_claimed":False,
      "field_evidence_claimed":False,
    }

def main():
    import argparse
    ap=argparse.ArgumentParser()
    ap.add_argument("--csv-output",type=Path)
    ap.add_argument("--json-output",type=Path)
    args=ap.parse_args()
    rows,text,summary=build()
    if args.csv_output:
        args.csv_output.write_text(text,encoding="utf-8")
    if args.json_output:
        args.json_output.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import json
from pathlib import Path
import prepare_stm32g0_layer1_admission_proposal_v18 as p

HERE=Path(__file__).resolve().parent
LOCK=HERE/"stm32g0-layer1-admission-proposal-v1.8.json"

def main():
    frozen=json.loads(LOCK.read_text(encoding="utf-8"))
    _,_,live=p.build()
    for key in (
      "proposal_id","record_state","candidate_exact_count",
      "candidate_exact_set_sha256","candidate_csv_sha256",
      "layer1_catalog_resolution","layer2_backend_state",
      "current_g0_active_exact","current_g0_production_exact",
      "proposed_g0_catalog_exact_after","g0_active_coverage_after_percent",
      "whole_st_active_exact_denominator","whole_st_current_active_intersection",
      "whole_st_proposed_active_intersection_after","whole_st_active_gap_after",
      "whole_st_active_coverage_after_percent","production_exact_total_before",
      "production_exact_total_after_if_approved","production_write_authorized",
      "backend_mapping_required_for_layer1_admission",
      "engineering_verified_claimed","field_evidence_claimed"
    ):
        if frozen[key] != live[key]:
            raise SystemExit(f"proposal lock drift: {key}")
    print("STM32G0_LAYER1_ADMISSION_PROPOSAL_V18_LOCK_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import json
from pathlib import Path

import prepare_stm32wl3_layer1_admission_proposal_v46 as p

HERE=Path(__file__).resolve().parent
LOCK=HERE/"stm32wl3-layer1-admission-proposal-v4.6.json"

LOCKED_KEYS=(
    "schema_version","proposal_id","record_state","production_write_authorized",
    "production_exact_prestate","production_source_count_prestate",
    "production_wl3_exact_prestate","current_wl3_active_exact",
    "current_wl3_active_intersection_prestate","proposal_addition_count",
    "proposal_exact_set_sha256","proposal_csv_sha256","authority_id","authority_sha256",
    "layer1_catalog_resolution","metadata_direct_ordering_information_exact_count",
    "metadata_bounded_exception_exact_count","metadata_exception_exact_icpns",
    "backend_scope_evaluated","backend_state_for_new_rows","backend_state_semantics",
    "backend_mapping_required_for_layer1_admission","programming_profile_binding_claimed",
    "programming_profile_scope_expanded","series_counts","package_counts",
    "production_wl3_exact_after_if_approved","production_source_count_after_if_approved",
    "wl3_current_active_identity_coverage_after_if_published",
    "production_exact_after_if_approved","whole_st_active_exact_denominator",
    "whole_st_active_intersection_prestate","whole_st_active_intersection_after_if_approved",
    "whole_st_active_gap_after_if_approved","whole_st_active_coverage_after_if_approved_percent",
    "engineering_verified_claimed","field_evidence_claimed","ps_hil_claimed",
)

def main()->int:
    frozen=json.loads(LOCK.read_text(encoding="utf-8"))
    _,_,live=p.build()
    for key in LOCKED_KEYS:
        if frozen[key]!=live[key]:
            raise SystemExit(
                f"STM32WL3 proposal lock drift: {key}: "
                f"frozen={frozen[key]!r} live={live[key]!r}"
            )
    if frozen["source_pr"]!=730:
        raise SystemExit("STM32WL3 proposal source PR drift")
    if frozen["source_workflow_run_id"]!=37426648748:
        raise SystemExit("STM32WL3 proposal workflow run drift")
    if frozen["source_artifact_id"]!=11395307934:
        raise SystemExit("STM32WL3 proposal artifact id drift")
    if frozen["source_artifact_zip_sha256"]!="9bc906cb2fca075a8802bad476363337829506233dd9231856242d07d6fcbb07":
        raise SystemExit("STM32WL3 proposal artifact digest drift")
    print("STM32WL3_LAYER1_ADMISSION_PROPOSAL_V46_LOCK_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

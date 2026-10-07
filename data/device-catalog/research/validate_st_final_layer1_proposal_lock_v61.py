#!/usr/bin/env python3
import json
from pathlib import Path

import prepare_st_final_layer1_admission_proposal_v61 as p

HERE=Path(__file__).resolve().parent
LOCK=HERE/"st-final-layer1-admission-proposal-v6.1.json"

LOCKED_KEYS=(
    "schema_version","proposal_id","record_state","production_write_authorized",
    "production_exact_prestate","production_source_count_prestate",
    "proposal_addition_count","proposal_exact_set_sha256","proposal_csv_sha256",
    "family_addition_counts","family_production_prestates",
    "family_production_after_if_approved","metadata_ready_exact_count",
    "metadata_ordering_grammar_exact_count","metadata_official_exact_product_exact_count",
    "metadata_blocked_exact_count","metadata_exception_exact_count",
    "opaque_suffix_literal_exact_count","f4_lifecycle_authority_conflict_exact_count",
    "backend_scope_evaluated","existing_family_backend_mapping_inherited",
    "backend_type_claimed","backend_state_for_new_rows",
    "backend_mapping_required_for_layer1_admission",
    "programming_profile_binding_claimed","programming_profile_scope_expanded",
    "production_exact_after_if_approved","production_source_count_after_if_approved",
    "catalog_backend_partition_after_if_approved","whole_st_active_exact_denominator",
    "whole_st_active_intersection_prestate","whole_st_active_intersection_after_if_approved",
    "whole_st_active_gap_after_if_approved",
    "whole_st_active_coverage_after_if_approved_percent",
    "scoped_st_active_identity_coverage_after_if_published",
    "engineering_verified_claimed","field_evidence_claimed","ps_hil_claimed",
)

def main()->int:
    frozen=json.loads(LOCK.read_text(encoding="utf-8"))
    _,_,live=p.build()
    for key in LOCKED_KEYS:
        if frozen[key]!=live[key]:
            raise SystemExit(
                f"final ST proposal lock drift: {key}: frozen={frozen[key]!r} live={live[key]!r}"
            )
    if frozen["source_pr"]!=747:
        raise SystemExit("source PR drift")
    if frozen["source_workflow_run_id"]!=37572250038:
        raise SystemExit("source workflow run drift")
    if frozen["source_artifact_id"]!=11461201671:
        raise SystemExit("source artifact id drift")
    if frozen["source_artifact_sha256"]!="30a82373e31dd9da5ad93de1deaf52da56b56b6b8ca1f0f4206c7c427a0f951c":
        raise SystemExit("source artifact digest drift")
    if frozen["metadata_replay_pr"]!=746:
        raise SystemExit("metadata replay PR drift")
    if frozen["metadata_replay_merge_commit"]!="491e30660cb3a42838bd0555897bb0b5bf4278c4":
        raise SystemExit("metadata replay merge commit drift")
    if frozen["metadata_authority_git_blob_sha"]!="9f260f83c9f81147f1c768c846abcc39c9fd2bc8":
        raise SystemExit("metadata authority binding drift")
    print("ST_FINAL_LAYER1_ADMISSION_PROPOSAL_V61_LOCK_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

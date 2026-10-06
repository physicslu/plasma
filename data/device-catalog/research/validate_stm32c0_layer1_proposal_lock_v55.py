#!/usr/bin/env python3
import json
from pathlib import Path

import prepare_stm32c0_layer1_admission_proposal_v55 as p

HERE = Path(__file__).resolve().parent
LOCK = HERE / "stm32c0-layer1-admission-proposal-v5.5.json"

LOCKED_KEYS = (
    "schema_version","proposal_id","record_state","production_write_authorized",
    "production_exact_prestate","production_source_count_prestate",
    "production_c0_exact_prestate","current_c0_active_exact",
    "current_c0_active_intersection_prestate","proposal_addition_count",
    "proposal_exact_set_sha256","proposal_csv_sha256",
    "base_authority_sha256","delta_authority_id","delta_authority_sha256",
    "layer1_catalog_resolution","metadata_direct_ordering_information_exact_count",
    "metadata_bounded_exception_exact_count","metadata_exception_exact_icpns",
    "lifecycle_delta_exact_icpns","new_package_semantics",
    "backend_scope_evaluated","backend_type_claimed","backend_state_for_new_rows",
    "backend_state_semantics","backend_mapping_required_for_layer1_admission",
    "programming_profile_binding_claimed","programming_profile_scope_expanded",
    "series_counts","package_counts","production_c0_exact_after_if_approved",
    "production_source_count_after_if_approved",
    "c0_current_active_identity_coverage_after_if_published",
    "production_exact_after_if_approved","catalog_backend_partition_after_if_approved",
    "whole_st_active_exact_denominator","whole_st_active_intersection_prestate",
    "whole_st_active_intersection_after_if_approved",
    "whole_st_active_gap_after_if_approved",
    "whole_st_active_coverage_after_if_approved_percent",
    "engineering_verified_claimed","field_evidence_claimed","ps_hil_claimed",
)

def main() -> int:
    frozen = json.loads(LOCK.read_text(encoding="utf-8"))
    _, _, live = p.build()

    for key in LOCKED_KEYS:
        if frozen[key] != live[key]:
            raise SystemExit(
                f"STM32C0 proposal lock drift: {key}: "
                f"frozen={frozen[key]!r} live={live[key]!r}"
            )

    if frozen["source_pr"] != 739:
        raise SystemExit("STM32C0 proposal source PR drift")
    if frozen["source_workflow_run_id"] != 37472025031:
        raise SystemExit("STM32C0 proposal workflow run drift")
    if frozen["source_artifact_id"] != 11417885710:
        raise SystemExit("STM32C0 proposal artifact id drift")
    if frozen["source_artifact_zip_sha256"] != (
        "8e877965282eb3b46f4fe131de3591ea11616d7232884b701f131ba6d8a7968a"
    ):
        raise SystemExit("STM32C0 proposal artifact digest drift")
    if frozen["metadata_replay_pr"] != 738:
        raise SystemExit("STM32C0 metadata replay PR drift")
    if frozen["metadata_replay_merge_commit"] != (
        "5727124d98e2f26afd72d197fe35767b719e6514"
    ):
        raise SystemExit("STM32C0 metadata replay merge commit drift")

    print("STM32C0_LAYER1_ADMISSION_PROPOSAL_V55_LOCK_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

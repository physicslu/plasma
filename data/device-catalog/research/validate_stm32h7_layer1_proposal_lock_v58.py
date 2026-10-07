#!/usr/bin/env python3
import json
from pathlib import Path

import prepare_stm32h7_layer1_admission_proposal_v58 as p

HERE = Path(__file__).resolve().parent
LOCK = HERE / "stm32h7-layer1-admission-proposal-v5.8.json"

LOCKED_KEYS = (
    "schema_version","proposal_id","record_state","production_write_authorized",
    "production_exact_prestate","production_source_count_prestate",
    "production_h7_exact_prestate","current_h7_active_exact",
    "current_h7_active_intersection_prestate","proposal_addition_count",
    "proposal_exact_set_sha256","proposal_csv_sha256",
    "metadata_direct_ordering_information_exact_count",
    "metadata_bounded_exception_exact_count","metadata_exception_exact_icpns",
    "authority_extensions","backend_scope_evaluated",
    "existing_family_backend_mapping_inherited","backend_type_claimed",
    "backend_state_for_new_rows","backend_state_semantics",
    "backend_mapping_required_for_layer1_admission",
    "programming_profile_binding_claimed","programming_profile_scope_expanded",
    "series_counts","package_counts","production_h7_exact_after_if_approved",
    "production_source_count_after_if_approved",
    "h7_current_active_identity_coverage_after_if_published",
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
                f"STM32H7 proposal lock drift: {key}: "
                f"frozen={frozen[key]!r} live={live[key]!r}"
            )

    if frozen["source_pr"] != 744:
        raise SystemExit("STM32H7 proposal source PR drift")
    if frozen["source_workflow_run_id"] != 37552012782:
        raise SystemExit("STM32H7 proposal workflow run drift")
    if frozen["source_artifact_id"] != 11452379640:
        raise SystemExit("STM32H7 proposal artifact id drift")
    if frozen["source_artifact_sha256"] != (
        "888e9a696701e2d3b59b54c2cce0d5daa2f8070ad6805096f937aba27f42681d"
    ):
        raise SystemExit("STM32H7 proposal artifact digest drift")
    if frozen["metadata_replay_pr"] != 742:
        raise SystemExit("STM32H7 metadata replay PR drift")
    if frozen["metadata_replay_merge_commit"] != (
        "33ba7751eb183af2e37899e2778ebb4326a78951"
    ):
        raise SystemExit("STM32H7 metadata replay merge commit drift")
    if frozen["delta_authority_git_blob_sha"] != (
        "ccaee688584623147a118700155a9404f9940e07"
    ):
        raise SystemExit("STM32H7 delta authority binding drift")
    if frozen["base_authority_git_blob_sha"] != (
        "4e01d06fee1318c35390ad7707f884b3203d3d3f"
    ):
        raise SystemExit("STM32H7 base authority binding drift")

    print("STM32H7_LAYER1_ADMISSION_PROPOSAL_V58_LOCK_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

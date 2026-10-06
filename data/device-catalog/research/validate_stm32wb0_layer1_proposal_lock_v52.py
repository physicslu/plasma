#!/usr/bin/env python3
import json
from pathlib import Path

import prepare_stm32wb0_layer1_admission_proposal_v52 as p

HERE = Path(__file__).resolve().parent
LOCK = HERE / "stm32wb0-layer1-admission-proposal-v5.2.json"

LOCKED_KEYS = (
    "schema_version","proposal_id","record_state","production_write_authorized",
    "production_exact_prestate","production_source_count_prestate",
    "production_wb0_exact_prestate","current_wb0_active_exact",
    "current_wb0_active_intersection_prestate","proposal_addition_count",
    "proposal_exact_set_sha256","proposal_csv_sha256","authority_id","authority_sha256",
    "layer1_catalog_resolution","metadata_direct_ordering_information_exact_count",
    "metadata_bounded_exception_exact_count","metadata_exception_exact_icpns",
    "network_coprocessor_exact_count","network_coprocessor_semantic_preserved",
    "package_dependent_physical_pin_count_preserved",
    "backend_scope_evaluated","backend_type_claimed","backend_state_for_new_rows",
    "backend_state_semantics","backend_mapping_required_for_layer1_admission",
    "programming_profile_binding_claimed","programming_profile_scope_expanded",
    "series_counts","package_counts","production_wb0_exact_after_if_approved",
    "production_source_count_after_if_approved",
    "wb0_current_active_identity_coverage_after_if_published",
    "production_exact_after_if_approved","whole_st_active_exact_denominator",
    "whole_st_active_intersection_prestate","whole_st_active_intersection_after_if_approved",
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
                f"STM32WB0 proposal lock drift: {key}: "
                f"frozen={frozen[key]!r} live={live[key]!r}"
            )

    if frozen["source_pr"] != 736:
        raise SystemExit("STM32WB0 proposal source PR drift")
    if frozen["source_workflow_run_id"] != 37437294647:
        raise SystemExit("STM32WB0 proposal workflow run drift")
    if frozen["source_artifact_id"] != 11398828505:
        raise SystemExit("STM32WB0 proposal artifact id drift")
    if frozen["source_artifact_zip_sha256"] != (
        "9b09987703f2866d1364467ec1ca46360ca63c5979b08be233963ccd31a93e54"
    ):
        raise SystemExit("STM32WB0 proposal artifact digest drift")
    if frozen["metadata_replay_pr"] != 735:
        raise SystemExit("STM32WB0 metadata replay PR drift")
    if frozen["metadata_replay_merge_commit"] != (
        "6c6ff298f275b514ed396328b74d9f3a28fa72ed"
    ):
        raise SystemExit("STM32WB0 metadata replay merge commit drift")

    print("STM32WB0_LAYER1_ADMISSION_PROPOSAL_V52_LOCK_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

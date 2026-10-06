#!/usr/bin/env python3
import json
from pathlib import Path

import prepare_stm32n6_layer1_admission_proposal_v49 as p

HERE = Path(__file__).resolve().parent
LOCK = HERE / "stm32n6-layer1-admission-proposal-v4.9.json"

LOCKED_KEYS = (
    "schema_version","proposal_id","record_state","production_write_authorized",
    "production_exact_prestate","production_source_count_prestate",
    "production_n6_exact_prestate","current_n6_active_exact",
    "current_n6_active_intersection_prestate","proposal_addition_count",
    "proposal_exact_set_sha256","proposal_csv_sha256","authority_id","authority_sha256",
    "layer1_catalog_resolution","metadata_direct_ordering_information_exact_count",
    "metadata_bounded_exception_exact_count","metadata_exception_exact_icpns",
    "backend_scope_evaluated","backend_type_claimed","backend_state_for_new_rows",
    "backend_state_semantics","backend_mapping_required_for_layer1_admission",
    "external_memory_programming_profile_boundary",
    "programming_profile_binding_claimed","programming_profile_scope_expanded",
    "series_counts","package_counts","production_n6_exact_after_if_approved",
    "production_source_count_after_if_approved",
    "n6_current_active_identity_coverage_after_if_published",
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
                f"STM32N6 proposal lock drift: {key}: "
                f"frozen={frozen[key]!r} live={live[key]!r}"
            )

    if frozen["source_pr"] != 733:
        raise SystemExit("STM32N6 proposal source PR drift")
    if frozen["source_workflow_run_id"] != 37434384862:
        raise SystemExit("STM32N6 proposal workflow run drift")
    if frozen["source_artifact_id"] != 11397719001:
        raise SystemExit("STM32N6 proposal artifact id drift")
    if frozen["source_artifact_zip_sha256"] != (
        "2a122b622d25822e57d391700d1d36ae140533253ee65be135da77fd4757d9f6"
    ):
        raise SystemExit("STM32N6 proposal artifact digest drift")
    if frozen["metadata_replay_pr"] != 732:
        raise SystemExit("STM32N6 metadata replay PR drift")
    if frozen["metadata_replay_merge_commit"] != (
        "86098df51d458d83ec118c07a88591025bf7235c"
    ):
        raise SystemExit("STM32N6 metadata replay merge commit drift")

    print("STM32N6_LAYER1_ADMISSION_PROPOSAL_V49_LOCK_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
import json
from pathlib import Path

import prepare_stm32f2_layer1_admission_proposal_v40 as p

HERE = Path(__file__).resolve().parent
LOCK = HERE / "stm32f2-layer1-admission-proposal-v4.0.json"

LOCKED_KEYS = (
    "schema_version",
    "proposal_id",
    "record_state",
    "production_write_authorized",
    "production_exact_prestate",
    "production_f2_exact_prestate",
    "current_f2_active_exact",
    "current_f2_active_intersection_prestate",
    "proposal_addition_count",
    "proposal_exact_set_sha256",
    "proposal_csv_sha256",
    "authority_id",
    "authority_sha256",
    "layer1_catalog_resolution",
    "backend_scope_evaluated",
    "backend_state_for_new_rows",
    "backend_state_semantics",
    "backend_mapping_required_for_layer1_admission",
    "programming_profile_binding_claimed",
    "programming_profile_scope_expanded",
    "metadata_exception_exact_icpns",
    "direct_ordering_information_exact_count",
    "series_counts",
    "package_counts",
    "production_f2_exact_after_if_approved",
    "f2_current_active_identity_coverage_after_if_published",
    "production_exact_after_if_approved",
    "whole_st_active_exact_denominator",
    "whole_st_active_intersection_prestate",
    "whole_st_active_intersection_after_if_approved",
    "whole_st_active_gap_after_if_approved",
    "whole_st_active_coverage_after_if_approved_percent",
    "engineering_verified_claimed",
    "field_evidence_claimed",
    "ps_hil_claimed",
)

def main() -> int:
    frozen = json.loads(LOCK.read_text(encoding="utf-8"))
    _, _, live = p.build()
    for key in LOCKED_KEYS:
        if frozen[key] != live[key]:
            raise SystemExit(
                f"STM32F2 proposal lock drift: {key}: frozen={frozen[key]!r} live={live[key]!r}"
            )
    print("STM32F2_LAYER1_ADMISSION_PROPOSAL_V40_LOCK_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

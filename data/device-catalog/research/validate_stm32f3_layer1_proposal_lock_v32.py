#!/usr/bin/env python3
import json
from pathlib import Path

import prepare_stm32f3_layer1_admission_proposal_v32 as p

HERE = Path(__file__).resolve().parent
LOCK = HERE / "stm32f3-layer1-admission-proposal-v3.2.json"

LOCKED_KEYS = (
    "schema_version",
    "proposal_id",
    "record_state",
    "production_write_authorized",
    "production_exact_prestate",
    "production_f3_exact_prestate",
    "current_f3_active_exact",
    "current_f3_active_intersection_prestate",
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
    "series_counts",
    "package_counts",
    "production_f3_exact_after_if_approved",
    "f3_current_active_identity_coverage_after_if_published",
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
                f"STM32F3 proposal lock drift: {key}: frozen={frozen[key]!r} live={live[key]!r}"
            )
    print("STM32F3_LAYER1_ADMISSION_PROPOSAL_V32_LOCK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

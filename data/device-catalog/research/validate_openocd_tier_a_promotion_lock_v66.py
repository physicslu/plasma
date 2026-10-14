#!/usr/bin/env python3
import json
from pathlib import Path

import prepare_openocd_tier_a_backend_promotion_v66 as p

HERE=Path(__file__).resolve().parent
LOCK=HERE/"openocd-tier-a-backend-promotion-proposal-v6.6.json"

LOCKED_KEYS=(
    "schema_version",
    "proposal_id",
    "record_state",
    "production_write_authorized",
    "source_qualification_id",
    "promotion_exact_count",
    "promotion_exact_set_sha256",
    "promotion_delta_csv_sha256",
    "family_promotion_counts",
    "identifier_kind_counts",
    "affected_family_source_bindings_after_if_approved",
    "production_exact_total_before",
    "production_exact_total_after_if_approved",
    "production_source_count_before",
    "production_source_count_after_if_approved",
    "catalog_backend_partition_before",
    "catalog_backend_partition_after_if_approved",
    "active_openocd_route_before",
    "active_openocd_route_after_if_approved",
    "scoped_active_denominator",
    "active_openocd_route_coverage_after_if_approved_percent",
    "active_openocd_route_gap_after_if_approved",
    "programming_profile_state_for_promotions",
    "route_evidence_validation_status",
    "claims",
)

def main()->int:
    frozen=json.loads(LOCK.read_text(encoding="utf-8"))
    _,_,live=p.build()
    for key in LOCKED_KEYS:
        if frozen[key]!=live[key]:
            raise SystemExit(
                f"OpenOCD Tier A v6.6 lock drift: {key}: "
                f"frozen={frozen[key]!r} live={live[key]!r}"
            )
    if frozen["source_pr"]!=753:
        raise SystemExit("source PR drift")
    if frozen["source_workflow_run_id"]!=37590758341:
        raise SystemExit("source workflow run drift")
    if frozen["source_workflow_head_sha"]!="8b4e5aad14d55d5ceb0a8c088ac73219ba059e51":
        raise SystemExit("source workflow head drift")
    if frozen["source_artifact_id"]!=11469080022:
        raise SystemExit("source artifact id drift")
    if frozen["source_artifact_sha256"]!="e66a9882e972e6c8458fcaa18e1070ab87485a7398af248ec1f0f4e7dcf9faa9":
        raise SystemExit("source artifact digest drift")
    if frozen["upstream_identifier_qualification_pr"]!=752:
        raise SystemExit("upstream qualification PR drift")
    if frozen["upstream_identifier_qualification_merge_commit"]!="1bc5ea8c38851f7ffa7f5c0244adb77b9727b2a8":
        raise SystemExit("upstream qualification merge drift")
    print("OPENOCD_TIER_A_BACKEND_PROMOTION_PROPOSAL_V66_LOCK_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

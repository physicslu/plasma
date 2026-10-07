#!/usr/bin/env python3
import json
from pathlib import Path

import qualify_openocd_tier_a_identifiers_v65 as q

HERE=Path(__file__).resolve().parent
LOCK=HERE/"openocd-tier-a-identifier-qualification-v6.5.json"

LOCKED_KEYS=(
    "schema_version",
    "qualification_id",
    "record_state",
    "input_tier_a_exact_count",
    "identifier_qualified_exact_count",
    "identifier_blocked_exact_count",
    "identifier_ambiguous_exact_count",
    "qualified_exact_set_sha256",
    "blocked_exact_set_sha256",
    "qualified_csv_sha256",
    "blocked_csv_sha256",
    "qualified_family_counts",
    "blocked_family_counts",
    "resolved_identifier_kind_counts",
    "route_inventory_git_blob_sha",
    "route_inventory_semantics",
    "current_active_openocd_route_exact_count",
    "projected_route_exact_count_if_qualified_set_later_promoted",
    "scoped_active_denominator",
    "projected_route_coverage_percent_if_qualified_set_later_promoted",
    "projected_remaining_gap_if_qualified_set_later_promoted",
    "claims",
)

def main()->int:
    frozen=json.loads(LOCK.read_text(encoding="utf-8"))
    _,_,_,_,live=q.build()
    for key in LOCKED_KEYS:
        if frozen[key]!=live[key]:
            raise SystemExit(
                f"OpenOCD Tier A v6.5 lock drift: {key}: "
                f"frozen={frozen[key]!r} live={live[key]!r}"
            )
    if frozen["source_pr"]!=752:
        raise SystemExit("source PR drift")
    if frozen["source_workflow_run_id"]!=37590248210:
        raise SystemExit("source workflow run drift")
    if frozen["source_workflow_head_sha"]!="422f766560e59cda2dcc96e5fd61f113e0646c05":
        raise SystemExit("source workflow head drift")
    if frozen["source_artifact_id"]!=11467978681:
        raise SystemExit("source artifact id drift")
    if frozen["source_artifact_sha256"]!="818d603070d314ce136a5642d5a304e3734fd40f6bf9d6d4474ef29840d2fcb8":
        raise SystemExit("source artifact digest drift")
    if frozen["upstream_route_candidate_pr"]!=751:
        raise SystemExit("upstream route candidate PR drift")
    if frozen["upstream_route_candidate_merge_commit"]!="4d767b8401ad1979ef45d4554d5d09af72c2399a":
        raise SystemExit("upstream route candidate merge drift")
    print("OPENOCD_TIER_A_IDENTIFIER_QUALIFICATION_V65_LOCK_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

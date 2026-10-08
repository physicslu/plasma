#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import diagnose_openocd_a_residual_v618 as v618
import qualify_openocd_tier_a_identifiers_v65 as v65

EXPECTED_V618_EXACT_SET_SHA256 = "4868ba98e6162c7e4a97659058b3f55724f0e81e2c82c3ca352ce43c0d3cc851"
EXPECTED_V618_CSV_SHA256 = "df604ee4d02489016421fb4e684860161feb4d4ed0581b260c677a044f57e3b3"
EXPECTED_ROUTE_INVENTORY_GIT_BLOB_SHA = "0ef056e3363e20bb527590c4a4cc1cc0d7afb810"
EXPECTED_EXACT_COUNT = 17
EXPECTED_FAMILY_COUNTS = {
    "STM32F3": 4,
    "STM32G0": 12,
    "STM32L1": 1,
}

FIELDS = (
    "manufacturer","icpn","family","series","base_device",
    "candidate_openocd_target_config",
    "resolved_existing_identifier","resolved_existing_identifier_kind",
    "openocd_distribution","route_validation_status",
    "commercial_source_reference","commercial_source_authority",
    "commercial_verification_status",
    "diagnostic_relation","route_relaxed_literal_char",
    "commercial_relaxed_position_char",
    "evidence_state","programming_profile_state",
    "production_write_authorized",
)


class EvidenceReviewError(RuntimeError):
    pass


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise EvidenceReviewError(msg)


def build() -> tuple[list[dict[str,str]], str, dict[str,Any]]:
    diagnostic, _, v618_summary = v618.build()
    req(
        v618_summary["diagnostic_exact_set_sha256"] == EXPECTED_V618_EXACT_SET_SHA256,
        "v6.18 exact-set digest drift",
    )
    req(
        v618_summary["diagnostic_csv_sha256"] == EXPECTED_V618_CSV_SHA256,
        "v6.18 diagnostic CSV digest drift",
    )
    req(
        v65.EXPECTED_CATALOG_GIT_BLOB_SHA == EXPECTED_ROUTE_INVENTORY_GIT_BLOB_SHA,
        "frozen route-inventory digest drift",
    )

    selected = [
        row for row in diagnostic
        if row["probe_state"] == "unique_under_one_char_diagnostic"
    ]
    req(len(selected) == EXPECTED_EXACT_COUNT, f"v6.18 unique diagnostic drift: {len(selected)}")
    family_counts = dict(sorted(Counter(r["family"] for r in selected).items()))
    req(family_counts == EXPECTED_FAMILY_COUNTS, f"family partition drift: {family_counts}")

    production = v618.read_production_index()
    routes = v65.read_routes()
    out: list[dict[str,str]] = []

    for item in selected:
        row = production[item["icpn"]]
        target = item["candidate_openocd_target_config"]
        kinds = v65.allowed_kinds(row["family"])
        pool = [
            route for route in routes
            if route.get("plasma_series") == row["family"]
            and route.get("identifier_kind") in kinds
            and route.get("target_config") == target
            and route.get("subfamily") == row["series"]
        ]
        matches = v618.one_char_generalization_matches(item["normalized_core"], pool)
        req(len(matches) == 1, f"{item['icpn']}: one-char diagnostic no longer unique")
        route = matches[0]

        pattern = route["part_number"]
        req(pattern.endswith("x"), f"{item['icpn']}: expected terminal-wildcard ordering pattern")
        literal = pattern[:-1]
        req(len(literal) >= 2, f"{item['icpn']}: route identifier too short")
        diagnostic_prefix = literal[:-1]
        req(item["normalized_core"].startswith(diagnostic_prefix),
            f"{item['icpn']}: frozen one-char diagnostic relation drift")
        route_char = literal[-1]
        pos = len(diagnostic_prefix)
        commercial_char = (
            item["normalized_core"][pos]
            if len(item["normalized_core"]) > pos
            else ""
        )

        req(row["source_authority"] == "STMicroelectronics official",
            f"{item['icpn']}: commercial authority is not official ST")
        req(bool(row["source_reference"]), f"{item['icpn']}: missing commercial source reference")
        req(row["verification_status"].startswith("verified_"),
            f"{item['icpn']}: commercial identity is not in verified state")
        req(route.get("openocd_distribution") == "upstream-openocd",
            f"{item['icpn']}: route is not upstream OpenOCD")
        req(route.get("mapping_status") == "mapping_candidate",
            f"{item['icpn']}: route inventory state drift")
        req(route.get("validation_status") == "not_verified",
            f"{item['icpn']}: unexpected route validation state")

        out.append({
            "manufacturer": row["manufacturer"],
            "icpn": item["icpn"],
            "family": row["family"],
            "series": row["series"],
            "base_device": row["base_device"],
            "candidate_openocd_target_config": target,
            "resolved_existing_identifier": pattern,
            "resolved_existing_identifier_kind": route["identifier_kind"],
            "openocd_distribution": route["openocd_distribution"],
            "route_validation_status": route["validation_status"],
            "commercial_source_reference": row["source_reference"],
            "commercial_source_authority": row["source_authority"],
            "commercial_verification_status": row["verification_status"],
            "diagnostic_relation": "drop_final_literal_before_terminal_wildcard_exact_set_only",
            "route_relaxed_literal_char": route_char,
            "commercial_relaxed_position_char": commercial_char,
            "evidence_state": "commercial_identity_verified_route_candidate_unique_diagnostic_bridge",
            "programming_profile_state": "unresolved",
            "production_write_authorized": "false",
        })

    out.sort(key=lambda r: r["icpn"])
    req(len(out) == EXPECTED_EXACT_COUNT, "evidence review cardinality drift")
    req(len({r["icpn"] for r in out}) == EXPECTED_EXACT_COUNT, "duplicate exact ICPN")

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out)
    csv_text = buf.getvalue()

    bridges = {
        row["icpn"]: {
            "existing_identifier": row["resolved_existing_identifier"],
            "existing_identifier_kind": row["resolved_existing_identifier_kind"],
            "openocd_target_config": row["candidate_openocd_target_config"],
        }
        for row in out
    }

    summary = {
        "schema_version": 1,
        "review_id": "openocd-bounded-evidence-review-v6.19",
        "record_state": "RESEARCH_EXACT_SET_EVIDENCE_REVIEW",
        "input_v618_unique_one_char_exact_count": EXPECTED_EXACT_COUNT,
        "reviewed_exact_count": EXPECTED_EXACT_COUNT,
        "family_counts": family_counts,
        "reviewed_exact_set_sha256": hashlib.sha256(
            ("\n".join(r["icpn"] for r in out) + "\n").encode()
        ).hexdigest(),
        "review_csv_sha256": hashlib.sha256(csv_text.encode()).hexdigest(),
        "bridge_binding_sha256": hashlib.sha256(
            (
                "\n".join(
                    f"{icpn}|{binding['existing_identifier']}|"
                    f"{binding['existing_identifier_kind']}|{binding['openocd_target_config']}"
                    for icpn, binding in sorted(bridges.items())
                ) + "\n"
            ).encode()
        ).hexdigest(),
        "bridges": bridges,
        "source_evidence": {
            "v618_pr": 772,
            "v618_merge_commit": "f0bd658373880aa811893909790c1fa4c7541519",
            "v618_workflow_run_id": 37740572630,
            "v618_artifact_id": 11533722380,
            "v618_artifact_sha256": "7e4cb1a8d90decf784578fe7150e81ef795ed3fbcd1b67c377a419ab2413999f",
            "v618_diagnostic_exact_set_sha256": EXPECTED_V618_EXACT_SET_SHA256,
            "v618_diagnostic_csv_sha256": EXPECTED_V618_CSV_SHA256,
            "route_inventory_git_blob_sha": EXPECTED_ROUTE_INVENTORY_GIT_BLOB_SHA,
        },
        "evidence_interpretation": {
            "commercial_identity_authority": "official ST verified Production identity",
            "route_authority": "frozen upstream OpenOCD mapping-candidate inventory",
            "bridge_scope": "exact 17-row set only",
            "generic_one_char_rule_supported": False,
            "route_programming_validation": "not_verified",
        },
        "coverage_projection_if_later_promoted": {
            "current_active_openocd_route_exact_count": 3958,
            "bounded_bridge_candidates": 17,
            "potential_active_openocd_route_exact_count": 3975,
            "scoped_active_denominator": 4550,
            "potential_coverage_percent": 87.3626,
            "remaining_gap": 575,
        },
        "governance": {
            "exact_set_bridge_candidate": True,
            "generic_one_char_generalization_authorized": False,
            "production_mapping_write_authorized": False,
            "programming_profile_binding_claimed": False,
            "programming_verified_claimed": False,
            "engineering_verified_claimed": False,
            "hil_verified_claimed": False,
        },
    }
    return out, csv_text, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    _, csv_text, summary = build()
    if args.review:
        args.review.write_text(csv_text, encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("OPENOCD_BOUNDED_EVIDENCE_REVIEW_V619_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

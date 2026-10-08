#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

import probe_openocd_tier_a_suffix_normalization_v67 as v67

HERE = Path(__file__).resolve().parent

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)

def build() -> dict[str, Any]:
    rows, _, summary67 = v67.build()
    req(summary67["input_blocked_exact_count"] == 69, "v6.7 blocked cardinality drift")
    req(summary67["unique_after_catalog_suffix_removal_exact_count"] == 33,
        "v6.7 unique suffix-normalization count drift")

    selected = [
        row for row in rows
        if row["normalization_probe_state"] == "unique_after_catalog_suffix_removal"
    ]
    req(len(selected) == 33, "bounded suffix scope drift")
    req(len({row["icpn"] for row in selected}) == 33, "duplicate ICPN in bounded suffix scope")

    bridges = {}
    for row in sorted(selected, key=lambda r: r["icpn"]):
        req(row["option_suffix"], f'{row["icpn"]}: empty option suffix entered bounded policy')
        req(row["match_count"] == "1", f'{row["icpn"]}: suffix normalization is not unique')
        req(row["resolved_existing_identifier"], f'{row["icpn"]}: missing identifier')
        req(row["resolved_identifier_kind"] in {"ordering_pattern", "cmsis_device_name"},
            f'{row["icpn"]}: unsupported identifier kind')
        bridges[row["icpn"]] = {
            "family": row["family"],
            "series": row["series"],
            "base_device": row["base_device"],
            "option_suffix": row["option_suffix"],
            "normalized_core": row["normalized_core"],
            "existing_identifier": row["resolved_existing_identifier"],
            "existing_identifier_kind": row["resolved_identifier_kind"],
            "openocd_target_config": row["candidate_openocd_target_config"],
        }

    exacts = sorted(bridges)
    exact_set_sha = hashlib.sha256(("\n".join(exacts) + "\n").encode()).hexdigest()
    binding_lines = [
        "|".join((
            icpn,
            bridges[icpn]["family"],
            bridges[icpn]["option_suffix"],
            bridges[icpn]["normalized_core"],
            bridges[icpn]["existing_identifier_kind"],
            bridges[icpn]["existing_identifier"],
            bridges[icpn]["openocd_target_config"],
        ))
        for icpn in exacts
    ]
    binding_sha = hashlib.sha256(("\n".join(binding_lines) + "\n").encode()).hexdigest()

    family_counts = dict(sorted(Counter(v["family"] for v in bridges.values()).items()))
    suffix_counts = dict(sorted(Counter(v["option_suffix"] for v in bridges.values()).items()))
    kind_counts = dict(sorted(Counter(v["existing_identifier_kind"] for v in bridges.values()).items()))

    return {
        "schema_version": 1,
        "policy_id": "openocd-tier-a-bounded-suffix-normalization-v6.13",
        "record_state": "RESEARCH_POLICY_PROPOSAL_NOT_PRODUCTION",
        "source_probe": "openocd-tier-a-suffix-normalization-v6.7",
        "scope": {
            "exact_icpn_count": 33,
            "exact_icpns": exacts,
            "exact_set_sha256": exact_set_sha,
            "family_counts": family_counts,
            "option_suffix_counts": suffix_counts,
            "identifier_kind_counts": kind_counts,
        },
        "bridges": bridges,
        "binding_sha256": binding_sha,
        "governance": {
            "family_wide_suffix_removal_authorized": False,
            "exact_set_bridge_only": True,
            "future_unseen_icpn_covered": False,
            "production_mapping_write_authorized": False,
            "programming_profile_binding_claimed": False,
            "programming_verified_claimed": False,
            "engineering_verified_claimed": False,
            "hil_verified_claimed": False,
        },
        "coverage_projection_if_later_promoted": {
            "current_active_openocd_route_exact_count": 3594,
            "canonical_identifier_qualified": 320,
            "bounded_suffix_normalization_candidates": 33,
            "potential_active_openocd_route_exact_count": 3947,
            "scoped_active_denominator": 4550,
            "potential_coverage_percent": 86.7473,
            "remaining_gap": 603,
        },
    }

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    policy = build()
    text = json.dumps(policy, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    print("OPENOCD_TIER_A_BOUNDED_SUFFIX_V613_PASS")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

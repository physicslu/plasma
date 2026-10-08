#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import qualify_openocd_tier_a_identifiers_v65 as v65
import rebaseline_openocd_current_gap_v617 as v617

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_EXACT_COUNT = 25
EXPECTED_FAMILY_COUNTS = {
    "STM32C0": 5,
    "STM32F3": 4,
    "STM32G0": 12,
    "STM32G4": 1,
    "STM32L1": 1,
    "STM32L4": 2,
}
EXPECTED_SERIES_COUNTS = {
    "STM32C011": 1,
    "STM32C051": 1,
    "STM32C091": 1,
    "STM32C092": 2,
    "STM32F301": 3,
    "STM32F303": 1,
    "STM32G0B1": 8,
    "STM32G0C1": 4,
    "STM32G491": 1,
    "STM32L151": 1,
    "STM32L496": 2,
}

FIELDS = (
    "manufacturer","icpn","family","series","base_device","option_suffix",
    "candidate_openocd_target_config",
    "same_series_mapped_sibling_count",
    "same_series_route_rows","same_base_route_rows",
    "current_policy_match_count","suffix_normalized_policy_match_count",
    "prefix_probe_match_count","one_char_probe_match_count",
    "normalized_core","structural_gap_class","probe_state",
    "recommended_next_gate",
    "identifier_inferred","policy_change_authorized",
    "programming_profile_state","production_write_authorized",
)


class DiagnosticError(RuntimeError):
    pass


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise DiagnosticError(msg)


def read_production_index() -> dict[str,dict[str,str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out: dict[str,dict[str,str]] = {}
    for source in manifest["sources"]:
        path = (MANIFEST.parent / source["path"]).resolve()
        with path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                icpn = row["icpn"]
                req(icpn not in out, f"{icpn}: duplicate Production identity")
                out[icpn] = row
    return out


def literal_prefix(pattern: str) -> str:
    positions = [i for i, c in enumerate(pattern) if c.lower() == "x"]
    pos = min(positions or [len(pattern)])
    return pattern[:pos]


def normalize_catalog_suffix(row: dict[str,str]) -> str:
    icpn = row["icpn"]
    suffix = row.get("option_suffix", "")
    if suffix and icpn.endswith(suffix):
        return icpn[:-len(suffix)]
    return icpn


def dedup(rows: list[dict[str,str]]) -> list[dict[str,str]]:
    unique = {
        (r.get("part_number",""), r.get("identifier_kind",""), r.get("target_config","")): r
        for r in rows
    }
    return list(unique.values())


def resolve_policy_for_value(
    source: dict[str,str],
    value: str,
    target: str,
    routes: list[dict[str,str]],
) -> list[dict[str,str]]:
    candidate = {
        "icpn": value,
        "family": source["family"],
        "candidate_openocd_target_config": target,
    }
    return dedup(v65.resolve(candidate, routes))


def one_char_generalization_matches(
    normalized: str,
    same_series: list[dict[str,str]],
) -> list[dict[str,str]]:
    matches: list[dict[str,str]] = []
    for route in same_series:
        pattern = route.get("part_number", "")
        if route.get("identifier_kind") != "ordering_pattern" or not pattern.endswith("x"):
            continue
        prefix = pattern[:-1]
        if len(prefix) > 1 and normalized.startswith(prefix[:-1]):
            matches.append(route)
    return dedup(matches)


def build() -> tuple[list[dict[str,str]], str, dict[str,Any]]:
    current_gap, _, v617_summary = v617.build()
    req(v617_summary["current_gap_exact_count"] == 592, "v6.17 gap cardinality drift")

    residual = [
        row for row in current_gap
        if row["tier"] == "A_residual_same_series_existing_route"
    ]
    req(len(residual) == EXPECTED_EXACT_COUNT,
        f"current A residual count drift: {len(residual)}")

    family_counts = dict(sorted(Counter(r["family"] for r in residual).items()))
    series_counts = dict(sorted(Counter(r["series"] for r in residual).items()))
    req(family_counts == EXPECTED_FAMILY_COUNTS,
        f"current A residual family partition drift: {family_counts}")
    req(series_counts == EXPECTED_SERIES_COUNTS,
        f"current A residual series partition drift: {series_counts}")

    production = read_production_index()
    routes = v65.read_routes()
    out: list[dict[str,str]] = []

    for gap in residual:
        icpn = gap["icpn"]
        row = production[icpn]
        target = gap["candidate_openocd_target_config"]
        kinds = v65.allowed_kinds(row["family"])

        pool = [
            route for route in routes
            if route.get("plasma_series") == row["family"]
            and route.get("identifier_kind") in kinds
            and route.get("target_config") == target
        ]
        same_series = [
            route for route in pool
            if route.get("subfamily") == row["series"]
        ]
        same_base = [
            route for route in same_series
            if route.get("part_number","").startswith(row["base_device"])
            or row["base_device"].startswith(literal_prefix(route.get("part_number","")))
        ]

        current_matches = resolve_policy_for_value(row, row["icpn"], target, routes)
        normalized = normalize_catalog_suffix(row)
        suffix_matches = (
            resolve_policy_for_value(row, normalized, target, routes)
            if normalized != row["icpn"] else []
        )

        prefix_matches = dedup([
            route for route in same_series
            if route.get("identifier_kind") == "ordering_pattern"
            and route.get("part_number","").endswith("x")
            and normalized.startswith(route["part_number"][:-1])
        ])
        one_char_matches = one_char_generalization_matches(normalized, same_series)

        if same_base:
            structural = "route_inventory_present_policy_shape_gap"
        elif same_series:
            structural = "base_variant_absent_from_route_inventory"
        else:
            structural = "series_absent_from_route_inventory"

        if len(current_matches) == 1:
            probe_state = "unique_current_policy_match"
            gate = "qualify_current_policy_binding"
        elif len(current_matches) > 1:
            probe_state = "ambiguous_current_policy_match"
            gate = "resolve_policy_ambiguity_before_any_mapping"
        elif len(suffix_matches) == 1:
            probe_state = "unique_after_exact_catalog_suffix_removal"
            gate = "consider_exact_set_suffix_bridge_after_governance"
        elif len(suffix_matches) > 1:
            probe_state = "ambiguous_after_exact_catalog_suffix_removal"
            gate = "resolve_suffix_normalization_ambiguity"
        elif len(prefix_matches) == 1:
            probe_state = "unique_under_prefix_probe"
            gate = "review_bounded_prefix_bridge_not_family_wide_policy"
        elif len(prefix_matches) > 1:
            probe_state = "ambiguous_under_prefix_probe"
            gate = "reject_prefix_semantics_without_stronger_evidence"
        elif len(one_char_matches) == 1:
            probe_state = "unique_under_one_char_diagnostic"
            gate = "review_exact_set_bounded_bridge_with_authoritative_evidence"
        elif len(one_char_matches) > 1:
            probe_state = "ambiguous_under_one_char_diagnostic"
            gate = "reject_generalization_and_expand_route_evidence"
        elif structural == "base_variant_absent_from_route_inventory":
            probe_state = "no_identifier_probe_match"
            gate = "expand_canonical_route_inventory_for_missing_base_variant"
        elif structural == "series_absent_from_route_inventory":
            probe_state = "no_identifier_probe_match"
            gate = "expand_canonical_route_inventory_for_series"
        else:
            probe_state = "no_identifier_probe_match"
            gate = "obtain_authoritative_identifier_shape_evidence"

        out.append({
            "manufacturer": row["manufacturer"],
            "icpn": icpn,
            "family": row["family"],
            "series": row["series"],
            "base_device": row["base_device"],
            "option_suffix": row.get("option_suffix",""),
            "candidate_openocd_target_config": target,
            "same_series_mapped_sibling_count": gap["same_series_mapped_sibling_count"],
            "same_series_route_rows": str(len(same_series)),
            "same_base_route_rows": str(len(same_base)),
            "current_policy_match_count": str(len(current_matches)),
            "suffix_normalized_policy_match_count": str(len(suffix_matches)),
            "prefix_probe_match_count": str(len(prefix_matches)),
            "one_char_probe_match_count": str(len(one_char_matches)),
            "normalized_core": normalized,
            "structural_gap_class": structural,
            "probe_state": probe_state,
            "recommended_next_gate": gate,
            "identifier_inferred": "false",
            "policy_change_authorized": "false",
            "programming_profile_state": "unresolved",
            "production_write_authorized": "false",
        })

    out.sort(key=lambda row: row["icpn"])
    req(len(out) == EXPECTED_EXACT_COUNT, "diagnostic cardinality drift")
    req(len({r["icpn"] for r in out}) == EXPECTED_EXACT_COUNT, "duplicate diagnostic ICPN")

    req(all(r["current_policy_match_count"] == "0" for r in out),
        "unexpected current-policy match appeared in A residual set")
    req(all(r["suffix_normalized_policy_match_count"] == "0" for r in out),
        "unexpected suffix-normalized match appeared in A residual set")

    g0 = [r for r in out if r["family"] == "STM32G0"]
    req(len(g0) == 12, "G0 residual cardinality drift")
    req(all(r["prefix_probe_match_count"] == "0" for r in g0),
        "G0 prefix semantics changed from frozen v6.10 result")

    c0 = [r for r in out if r["family"] == "STM32C0"]
    req(len(c0) == 5, "C0 residual cardinality drift")
    req(all(r["structural_gap_class"] == "base_variant_absent_from_route_inventory" for r in c0),
        "C0 residual structure drifted from missing-base-variant class")

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out)
    csv_text = buf.getvalue()

    structural_counts = dict(sorted(Counter(r["structural_gap_class"] for r in out).items()))
    probe_counts = dict(sorted(Counter(r["probe_state"] for r in out).items()))
    gate_counts = dict(sorted(Counter(r["recommended_next_gate"] for r in out).items()))

    family_structural: dict[str,Counter[str]] = defaultdict(Counter)
    family_probe: dict[str,Counter[str]] = defaultdict(Counter)
    for row in out:
        family_structural[row["family"]][row["structural_gap_class"]] += 1
        family_probe[row["family"]][row["probe_state"]] += 1

    summary = {
        "schema_version": 1,
        "analysis_id": "openocd-a-residual-diagnostic-v6.18",
        "record_state": "RESEARCH_DIAGNOSTIC_ONLY",
        "input_v617_a_residual_exact_count": EXPECTED_EXACT_COUNT,
        "diagnostic_exact_count": EXPECTED_EXACT_COUNT,
        "diagnostic_exact_set_sha256": hashlib.sha256(
            ("\n".join(r["icpn"] for r in out) + "\n").encode()
        ).hexdigest(),
        "diagnostic_csv_sha256": hashlib.sha256(csv_text.encode()).hexdigest(),
        "family_counts": family_counts,
        "series_counts": series_counts,
        "structural_gap_counts": structural_counts,
        "probe_state_counts": probe_counts,
        "recommended_next_gate_counts": gate_counts,
        "family_structural_gap_counts": {
            family: dict(sorted(counts.items()))
            for family, counts in sorted(family_structural.items())
        },
        "family_probe_state_counts": {
            family: dict(sorted(counts.items()))
            for family, counts in sorted(family_probe.items())
        },
        "frozen_route_inventory_git_blob_sha": v65.EXPECTED_CATALOG_GIT_BLOB_SHA,
        "current_active_openocd_route_exact_count": 3958,
        "scoped_active_denominator": 4550,
        "current_route_coverage_percent": 86.9890,
        "claims": {
            "identifier_inferred": False,
            "prefix_policy_authorized": False,
            "one_char_generalization_authorized": False,
            "production_write_authorized": False,
            "programming_profile_binding_claimed": False,
            "programming_verified_claimed": False,
            "engineering_verified_claimed": False,
            "hil_verified_claimed": False,
        },
    }
    return out, csv_text, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--diagnostic", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()
    _, csv_text, summary = build()
    if args.diagnostic:
        args.diagnostic.write_text(csv_text, encoding="utf-8")
    if args.summary:
        args.summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("OPENOCD_A_RESIDUAL_DIAGNOSTIC_V618_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

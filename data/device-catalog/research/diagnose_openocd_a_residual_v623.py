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
import rebaseline_openocd_current_gap_v622 as v622
import diagnose_openocd_a_residual_v618 as v618

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_EXACT = [
    "STM32C011D6Y6TR",
    "STM32C051D8Y6TR",
    "STM32C091ECY6TR",
    "STM32C092ECY3TR",
    "STM32C092ECY6TR",
    "STM32G491RCY6TR",
    "STM32L496WGY6PST",
    "STM32L496WGY6PTR",
]
EXPECTED_FAMILY_COUNTS = {
    "STM32C0": 5,
    "STM32G4": 1,
    "STM32L4": 2,
}
EXPECTED_SERIES_COUNTS = {
    "STM32C011": 1,
    "STM32C051": 1,
    "STM32C091": 1,
    "STM32C092": 2,
    "STM32G491": 1,
    "STM32L496": 2,
}

FIELDS = (
    "manufacturer","icpn","family","series","base_device","package","option_suffix",
    "candidate_openocd_target_config",
    "same_series_mapped_sibling_count",
    "same_base_mapped_sibling_count",
    "same_base_mapped_identifiers",
    "same_series_route_rows",
    "same_base_route_rows",
    "same_base_route_identifiers",
    "normalized_core",
    "one_char_probe_match_count",
    "one_char_probe_identifiers",
    "structural_class",
    "evidence_gap",
    "recommended_next_gate",
    "generic_package_substitution_authorized",
    "identifier_inferred",
    "production_write_authorized",
)


class DiagnosticError(RuntimeError):
    pass


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise DiagnosticError(msg)


def read_production() -> list[dict[str,str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows: list[dict[str,str]] = []
    for source in manifest["sources"]:
        path = (MANIFEST.parent / source["path"]).resolve()
        with path.open(newline="", encoding="utf-8") as stream:
            rows.extend(csv.DictReader(stream))
    return rows


def literal_prefix(pattern: str) -> str:
    positions = [i for i, c in enumerate(pattern) if c.lower() == "x"]
    pos = min(positions or [len(pattern)])
    return pattern[:pos]


def normalized_core(row: dict[str,str]) -> str:
    suffix = row.get("option_suffix", "")
    icpn = row["icpn"]
    if suffix and icpn.endswith(suffix):
        return icpn[:-len(suffix)]
    return icpn


def dedup_routes(rows: list[dict[str,str]]) -> list[dict[str,str]]:
    seen = {}
    for row in rows:
        key = (
            row.get("part_number",""),
            row.get("identifier_kind",""),
            row.get("target_config",""),
        )
        seen[key] = row
    return list(seen.values())


def one_char_matches(core: str, routes: list[dict[str,str]]) -> list[dict[str,str]]:
    matches: list[dict[str,str]] = []
    for route in routes:
        pattern = route.get("part_number", "")
        if route.get("identifier_kind") != "ordering_pattern" or not pattern.endswith("x"):
            continue
        literal = pattern[:-1]
        if len(literal) > 1 and core.startswith(literal[:-1]):
            matches.append(route)
    return dedup_routes(matches)


def build() -> tuple[list[dict[str,str]], str, dict[str,Any]]:
    gap, _, gap_summary = v622.build()
    req(gap_summary["current_gap_exact_count"] == 575, "v6.22 gap cardinality drift")

    residual = [
        row for row in gap
        if row["tier"] == "A_residual_same_series_existing_route"
    ]
    req(len(residual) == 8, f"A residual count drift: {len(residual)}")
    req(sorted(r["icpn"] for r in residual) == EXPECTED_EXACT,
        "A residual exact set drift")

    production_rows = read_production()
    production_by_icpn = {r["icpn"]: r for r in production_rows}
    mapped = [r for r in production_rows if r["mapping_status"] != "no_mapping"]
    routes = v65.read_routes()

    out: list[dict[str,str]] = []

    for gap_row in residual:
        row = production_by_icpn[gap_row["icpn"]]
        target = gap_row["candidate_openocd_target_config"]
        kinds = v65.allowed_kinds(row["family"])

        same_series_mapped = [
            r for r in mapped
            if r["family"] == row["family"] and r["series"] == row["series"]
        ]
        same_base_mapped = [
            r for r in same_series_mapped if r["base_device"] == row["base_device"]
        ]

        route_pool = [
            r for r in routes
            if r.get("plasma_series") == row["family"]
            and r.get("identifier_kind") in kinds
            and r.get("target_config") == target
            and r.get("subfamily") == row["series"]
        ]
        same_base_routes = [
            r for r in route_pool
            if r.get("part_number","").startswith(row["base_device"])
            or row["base_device"].startswith(literal_prefix(r.get("part_number","")))
        ]

        core = normalized_core(row)
        one_char = one_char_matches(core, route_pool)

        if row["family"] == "STM32G4":
            req(row["icpn"] == "STM32G491RCY6TR", "unexpected G4 residual")
            req(len(same_base_mapped) >= 1, "G4 same-base mapped siblings disappeared")
            req(len(one_char) > 1, "G4 ambiguity no longer reproduced")
            structural = "same_base_route_family_present_package_variant_ambiguous"
            evidence_gap = "package_code_Y_not_uniquely_bound_to_existing_I_or_T_ordering_pattern"
            gate = "obtain_authoritative_package_variant_route_evidence_before_exact_bridge"
        else:
            req(len(same_base_mapped) == 0,
                f"{row['icpn']}: expected no mapped sibling for exact base")
            req(len(same_base_routes) == 0,
                f"{row['icpn']}: expected missing canonical route for exact base")
            structural = "exact_base_variant_missing_from_route_inventory"
            evidence_gap = "commercial_exact_identity_exists_but_no_exact_base_route_inventory_entry"
            gate = "expand_canonical_route_inventory_from_authoritative_ordering_evidence"

        out.append({
            "manufacturer": row["manufacturer"],
            "icpn": row["icpn"],
            "family": row["family"],
            "series": row["series"],
            "base_device": row["base_device"],
            "package": row.get("package",""),
            "option_suffix": row.get("option_suffix",""),
            "candidate_openocd_target_config": target,
            "same_series_mapped_sibling_count": str(len(same_series_mapped)),
            "same_base_mapped_sibling_count": str(len(same_base_mapped)),
            "same_base_mapped_identifiers": "|".join(sorted({
                r.get("existing_identifier","") for r in same_base_mapped
                if r.get("existing_identifier","")
            })),
            "same_series_route_rows": str(len(route_pool)),
            "same_base_route_rows": str(len(same_base_routes)),
            "same_base_route_identifiers": "|".join(sorted({
                r.get("part_number","") for r in same_base_routes
                if r.get("part_number","")
            })),
            "normalized_core": core,
            "one_char_probe_match_count": str(len(one_char)),
            "one_char_probe_identifiers": "|".join(sorted({
                r.get("part_number","") for r in one_char
                if r.get("part_number","")
            })),
            "structural_class": structural,
            "evidence_gap": evidence_gap,
            "recommended_next_gate": gate,
            "generic_package_substitution_authorized": "false",
            "identifier_inferred": "false",
            "production_write_authorized": "false",
        })

    out.sort(key=lambda r: r["icpn"])
    req([r["icpn"] for r in out] == EXPECTED_EXACT, "diagnostic exact-set drift")

    family_counts = dict(sorted(Counter(r["family"] for r in out).items()))
    series_counts = dict(sorted(Counter(r["series"] for r in out).items()))
    structural_counts = dict(sorted(Counter(r["structural_class"] for r in out).items()))
    gate_counts = dict(sorted(Counter(r["recommended_next_gate"] for r in out).items()))

    req(family_counts == EXPECTED_FAMILY_COUNTS, f"family partition drift: {family_counts}")
    req(series_counts == EXPECTED_SERIES_COUNTS, f"series partition drift: {series_counts}")
    req(structural_counts == {
        "exact_base_variant_missing_from_route_inventory": 7,
        "same_base_route_family_present_package_variant_ambiguous": 1,
    }, f"structural partition drift: {structural_counts}")

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(out)
    csv_text = buf.getvalue()

    summary = {
        "schema_version": 1,
        "analysis_id": "openocd-a-residual-deep-diagnostic-v6.23",
        "record_state": "RESEARCH_DIAGNOSTIC_ONLY",
        "input_v622_gap_exact_count": 575,
        "a_residual_exact_count": 8,
        "a_residual_exact_set_sha256": hashlib.sha256(
            ("\n".join(r["icpn"] for r in out) + "\n").encode()
        ).hexdigest(),
        "diagnostic_csv_sha256": hashlib.sha256(csv_text.encode()).hexdigest(),
        "family_counts": family_counts,
        "series_counts": series_counts,
        "structural_counts": structural_counts,
        "recommended_next_gate_counts": gate_counts,
        "exact_icpns": [r["icpn"] for r in out],
        "g4_ambiguity": {
            "icpn": "STM32G491RCY6TR",
            "rule": "one_char_package_position_probe",
            "generic_substitution_authorized": False,
        },
        "route_inventory_expansion_scope": {
            "exact_count": 7,
            "families": {"STM32C0": 5, "STM32L4": 2},
            "production_write_authorized": False,
        },
        "coverage_projection_if_all_8_later_resolved": {
            "current_active_openocd_route_exact_count": 3975,
            "potential_active_openocd_route_exact_count": 3983,
            "scoped_active_denominator": 4550,
            "potential_coverage_percent": round(3983 / 4550 * 100, 4),
            "remaining_gap": 567,
        },
        "claims": {
            "identifier_inferred": False,
            "generic_package_substitution_authorized": False,
            "route_inventory_expansion_authorized": False,
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
    print("OPENOCD_A_RESIDUAL_DEEP_DIAGNOSTIC_V623_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

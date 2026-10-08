#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import re
from collections import Counter
from pathlib import Path
from typing import Any

import diagnose_openocd_a_residual_v623 as v623

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
ST_TREE = HERE / "sources/st-open-pin-mcu-tree-7d1f1514.tsv"
L4_AUTHORITY = HERE / "stm32l4-phase-l4.3-ordering-authority.json"
STRUCTURAL = HERE / "st-multisource-structural-coverage-v0.4.json"

EXPECTED_ST_TREE_GIT_BLOB_SHA = "2812b968d2d7b194f5fbfa6af8757398ab4e0cd6"
EXPECTED_L4_AUTHORITY_GIT_BLOB_SHA = "745dd3d36f41aa533b9e0e89ff8c4c91aee197da"
EXPECTED_STRUCTURAL_GIT_BLOB_SHA = "6beb7b564d59ef0b4e39ae915c7438867d3b4d8c"
EXPECTED_ST_TREE_COMMIT = "7d1f1514ed5583ec5007ad91236b4e1d377295b1"
EXPECTED_ST_TREE_SHA = "d8715ae7453883f62377e87b529f94012323f062"

C0_BINDINGS = {
    "STM32C011D6Y6TR": ("STM32C011D6Yx", "933c9286fcfb890193e1e9253ced6265c94c0b83"),
    "STM32C051D8Y6TR": ("STM32C051D8Yx", "6eb11c42ce3d3fac6693a36b01743cd6ae4bdd09"),
    "STM32C091ECY6TR": ("STM32C091ECYx", "7edcb4f2e5557ae2fc4643f4556139af00459eb9"),
    "STM32C092ECY3TR": ("STM32C092ECYx", "0fb4ebd15c93d52f30a14700680d7616ec5b5a4b"),
    "STM32C092ECY6TR": ("STM32C092ECYx", "0fb4ebd15c93d52f30a14700680d7616ec5b5a4b"),
}
L4_PATTERN = "STM32L496WGYxP"
L4_PATTERN_BLOB = "85c4f770886e119846e18917674a27841f25b8b9"
L4_EXACT = {
    "STM32L496WGY6PTR",
    "STM32L496WGY6PST",
}

FIELDS = (
    "icpn","family","series","base_device","package","option_suffix",
    "authoritative_pattern","authority_source","authority_object_blob_sha",
    "commercial_core","pattern_fullmatch",
    "current_resolver_compatible",
    "review_state","blocking_reason","recommended_next_gate",
    "canonical_inventory_write_authorized","production_write_authorized",
)


class ReviewError(RuntimeError):
    pass


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ReviewError(msg)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()


def pattern_matches(pattern: str, value: str) -> bool:
    expr = "".join("[A-Z0-9]" if c == "x" else re.escape(c) for c in pattern)
    return re.fullmatch(expr, value) is not None


def commercial_core(icpn: str) -> str:
    for suffix in ("TR", "TT"):
        if icpn.endswith(suffix):
            return icpn[:-len(suffix)]
    return icpn


def read_production_index() -> dict[str,dict[str,str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    out: dict[str,dict[str,str]] = {}
    for source in manifest["sources"]:
        path = (MANIFEST.parent / source["path"]).resolve()
        with path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                req(row["icpn"] not in out, f"duplicate Production ICPN: {row['icpn']}")
                out[row["icpn"]] = row
    return out


def read_tree() -> dict[str,str]:
    structural_raw = STRUCTURAL.read_bytes()
    req(git_blob_sha(structural_raw) == EXPECTED_STRUCTURAL_GIT_BLOB_SHA,
        "ST multisource structural record blob drift")
    structural = json.loads(structural_raw)
    mx1 = structural["mx1_subset"]
    req(mx1["repository"] == "STMicroelectronics/STM32_open_pin_data",
        "ST Open Pin repository authority drift")
    req(mx1["commit"] == EXPECTED_ST_TREE_COMMIT, "ST Open Pin commit drift")
    req(mx1["mcu_tree_sha"] == EXPECTED_ST_TREE_SHA, "ST Open Pin MCU tree SHA drift")
    req(mx1["source_path"] == "sources/st-open-pin-mcu-tree-7d1f1514.tsv",
        "ST Open Pin source-lock path drift")
    req(mx1["exact_orderable_mpn_source"] is False,
        "structural pattern source incorrectly promoted to exact commercial authority")
    req(mx1["manufacturer_marketing_lifecycle_authority"] is False,
        "structural pattern source incorrectly promoted to lifecycle authority")

    raw = ST_TREE.read_bytes()
    req(git_blob_sha(raw) == EXPECTED_ST_TREE_GIT_BLOB_SHA, "ST Open Pin source-lock blob drift")
    lines = raw.decode("utf-8").splitlines()
    req(lines[0] == f"# official_git_tree_sha={EXPECTED_ST_TREE_SHA}", "ST tree SHA header drift")
    req(
        lines[1]
        == f"# origin=https://api.github.com/repos/STMicroelectronics/STM32_open_pin_data/git/trees/{EXPECTED_ST_TREE_SHA}",
        "ST tree origin drift",
    )
    reader = csv.DictReader(lines[2:], delimiter="\t")
    return {row["name"]: row["sha"] for row in reader if row.get("name")}


def l4_authority() -> tuple[dict[str,Any],dict[str,Any]]:
    raw = L4_AUTHORITY.read_bytes()
    req(git_blob_sha(raw) == EXPECTED_L4_AUTHORITY_GIT_BLOB_SHA, "L4 ordering authority blob drift")
    payload = json.loads(raw)
    recs = [r for r in payload["records"] if r["series"] == "STM32L496"]
    req(len(recs) == 1, "STM32L496 authority record missing/duplicated")
    rec = recs[0]
    grammar = payload["grammars"][rec["suffix_grammar"]]
    req(rec["document_id"] == "DS11585", "STM32L496 document authority drift")
    req(rec["revision"] == 20 and rec["ordering_pdf_page"] == 274,
        "STM32L496 ordering reference drift")
    req(rec["package_codes"]["Y"] == "WLCSP", "STM32L496 Y package authority drift")
    req(rec["pin_codes"]["W"] == "115", "STM32L496 W pin authority drift")
    req(rec["temperature_codes"]["6"] == "-40..85 C", "STM32L496 temp authority drift")
    req("PTR" in grammar["allowed_tails"] and "PST" in grammar["allowed_tails"],
        "STM32L496 required suffix tails missing")
    return rec, grammar


def build() -> tuple[list[dict[str,str]], str, dict[str,Any]]:
    residual_rows, _, v623_summary = v623.build()
    req(v623_summary["a_residual_exact_count"] == 8, "v6.23 input drift")

    production = read_production_index()
    tree = read_tree()
    l4_rec, l4_grammar = l4_authority()

    scope = sorted(set(C0_BINDINGS) | L4_EXACT)
    req(len(scope) == 7, "v6.24 review scope drift")
    req("STM32G491RCY6TR" not in scope, "G4 ambiguity leaked into v6.24")

    rows: list[dict[str,str]] = []
    for icpn in scope:
        row = production[icpn]
        req(row["mapping_status"] == "no_mapping", f"{icpn}: already mapped")
        core = commercial_core(icpn)

        if icpn in C0_BINDINGS:
            pattern, object_sha = C0_BINDINGS[icpn]
            name = pattern + ".xml"
            req(tree.get(name) == object_sha, f"{icpn}: ST source-lock pattern missing/drifted")
            req(pattern_matches(pattern, core), f"{icpn}: C0 authoritative pattern mismatch")
            review_state = "authoritative_pattern_ready_for_inventory_proposal"
            blocking = "none_for_research_inventory_proposal"
            next_gate = "prepare_bounded_c0_route_inventory_expansion_proposal"
            resolver_compatible = True
            authority_source = (
                f"STMicroelectronics/STM32_open_pin_data@{EXPECTED_ST_TREE_COMMIT}:{name}"
            )
        else:
            req(icpn in L4_EXACT, f"unexpected scope row {icpn}")
            req(tree.get(L4_PATTERN + ".xml") == L4_PATTERN_BLOB,
                f"{icpn}: L4 Open Pin pattern missing/drifted")
            req(row["base_device"] == "STM32L496WG", f"{icpn}: L4 base drift")
            req(row["package"] == "WLCSP", f"{icpn}: L4 package drift")
            req(row["pin_count"] == "115", f"{icpn}: L4 pin drift")
            req(row["temperature_grade"] == "-40..85 C", f"{icpn}: L4 temperature drift")
            req(row["option_suffix"] in l4_grammar["allowed_tails"],
                f"{icpn}: L4 suffix not covered by authority grammar")
            pattern = L4_PATTERN
            object_sha = L4_PATTERN_BLOB
            fullmatch = pattern_matches(pattern, core)
            resolver_compatible = False
            authority_source = (
                f"STMicroelectronics/STM32_open_pin_data@{EXPECTED_ST_TREE_COMMIT}:{L4_PATTERN}.xml"
                f"|DS11585 Rev 20 p274"
            )

            if icpn.endswith("PTR"):
                req(fullmatch, f"{icpn}: PTR core should match WGYxP")
                review_state = "authoritative_pattern_present_resolver_shape_blocked"
                blocking = "L4_current_prefix_resolver_requires_pattern_ending_in_x"
                next_gate = "review_bounded_nonterminal_x_pattern_support_for_exact_l4_scope"
            else:
                req(icpn.endswith("PST"), f"{icpn}: unexpected L4 suffix")
                req(not fullmatch, f"{icpn}: PST unexpectedly fullmatches WGYxP")
                review_state = "authoritative_pattern_present_suffix_transform_blocked"
                blocking = (
                    "PST_is_authoritative_but_requires_bounded_transform_to_P_route_shape_"
                    "before_nonterminal_x_pattern_can_be_consumed"
                )
                next_gate = "review_bounded_l496_suffix_transform_and_nonterminal_x_support"

        fullmatch = pattern_matches(pattern, core)
        rows.append({
            "icpn": icpn,
            "family": row["family"],
            "series": row["series"],
            "base_device": row["base_device"],
            "package": row.get("package",""),
            "option_suffix": row.get("option_suffix",""),
            "authoritative_pattern": pattern,
            "authority_source": authority_source,
            "authority_object_blob_sha": object_sha,
            "commercial_core": core,
            "pattern_fullmatch": str(fullmatch).lower(),
            "current_resolver_compatible": str(resolver_compatible).lower(),
            "review_state": review_state,
            "blocking_reason": blocking,
            "recommended_next_gate": next_gate,
            "canonical_inventory_write_authorized": "false",
            "production_write_authorized": "false",
        })

    rows.sort(key=lambda r: r["icpn"])
    states = dict(sorted(Counter(r["review_state"] for r in rows).items()))
    req(states == {
        "authoritative_pattern_present_resolver_shape_blocked": 1,
        "authoritative_pattern_present_suffix_transform_blocked": 1,
        "authoritative_pattern_ready_for_inventory_proposal": 5,
    }, f"review-state partition drift: {states}")

    patterns = sorted({r["authoritative_pattern"] for r in rows})
    req(patterns == [
        "STM32C011D6Yx",
        "STM32C051D8Yx",
        "STM32C091ECYx",
        "STM32C092ECYx",
        "STM32L496WGYxP",
    ], f"authoritative pattern set drift: {patterns}")

    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    csv_text = buf.getvalue()

    summary = {
        "schema_version": 1,
        "analysis_id": "openocd-route-inventory-authority-review-v6.24",
        "record_state": "RESEARCH_REVIEW_ONLY",
        "input_a_residual_exact_count": 8,
        "review_exact_count": 7,
        "excluded_g4_ambiguity_exact_count": 1,
        "review_exact_set_sha256": hashlib.sha256(
            ("\n".join(r["icpn"] for r in rows) + "\n").encode()
        ).hexdigest(),
        "review_csv_sha256": hashlib.sha256(csv_text.encode()).hexdigest(),
        "authoritative_pattern_count": len(patterns),
        "authoritative_patterns": patterns,
        "review_state_counts": states,
        "c0": {
            "exact_count": 5,
            "authoritative_pattern_count": 4,
            "inventory_proposal_ready_exact_count": 5,
        },
        "l4": {
            "exact_count": 2,
            "authoritative_pattern": L4_PATTERN,
            "resolver_shape_blocked_exact_count": 1,
            "suffix_transform_blocked_exact_count": 1,
            "suffix_grammar": l4_rec["suffix_grammar"],
            "allowed_tails_confirmed": ["PST", "PTR"],
        },
        "authority_locks": {
            "st_open_pin_source_lock_git_blob_sha": EXPECTED_ST_TREE_GIT_BLOB_SHA,
            "st_open_pin_repository_commit": EXPECTED_ST_TREE_COMMIT,
            "st_open_pin_mcu_tree_sha": EXPECTED_ST_TREE_SHA,
            "stm32l4_ordering_authority_git_blob_sha": EXPECTED_L4_AUTHORITY_GIT_BLOB_SHA,
            "st_multisource_structural_record_git_blob_sha": EXPECTED_STRUCTURAL_GIT_BLOB_SHA,
        },
        "coverage_projection_c0_only_if_later_separately_promoted": {
            "current_active_openocd_route_exact_count": 3975,
            "candidate_exact_count": 5,
            "potential_active_openocd_route_exact_count": 3980,
            "scoped_active_denominator": 4550,
            "potential_coverage_percent": 87.4725,
            "remaining_gap": 570,
        },
        "claims": {
            "canonical_inventory_write_authorized": False,
            "generic_pattern_generalization_authorized": False,
            "l4_resolver_policy_change_authorized": False,
            "l4_suffix_transform_authorized": False,
            "production_write_authorized": False,
            "programming_profile_binding_claimed": False,
            "programming_verified_claimed": False,
            "engineering_verified_claimed": False,
            "hil_verified_claimed": False,
        },
    }
    return rows, csv_text, summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--review", type=Path)
    parser.add_argument("--summary", type=Path)
    args = parser.parse_args()

    _, csv_text, summary = build()
    if args.review:
        args.review.write_text(csv_text, encoding="utf-8")
    if args.summary:
        args.summary.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("OPENOCD_ROUTE_INVENTORY_AUTHORITY_REVIEW_V624_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

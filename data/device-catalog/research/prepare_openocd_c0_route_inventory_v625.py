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

import qualify_openocd_tier_a_identifiers_v65 as v65
import review_openocd_route_inventory_authority_v624 as v624

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
CATALOG = HERE / "openocd-parts-canonical.csv"
POLICY = HERE / "openocd-c0-bounded-route-inventory-v6.25.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_CATALOG_GIT_BLOB_SHA = "0ef056e3363e20bb527590c4a4cc1cc0d7afb810"
EXPECTED_CURRENT_MAPPED = 4054
EXPECTED_CURRENT_NO_MAPPING = 575

CANONICAL_FIELDS = (
    "vendor","family","subfamily","plasma_series","part_number","identifier_kind",
    "cpu_architectures","target_config","openocd_distribution","mapping_status",
    "validation_status","catalog_origin",
)
PROPOSAL_ORIGIN = "openocd-c0-bounded-route-inventory-v6.25.csv"


class ProposalError(RuntimeError):
    pass


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ProposalError(msg)


def git_blob_sha(data: bytes) -> str:
    return hashlib.sha1(
        f"blob {len(data)}\0".encode("ascii") + data,
        usedforsecurity=False,
    ).hexdigest()


def read_catalog() -> list[dict[str,str]]:
    raw = CATALOG.read_bytes()
    req(git_blob_sha(raw) == EXPECTED_CATALOG_GIT_BLOB_SHA,
        "canonical route inventory preimage drift")
    with io.StringIO(raw.decode("utf-8")) as stream:
        reader = csv.DictReader(stream)
        req(tuple(reader.fieldnames or ()) == CANONICAL_FIELDS,
            f"canonical schema drift: {reader.fieldnames}")
        rows = list(reader)
    req(rows, "canonical route inventory unexpectedly empty")
    return rows


def read_production() -> dict[str,dict[str,str]]:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    rows: dict[str,dict[str,str]] = {}
    mapped = 0
    no_mapping = 0
    for source in manifest["sources"]:
        path = (MANIFEST.parent / source["path"]).resolve()
        with path.open(newline="", encoding="utf-8") as stream:
            for row in csv.DictReader(stream):
                req(row["icpn"] not in rows, f"duplicate Production ICPN: {row['icpn']}")
                rows[row["icpn"]] = row
                if row["mapping_status"] == "no_mapping":
                    no_mapping += 1
                else:
                    mapped += 1
    req(mapped == EXPECTED_CURRENT_MAPPED, f"Production mapped drift: {mapped}")
    req(no_mapping == EXPECTED_CURRENT_NO_MAPPING, f"Production no_mapping drift: {no_mapping}")
    return rows


def unique_route_metadata(
    rows: list[dict[str,str]], subfamily: str, target_config: str
) -> dict[str,str]:
    siblings = [
        row for row in rows
        if row["vendor"] == "STMicroelectronics"
        and row["plasma_series"] == "STM32C0"
        and row["subfamily"] == subfamily
        and row["target_config"] == target_config
        and row["mapping_status"] == "mapping_candidate"
        and row["validation_status"] == "not_verified"
    ]
    req(siblings, f"{subfamily}: no current canonical sibling route")
    stable_fields = (
        "family","plasma_series","cpu_architectures",
        "target_config","openocd_distribution","mapping_status","validation_status",
    )
    metadata: dict[str,str] = {}
    for field in stable_fields:
        values = {row[field] for row in siblings}
        req(len(values) == 1, f"{subfamily}: {field} sibling metadata not unique: {values}")
        metadata[field] = next(iter(values))
    req(metadata["family"] == "STM32C0 Series", f"{subfamily}: family label drift")
    req(metadata["plasma_series"] == "STM32C0", f"{subfamily}: Plasma series drift")
    req(metadata["target_config"] == "tcl/target/stm32c0x.cfg", f"{subfamily}: target drift")
    req(metadata["openocd_distribution"] == "upstream-openocd",
        f"{subfamily}: OpenOCD distribution drift")
    return metadata


def current_matches(candidate: dict[str,str], rows: list[dict[str,str]]) -> list[dict[str,str]]:
    target = "tcl/target/stm32c0x.cfg"
    core = v65.commercial_core(candidate)
    matches = []
    for route in rows:
        if (
            route.get("vendor") == "STMicroelectronics"
            and route.get("plasma_series") == "STM32C0"
            and route.get("identifier_kind") == "ordering_pattern"
            and route.get("target_config") == target
            and route.get("part_number","").endswith("x")
            and core.startswith(route["part_number"][:-1])
        ):
            matches.append(route)
    unique = {
        (r["part_number"],r["identifier_kind"],r["target_config"]): r
        for r in matches
    }
    return list(unique.values())


def render_csv(rows: list[dict[str,str]]) -> str:
    buf = io.StringIO(newline="")
    writer = csv.DictWriter(buf, fieldnames=CANONICAL_FIELDS, lineterminator="\n")
    writer.writeheader()
    writer.writerows(rows)
    return buf.getvalue()


def build() -> tuple[list[dict[str,str]],str,dict[str,Any]]:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    review_rows, _, review = v624.build()
    req(review["analysis_id"] == "openocd-route-inventory-authority-review-v6.24",
        "v6.24 review identity drift")
    req(review["c0"]["inventory_proposal_ready_exact_count"] == 5,
        "v6.24 C0 ready scope drift")

    catalog = read_catalog()
    production = read_production()

    exact = policy["scope"]["exact_icpns"]
    patterns = policy["scope"]["authoritative_patterns"]
    req(exact == sorted(exact) and len(exact) == 5 and len(set(exact)) == 5,
        "policy exact scope invalid")
    req(patterns == sorted(patterns) and len(patterns) == 4 and len(set(patterns)) == 4,
        "policy pattern scope invalid")
    req(set(policy["bindings"]) == set(exact), "policy binding exact scope drift")
    req(set(policy["patterns"]) == set(patterns), "policy pattern evidence scope drift")

    review_ready = {
        row["icpn"]: row["authoritative_pattern"]
        for row in review_rows
        if row["review_state"] == "authoritative_pattern_ready_for_inventory_proposal"
    }
    req(review_ready == policy["bindings"], "v6.24 -> v6.25 binding drift")

    current_parts = {(row["vendor"],row["part_number"].upper()) for row in catalog}
    proposal_rows: list[dict[str,str]] = []
    target = policy["route"]["target_config"]

    for pattern in patterns:
        evidence = policy["patterns"][pattern]
        subfamily = evidence["subfamily"]
        req(("STMicroelectronics",pattern.upper()) not in current_parts,
            f"{pattern}: already present in canonical inventory")
        metadata = unique_route_metadata(catalog, subfamily, target)
        proposal_rows.append({
            "vendor":"STMicroelectronics",
            "family":metadata["family"],
            "subfamily":subfamily,
            "plasma_series":metadata["plasma_series"],
            "part_number":pattern,
            "identifier_kind":"ordering_pattern",
            "cpu_architectures":metadata["cpu_architectures"],
            "target_config":metadata["target_config"],
            "openocd_distribution":metadata["openocd_distribution"],
            "mapping_status":"mapping_candidate",
            "validation_status":"not_verified",
            "catalog_origin":PROPOSAL_ORIGIN,
        })

    proposal_rows.sort(key=lambda r:r["part_number"])
    expanded = catalog + proposal_rows

    binding_rows = []
    for icpn in exact:
        prod = production[icpn]
        req(prod["family"] == "STM32C0", f"{icpn}: family drift")
        req(prod["mapping_status"] == "no_mapping", f"{icpn}: Production prestate not no_mapping")
        before = current_matches(prod,catalog)
        after = current_matches(prod,expanded)
        req(len(before) == 0, f"{icpn}: pre-proposal route unexpectedly resolves")
        req(len(after) == 1, f"{icpn}: proposal does not resolve uniquely: {len(after)}")
        req(after[0]["part_number"] == policy["bindings"][icpn],
            f"{icpn}: proposal resolved wrong pattern")
        binding_rows.append({
            "icpn":icpn,
            "pattern":after[0]["part_number"],
            "target_config":after[0]["target_config"],
        })

    proposal_csv = render_csv(proposal_rows)
    exact_set_sha = hashlib.sha256(
        ("\n".join(exact)+"\n").encode()
    ).hexdigest()
    pattern_set_sha = hashlib.sha256(
        ("\n".join(patterns)+"\n").encode()
    ).hexdigest()
    binding_sha = hashlib.sha256(
        ("\n".join(
            f"{r['icpn']}|{r['pattern']}|{r['target_config']}"
            for r in binding_rows
        )+"\n").encode()
    ).hexdigest()

    req(policy["governance"]["exact_set_only"] is True, "exact-set governance opened")
    for key in (
        "generic_c0_pattern_expansion_authorized",
        "canonical_inventory_write_authorized",
        "production_mapping_write_authorized",
        "programming_profile_binding_claimed",
        "programming_verified_claimed",
        "engineering_verified_claimed",
        "hil_verified_claimed",
    ):
        req(policy["governance"][key] is False, f"v6.25 overclaim: {key}")

    summary = {
        "schema_version":1,
        "proposal_id":"openocd-c0-bounded-route-inventory-expansion-v6.25",
        "record_state":"RESEARCH_PROPOSAL_ONLY",
        "canonical_inventory_preimage_git_blob_sha":EXPECTED_CATALOG_GIT_BLOB_SHA,
        "canonical_inventory_current_row_count":len(catalog),
        "canonical_inventory_proposed_row_delta":4,
        "canonical_inventory_projected_row_count":len(catalog)+4,
        "proposal_exact_icpn_count":5,
        "proposal_pattern_count":4,
        "proposal_exact_set_sha256":exact_set_sha,
        "proposal_pattern_set_sha256":pattern_set_sha,
        "proposal_binding_sha256":binding_sha,
        "proposal_csv_sha256":hashlib.sha256(proposal_csv.encode()).hexdigest(),
        "patterns":patterns,
        "bindings":policy["bindings"],
        "pre_proposal_unique_resolutions":0,
        "post_proposal_unique_resolutions":5,
        "production_prestate":{
            "mapped":EXPECTED_CURRENT_MAPPED,
            "no_mapping":EXPECTED_CURRENT_NO_MAPPING,
            "active_openocd_route_exact_count":3975,
            "active_openocd_route_denominator":4550,
            "active_openocd_route_coverage_percent":87.3626,
        },
        "inventory_only_projection":{
            "production_mapping_changes":0,
            "active_openocd_route_exact_count":3975,
            "active_openocd_route_coverage_percent":87.3626,
            "remaining_production_gap":575,
        },
        "if_later_separately_promoted_to_production":{
            "candidate_exact_count":5,
            "potential_active_openocd_route_exact_count":3980,
            "active_openocd_route_denominator":4550,
            "potential_coverage_percent":87.4725,
            "potential_remaining_gap":570,
        },
        "claims":{
            "canonical_inventory_write_authorized":False,
            "production_mapping_write_authorized":False,
            "programming_profile_binding_claimed":False,
            "programming_verified_claimed":False,
            "engineering_verified_claimed":False,
            "hil_verified_claimed":False,
        },
    }
    req(Counter(r["subfamily"] for r in proposal_rows) == Counter({
        "STM32C011":1,"STM32C051":1,"STM32C091":1,"STM32C092":1
    }), "proposal subfamily partition drift")
    return proposal_rows, proposal_csv, summary


def main() -> int:
    parser=argparse.ArgumentParser()
    parser.add_argument("--proposal-csv",type=Path)
    parser.add_argument("--summary",type=Path)
    args=parser.parse_args()

    _,proposal_csv,summary=build()
    if args.proposal_csv:
        args.proposal_csv.write_text(proposal_csv,encoding="utf-8")
    if args.summary:
        args.summary.write_text(
            json.dumps(summary,indent=2,sort_keys=True)+"\n",
            encoding="utf-8",
        )
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_C0_ROUTE_INVENTORY_PROPOSAL_V625_PASS")
    return 0


if __name__=="__main__":
    raise SystemExit(main())

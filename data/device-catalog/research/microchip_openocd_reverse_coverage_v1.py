#!/usr/bin/env python3
"""Microchip Phase 1: reverse coverage Target CFG -> DFP Device -> ICPN.

Only the THREE requested columns are resolved: ICPN, manufacturer Base Device,
and pinned OpenOCD Target CFG. Classification is a Research *candidate* only;
no driver, memory, electronics, silicon or software support qualification.

Requires original archived manufacturer DFP index bytes for concrete device
names. Optional MCP rollup supplies original-source-linked commercial ICPNs,
but an already-derived rollup by itself is NOT fresh original-byte replay.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

import microchip_openocd_core_first_v1 as gates
from microchip_dfp_index_inventory_v1 import archived_inventory

# The only non-identical DFP-name/MCP-base alias in this version is an
# independently reviewed manufacturer pair from Microchip Phase 1 pilot.
# Do NOT append suffixes or generalize this exception to other parts.
REVIEWED_ALIAS = {
    "ATSAMD21G18": {
        "dfp_name": "ATSAMD21G18A",
        "required_source_query": "ATSAMD21G18A",
        "reviewed_pilot_icpns": ("ATSAMD21G18A-MU", "ATSAMD21G18A-MF"),
        "authority": "microchip-adr0002-phase1-ic-information-pilot-v1.json",
    }
}
ICPN_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9+._/\-]{1,95}\Z")
SHA256_RE = re.compile(r"[a-f0-9]{64}\Z")


def require(test, reason):
    if not test:
        raise ValueError(reason)


def source_lock():
    lock = json.loads(gates.SOURCE_LOCK.read_text(encoding="utf-8"))
    release = json.loads(gates.OPENOCD_RELEASE.read_text(encoding="utf-8"))
    gates.validate_registry(lock, release)
    obs = json.loads(gates.OBSERVATION.read_text(encoding="utf-8"))
    gates.validate_frozen_observation(lock, obs)
    return lock, obs


def cfg_index(lock, inventory):
    """Traverse locked OpenOCD cfg groups FIRST, never scan 24k SKUs with regex."""
    require(inventory["source_bytes_sha256"] == gates.PINNED_DFP_SOURCE
            and inventory["manufacturer"] == "Microchip"
            and inventory["observed_distinct_device_support_names"] == 3717
            and inventory["population_boundary_validated"] is False
            and inventory["production_write_authorized"] is False,
            "pinned original Microchip DFP snapshot unavailable")
    # Existing upstream source-locked Research grouping already validates
    # DFP restricted packs and names; independent checksum is checked by
    # archived_inventory, not by trusting any derived count.
    observed = gates.triage_names(lock, inventory)
    gates.validate_frozen_observation(lock,
                                     json.loads(gates.OBSERVATION.read_text(
                                         encoding="utf-8")), observed)
    all_names = {}
    for pack in inventory["device_packs"]:
        restricted = (pack["discovery_lane"] in gates.ARCHIVAL_LANES
                      or pack["pack_name"] in gates.ACCESSORY_PACKS)
        for name in pack["device_names"]:
            norm = name.upper()
            require(norm not in all_names, "duplicate case-insensitive DFP device")
            all_names[norm] = {"name": name, "restricted": restricted,
                               "pack_name": pack["pack_name"],
                               "pack_version": pack["pack_version"]}
    groups = []
    indexed = {}
    for rank, key in (("P0", "p0_research_leads"), ("P1", "p1_bounded_leads")):
        for g in lock[key]:
            pattern = re.compile(g["matcher"], re.IGNORECASE)
            matched = []
            for norm, entry in all_names.items():
                if entry["restricted"] or not pattern.match(entry["name"]):
                    continue
                require(norm not in indexed,
                        "ambiguous cfg for one original DFP device name")
                indexed[norm] = {"dfp_name": entry["name"],
                                 "openocd_target_cfg": g["target"],
                                 "cfg_source_git_blob": g["target_sha"],
                                 "lead_id": g["id"], "priority": rank,
                                 "manufacturer_pack": entry["pack_name"],
                                 "pack_version": entry["pack_version"],
                                 "match_state": "DFP_DEVICE_NAME_CFG_RESEARCH_CANDIDATE"}
                matched.append(entry["name"])
            groups.append({
                "priority": rank, "research_lead": g["id"],
                "openocd_target_cfg": g["target"],
                "openocd_target_git_blob_sha1": g["target_sha"],
                "dfp_device_name_count": len(matched),
                "dfp_device_names": sorted(matched),
                "exact_icpn_software_supported": False,
                "cfg_applicability_reviewed": False,
            })
    require(len(groups) == 11
            and sum(g["dfp_device_name_count"] for g in groups if g["priority"]=="P0")==364
            and sum(g["dfp_device_name_count"] for g in groups if g["priority"]=="P1")==12
            and len(indexed)==376, "reverse DFP / source-lock population drift")
    return groups, indexed


def join_icpns(lock, indexed, rollup):
    """Optional manufacturer-MCP basePartNumber -> source-locked DFP config.

    Derived rollup is NOT trusted as self-contained original bytes. The result
    marks original_bytes_replayed_in_this_command=False, without exception.
    """
    require(rollup.get("type") == "microchip-source-pinned-disjoint-dfp-evidence-merger"
            and rollup.get("manufacturer") == "Microchip"
            and rollup.get("original_dfp_index_sha256") == gates.PINNED_DFP_SOURCE
            and rollup.get("manufacturer_population_complete") is False
            and rollup.get("global_active_denominator") is None
            and rollup.get("production_write_authorized") is False
            and rollup.get("commercial_sku_denominator_established") is False,
            "rollup does not belong to pinned research evidence")
    candidates = rollup.get("ordering_candidates")
    require(isinstance(candidates, list)
            and len(candidates)==rollup["unique_exact_prefix_research_candidates"]
            and len(candidates)<=24051, "untrusted research ICPN candidate count")
    results, states, cfg_count = [], Counter(), Counter()
    ids = set()
    for item in sorted(candidates, key=lambda x:x["icpn"].upper()):
        icpn = item.get("icpn")
        require(isinstance(icpn, str) and ICPN_RE.fullmatch(icpn),
                "invalid original manufacturer full order code")
        key = icpn.upper()
        require(key not in ids, "duplicate commercial ICPN in candidate rollup")
        ids.add(key)
        sources = item.get("sources")
        require(isinstance(sources, list) and sources,
                "unlinked commercial ordering candidate")
        bases, queries, hashes = set(), set(), set()
        for source in sources:
            base = source.get("basePartNumber")
            query = source.get("query")
            digest = source.get("response_sha256")
            require(isinstance(query, str) and query
                    and isinstance(digest, str)
                    and SHA256_RE.fullmatch(digest),
                    "commercial observation missing original-response source link")
            queries.add(query.upper())
            hashes.add(digest)
            if isinstance(base, str) and base.strip():
                require(ICPN_RE.fullmatch(base.strip()),
                        "untrusted manufacturer base identity")
                bases.add(base.strip().upper())
        base = next(iter(bases)) if len(bases)==1 else None
        if len(bases)>1:
            state, cfg, dfp = "CONFLICTING_MANUFACTURER_BASE", None, None
        elif base is None:
            state, cfg, dfp = "UNKNOWN_MANUFACTURER_BASE", None, None
        else:
            match = indexed.get(base)
            alias = REVIEWED_ALIAS.get(base)
            if not match and alias and alias["required_source_query"] in queries:
                match = indexed.get(alias["dfp_name"])
                if match is not None and match["priority"] == "P0":
                    state = "REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE"
                else:
                    match = None
            elif match:
                state = "EXACT_DFP_NAME_CFG_CANDIDATE"
            if match:
                cfg, dfp = match["openocd_target_cfg"], match["dfp_name"]
                if match["priority"] == "P1":
                    state = "P1_TARGET_ONLY_CFG_CANDIDATE"
                cfg_count[cfg] += 1
            else:
                cfg, dfp = None, None
                state = "NO_DFP_NAME_CFG_CROSSWALK"
        states[state] += 1
        results.append({
            "icpn": icpn,
            "base_device": base,
            "openocd_target_cfg": cfg,
            "dfp_device_name": dfp,
            "mapping_state": state,
            "original_mcp_response_sha256_refs": sorted(hashes),
            "manufacturer_base_identity_evidence": (
                "MCP_ROLLUP_ORIGINAL_RESPONSE_LINKS_NOT_REPLAYED_IN_THIS_COMMAND"),
            "cfg_applicability_reviewed": False,
            "software_supported_claimed": False,
            "production_write_authorized": False,
        })
    require(sum(states.values())==len(candidates), "ICPN state coverage gap")
    return results, dict(sorted(states.items())), dict(sorted(cfg_count.items()))


def build(dfp_root=None, mcp_rollup=None):
    lock, observation = source_lock()
    if mcp_rollup is not None:
        require(dfp_root is not None,
                "ICPN join requires actual pinned original DFP source; no heuristic-only join")
    report = {
        "schema_version": 1,
        "policy": "ADR-0002 Phase 1 - IC Information",
        "manufacturer": "Microchip",
        "scope": "reverse_openocd_cfg_to_dfp_base_to_source_linked_research_icpn",
        "openocd_release": "0.12.0",
        "openocd_source_commit": lock["provider"]["commit"],
        "original_dfp_index_sha256_required": gates.PINNED_DFP_SOURCE,
        "original_dfp_observation_available_in_this_run": dfp_root is not None,
        "cfg_research_group_count": 11,
        "p0_target_cfg_count": 9,
        "p1_target_only_cfg_count": 2,
        "frozen_dfp_name_count": observation["observed_original_dfp_support_names"],
        "frozen_dfp_p0_names": observation["dfp_research_priority_counts"]["P0"],
        "frozen_dfp_p1_names": observation["dfp_research_priority_counts"]["P1"],
        "research_icpn_candidate_count_from_other_stage_not_joined": 24051,
        "exact_icpn_cfg_candidate_count": None,
        "icpn_denominator_joined_in_this_run": None,
        "cfg_group_rows": [],
        "icpn_rows": [],
        "icpn_mapping_state_counts": {},
        "icpn_by_cfg_candidate_counts": {},
        "all_icpn_original_bytes_replayed_in_this_command": False,
        "base_device_from_suffix_inference": False,
        "cfg_software_supported_claimed": False,
        "production_write_authorized": False,
        "phase2_programming_authorized": False,
        "phase3_compatibility_authorized": False,
    }
    if dfp_root is not None:
        inventory = archived_inventory(dfp_root)
        groups, indexed = cfg_index(lock, inventory)
        report["cfg_group_rows"] = groups
        report["actual_original_dfp_p0_names_replayed"]=sum(
            g["dfp_device_name_count"] for g in groups if g["priority"]=="P0")
        report["actual_original_dfp_p1_names_replayed"]=sum(
            g["dfp_device_name_count"] for g in groups if g["priority"]=="P1")
        if mcp_rollup is not None:
            rows, states, counts = join_icpns(lock, indexed, mcp_rollup)
            report["icpn_rows"] = rows
            report["icpn_mapping_state_counts"] = states
            report["icpn_by_cfg_candidate_counts"] = counts
            report["icpn_denominator_joined_in_this_run"] = len(rows)
            report["exact_icpn_cfg_candidate_count"] = sum(
                v for k,v in states.items()
                if k in ("EXACT_DFP_NAME_CFG_CANDIDATE",
                         "REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE",
                         "P1_TARGET_ONLY_CFG_CANDIDATE"))
    return report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--dfp-evidence-root", type=Path)
    p.add_argument("--mcp-rollup", type=Path,
                   help="previously generated source-linked 23k Research rollup; not independent raw replay")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()
    output = args.output.resolve()
    require("production" not in {part.casefold() for part in output.parts},
            "Research report must not write Production")
    raw = json.loads(args.mcp_rollup.read_text(encoding="utf-8")) if args.mcp_rollup else None
    report = build(args.dfp_evidence_root, raw)
    if args.verify:
        require(json.loads(output.read_text(encoding="utf-8")) == report,
                "reverse CFG mapping report differs from original-source replay")
        print("Microchip reverse CFG candidate crosswalk PASS")
    else:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
        print(json.dumps({k:v for k,v in report.items()
                          if k not in ("cfg_group_rows","icpn_rows")},
                         sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

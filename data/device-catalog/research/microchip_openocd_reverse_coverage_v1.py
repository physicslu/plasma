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
import tempfile
import zipfile

import microchip_phase1_portable_custody_v1 as portable
import microchip_phase1_p0_second_cohort_v1 as second
import microchip_mcp_full_rollup_v1 as full_mcp
import microchip_mcp_batch_plan_v1 as batch_plan
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




def portable_original_icpn_rollup(path):
    """Reconstruct bounded ICPN observations from source-replayed original MCP bytes.

    Does NOT enumerate 24,051 candidates or the full family SKU population.
    """
    original = portable.verify(path)
    require(original["offline_bundle_verification"] == "PASS"
            and original["original_mcp_dual_pagination_replayed"] is True
            and original["source_to_phase1_chart_report_replayed"] is True
            and original["source_file_count"] >= 10,
            "original two-query Microchip bundle has not independently replayed")
    with tempfile.TemporaryDirectory() as td:
        with zipfile.ZipFile(path) as archive:
            # portable.verify rejects zip traversal, symlinks, duplicates, size.
            archive.extractall(td)
        root = Path(td)
        source_report = second.build(
            root / "chart",
            {"sam-e5-d5": root / "mcp-e5",
             "pic32mx": root / "mcp-pic32"},
            {"sam-e5-d5": "REPLAYED", "pic32mx": "REPLAYED"})
    rows = []
    for entry in source_report["exact_mcp_source_observed_not_admitted"]:
        rows.append({
            "icpn": entry["source_part_number"],
            "sources": [{
                "query": entry["query"],
                "basePartNumber": entry["source_base_part_number"],
                "response_sha256": entry["source_sha256"],
                "evidence_file": entry["source_file"],
            }],
        })
    require(rows and
            source_report["mcp_state_counts"]["CURRENT_REPLAYED_MATCH"] == 2,
            "empty/incomplete original-source Microchip cohort")
    return {
        "type": "microchip-source-pinned-disjoint-dfp-evidence-merger",
        "manufacturer": "Microchip",
        "original_dfp_index_sha256": gates.PINNED_DFP_SOURCE,
        "manufacturer_population_complete": False,
        "global_active_denominator": None,
        "production_write_authorized": False,
        "commercial_sku_denominator_established": False,
        "unique_exact_prefix_research_candidates": len(rows),
        "ordering_candidates": rows,
    }


def replay_all_original_batch_sources(dfp_root, source_specs):
    """Recompute all Research candidates from captured original MCP responses.

    This accepts only the 13 operator-identified, disjoint source roots:
    the original bounded 16-batch dataset plus 12 independently named
    shards. The SHA-verified original DFP index derives their exact plan.
    A failing original-source replay, changed research population or
    conflicting lifecycle must abort the whole run rather than map partial
    batches or silently report a smaller numerator.
    """
    require(dfp_root is not None, "original manufacturer DFP index required")
    require(isinstance(source_specs, list) and len(source_specs) == 13,
            "full original sweep requires 16-batch archive plus 12 shard archives")
    labels = [label for label, _ in source_specs]
    require(set(labels) == {"original-16-batches"} |
            {f"shard-{n}" for n in range(12)} and len(labels) == 13,
            "missing, duplicated or unapproved Microchip original research shard")
    inventory = archived_inventory(dfp_root)
    reg = json.loads(batch_plan.REGISTRY.read_text(encoding="utf-8"))
    digest = reg["gate_1b_surface_audit"]["dfp_index_observation"]["raw_index_sha256"]
    require(digest == gates.PINNED_DFP_SOURCE
            and inventory["source_bytes_sha256"] == digest,
            "unpinned original manufacturer DFP source")
    expected = batch_plan.plan_inventory(inventory, digest, batch_size=10)
    result = full_mcp.build(expected, inventory, digest, source_specs)
    audit = json.loads((gates.HERE / 
        "microchip-dfp-full-first-pass-audit-20261013.json").read_text(encoding="utf-8"))
    # The historical 23,427 is an *observation-event* count, not the number
    # of per-identity links retained by the deduplicated 23,276-row rollup.
    # Likewise 321 original batch dirs include eight source-attestation
    # quarantines. Preserve these denominators independently.
    reports = result["batch_reports"]
    not_archived = set(result["not_archived_batch_ids"])
    observed_ids = {r["batch_id"] for r in reports} - not_archived
    quarantined = {r["batch_id"] for r in reports
                   if r.get("state") == "entire_batch_quarantined"}
    attested = len(observed_ids - quarantined)
    retained_links = sum(len(v["sources"])
                         for v in result["ordering_candidates"])
    actual_replay = {
        "original_dfp_index_sha256": digest,
        "planned_dfp_queries": expected["supported_text_search_seeds"],
        "planned_batches": expected["batch_count"],
        "batch_archives_with_valid_capture_attestation": attested,
        "batches_quarantined_due_to_missing_attestation_after_worker_timeouts": len(quarantined),
        "complete_positive_exact_prefix_queries": result["replayed_positive_exact_prefix_queries"],
        "fully_replayed_zero_exact_prefix_queries": result["replayed_zero_exact_prefix_queries"],
        "unique_exact_prefix_candidates_without_conflicts": result["unique_exact_prefix_research_candidates"],
        "raw_lifecycle_conflicts": result["conflicting_lifecycle_identity_count"],
        "replayed_queries": result["replayed_queries"],
        "original_batch_directories_observed": result["observed_batch_archives"],
        "deduplicated_rollup_retained_source_links": retained_links,
    }
    expected_replay = {k: audit[k] for k in actual_replay
                       if k not in ("replayed_queries",
                                    "original_batch_directories_observed",
                                    "deduplicated_rollup_retained_source_links")}
    expected_replay.update({
        "replayed_queries":
            audit["complete_positive_exact_prefix_queries"] +
            audit["fully_replayed_zero_exact_prefix_queries"],
        "original_batch_directories_observed": expected["batch_count"],
        # Every row must carry at least one original MCP response source.
        # This historical rollup retains one link per distinct candidate;
        # do not confuse it with audit's pre-dedup 23,427 event count.
        "deduplicated_rollup_retained_source_links":
            result["unique_exact_prefix_research_candidates"],
    })
    drift = {key: {"observed": value, "frozen_expected": expected_replay[key]}
             for key, value in actual_replay.items()
             if value != expected_replay[key]}
    require(not drift and result["production_write_authorized"] is False,
            "original manufacturer full sweep differs from audited 2026-10-13 evidence: " +
            json.dumps(drift, sort_keys=True))
    return result, {
        "original_source_count": len(source_specs),
        "original_batch_directories_observed": result["observed_batch_archives"],
        "original_batch_archives_replayed": attested,
        "quarantined_batch_archives_not_admitted": len(quarantined),
        "source_linked_observations_in_prior_audit": audit["verified_original_source_response_links"],
        "deduplicated_rollup_source_links_retained": retained_links,
        "exact_prefix_queries_replayed": result["replayed_queries"],
        "positive_exact_prefix_queries": result["replayed_positive_exact_prefix_queries"],
        "zero_exact_prefix_queries": result["replayed_zero_exact_prefix_queries"],
        "distinct_original_mcp_response_links": audit["verified_original_source_response_links"],
        "historical_research_icpn_candidates_replayed": result["unique_exact_prefix_research_candidates"],
        "manufacturer_whole_population_known": False,
        "source_replay_status": "REPLAYED_AGAINST_PINNED_ORIGINAL_BYTES",
    }


def build(dfp_root=None, mcp_rollup=None, portable_bundle=None,
          original_batch_sources=None):
    lock, observation = source_lock()
    require(sum(x is not None for x in (mcp_rollup, portable_bundle,
            original_batch_sources)) <= 1,
            "only one original or derived Microchip ICPN input is allowed")
    source_replay = None
    if original_batch_sources is not None:
        mcp_rollup, source_replay = replay_all_original_batch_sources(
            dfp_root, original_batch_sources)
    if portable_bundle is not None:
        mcp_rollup = portable_original_icpn_rollup(portable_bundle)
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
        "all_icpn_original_bytes_replayed_in_this_command": (
            portable_bundle is not None or original_batch_sources is not None),
        "full_batch_original_source_replay": source_replay,
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
            if portable_bundle is not None or original_batch_sources is not None:
                for row in rows:
                    row["manufacturer_base_identity_evidence"] = (
                        "ORIGINAL_MICROCHIP_MCP_RESPONSE_REPLAYED_IN_THIS_COMMAND")
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
    p.add_argument("--original-batch-source", action="append",
                   metavar="LABEL=PATH",
                   help="all thirteen original MCP roots: original-16-batches plus shard-0 through shard-11; forces complete original source replay")
    p.add_argument("--portable-bundle", type=Path,
                   help="verified original two-query Microchip source ZIP from PR #878")
    p.add_argument("--mcp-rollup", type=Path,
                   help="previously generated source-linked 23k Research rollup; not independent raw replay")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()
    output = args.output.resolve()
    require("production" not in {part.casefold() for part in output.parts},
            "Research report must not write Production")
    raw = json.loads(args.mcp_rollup.read_text(encoding="utf-8")) if args.mcp_rollup else None
    sources = None
    if args.original_batch_source is not None:
        sources = []
        for value in args.original_batch_source:
            require("=" in value, "original batch source must be LABEL=PATH")
            label, root = value.split("=", 1)
            sources.append((label, Path(root)))
    report = build(args.dfp_evidence_root, raw, args.portable_bundle, sources)
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

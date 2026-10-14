#!/usr/bin/env python3
"""ADR-0002 Phase 1: two NEW chart-selected P0 MCP queries, source-bound.

No automatic suffix fabrication, ICPN admission, software-support claims, or
manufacturer-wide count. This extension leaves the PR #871 reviewed SAMD21
original evidence and its distinct query alias unmodified.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import microchip_phase1_p0_chart_batch_v1 as chart
import microchip_phase1_p0_mcp_crosswalk_v1 as existing
import microchip_mcp_probe_v1 as mcp

LEADS = ("sam-e5-d5", "pic32mx")
HISTORIC_BASE = "ATSAMD21G18"
VALID_QUERY = re.compile(r"[A-Za-z][A-Za-z0-9]{4,39}\Z")
STATES = ("CURRENT_REPLAYED_MATCH", "CURRENT_REPLAYED_NO_EXACT_MATCH",
          "SOURCE_NOT_AVAILABLE", "PREVIOUS_REPLAYED_NOT_RECHECKED", "NOT_QUERIED")


def require(ok, message):
    if not ok:
        raise ValueError(message)


def cohort(chart_report):
    """The query must be a literal P0 chart Base Device, NOT an inferred suffix."""
    require(chart_report.get("policy") == "ADR-0002 Phase 1 - IC Information"
            and chart_report.get("manufacturer") == "Microchip"
            and chart_report.get("all_records_research_only") is True
            and chart_report.get("production_write_authorized") is False
            and chart_report.get("chart_scope") ==
                "microchipdirect_chart_branchID_21_mid_3_only"
            and chart_report.get("pinned_openocd_commit") ==
                chart.EXPECTED_OPENOCD_COMMIT
            and chart_report["chart_records"]["P0_source_leads"] == 341
            and len(chart_report["p0_family_records"]) == 341,
            "untrusted original P0 manufacturer chart cohort")
    group = {}
    names = set()
    for record in chart_report["p0_family_records"]:
        name = record["base_device_chart_observation"]
        require(name not in names, "duplicate P0 Base Device in source chart")
        names.add(name)
        if record["source_lead_id"] in LEADS and VALID_QUERY.fullmatch(name):
            group.setdefault(record["source_lead_id"], []).append(record)
    require(all(group.get(lead) for lead in LEADS),
            "required chart P0 lead has no safe original-name candidate")
    selected = []
    for lead in LEADS:
        row = sorted(group[lead], key=lambda x: x["base_device_chart_observation"])[0]
        name = row["base_device_chart_observation"]
        require(name != HISTORIC_BASE, "reviewed SAMD21 pilot cannot be recaptured")
        selected.append({
            "lead_id": lead,
            "manufacturer_chart_base_device": name,
            "mcp_search_term": name,
            "selection_rule": "first_lexical_chart_p0_base_device_no_suffix_inference",
            "source_chart_tr_ordinal": row["source_tr_ordinal"],
            "source_chart_sha256": chart_report["source_original_sha256"],
            "source_authority": "manufacturer_parametric_base_name_only",
            "query_intent": "EXPLORATORY_READ_ONLY_NOT_ORDER_CODE_REVIEW",
            "exact_icpn_admission_authorized": False,
        })
    require(len({x["mcp_search_term"] for x in selected}) == 2,
            "ambiguous two-lead selection")
    require(HISTORIC_BASE in names, "previously reviewed chart canary vanished")
    return selected


def report(chart_report, sources):
    """sources is mapping lead -> (REPLAYED, original-root) or (SOURCE_NOT_AVAILABLE, None).
    A missing lead means NOT_RUN; no negative count may be inferred.
    """
    plan = cohort(chart_report)
    require(set(sources) <= set(LEADS), "unapproved new Microchip MCP query")
    rows, quarantine, query_results = [], [], []
    for selected in plan:
        lead = selected["lead_id"]
        name = selected["mcp_search_term"]
        outcome, location = sources.get(lead, ("NOT_RUN", None))
        require(outcome in ("NOT_RUN", "SOURCE_NOT_AVAILABLE", "REPLAYED"),
                "invalid source-acquisition state")
        require((location is not None) is (outcome == "REPLAYED"),
                "source data/outcome mismatch")
        if outcome == "REPLAYED":
            verified, source_rows = existing.original_primary_mcp_records(location, name)
            scoped = []
            for value in source_rows.values():
                icpn = value["source_part_number"]
                if not mcp.exact_ordering_prefix(icpn, name):
                    continue
                if icpn.upper() == name.upper():
                    reason = "BARE_CHART_NAME_NOT_PROVEN_ORDERABLE"
                elif value["source_base_part_number"] != selected["manufacturer_chart_base_device"]:
                    reason = "MANUFACTURER_BASE_DEVICE_MISMATCH"
                else:
                    reason = None
                entry = {
                    **value,
                    "chart_base_device": selected["manufacturer_chart_base_device"],
                    "openocd_research_lead": lead,
                    "original_mcp_pagination_replayed": True,
                    "order_code_identity_reviewed": False,
                    "phase1_exact_fields_verified": 0,
                    "internal_admission_state": "NOT_ADMITTED",
                    "software_supported_claimed": False,
                }
                if reason:
                    entry["quarantine_reason"] = reason
                    quarantine.append(entry)
                else:
                    entry["candidate_status"] = "SOURCE_OBSERVED_NOT_REVIEWED"
                    scoped.append(entry)
            rows.extend(scoped)
            count = len(scoped)
            status = "CURRENT_REPLAYED_MATCH" if count else "CURRENT_REPLAYED_NO_EXACT_MATCH"
            query_results.append({
                **selected, "status": status,
                "source_total_search_rows": verified["reported_total"],
                "source_exact_prefix_rows_including_bare": verified[
                    "exact_prefix_ordering_count"],
                "source_fuzzy_rows_excluded": verified["fuzzy_foreign_ordering_count"],
                "source_exact_ordering_candidates_not_admitted": count,
                "source_original_manifest_sha256": hashlib.sha256(
                    (Path(location) / "manifest.json").read_bytes()).hexdigest(),
                "source_response_file_count": len(json.loads(
                    (Path(location) / "manifest.json").read_text(encoding="utf-8"))["responses"]),
                "source_independent_pagination_replayed": True,
                "manufacturer_sku_population_complete": False,
            })
        else:
            query_results.append({
                **selected, "status": (
                    "SOURCE_NOT_AVAILABLE" if outcome == "SOURCE_NOT_AVAILABLE"
                    else "NOT_QUERIED"),
                "source_total_search_rows": None,
                "source_exact_prefix_rows_including_bare": None,
                "source_fuzzy_rows_excluded": None,
                "source_exact_ordering_candidates_not_admitted": None,
                "source_original_manifest_sha256": None,
                "source_independent_pagination_replayed": False,
                "manufacturer_sku_population_complete": False,
            })
    # Disallow overcounting one full commercial order code from two different queries.
    ids = [r["source_part_number"].upper() for r in rows]
    require(len(set(ids)) == len(ids), "cross-query duplicate commercial ICPN")
    selected_status = {r["manufacturer_chart_base_device"]: r["status"]
                       for r in query_results}
    states = Counter()
    matrix = []
    for origin in sorted(chart_report["p0_family_records"],
                         key=lambda r: r["base_device_chart_observation"]):
        name = origin["base_device_chart_observation"]
        state = (selected_status[name] if name in selected_status else
                 "PREVIOUS_REPLAYED_NOT_RECHECKED" if name == HISTORIC_BASE else
                 "NOT_QUERIED")
        states[state] += 1
        matrix.append({
            "chart_base_device": name,
            "openocd_research_lead": origin["source_lead_id"],
            "mcp_source_state": state,
            "observed_commercial_candidates_this_run": (
                next(q["source_exact_ordering_candidates_not_admitted"]
                     for q in query_results
                     if q["manufacturer_chart_base_device"] == name)
                if name in selected_status else None),
            "manufacturer_sku_count_complete": False,
            "exact_icpn_admitted": 0,
            "software_supported_claimed": False,
        })
    require(len(matrix) == 341 and sum(states.values()) == 341
            and states["PREVIOUS_REPLAYED_NOT_RECHECKED"] == 1,
            "P0 chart denominator or historical state miscount")
    return {
        "schema_version": 1,
        "policy": "ADR-0002 Phase 1 - IC Information",
        "manufacturer": "Microchip",
        "p0_chart_source_sha256": chart_report["source_original_sha256"],
        "p0_chart_source_url": chart_report["source_url"],
        "pinned_openocd_commit": chart_report["pinned_openocd_commit"],
        "scope": "two_new_chart_selected_p0_queries_exploratory",
        "observed_chart_p0_base_device_denominator": 341,
        "query_plan": plan,
        "query_results": query_results,
        "exact_mcp_source_observed_not_admitted": sorted(rows, key=lambda r:r["source_part_number"]),
        "quarantined_identity_rows": sorted(quarantine,key=lambda r:r["source_part_number"]),
        "mcp_state_counts": {key: states[key] for key in STATES},
        "p0_chart_coverage_matrix": matrix,
        "manufacturer_complete_ordering_codes": False,
        "known_unqueried_family_exact_icpn_count": None,
        "current_exact_icpn_admissions": 0,
        "phase1_exact_icpn_specifications_verified": 0,
        "openocd_software_supported_claimed": False,
        "production_write_authorized": False,
        "catalog_publication_authorized": False,
        "phase2_programming_authorized": False,
        "phase3_compatibility_authorized": False,
        "original_bytes_durable_archive_verified": False,
    }


def build(chart_root, originals, statuses):
    data = chart.build_report(chart_root)
    src = {}
    for lead in LEADS:
        state = statuses.get(lead, "NOT_RUN")
        location = originals.get(lead)
        src[lead] = (state, location)
    return report(data, src)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--chart-original-root", required=True, type=Path)
    action = p.add_mutually_exclusive_group(required=True)
    action.add_argument("--plan", type=Path)
    action.add_argument("--report", type=Path)
    action.add_argument("--verify", type=Path)
    p.add_argument("--e5-original-root", type=Path)
    p.add_argument("--e5-outcome", choices=("NOT_RUN", "REPLAYED", "SOURCE_NOT_AVAILABLE"),
                   default="NOT_RUN")
    p.add_argument("--pic32-original-root", type=Path)
    p.add_argument("--pic32-outcome", choices=("NOT_RUN", "REPLAYED", "SOURCE_NOT_AVAILABLE"),
                   default="NOT_RUN")
    args = p.parse_args()
    target = args.plan or args.report or args.verify
    require("production" not in {p.casefold() for p in target.resolve().parts},
            "Production output prohibited")
    original = chart.build_report(args.chart_original_root)
    if args.plan is not None:
        data = {"schema_version": 1, "scope": "research_two_unapproved_p0_queries",
                "p0_chart_original_sha256": original["source_original_sha256"],
                "selected": cohort(original),
                "query_count_upper_bound": 2,
                "production_write_authorized": False}
    else:
        data = report(original, {
            "sam-e5-d5": (args.e5_outcome, args.e5_original_root),
            "pic32mx": (args.pic32_outcome, args.pic32_original_root)})
    if args.verify is not None:
        require(data == json.loads(args.verify.read_text(encoding="utf-8")),
                "two-query original manufacturer source replay mismatch")
        print("Microchip Phase 1 two-query source replay PASS")
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n",
                      encoding="utf-8")
    print(json.dumps({
        "source_states": data.get("mcp_state_counts"),
        "query_results": [
            {"lead": r["lead_id"], "query": r["mcp_search_term"],
             "status": r["status"],
             "candidates": r["source_exact_ordering_candidates_not_admitted"]}
            for r in data.get("query_results", [])],
        "query_plan": data.get("selected"),
    }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

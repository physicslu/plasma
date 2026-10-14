#!/usr/bin/env python3
"""ADR-0002 Phase 1: chart P0 Base Device <-> source-replayed MCP exact ICPN.

One owner-reviewed SAMD21 manufacturer query is used as a bounded pilot.
An unqueried P0 Base Device has UNKNOWN exact-ICPN coverage, never zero.
This file never admits a catalog row or qualifies OpenOCD programming.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

import microchip_phase1_p0_chart_batch_v1 as chart
import microchip_mcp_paged_probe_v2 as paged
import microchip_mcp_probe_v1 as mcp
import microchip_phase1_mcp_identity_v1 as pilot_identity
from microchip_phase1_information_v1 import DEFAULT_PATH, check

# This is not an algorithm to infer commercial naming suffixes.
# Every further query/base pair must be reviewed and committed independently.
REVIEWED_QUERY = {
    "chart_base_device": "ATSAMD21G18",
    "manufacturer_mcp_search_term": "ATSAMD21G18A",
    "basis": "previously-reviewed-exact-ICPN-manufacturer-basePartNumber-PR862",
}
EXPECTED_P0_COUNT = 341
MAX_EXACT_ROWS = 600


def require(ok, message):
    if not ok:
        raise ValueError(message)


def original_primary_mcp_records(root, query):
    """Re-read raw primary pagination ONLY AFTER full 20/60 replay succeeds."""
    validated = paged.replay(root, query)
    require(validated["independent_page_size_identity_and_lifecycle_match"]
            and validated["reported_total"] <= MAX_EXACT_ROWS,
            "unreconciled/oversized manufacturer MCP responses")
    manifest = json.loads((Path(root) / "manifest.json").read_text(encoding="utf-8"))
    require(manifest["query"] == query and manifest["endpoint"] == mcp.ENDPOINT,
            "MCP source manifest/query mismatch")
    primary = {}
    for e in manifest["responses"]:
        request = e["request"]
        if request["method"] != "tools/call":
            continue
        args = request["params"]["arguments"]
        if args["limit"] != paged.PRIMARY_LIMIT:
            continue
        raw = (Path(root) / e["file"]).read_bytes()
        require(hashlib.sha256(raw).hexdigest() == e["sha256"],
                "MCP raw SHA mismatch during crosswalk")
        payload = mcp.product_data(mcp.decode(raw, request["id"]))
        _, rows = paged.validate_page(payload, args["offset"], args["limit"],
                                      query=query)
        for offset, row in enumerate(rows):
            name = row["partNumber"]
            norm = name.upper()
            require(norm not in primary, "ambiguous case-insensitive source ICPN")
            primary[norm] = {
                "source_part_number": name,
                "source_base_part_number": row.get("basePartNumber"),
                "raw_lifecycle_not_admission": row["lifecycleStatus"],
                "source_mcp_product_url": row.get("productUrl"),
                "source_file": e["file"],
                "source_sha256": e["sha256"],
                "source_locator": f"products[{offset}]",
                "query": query,
                "request_limit": args["limit"],
                "request_offset": args["offset"],
            }
    require(len(primary) == validated["reported_total"],
            "primary MCP raw source records incomplete")
    require({v["source_part_number"] for v in primary.values()} ==
            set(validated["ordering_parts"]), "MCP crosswalk/replay identity drift")
    return validated, primary


def crosswalk_from_evidence(chart_report, mcp_root=None,
                            capture_outcome="NOT_RUN",
                            reviewed_pilot_path=DEFAULT_PATH):
    """Project one exact-source-limited pilot onto full chart P0 denominator."""
    require(chart_report.get("policy") == "ADR-0002 Phase 1 - IC Information"
            and chart_report.get("manufacturer") == "Microchip"
            and chart_report.get("chart_scope") ==
            "microchipdirect_chart_branchID_21_mid_3_only"
            and chart_report.get("all_records_research_only") is True
            and chart_report.get("production_write_authorized") is False,
            "untrusted Phase 1 source chart report")
    counts = chart_report["chart_records"]
    p0 = chart_report["p0_family_records"]
    require(counts["P0_source_leads"] == EXPECTED_P0_COUNT
            and len(p0) == EXPECTED_P0_COUNT
            and counts["observed_chart_base_devices"] ==
            sum(counts[x] for x in ("P0_source_leads", "P1_deferred",
                                   "P2_archive_only"))
            and chart_report["pinned_openocd_commit"] ==
            chart.EXPECTED_OPENOCD_COMMIT,
            "P0 source denominator or pinned OpenOCD version changed")
    base_map = {r["base_device_chart_observation"]: r for r in p0}
    require(len(base_map) == len(p0)
            and REVIEWED_QUERY["chart_base_device"] in base_map,
            "missing/duplicate official P0 base name")
    require(capture_outcome in ("NOT_RUN", "SOURCE_NOT_AVAILABLE", "REPLAYED"),
            "unknown acquisition state")
    require((mcp_root is not None) is (capture_outcome == "REPLAYED"),
            "source bytes and acquisition outcome disagree")

    pilot = json.loads(Path(reviewed_pilot_path).read_text(encoding="utf-8"))
    check(pilot)
    approved_pilot = {
        r["icpn"].upper(): r["fields"]["base_device"]["value"].upper()
        for r in pilot["records"]
        if r["fields"]["base_device"]["status"] == "VERIFIED"
    }
    require(approved_pilot == {
        "ATSAMD21G18A-MF": "ATSAMD21G18",
        "ATSAMD21G18A-MU": "ATSAMD21G18",
    }, "original two-ICPN reviewed cohort changed")

    identity_rows = []
    quarantined = []
    source_meta = None
    pilot_matches = []
    if capture_outcome == "REPLAYED":
        query = REVIEWED_QUERY["manufacturer_mcp_search_term"]
        summary, source = original_primary_mcp_records(mcp_root, query)
        verified_pilot = pilot_identity.replay_identity(mcp_root, pilot)
        require(verified_pilot["matched_exact_manufacturer_icpns"] == 2
                and verified_pilot["original_mcp_pagination_replayed"] is True,
                "previously approved exact pilot identity not reproducible")
        pilot_matches = sorted(row["icpn"] for row in
                               verified_pilot["exact_manufacturer_identity_evidence"])
        source_meta = {
            "query": query,
            "reviewed_chart_base_device": REVIEWED_QUERY["chart_base_device"],
            "reviewed_query_basis": REVIEWED_QUERY["basis"],
            "original_response_count": len(json.loads(
                (Path(mcp_root) / "manifest.json").read_text(encoding="utf-8"))["responses"]),
            "reported_search_result_count": summary["reported_total"],
            "exact_prefix_count_including_bare_query": summary[
                "exact_prefix_ordering_count"],
            "fuzzy_result_count_excluded": summary["fuzzy_foreign_ordering_count"],
            "independent_pagination_replayed": True,
        }
        for row in source.values():
            number = row["source_part_number"]
            if not mcp.exact_ordering_prefix(number, query):
                # Only source queries matching the reviewed alias are eligible.
                continue
            if number.upper() == query:
                reason = "BARE_QUERY_NOT_PROVEN_COMMERCIAL_ORDER_CODE"
            elif row["source_base_part_number"] != REVIEWED_QUERY["chart_base_device"]:
                reason = "MANUFACTURER_BASE_DEVICE_MISMATCH"
            else:
                reason = None
            entry = {
                **row,
                "official_mcp_original_identity_observed": True,
                "internal_admission_state": "NOT_ADMITTED",
                "software_supported_claimed": False,
                "phase1_exact_specifications_complete": False,
            }
            if reason:
                entry["quarantine_reason"] = reason
                quarantined.append(entry)
            else:
                entry["review_state"] = (
                    "PREVIOUSLY_REVIEWED_EXACT_PILOT_REPLAYED" if
                    number.upper() in approved_pilot else
                    "ORIGINAL_MANUFACTURER_EXACT_ORDERING_OBSERVED_NOT_REVIEWED")
                identity_rows.append(entry)
        require({x["source_part_number"].upper() for x in identity_rows}
                >= set(approved_pilot),
                "approved commercial ICPNs missing from linked chart group")

    states = Counter()
    matrix = []
    for base, row in sorted(base_map.items()):
        selected = base == REVIEWED_QUERY["chart_base_device"]
        state = ("MCP_ORIGINAL_IDENTITY_REPLAYED" if selected and
                 capture_outcome == "REPLAYED" else
                 "MCP_SOURCE_NOT_AVAILABLE" if selected and
                 capture_outcome == "SOURCE_NOT_AVAILABLE" else
                 "NOT_QUERIED")
        states[state] += 1
        fields = row["fields_family_scope_only"]
        require(all(v["status"] in ("PARTIAL", "UNKNOWN")
                    for v in fields.values()),
                "unreviewed chart family field promoted")
        matrix.append({
            "chart_base_device": base,
            "openocd_research_lead": row["source_lead_id"],
            "chart_source_tr_ordinal": row["source_tr_ordinal"],
            "chart_source_sha256": chart_report["source_original_sha256"],
            "manufacturer_mcp_identity_state": state,
            "manufacturer_exact_icpns_observed": (
                len(identity_rows) if state == "MCP_ORIGINAL_IDENTITY_REPLAYED"
                else None),
            "manufacturer_exact_icpn_count_complete": False,
            "chart_flash_state": fields["flash"]["status"],
            "chart_ram_state": fields["ram"]["status"],
            "chart_vdd_state": fields["vdd"]["status"],
            "chart_io_supply_state": fields["io_supply"]["status"],
            "chart_vdda_state": fields["vdda"]["status"],
            "exact_icpn_admitted": 0,
            "openocd_software_supported_claimed": False,
        })
    require(sum(states.values()) == EXPECTED_P0_COUNT,
            "P0 MCP identity coverage denominator miscomputed")
    return {
        "schema_version": 1,
        "policy": "ADR-0002 Phase 1 - IC Information",
        "manufacturer": "Microchip",
        "source_chart_original_sha256": chart_report["source_original_sha256"],
        "source_chart_url": chart_report["source_url"],
        "pinned_openocd_commit": chart_report["pinned_openocd_commit"],
        "population_boundary": "341_observed_chart_P0_base_device_rows_only",
        "total_p0_chart_base_devices": EXPECTED_P0_COUNT,
        "mcp_source_state_by_chart_base_device": {
            x: states[x] for x in (
                "MCP_ORIGINAL_IDENTITY_REPLAYED",
                "MCP_SOURCE_NOT_AVAILABLE", "NOT_QUERIED")},
        "reviewed_pilot_query": REVIEWED_QUERY,
        "reviewed_pilot_capture_state": capture_outcome,
        "reviewed_pilot_original_source_summary": source_meta,
        "replayed_exact_pilot_icpns": pilot_matches,
        "commercial_icpn_original_rows_observed_not_admitted": identity_rows,
        "quarantined_mcp_exact_prefix_rows": quarantined,
        "p0_chart_to_mcp_matrix": matrix,
        "mcp_global_or_family_sku_census_complete": False,
        "unqueried_source_exact_icpn_count": None,
        "total_exact_icpn_admissions": 0,
        "software_supported_icpn_count": None,
        "phase1_field_verified_from_chart": 0,
        "production_write_authorized": False,
        "catalog_publication_authorized": False,
        "phase2_programming_authorized": False,
        "phase3_compatibility_authorized": False,
    }


def build(chart_root, mcp_root=None, capture_outcome="NOT_RUN"):
    chart_report = chart.build_report(chart_root)
    return crosswalk_from_evidence(chart_report, mcp_root, capture_outcome)


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--chart-original-root", type=Path, required=True)
    ap.add_argument("--mcp-original-root", type=Path)
    ap.add_argument("--mcp-outcome", default="NOT_RUN",
                    choices=("NOT_RUN", "SOURCE_NOT_AVAILABLE", "REPLAYED"))
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--verify", type=Path)
    args = ap.parse_args()
    dest = args.output or args.verify
    require("production" not in {p.casefold() for p in dest.resolve().parts},
            "Production output prohibited")
    report = build(args.chart_original_root, args.mcp_original_root,
                   args.mcp_outcome)
    if args.verify:
        require(json.loads(args.verify.read_text(encoding="utf-8")) == report,
                "MCP/chart original-source crosswalk replay mismatch")
        print("Microchip Phase 1 P0 MCP/chart crosswalk replay PASS")
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                        encoding="utf-8")
        print(json.dumps({
            "base_device_count": report["total_p0_chart_base_devices"],
            "source_states": report["mcp_source_state_by_chart_base_device"],
            "source_observed_exact_candidate_count": len(
                report["commercial_icpn_original_rows_observed_not_admitted"]),
            "quarantined_source_identity_count": len(
                report["quarantined_mcp_exact_prefix_rows"]),
            "previously_reviewed_pilot_icpns": report["replayed_exact_pilot_icpns"],
        }, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

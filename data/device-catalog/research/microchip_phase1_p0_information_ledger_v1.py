#!/usr/bin/env python3
"""ADR-0002 Phase 1: Microchip P0 Research information completeness ledger.

Input is the SHA256-pinned, original-source-replayed CFG-FIRST *Research*
crosswalk from microchip_openocd_reverse_coverage_v1.py. This command is a
derivation, NOT a new read of original MCP response bytes. It makes no new
official spec observations, production admission or OpenOCD qualification.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

from microchip_phase1_information_v1 import FIELDS, STATUSES
import microchip_phase1_p0_chart_batch_v1 as chart_batch

EXPECTED_ALL = 23276
EXPECTED_P0 = 2437
EXPECTED_P0_EXACT = 2414
EXPECTED_P0_ALIAS = 23
EXPECTED_P1 = 126
P0_CFGS = {
    "tcl/target/at91samdXX.cfg": 667,
    "tcl/target/atsame5x.cfg": 354,
    "tcl/target/atsamv.cfg": 175,
    "tcl/target/pic32mx.cfg": 1241,
}
P0_STATES = {
    "EXACT_DFP_NAME_CFG_CANDIDATE": EXPECTED_P0_EXACT,
    "REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE": EXPECTED_P0_ALIAS,
}
UNKNOWN_FIELDS = tuple(f for f in FIELDS if f not in
                       ("manufacturer", "icpn", "base_device"))
SHA = set("0123456789abcdef")


def require(test, reason):
    if not test:
        raise ValueError(reason)


def valid_sha(value):
    return isinstance(value, str) and len(value) == 64 and set(value) <= SHA


def status_field(status, value=None, *, locator=None, hashes=None, unit=None,
                 scope=None, note=None):
    require(status in STATUSES, "invalid Phase 1 field state")
    if status == "UNKNOWN":
        require(value is None and locator is None and hashes is None and
                unit is None and scope is None, "unknown field carries invented data")
    else:
        require(value is not None and isinstance(locator, str) and locator and
                isinstance(hashes, list) and hashes and
                all(valid_sha(x) for x in hashes) and scope,
                "verified field has no original manufacturer source linkage")
    return {
        "status": status, "value": value, "unit": unit,
        "evidence_scope": scope,
        "source_locator": locator, "original_response_sha256_refs": hashes,
        "notes": note,
    }


def verify_upstream(source):
    require(isinstance(source, dict) and source.get("schema_version") == 1
            and source.get("manufacturer") == "Microchip"
            and source.get("scope") ==
                "reverse_openocd_cfg_to_dfp_base_to_source_linked_research_icpn"
            and source.get("openocd_release") == "0.12.0"
            and source.get("all_icpn_original_bytes_replayed_in_this_command") is True
            and source.get("original_dfp_observation_available_in_this_run") is True
            and source.get("original_dfp_index_sha256_required") ==
                "9a00c71e262882687219fce322169435a36d45ac06d0a26bf146c4d6a5db83b0"
            and source.get("p0_target_cfg_count") == 9
            and source.get("p1_target_only_cfg_count") == 2
            and source.get("actual_original_dfp_p0_names_replayed") == 364
            and source.get("actual_original_dfp_p1_names_replayed") == 12
            and source.get("icpn_denominator_joined_in_this_run") == EXPECTED_ALL
            and source.get("production_write_authorized") is False
            and source.get("cfg_software_supported_claimed") is False
            and source.get("phase2_programming_authorized") is False
            and source.get("phase3_compatibility_authorized") is False,
            "not an original-source-replayed, source-locked Microchip Research cohort")
    history = source.get("full_batch_original_source_replay")
    require(isinstance(history, dict) and
            history.get("historical_research_icpn_candidates_replayed") == EXPECTED_ALL
            and history.get("original_batch_directories_observed") == 321
            and history.get("original_batch_archives_replayed") == 313
            and history.get("quarantined_batch_archives_not_admitted") == 8
            and history.get("exact_prefix_queries_replayed") == 2821
            and history.get("source_replay_status") ==
                "REPLAYED_AGAINST_PINNED_ORIGINAL_BYTES",
            "original manufacturer batch replay and quarantine gate incomplete")
    rows = source.get("icpn_rows")
    require(isinstance(rows, list) and len(rows) == EXPECTED_ALL,
            "Microchip original exact-ICPN denominator drift")
    states = Counter(r.get("mapping_state") for r in rows)
    require(states == Counter({
        "EXACT_DFP_NAME_CFG_CANDIDATE": EXPECTED_P0_EXACT,
        "REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE": EXPECTED_P0_ALIAS,
        "P1_TARGET_ONLY_CFG_CANDIDATE": EXPECTED_P1,
        "NO_DFP_NAME_CFG_CROSSWALK": EXPECTED_ALL - EXPECTED_P0 - EXPECTED_P1,
    }) and source.get("icpn_mapping_state_counts") == dict(states),
            "CFG-first candidate states inconsistent with source replay")
    return rows


def make_entry(row):
    require(row.get("mapping_state") in P0_STATES
            and row.get("openocd_target_cfg") in P0_CFGS
            and row.get("manufacturer_base_identity_evidence") ==
                "ORIGINAL_MICROCHIP_MCP_RESPONSE_REPLAYED_IN_THIS_COMMAND"
            and row.get("production_write_authorized") is False
            and row.get("software_supported_claimed") is False
            and row.get("cfg_applicability_reviewed") is False,
            "P0 information row not source-locked or qualification overclaimed")
    icpn, base, cfg, dfp = (
        row.get("icpn"), row.get("base_device"),
        row.get("openocd_target_cfg"), row.get("dfp_device_name"))
    require(all(isinstance(v, str) and v.strip() for v in (icpn, base, cfg, dfp)),
            "P0 missing manufacturer order-code/base/CFG linkage")
    hashes = row.get("original_mcp_response_sha256_refs")
    require(isinstance(hashes, list) and hashes and
            len(set(hashes)) == len(hashes) and
            all(valid_sha(x) for x in hashes),
            "P0 evidence missing original MCP response byte digest")
    require((row["mapping_state"] == "EXACT_DFP_NAME_CFG_CANDIDATE"
             and base.upper() == dfp.upper()) or
            row["mapping_state"] == "REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE",
            "CFG candidate DFP/base relationship contradicts evidence")
    # Original manufacturer search_products response proves only Part Number
    # and basePartNumber here. A CFG candidate proves NO IC information field.
    loc = f"Microchip MCP search_products partNumber={icpn}"
    manufacturer_loc = loc + " (original manufacturer MCP response)"
    fields = {
        "manufacturer": status_field(
            "VERIFIED", "Microchip", locator=manufacturer_loc,
            hashes=hashes, scope="exact_mcp_response_row"),
        "icpn": status_field(
            "VERIFIED", icpn, locator=loc + " / partNumber",
            hashes=hashes, scope="exact_mcp_response_row"),
        "base_device": status_field(
            "VERIFIED", base, locator=loc + " / basePartNumber",
            hashes=hashes, scope="exact_mcp_response_row"),
    }
    for name in UNKNOWN_FIELDS:
        fields[name] = status_field("UNKNOWN", note=(
            "Official exact-variant Phase 1 information evidence not yet "
            "replayed and bound to this ICPN; no inference from name/CFG/family."
        ))
    require(set(fields) == set(FIELDS), "Phase 1 13-field contract changed")
    return {
        "manufacturer": "Microchip", "icpn": icpn, "base_device": base,
        "openocd_target_cfg_research_only": cfg,
        "dfp_name": dfp, "cfg_candidate_state": row["mapping_state"],
        "source_original_mcp_response_sha256_refs": hashes,
        "manufacturer_research_identity": "SOURCE_LINKED_EXACT_PART_OBSERVED",
        "internal_identity_admission": "NOT_ADMITTED",
        "phase1_information_state": "INCOMPLETE_FIELDS_REQUIRE_OFFICIAL_EVIDENCE",
        "fields": fields,
        "software_supported_claimed": False,
        "production_write_authorized": False,
    }


def enrich_from_replayed_chart(records, chart_report):
    """Add only family-scope PARTIAL fields to exact-base-joined ICPNs.

    The official chart does not prove exact-variant package, pins or temperature.
    Do not infer missing supplies, core architecture or exact commercial SKU.
    """
    require(chart_report.get("schema_version") == 1
            and chart_report.get("policy") == "ADR-0002 Phase 1 - IC Information"
            and chart_report.get("manufacturer") == "Microchip"
            and chart_report.get("chart_scope") ==
                "microchipdirect_chart_branchID_21_mid_3_only"
            and chart_report.get("chart_records", {}).get("P0_source_leads") == 341
            and chart_report.get("exact_icpn_fields_verified_from_chart") == 0
            and chart_report.get("production_write_authorized") is False
            and chart_report.get("catalog_publication_authorized") is False,
            "source-replayed original Microchip chart P0 proof absent")
    sha = chart_report.get("source_original_sha256")
    require(valid_sha(sha), "chart original bytes digest absent")
    chart_rows = chart_report.get("p0_family_records")
    require(isinstance(chart_rows, list) and len(chart_rows) == 341,
            "missing/ambiguous source-locked Base Device chart rows")
    by_base = {}
    for r in chart_rows:
        base = r.get("base_device_chart_observation")
        require(isinstance(base, str) and base and base.upper() not in by_base
                and r.get("priority") == "P0"
                and r.get("exact_icpn_verified_from_chart") is False,
                "ambiguous or incorrectly qualified chart base")
        by_base[base.upper()] = r
    allowed = {"package", "pin_count", "flash", "ram", "vdd",
               "temperature", "core_model"}
    matched = 0
    filled = Counter()
    not_in_chart = []
    for rec in records:
        found = by_base.get(rec["base_device"].upper())
        if found is None:
            not_in_chart.append({
                "icpn": rec["icpn"],
                "manufacturer_base_device": rec["base_device"],
                "openocd_target_cfg_research_only":
                    rec["openocd_target_cfg_research_only"],
                "gap": "NO_EXACT_BASE_NAME_IN_OBSERVED_32BIT_CHART",
            })
            continue
        matched += 1
        source_fields = found.get("fields_family_scope_only", {})
        require(isinstance(source_fields, dict), "invalid base chart fields")
        for field in allowed:
            observed = source_fields.get(field, {})
            require(observed.get("status") in ("PARTIAL", "UNKNOWN")
                    and observed.get("source_original_sha256") == sha
                    and observed.get("evidence_scope") ==
                        "official_base_device_chart_not_exact_icpn",
                    "chart family-field provenance invalid")
            if observed["status"] != "PARTIAL":
                continue
            value = observed.get("value")
            raw = observed.get("original_raw_value")
            head = observed.get("original_header")
            unit = observed.get("original_unit")
            tr = observed.get("source_tr_ordinal")
            col = observed.get("source_column_number_1based")
            require(value is not None and isinstance(raw, str) and raw
                    and isinstance(head, str) and head
                    and isinstance(tr, int) and tr > 0
                    and isinstance(col, int) and col > 0,
                    "chart PARTIAL value missing raw-unit/row/column evidence")
            rec["fields"][field] = status_field(
                "PARTIAL", value,
                locator=(f"{chart_report['source_url']} / TR {tr} / "
                         f"column {col}: {head} = {raw}"),
                hashes=[sha], scope="official_base_device_chart_not_exact_icpn",
                unit=unit, note=(
                    "Manufacturer parametric Base Device row only. "
                    "Exact ICPN applicability has not been proven. "
                    "Original raw units are preserved."))
            filled[field] += 1
    return {
        "source_chart_scope": chart_report["chart_scope"],
        "source_chart_original_sha256": sha,
        "p0_manufacturer_chart_base_count": 341,
        "p0_icpns_exact_manufacturer_base_joined_to_chart": matched,
        "p0_icpns_not_in_observed_chart": len(not_in_chart),
        "chart_unmatched_by_research_cfg": dict(sorted(Counter(
            r["openocd_target_cfg_research_only"] for r in not_in_chart).items())),
        "chart_unmatched_exact_icpns": sorted(not_in_chart,
                                            key=lambda row: row["icpn"].upper()),
        "partial_field_observation_counts": dict(sorted(filled.items())),
        "exact_variant_fields_promoted_by_chart": 0,
        "chart_family_scope_only": True,
    }


def build(source, *, upstream_bytes_sha256, chart_report=None):
    require(valid_sha(upstream_bytes_sha256), "upstream source report SHA256 required")
    rows = verify_upstream(source)
    selected = [make_entry(row) for row in rows
                if row["mapping_state"] in P0_STATES]
    require(len(selected) == EXPECTED_P0, "P0 source cohort size changed")
    selected.sort(key=lambda r:r["icpn"].upper())
    ids = [r["icpn"].upper() for r in selected]
    require(len(ids) == len(set(ids)), "duplicate P0 exact manufacturer ICPN")
    chart_source = (enrich_from_replayed_chart(selected, chart_report)
                    if chart_report is not None else None)
    cfg = Counter(r["openocd_target_cfg_research_only"] for r in selected)
    status = Counter(r["cfg_candidate_state"] for r in selected)
    require(dict(cfg) == P0_CFGS and dict(status) == P0_STATES,
            "P0 CFG/Base Device distribution changed")
    counts = {field: Counter(r["fields"][field]["status"] for r in selected)
              for field in FIELDS}
    by_cfg = defaultdict(lambda: {field: Counter() for field in FIELDS})
    for r in selected:
        group = by_cfg[r["openocd_target_cfg_research_only"]]
        for field in FIELDS:
            group[field][r["fields"][field]["status"]] += 1
    def all_statuses(c):
        return {s: c[s] for s in STATUSES}
    return {
        "schema_version": 1,
        "policy": "ADR-0002 Phase 1 - IC Information",
        "scope": "microchip_p0_research_ic_information_evidence_gap_ledger",
        "manufacturer": "Microchip",
        "original_cfg_reverse_source_report_sha256": upstream_bytes_sha256,
        "chart_original_bytes_replayed_by_upstream_chart_builder": chart_report is not None,
        "p0_family_chart_evidence": chart_source,
        "input_original_evidence_replay_claim": "VERIFIED_BY_UPSTREAM_REVERSE_REPLAYER",
        "original_manufacturer_bytes_replayed_by_this_projection": False,
        "phase1_field_contract": list(FIELDS),
        "p0_icpn_count": EXPECTED_P0,
        "source_replayed_research_icpn_denominator": EXPECTED_ALL,
        "p0_cfg_research_candidate_counts": dict(sorted(cfg.items())),
        "p0_mapping_states": dict(sorted(status.items())),
        "per_field_coverage": {k: all_statuses(counts[k]) for k in FIELDS},
        "per_cfg_per_field_coverage": {
            k: {f: all_statuses(group[f]) for f in FIELDS}
            for k, group in sorted(by_cfg.items())
        },
        "field_unknown_denominator": len(UNKNOWN_FIELDS),
        "record_level_phase1_information_complete": 0,
        "record_level_internal_identity_admitted": 0,
        "records": selected,
        "record_level_software_supported": 0,
        "phase1_p0_information_complete_claimed": False,
        "openocd_software_supported_claimed": False,
        "production_write_authorized": False,
        "catalog_publication_authorized": False,
        "phase2_programming_authorized": False,
        "phase3_compatibility_authorized": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--upstream-cfg-report", type=Path, required=True)
    p.add_argument("--chart-original-root", type=Path,
                   help="original official chart HTML and manifest; independently replayed, family-scope PARTIAL only")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--verify", action="store_true")
    args = p.parse_args()
    output = args.output.resolve()
    require("production" not in {x.lower() for x in output.parts},
            "Research P0 Phase 1 output cannot write Production")
    raw = args.upstream_cfg_report.read_bytes()
    require(len(raw) <= 64 * 1024 * 1024, "unexpectedly large upstream report")
    chart = chart_batch.build_report(args.chart_original_root) if args.chart_original_root else None
    result = build(json.loads(raw), upstream_bytes_sha256=hashlib.sha256(raw).hexdigest(),
                   chart_report=chart)
    if args.verify:
        require(json.loads(output.read_text(encoding="utf-8")) == result,
                "P0 Phase 1 coverage differs from upstream original-source report")
        print("Microchip P0 Phase 1 Research gap ledger PASS")
    else:
        require(not output.exists(), "P0 evidence output exists; do not overwrite")
        output.parent.mkdir(parents=True, exist_ok=True)
        with output.open("x", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False, sort_keys=True)
            f.write("\n")
        print(json.dumps({k:v for k,v in result.items() if k not in (
            "records","per_cfg_per_field_coverage")}, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

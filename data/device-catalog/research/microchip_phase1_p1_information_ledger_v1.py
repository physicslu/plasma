#!/usr/bin/env python3
"""Microchip Phase 1 P1 IC Information — exact ICPN source-evidence ledger.

P1 is Research priority (Target-only OpenOCD CFG), NOT Phase 1 vs Phase 2.
The upstream 23,276-row Research source has to be independently replayed by
microchip_openocd_reverse_coverage_v1.py in the same CI job. This program is
a read-only *derivation* and optionally independently replays the vendor HTML
chart for *family-scope PARTIAL* information. NEVER set software SUPPORTED,
internal admission, publication, or Programming/physical qualification.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path

import microchip_phase1_p0_information_ledger_v1 as p0
import microchip_phase1_p0_chart_batch_v1 as chart
from microchip_phase1_chart_semantics_v1 import HEADERS
from microchip_phase1_information_v1 import FIELDS, STATUSES
from microchip_openocd_reverse_coverage_v1 import gates

P1_EXPECTED = 126
P1_CFG = "tcl/target/atsaml1x.cfg"
P1_STATE = "P1_TARGET_ONLY_CFG_CANDIDATE"
FAMILY_FIELDS = ("package", "pin_count", "flash", "ram",
                 "vdd", "temperature", "core_model")
UNRESOLVED = tuple(x for x in FIELDS if x not in
                   ("manufacturer", "icpn", "base_device"))
MAX_UPSTREAM = 64 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def identity(row):
    require(row.get("mapping_state") == P1_STATE
            and row.get("openocd_target_cfg") == P1_CFG
            and row.get("manufacturer_base_identity_evidence") ==
                "ORIGINAL_MICROCHIP_MCP_RESPONSE_REPLAYED_IN_THIS_COMMAND"
            and row.get("software_supported_claimed") is False
            and row.get("cfg_applicability_reviewed") is False
            and row.get("production_write_authorized") is False,
            "P1 source-bound Target-only record or eligibility invalid")
    icpn = row.get("icpn")
    base = row.get("base_device")
    dfp = row.get("dfp_device_name")
    require(all(isinstance(v, str) and v.strip() for v in (icpn,base,dfp))
            and base.upper() == dfp.upper(),
            "original manufacturer Base Device is not exact DFP name")
    hashes = row.get("original_mcp_response_sha256_refs")
    require(isinstance(hashes, list) and len(hashes)>0
            and len(set(hashes)) == len(hashes)
            and all(p0.valid_sha(v) for v in hashes),
            "P1 missing untampered original MCP source SHA references")
    loc = f"Microchip MCP search_products partNumber={icpn}"
    fields = {
        "manufacturer": p0.status_field(
            "VERIFIED", "Microchip", hashes=hashes,
            locator=loc+" / manufacturer", scope="exact_mcp_response_row"),
        "icpn": p0.status_field(
            "VERIFIED", icpn, hashes=hashes,
            locator=loc+" / partNumber", scope="exact_mcp_response_row"),
        "base_device": p0.status_field(
            "VERIFIED", base, hashes=hashes,
            locator=loc+" / basePartNumber", scope="exact_mcp_response_row"),
    }
    for key in UNRESOLVED:
        fields[key] = p0.status_field(
            "UNKNOWN", note="Exact ICPN official specification not established; "
            "Target-only OpenOCD cfg is not manufacturer information.")
    require(set(fields)==set(FIELDS), "Phase 1 field contract changed")
    return {
        "manufacturer": "Microchip", "icpn": icpn, "base_device": base,
        "dfp_name": dfp, "cfg_candidate_state": P1_STATE,
        "openocd_target_cfg_research_only": P1_CFG,
        "target_cfg_is_flash_software_support": False,
        "source_original_mcp_response_sha256_refs": hashes,
        "manufacturer_research_identity": "SOURCE_LINKED_EXACT_PART_OBSERVED",
        "internal_identity_admission": "NOT_ADMITTED",
        "phase1_information_state": "INCOMPLETE_FIELDS_REQUIRE_OFFICIAL_EVIDENCE",
        "fields": fields,
        "software_supported_claimed": False, "production_write_authorized": False,
    }


def chart_p1_fields(original_root):
    """Independently replay original Microchip HTML and return observed P1 rows.

    The preexisting chart builder deliberately defers P1 fields. A source-row
    alignment is proved by exact original TR ordinal, named header and base.
    """
    checked = chart.build_report(original_root)
    require(checked.get("policy") == "ADR-0002 Phase 1 - IC Information"
            and checked.get("manufacturer") == "Microchip"
            and checked.get("pinned_openocd_commit") ==
                "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
            and checked.get("chart_scope") ==
                "microchipdirect_chart_branchID_21_mid_3_only"
            and checked.get("chart_records",{}).get("P0_source_leads")==341
            and checked.get("exact_icpn_fields_verified_from_chart")==0
            and checked.get("production_write_authorized") is False
            and checked.get("catalog_publication_authorized") is False,
            "incorrect or unsourced original 32-bit Microchip chart")
    sha = checked.get("source_original_sha256")
    require(p0.valid_sha(sha), "invalid source-original Chart SHA256")
    rows = chart.ChartRows()
    source=(Path(original_root)/"original-chart.html").read_bytes()
    require(hashlib.sha256(source).hexdigest()==sha,
            "original chart HTML byte integrity drift")
    rows.feed(source.decode("utf-8",errors="replace"))
    rows.close()
    headers = [h for h in rows.header_samples
               if len(h["headers_observed"])==len(set(h["headers_observed"]))
               and set(HEADERS.values()) <= set(h["headers_observed"])]
    require(len(headers)==1 and
            headers[0]["headers_observed"]==checked["source_original_header_names"],
            "original chart semantic header diverges")
    names = headers[0]["headers_observed"]
    columns = {key:names.index(label) for key,label in HEADERS.items()}
    existing = {tr:cells for tr,cells in rows.rows}
    selected = checked.get("p1_deferred_base_names")
    require(isinstance(selected,list)
            and len(selected)==checked["chart_records"]["P1_deferred"],
            "original chart P1 deferred population inconsistent")
    mapped={}
    for item in selected:
        base=item.get("base_device_chart_observation")
        tr=item.get("source_tr_ordinal")
        require(isinstance(base,str) and base
                and base.upper() not in mapped
                and item.get("priority")=="P1"
                and item.get("exact_icpn_verified_from_chart") is False
                and item.get("record_scope") ==
                    "manufacturer_chart_base_device_research_only"
                and isinstance(tr,int) and tr>0,
                "duplicate or falsely qualified manufacturer P1 Chart row")
        raw=existing.get(tr)
        require(raw is not None and len(raw)==len(names)
                and chart.chart_name(raw[columns["base_device"]])==base.upper(),
                "P1 original chart TR/Base row reattachment conflict")
        field_values={
            field:chart.evidence_for_field(
                field, header, raw[index], tr, index+1, sha)
            for field,header in HEADERS.items()
            for index in [columns[field]]
        }
        mapped[base.upper()]={"fields":field_values, "original_tr":tr}
    return checked,mapped


def bind_chart(records, checked, mapped):
    require(checked.get("chart_records",{}).get("P1_deferred")==len(mapped)
            and checked.get("exact_icpn_fields_verified_from_chart")==0,
            "untrusted P1 chart grouping")
    sha=checked["source_original_sha256"]
    require(p0.valid_sha(sha), "P1 chart SHA invalid")
    matches=0
    quantities=Counter()
    unlinked=[]
    for record in records:
        observed=mapped.get(record["base_device"].upper())
        if observed is None:
            unlinked.append(record["icpn"])
            continue
        matches+=1
        for field in FAMILY_FIELDS:
            entry=observed["fields"].get(field)
            require(entry is not None
                    and entry.get("status") in ("PARTIAL","UNKNOWN")
                    and entry.get("evidence_scope") ==
                        "official_base_device_chart_not_exact_icpn"
                    and entry.get("source_original_sha256")==sha,
                    "missing P1 family field / untrusted provenance")
            if entry["status"]!="PARTIAL":
                continue
            value=entry["value"]
            raw=entry["original_raw_value"]
            header=entry["original_header"]
            tr=entry["source_tr_ordinal"]
            col=entry["source_column_number_1based"]
            require(value is not None and isinstance(raw,str) and raw
                    and isinstance(header,str) and header
                    and isinstance(tr,int) and tr>0
                    and isinstance(col,int) and col>0,
                    "P1 Chart PARTIAL source row/value missing")
            record["fields"][field]=p0.status_field(
                "PARTIAL",value,unit=entry["original_unit"],
                locator=(f"{checked['source_url']} / TR {tr} / "
                         f"column {col}: {header} = {raw}"),
                hashes=[sha],
                scope="official_base_device_chart_not_exact_icpn",
                note="Family-only official chart parametric; cannot certify "
                     "the exact commercial ICPN ordering suffix.")
            quantities[field]+=1
    return {
        "official_chart_scope":checked["chart_scope"],
        "official_original_chart_sha256":sha,
        "chart_p1_base_name_count":len(mapped),
        "p1_icpns_exact_base_joined_to_chart":matches,
        "p1_icpns_no_chart_base_match":len(unlinked),
        "p1_unmatched_icpns":sorted(unlinked),
        "partial_field_observation_counts":dict(sorted(quantities.items())),
        "chart_exact_variant_verified_fields":0,
    }


def build(source, original_source_sha256, chart_root=None):
    require(p0.valid_sha(original_source_sha256),
            "original reverse mapping report SHA-256 required")
    upstream=p0.verify_upstream(source)
    actual=[r for r in upstream if r.get("mapping_state")==P1_STATE]
    require(len(actual)==P1_EXPECTED,
            "P1 research ICPN cohort changed")
    entries=[identity(r) for r in actual]
    entries.sort(key=lambda x:x["icpn"].upper())
    ids=[x["icpn"].upper() for x in entries]
    require(len(set(ids))==len(ids),
            "duplicate P1 exact manufacturer ICPN")
    distinct_bases=Counter(x["base_device"].upper() for x in entries)
    # Do not conflate 126 commercial ICPNs with 12 distinct DFP names:
    # report separate denominators; rely on original source evidence.
    source_cfg_groups=source.get("cfg_group_rows")
    require(isinstance(source_cfg_groups,list)
            and len(source_cfg_groups)==11,
            "source CFG-first DFP group evidence missing")
    relevant=[g for g in source_cfg_groups
              if g.get("openocd_target_cfg")==P1_CFG
              and g.get("priority")=="P1"]
    require(len(relevant)==1 and relevant[0].get("dfp_device_name_count")==12
            and set(distinct_bases) <=
                {s.upper() for s in relevant[0]["dfp_device_names"]},
            "manufacturer P1 base is not within the pinned DFP candidate set")
    chart_audit=None
    if chart_root is not None:
        report,mapped=chart_p1_fields(chart_root)
        chart_audit=bind_chart(entries,report,mapped)
    field_counts={k:Counter(e["fields"][k]["status"] for e in entries)
                  for k in FIELDS}
    def all_states(c):
        return {s:c[s] for s in STATUSES}
    return {
        "schema_version":1,
        "policy":"ADR-0002 Phase 1 - IC Information",
        "scope":"microchip_p1_126_target_only_research_ic_information_ledger",
        "manufacturer":"Microchip",
        "research_priority":"P1",
        "original_cfg_reverse_source_report_sha256":original_source_sha256,
        "source_replayed_research_icpn_denominator":p0.EXPECTED_ALL,
        "source_replayed_p0_icpns_retained_separately":p0.EXPECTED_P0,
        "p1_target_only_icpn_count":P1_EXPECTED,
        "p1_unique_original_mcp_base_device_count":len(distinct_bases),
        "p1_distinct_base_icpn_counts":dict(sorted(distinct_bases.items())),
        "p1_openocd_target_cfg_research_only":P1_CFG,
        "p1_target_only_not_software_supported":True,
        "original_manufacturer_bytes_replayed_by_this_projection":False,
        "upstream_original_manufacturer_bytes_replayed":True,
        "chart_original_bytes_replayed_by_upstream_chart_builder":chart_root is not None,
        "p1_official_chart_evidence":chart_audit,
        "per_field_coverage":{k:all_states(v) for k,v in field_counts.items()},
        "phase1_field_contract":list(FIELDS),
        "phase1_fully_verified_exact_icpns":0,
        "internal_identity_admitted_count":0,
        "software_supported_icpn_count":0,
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "phase2_programming_authorized":False,
        "phase3_compatibility_authorized":False,
        "records":entries,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--upstream-cfg-report",type=Path,required=True)
    parser.add_argument("--chart-original-root",type=Path)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    output=args.output.resolve()
    require("production" not in {x.casefold() for x in output.parts},
            "Research-only P1 output cannot write Production")
    raw=args.upstream_cfg_report.read_bytes()
    require(0<len(raw)<=MAX_UPSTREAM,"invalid upstream Research source size")
    result=build(json.loads(raw),hashlib.sha256(raw).hexdigest(),
                 chart_root=args.chart_original_root)
    if args.verify:
        require(json.loads(output.read_text(encoding="utf-8"))==result,
                "P1 Phase 1 source-bound report replay differs")
        print("MICROCHIP P1 PHASE1 SOURCE-BOUND REPLAY PASS")
    else:
        require(not output.exists(),
                "P1 research output already exists, refusing overwrite")
        output.parent.mkdir(parents=True,exist_ok=True)
        with output.open("x",encoding="utf-8") as dst:
            json.dump(result,dst,sort_keys=True,indent=2)
            dst.write("\n")
        print(json.dumps({k:v for k,v in result.items() if k!="records"},
                         sort_keys=True,indent=2))


if __name__=="__main__":
    main()

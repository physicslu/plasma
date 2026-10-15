#!/usr/bin/env python3
"""ADR-0002 Phase 1: source-confirmed exact ICPN S1 and information-quality S1_complete.

Unlike P0/P1/P2 OpenOCD research priority, S1 is a manufacturer identity
qualification. Only official original MCP partNumber+basePartNumber source
observations with original SHA, source URI, scope and *actual capture time*
enter S1. Existing family chart observations remain PARTIAL, never VERIFIED.
This is read-only Research; no Product Catalog admission, Phase 2 or Phase 3.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re

import microchip_phase1_p0_information_ledger_v1 as p0
from microchip_phase1_information_v1 import FIELDS, STATUSES

EXPECTED = 23276
P0 = 2437
P1 = 126
P2 = EXPECTED-P0-P1
OFFICIAL_URI = "https://api.microchip.com/mcp/resources"
MATERIAL_SCOPE = "official_mcp_search_products_exact_partNumber_row"
REQUIRED = (
    "manufacturer", "icpn", "base_device", "package", "pin_count",
    "flash", "ram", "vdd", "io_supply", "vdda", "temperature")
VALID_STATES = frozenset(("IDENTIFIED", "RESEARCH_ONLY", "IDENTITY_DISPUTED"))
BLOB_CAP = 64*1024*1024


def require(ok, why):
    if not ok:
        raise ValueError(why)


def valid_time(raw):
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed=datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        return None
    return parsed.isoformat()


def prepare_ledger(name, info, upstream_sha, expected):
    require(info.get("schema_version")==1
            and info.get("manufacturer")=="Microchip"
            and info.get("original_cfg_reverse_source_report_sha256")==upstream_sha
            and info.get("production_write_authorized") is False
            and info.get("catalog_publication_authorized") is False
            and info.get("phase2_programming_authorized") is False
            and info.get("phase3_compatibility_authorized") is False
            and info.get("phase1_field_contract")==list(FIELDS)
            and info.get("source_replayed_research_icpn_denominator")==EXPECTED
            and len(info.get("records",[]))==expected,
            "untrusted source-joined "+name+" field evidence ledger")
    result={}
    for record in info["records"]:
        icpn=record["icpn"].upper()
        require(icpn not in result, "duplicate exact ICPN in "+name)
        require(record.get("software_supported_claimed") is False
                and record.get("production_write_authorized") is False
                and record.get("internal_identity_admission")=="NOT_ADMITTED",
                "field research cannot authorize software or admission")
        fields=record["fields"]
        require(set(fields)==set(FIELDS),
                "missing field coverage in "+name)
        for key,field in fields.items():
            require(field.get("status") in STATUSES,
                    "illegal exact-field evidence state")
            if field["status"]=="PARTIAL":
                require(field.get("value") is not None
                        and field.get("evidence_scope")
                        and field.get("original_response_sha256_refs"),
                        "family partial field missing original source")
            if field["status"]=="UNKNOWN":
                require(field.get("value") is None,
                        "unknown Phase 1 field filled without authority")
        result[icpn]=record
    return result


def identity(row):
    code,base=row.get("icpn"),row.get("base_device")
    hashes=row.get("original_mcp_response_sha256_refs")
    sources=row.get("manufacturer_exact_material_source_observations")
    defects=[]
    if not isinstance(code,str) or not code or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9+._/\-]{1,95}",code):
        defects.append("INVALID_COMPLETE_COMMERCIAL_ICPN")
    if not isinstance(base,str) or not base.strip():
        defects.append("NO_MANUFACTURER_CONFIRMED_BASE")
    if row.get("manufacturer_base_identity_evidence") != (
            "ORIGINAL_MICROCHIP_MCP_RESPONSE_REPLAYED_IN_THIS_COMMAND"):
        defects.append("NOT_INDEPENDENTLY_ORIGINAL_MCP_REPLAYED")
    if row.get("mapping_state") not in (
            "EXACT_DFP_NAME_CFG_CANDIDATE",
            "REVIEWED_MANUFACTURER_ALIAS_CFG_CANDIDATE",
            "P1_TARGET_ONLY_CFG_CANDIDATE",
            "NO_DFP_NAME_CFG_CROSSWALK"):
        defects.append("CONFLICTING_OR_UNCLASSIFIED_ORIGINAL_IDENTITY")
    if not isinstance(hashes,list) or not hashes or (
            len(set(hashes))!=len(hashes)) or not all(
            p0.valid_sha(h) for h in hashes):
        defects.append("NO_UNAMBIGUOUS_RAW_RESPONSE_SHA")
    if not isinstance(sources,list) or not sources:
        defects.append("MISSING_EXACT_MATERIAL_OBSERVATIONS")
        sources=[]
    official=[]
    if isinstance(hashes,list):
        expected=set(h for h in hashes if isinstance(h,str))
    else:
        expected=set()
    for src in sources:
        if not isinstance(src,dict):
            defects.append("UNTRUSTED_SOURCE_RECORD")
            continue
        base_observed=src.get("manufacturer_base_part_number")
        if src.get("manufacturer_official_source_uri")!=OFFICIAL_URI or (
                src.get("source_scope")!=MATERIAL_SCOPE):
            defects.append("SOURCE_NOT_OFFICIAL_EXACT_MATERIAL")
        if (src.get("exact_icpn")!=code or
                not isinstance(base_observed,str) or
                not isinstance(base,str) or
                base_observed.upper()!=base.upper()):
            defects.append("EXACT_MATERIAL_BASE_DISPUTED")
        if (src.get("original_response_sha256") not in expected or
                not isinstance(src.get("source_query"),str) or
                not src["source_query"]):
            defects.append("MATERIAL_RESPONSE_NOT_BOUND_TO_ORIGINAL_SHA")
        time=valid_time(src.get("original_observed_at_utc"))
        if time is None:
            defects.append("ORIGINAL_OBSERVATION_TIMESTAMP_MISSING")
        if time is not None and src.get("original_response_sha256") in expected:
            official.append(time)
    if len(official)==0:
        defects.append("NO_TIMESTAMPED_ORIGINAL_MATERIAL_PROOF")
    # A bad source must not be outvoted by one apparently good response.
    defects=sorted(set(defects))
    state = ("IDENTIFIED" if not defects else
             "IDENTITY_DISPUTED" if any(x.endswith("DISPUTED")
                                      or x.startswith("CONFLICTING")
                                      for x in defects) else "RESEARCH_ONLY")
    require(state in VALID_STATES, "invalid S1 state")
    return state,defects,sorted(set(official))


def create(source, p0_info, p1_info, original_upstream_sha):
    # The original MCP/DFP archive inputs were independently replayed by
    # the upstream command in this same CI job. Never use derived-only rollups.
    rows=p0.verify_upstream(source)
    require(len(rows)==EXPECTED, "manufacturer exact ICPN cohort drift")
    first=prepare_ledger("P0",p0_info,original_upstream_sha,P0)
    second=prepare_ledger("P1",p1_info,original_upstream_sha,P1)
    require(not (set(first)&set(second)), "P0/P1 overlapping identities")
    report=[]
    existing=set()
    priority=Counter()
    states=Counter()
    reasons=Counter()
    fields_count={key:Counter() for key in FIELDS}
    included_by_base=Counter()
    complete=0
    capture_provenance=Counter()
    for row in rows:
        icpn=row.get("icpn")
        require(isinstance(icpn,str), "raw source has no commercial ICPN")
        ident=icpn.upper()
        require(ident not in existing,"duplicated official commercial identity")
        existing.add(ident)
        source_priority = ("P0" if ident in first else
                           "P1" if ident in second else "P2")
        priority[source_priority]+=1
        record=first.get(ident) or second.get(ident)
        if record is not None:
            require(record["base_device"].upper()==row["base_device"].upper()
                    and record["source_original_mcp_response_sha256_refs"]==
                        row["original_mcp_response_sha256_refs"],
                    "information ledger diverges from original MCP exact identity")
            fields={key:record["fields"][key]["status"] for key in FIELDS}
        else:
            fields={key:("VERIFIED" if key in
                      ("manufacturer","icpn","base_device") else "UNKNOWN")
                    for key in FIELDS}
        state,defects,timestamps=identity(row)
        states[state]+=1
        for reason in defects:
            reasons[reason]+=1
        if state=="IDENTIFIED":
            included_by_base[row["base_device"].upper()]+=1
            if all(fields[key]=="VERIFIED" for key in REQUIRED):
                complete+=1
        for key,val in fields.items():
            fields_count[key][val]+=1
        for raw_observation in row.get(
                "manufacturer_exact_material_source_observations",[]):
            if isinstance(raw_observation,dict):
                capture_provenance[
                    "original_source_timestamps_present" if valid_time(
                        raw_observation.get("original_observed_at_utc"))
                    else "original_source_timestamp_missing"]+=1
        report.append({
            "manufacturer":"Microchip","icpn":icpn,
            "base_device":row.get("base_device"),
            "phase1_identity_status":state,
            "phase1_information_status":(
                "INFORMATION_COMPLETE" if state=="IDENTIFIED" and
                all(fields[key]=="VERIFIED" for key in REQUIRED)
                else "INFORMATION_INCOMPLETE"),
            "phase1_identity_defects":defects,
            "material_official_source_uri":OFFICIAL_URI,
            "source_scope":MATERIAL_SCOPE,
            "observed_at_utc_from_original_responses":timestamps,
            "original_mcp_response_sha256_refs":
                row.get("original_mcp_response_sha256_refs"),
            "raw_manufacturer_lifecycle_status":
                row.get("manufacturer_raw_lifecycle_status"),
            "research_priority_separate_from_phase":source_priority,
            "information_field_statuses":fields,
            "internal_identity_admitted":False,
            "openocd_software_supported_asserted":False,
            "physical_hil_passed_asserted":False,
        })
    require(priority==Counter({"P0":P0,"P1":P1,"P2":P2}),
            "original research-priority partition drift")
    require(set(first)|set(second) <= existing,
            "P0/P1 original information ledger lost identities")
    require(sum(states.values())==EXPECTED
            and all(sum(v.values())==EXPECTED for v in fields_count.values())
            and complete<=states["IDENTIFIED"],
            "Phase 1 Exact ICPN funnel invariants broken")
    report.sort(key=lambda r:r["icpn"].upper())
    return {
        "schema_version":1,
        "policy":"ADR-0002 Phase 1 Original Manufacturer Exact ICPN Funnel",
        "manufacturer":"Microchip",
        "official_mcp_source_uri":OFFICIAL_URI,
        "original_source_replay_claim":
            "PINNED_ORIGINAL_MCP_AND_DFP_ARCHIVES_REPLAYED_IN_UPSTREAM_CI",
        "upstream_full_original_mcp_report_sha256":original_upstream_sha,
        "source_subset_observed_distinct_commercial_icpns":EXPECTED,
        "source_scope_not_global_manufacturer_census":True,
        "phase1_s1_identified":states["IDENTIFIED"],
        "phase1_s1_complete":complete,
        "phase1_research_only_source_gaps":states["RESEARCH_ONLY"],
        "phase1_identity_disputed":states["IDENTITY_DISPUTED"],
        "source_observation_timestamp_evidence_counts":
            dict(sorted(capture_provenance.items())),
        "missing_identity_evidence_by_reason":dict(sorted(reasons.items())),
        "phase1_distinct_identified_manufacturer_bases":
            len(included_by_base),
        "legacy_research_priority_counts_separate_from_phases":
            dict(sorted(priority.items())),
        "phase1_information_coverage_all_source_observed_icpns":{
            field:{status:fields_count[field][status] for status in STATUSES}
            for field in FIELDS},
        "phase1_required_information_fields":list(REQUIRED),
        "source_original_mcp_evidence_is_product_catalog_admission":False,
        "manufacturer_whole_population_covered":False,
        "openocd_software_supported_count_from_this_phase":0,
        "phase3_hil_passed_count_from_this_phase":0,
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "phase2_programming_authorized":False,
        "phase3_compatibility_authorized":False,
        "records":report,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--upstream-cfg-report",type=Path,required=True)
    ap.add_argument("--p0-information-ledger",type=Path,required=True)
    ap.add_argument("--p1-information-ledger",type=Path,required=True)
    ap.add_argument("--output",type=Path,required=True)
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    require("production" not in {p.lower() for p in args.output.resolve().parts},
            "Phase 1 output cannot write Production")
    original=args.upstream_cfg_report.read_bytes()
    require(0<len(original)<=BLOB_CAP,
            "source-replayed original-MCP report missing or oversized")
    source=json.loads(original)
    result=create(source,
                  json.loads(args.p0_information_ledger.read_text("utf-8")),
                  json.loads(args.p1_information_ledger.read_text("utf-8")),
                  hashlib.sha256(original).hexdigest())
    if args.verify:
        require(json.loads(args.output.read_text("utf-8"))==result,
                "Phase 1 source identity funnel offline replay mismatch")
        print("MICROCHIP PHASE 1 S1 FUNNEL REPLAY PASS")
    else:
        require(not args.output.exists(),
                "Refusing to overwrite existing Phase 1 research report")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as dst:
            json.dump(result,dst,sort_keys=True,indent=2)
            dst.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k!="records"},
                     sort_keys=True,indent=2))


if __name__=="__main__":
    main()

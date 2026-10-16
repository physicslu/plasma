#!/usr/bin/env python3
"""ADR-0002 authority boundary for ALL Microchip Phase 1 / Phase 2 identities.

Reads the independently original-MCP-replayed Microchip 23,276 Exact ICPN
Phase 1 identity report. Exposes the canonical cross-vendor Phase 1/2/3
states ONLY; legacy P0/P1/P2/CFG priority may remain in archived raw source
for replay but NEVER becomes a canonical Phase or Selector visibility gate.

The output is a Research snapshot/status projection. It is not automatically
a Product deployment, validated Programming Profile, or executable route.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path

OFFICIAL_URI = "https://api.microchip.com/mcp/resources"
MATERIAL_SCOPE = "official_mcp_search_products_exact_partNumber_row"
IDENTITY_STATES = frozenset(("IDENTIFIED", "RESEARCH_ONLY", "IDENTITY_DISPUTED"))
FIELD_STATES = frozenset(("VERIFIED", "PARTIAL", "UNKNOWN", "CONFLICT", "NOT_APPLICABLE"))
PHASE2_STATES = frozenset(("UNKNOWN", "CANDIDATE", "SUPPORTED", "UNSUPPORTED"))
PHASE3_STATES = frozenset(("NOT_TESTED", "PASSED", "FAILED"))
FIELD_MAP = {
    "manufacturer": "manufacturer",
    "icpn": "icpn",
    "base_device": "base_device",
    "package": "package",
    "pin_count": "pin_count",
    "flash": "flash",
    "ram": "ram",
    "vdd": "working_vdd",
    "io_supply": "io_supply",
    "vdda": "vdda",
    "temperature": "temperature",
    "core_architecture": "core_architecture",
    "core_model": "core_model",
}
REQUIRED = (
    "manufacturer", "icpn", "base_device", "package", "pin_count",
    "flash", "ram", "working_vdd", "io_supply", "vdda", "temperature",
)
EXACT_SNAPSHOT_COUNT = 23276
MAX_BYTES = 64 * 1024 * 1024


def require(predicate, reason):
    if not predicate:
        raise ValueError(reason)


def sha256(s):
    return isinstance(s, str) and len(s)==64 and all(
        char in "0123456789abcdef" for char in s
    )


def canonical_projection(source: dict) -> dict:
    """Derive permitted *status* from original manufacturer proof, never CFG."""
    require(source.get("schema_version")==1
            and source.get("policy")=="ADR-0002 Phase 1 Original Manufacturer Exact ICPN Funnel"
            and source.get("manufacturer")=="Microchip"
            and source.get("official_mcp_source_uri")==OFFICIAL_URI
            and source.get("source_subset_observed_distinct_commercial_icpns")==EXACT_SNAPSHOT_COUNT
            and source.get("source_scope_not_global_manufacturer_census") is True
            and sha256(source.get("upstream_full_original_mcp_report_sha256"))
            and source.get("production_write_authorized") is False
            and source.get("catalog_publication_authorized") is False
            and source.get("phase2_programming_authorized") is False
            and source.get("phase3_compatibility_authorized") is False,
            "untrusted/unbounded original manufacturer Phase 1 report")
    raw=source.get("records")
    require(isinstance(raw,list) and len(raw)==EXACT_SNAPSHOT_COUNT,
            "source original manufacturer Exact ICPN count drift")
    out=[]
    seen=set()
    identities=Counter()
    coverage={f:Counter() for f in FIELD_MAP.values()}
    complete=0
    for r in raw:
        icpn=r.get("icpn")
        ident=r.get("phase1_identity_status")
        fields=r.get("information_field_statuses")
        require(isinstance(icpn,str) and icpn
                and icpn.upper() not in seen,
                "duplicate/incomplete manufacturer exact material")
        seen.add(icpn.upper())
        require(r.get("manufacturer")=="Microchip"
                and isinstance(r.get("base_device"),str)
                and r["base_device"]
                and ident in IDENTITY_STATES
                and isinstance(fields,dict)
                and set(fields)==set(FIELD_MAP)
                and r.get("material_official_source_uri")==OFFICIAL_URI
                and r.get("source_scope")==MATERIAL_SCOPE
                and r.get("internal_identity_admitted") is False
                and r.get("openocd_software_supported_asserted") is False
                and r.get("physical_hil_passed_asserted") is False,
                "Phase 1 identity proof or no-qualification contract violated")
        hashes=r.get("original_mcp_response_sha256_refs")
        require(isinstance(hashes,list) and len(hashes)>0
                and len(set(hashes))==len(hashes)
                and all(sha256(v) for v in hashes),
                "missing original official Microchip MCP exact-material SHA")
        capture=r.get("observed_at_utc_from_original_responses")
        require(isinstance(capture,(str,list,dict))
                and bool(capture),
                "exact material original observation time missing")
        require(all(x in FIELD_STATES for x in fields.values()),
                "invalid ADR-0002 field evidence state")
        normalized={canonical:fields[legacy]
                    for legacy,canonical in FIELD_MAP.items()}
        visible=ident=="IDENTIFIED"
        is_complete=(visible and all(normalized[f] in
                     ("VERIFIED","NOT_APPLICABLE") for f in REQUIRED))
        require((r.get("phase1_information_status")=="INFORMATION_COMPLETE")==is_complete,
                "Phase 1 INFORMATION_COMPLETE is not justified by field states")
        require(not visible or all(normalized[f]=="VERIFIED" for f in
                    ("manufacturer","icpn","base_device")),
                "claimed manufacturer identity without exact source fields")
        identities[ident]+=1
        complete+=int(is_complete)
        for field,status in normalized.items():
            coverage[field][status]+=1
        out.append({
            "manufacturer":"Microchip",
            "icpn":icpn,
            "base_device":r["base_device"],
            "phase1":{
                "identity_state":ident,
                "information_state":r["phase1_information_status"],
                "field_states":normalized,
                "official_material_source_uri":OFFICIAL_URI,
                "original_manufacturer_sha256_refs":hashes,
                "source_observed_at_utc":capture,
                "source_scope":MATERIAL_SCOPE,
            },
            "phase2":{
                # This projection holds no independent versioned Programming
                # qualification. A research CFG MUST NOT promote this field.
                "programming_state":"UNKNOWN",
                "qualification_provider":None,
                "programming_profile":None,
                "supported_operations":[],
            },
            "phase3":{
                "compatibility_state":"NOT_TESTED",
                "qualified_configurations":[],
            },
            "ic_selector_visible":visible,
            "execution_authorized":False,
        })
    require(len(out)==EXACT_SNAPSHOT_COUNT, "Microchip Phase 1 denominator mismatch")
    require(identities["IDENTIFIED"]==source.get("phase1_s1_identified")
            and complete==source.get("phase1_s1_complete")
            and identities["RESEARCH_ONLY"]==source.get("phase1_research_only_source_gaps")
            and identities["IDENTITY_DISPUTED"]==source.get("phase1_identity_disputed"),
            "Microchip Phase 1 / information counts not independently derived")
    out.sort(key=lambda r:r["icpn"].upper())
    return {
        "schema_version":1,
        "policy":"ADR-0002",
        "manufacturer":"Microchip",
        "scope":"bounded_original_manufacturer_exact_icpn_snapshot",
        "phase1_exact_icpn_observed":EXACT_SNAPSHOT_COUNT,
        "phase1_identity_counts":dict(sorted(identities.items())),
        "phase1_information_complete_count":complete,
        "selector_visible_identified_count":identities["IDENTIFIED"],
        "phase2_programming_state_counts":{"UNKNOWN":EXACT_SNAPSHOT_COUNT,
                                          "CANDIDATE":0,"SUPPORTED":0,"UNSUPPORTED":0},
        "phase3_compatibility_state_counts":{"NOT_TESTED":EXACT_SNAPSHOT_COUNT,
                                             "PASSED":0,"FAILED":0},
        "field_coverage":{
            f:{status:coverage[f][status] for status in
               ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT","NOT_APPLICABLE")}
            for f in FIELD_MAP.values()},
        "upstream_full_original_mcp_report_sha256":
            source["upstream_full_original_mcp_report_sha256"],
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "phase2_programming_authorized":False,
        "phase3_hil_authorized":False,
        "no_legacy_priority_in_canonical_output":True,
        "selector_visibility_not_yet_deployed_by_this_artifact":True,
        "records":out,
    }


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-s1-funnel",type=Path,required=True)
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--verify",action="store_true")
    args=parser.parse_args()
    require("production" not in {x.casefold() for x in args.output.resolve().parts},
            "cannot publish canonical snapshot directly to Production")
    raw=args.source_s1_funnel.read_bytes()
    require(0<len(raw)<=MAX_BYTES, "source S1 report absent/too large")
    report=canonical_projection(json.loads(raw))
    rendered=(json.dumps(report,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode()
    if args.verify:
        require(args.output.read_bytes()==rendered,
                "canonical ADR-0002 projection failed deterministic replay")
    else:
        require(not args.output.exists(),"refuse overwrite of source-locked projection")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_bytes(rendered)
    print(json.dumps({k:v for k,v in report.items() if k!="records"},
                     indent=2,sort_keys=True,ensure_ascii=False))
    print("MICROCHIP_ADR0002_CANONICAL_PHASE1_2_3_PASS")


if __name__=="__main__":
    main()

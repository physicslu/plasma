#!/usr/bin/env python3
"""ADR-0002 Microchip Phase 1: independently source-locked remaining 2,441.

Inputs are ORIGINAL manufacturer-MCP replay-derived canonical 23,276
identities, a frozen five-CFG / 2,563 exact-SKU field ledger, and original
MCP + DS60001513G audited 122 ordinary SAM L10/L11 first-batch identities.
Never fabricate packages, voltages, temperature grades or SKU suffixes.
Never treat CFG matches as software qualification or executable routes.

This produces a read-only Phase 1 candidate JSONL + audit JSON for later
Catalog ingestion; it DOES NOT insert entries into Production, issue Jobs
or make Phase 2/3 claims. The original four special VAO exact SKUs remain
IDENTIFIED in the 2,441 backlog with unqualified optional fields.
"""
from __future__ import annotations

import argparse
import csv
import io
from collections import Counter
import hashlib
import json
from pathlib import Path

import microchip_phase1_cfg2563_st_field_ledger_v1 as frozen
import microchip_adr0002_cfg2563_target_scope_v1 as target
import microchip_phase1_p1_ordering_crosswalk_v1 as official_pdf

SOURCE=23276
COHORT=2563
FIRST=122
REMAINING=2441
REMAINING_BY_CFG={
    "tcl/target/pic32mx.cfg":1241,
    "tcl/target/at91samdXX.cfg":667,
    "tcl/target/atsame5x.cfg":354,
    "tcl/target/atsamv.cfg":175,
    "tcl/target/atsaml1x.cfg":4,
}
FIRST_CODES_SHA="7a75e18a5f23cc2b80e10e1675918ce7da0601fe0d8d35664ebb78c4fb8d3b64"
EXPECTED_REMAINING_IDS_SHA="fa29b7a2b739caad4aa8cd0bc6e8d6ee74a90aa50ea230b5e3c7a10b2eb81db6"
EXPECTED_QUEUE_JSONL_SHA="965b7faaba2942cdadf982768236c7a666bce46733b2afc3a16ea3e03de824e8"
PHASE_FIELDS=frozen.ST_FIELDS
EVIDENCE_STATES=("VERIFIED","PARTIAL","UNKNOWN","CONFLICT","NOT_APPLICABLE")
PDF_SHA=official_pdf.PDF_SHA


def require(ok:bool, message:str):
    if not ok:
        raise ValueError(message)


def read(path:Path):
    raw=path.read_bytes()
    require(0<len(raw)<=64*1024*1024,"missing/oversized original replay report")
    return json.loads(raw)


def digest_ids(items:list[str]):
    return hashlib.sha256(("".join(x+"\n" for x in sorted(items))).encode()).hexdigest()


def derive(original:dict, freeze:dict, first_audit:dict):
    """Cross-source exact identity and first-batch subtraction, no CFG inference."""
    target.select_target(original,freeze)
    require(original["phase1_identity_counts"].get("IDENTIFIED")==SOURCE
            and original["phase2_programming_state_counts"]["SUPPORTED"]==0
            and original["phase3_compatibility_state_counts"]["PASSED"]==0,
            "ADR-0002 phase states drift or software-only support overclaim")
    require(first_audit.get("schema_version")==1
            and first_audit.get("p1_original_mcp_exact_icpn_count")==126
            and first_audit.get("p1_base_device_count")==12
            and first_audit.get("pdf_source_replay",{}).get("original_pdf_sha256")==PDF_SHA
            and first_audit.get("status_counts")=={
              "MCP_EXACT_CODE_MATCHES_PDF_ORDERING_GRAMMAR":122,
              "MCP_VAO_SPECIAL_SUFFIX_SEPARATE_SOURCE_REVIEW_REQUIRED":4}
            and first_audit.get("software_supported_icpns")==0
            and first_audit.get("internal_admitted_icpns")==0
            and first_audit.get("production_write_authorized") is False
            and first_audit.get("catalog_publication_authorized") is False,
            "first 122 PDF+manufacturer replay does not match frozen material")
    first=set()
    unusual=set()
    all_pdf=set()
    for r in first_audit["records"]:
        icpn=r["icpn"].upper()
        require(icpn not in all_pdf and frozen.is_sha(r["source_pdf_original_sha256"]),
                "duplicate/original PDF hash missing in original 126")
        all_pdf.add(icpn)
        require(r["source_pdf_original_sha256"]==PDF_SHA
                and r["software_supported_claimed"] is False
                and r["production_write_authorized"] is False,
                "first batch source silently gained software qualification")
        state=r["status"]
        if state=="MCP_EXACT_CODE_MATCHES_PDF_ORDERING_GRAMMAR":
            require(official_pdf.ORDER.fullmatch(icpn) is not None,
                    "first batch code is not an official ordinary ordering variant")
            first.add(icpn)
        elif state=="MCP_VAO_SPECIAL_SUFFIX_SEPARATE_SOURCE_REVIEW_REQUIRED":
            require(icpn.endswith("VAO") and
                    r.get("special_suffix_observed")=="VAO",
                    "special original SKU not quarantined")
            unusual.add(icpn)
        else:
            raise ValueError("unreviewed manufacturer material ordering status")
    require(len(first)==FIRST and len(unusual)==4
            and digest_ids(list(first))==FIRST_CODES_SHA,
            "122 exact Phase 1 first-batch identity digest drift")
    canonical={r["icpn"].upper():r for r in original["records"]}
    require(len(canonical)==SOURCE,
            "duplicate canonical original manufacturer full order code")
    freeze_set={r["icpn"].upper() for r in freeze["records"]}
    require(len(freeze_set)==COHORT and all_pdf<=freeze_set
            and first<=freeze_set and unusual<=freeze_set,
            "first source-verified batch does not belong to frozen five CFG")
    pending=freeze_set-first
    require(len(pending)==REMAINING and unusual<=pending,
            "subtraction of source-verified first-batch exact ICPNs drift")
    rows=[]
    statuses={field:Counter() for field in PHASE_FIELDS}
    groups=Counter()
    for record in freeze["records"]:
        code=record["icpn"].upper()
        if code in first:
            continue
        source=canonical[code]
        require(record["phase1_identity_status"]=="IDENTIFIED"
                and source["phase1"]["identity_state"]=="IDENTIFIED"
                and source["ic_selector_visible"] is True
                and source["phase1"]["source_scope"]==
                    "official_mcp_search_products_exact_partNumber_row"
                and source["phase1"]["original_manufacturer_sha256_refs"]==
                    record["source_original_mcp_response_sha256_refs"]
                and record["base_device"].upper()==source["base_device"].upper(),
                "Phase 1 official exact manufacturer evidence not preserved")
        require(source["phase2"]["programming_state"]=="UNKNOWN"
                and source["phase3"]["compatibility_state"]=="NOT_TESTED"
                and source["execution_authorized"] is False,
                "Phase 2 or HIL cannot be inferred from frozen CFG discovery")
        fields=record["fields"]
        require(set(fields)==set(PHASE_FIELDS),"Phase 1 canonical field schema drift")
        normalized={}
        for field in PHASE_FIELDS:
            v=fields[field]
            state=v["state"]
            require(state in EVIDENCE_STATES,
                    "Phase 1 unsupported field evidence state")
            if state=="UNKNOWN":
                require(v["value"] is None and not v["source_sha256_refs"],
                        "unknown Phase 1 field has invented source or numeric zero")
            elif state in ("VERIFIED","PARTIAL","NOT_APPLICABLE"):
                require(v["source_authority"]=="Microchip Technology official"
                        and v["source_sha256_refs"]
                        and all(frozen.is_sha(z) for z in v["source_sha256_refs"]),
                        "asserted Phase 1 field without original manufacturer source")
                if state=="NOT_APPLICABLE":
                    require(v["value"] is None and
                            "NOT_APPLICABLE" in (v["notes"] or "").upper(),
                            "not-applicable rail requires explicit source absence proof")
            if field in ("manufacturer","icpn","base_device"):
                require(state=="VERIFIED",
                        "manufacturer exact material identity not verified")
            normalized[field]=v
            statuses[field][state]+=1
        cfg=record["openocd_target_cfg_research_only"]
        groups[cfg]+=1
        rows.append({
            "manufacturer":"Microchip",
            "icpn":record["icpn"],
            "base_device":record["base_device"],
            "phase1_identity_status":"IDENTIFIED",
            "phase1_information_status":record["phase1_information_status"],
            "phase1_fields":normalized,
            "official_material_source_uri":source["phase1"]["official_material_source_uri"],
            "source_scope":source["phase1"]["source_scope"],
            "source_observed_at_utc":source["phase1"]["source_observed_at_utc"],
            "original_manufacturer_sha256_refs":
                source["phase1"]["original_manufacturer_sha256_refs"],
            "research_only_cfg_lead":cfg,
            "research_cfg_is_executable_mapping":False,
            "phase2_programming_state":"UNKNOWN",
            "phase3_compatibility_state":"NOT_TESTED",
            "executable_openocd_target_cfg":None,
            "openocd_software_supported":False,
            "job_batch_execution_authorized":False,
            "source_pinned_not_production_published":True,
            "manufacturer_ordering_exception_needing_field_review":
                code in unusual,
        })
    rows.sort(key=lambda x:x["icpn"].upper())
    require(len(rows)==REMAINING and dict(groups)==REMAINING_BY_CFG,
            "remaining Phase 1 CFG-first actual target count drift")
    require(sum(x["manufacturer_ordering_exception_needing_field_review"] for x in rows)==4,
            "special VAO identities were incorrectly removed or promoted")
    require(all(x["phase1_information_status"]=="INFORMATION_INCOMPLETE" for x in rows),
            "unexpected field completeness promotion")
    summary={
        "schema_version":1,
        "policy":"ADR-0002",
        "manufacturer":"Microchip",
        "scope":"frozen_five_cfg_phase1_remaining_2441_identity_delivery_queue",
        "source_original_official_identity_snapshot":SOURCE,
        "phase1_engineering_target_exact_icpns":COHORT,
        "first_proposed_122_exact_icpns":FIRST,
        "first_122_exact_icpn_sha256":FIRST_CODES_SHA,
        "remaining_phase1_identified_exact_icpns":REMAINING,
        "remaining_icpn_names_sha256":digest_ids([r["icpn"].upper() for r in rows]),
        "remaining_cfg_counts":dict(sorted(groups.items())),
        "remaining_special_vao_exact_icpns":4,
        "phase1_information_complete":0,
        "phase2_supported":0,
        "phase3_passed":0,
        "phase1_field_coverage":{
            k:{state:statuses[k][state] for state in EVIDENCE_STATES}
            for k in PHASE_FIELDS
        },
        "source_5cfg_2563_identity_sha256":frozen.FROZEN_IDENTITY_SHA256,
        "source_original_pdf_sha256":PDF_SHA,
        "source_mcp_original_snapshot_sha256":
            original["upstream_full_original_mcp_report_sha256"],
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "programming_execution_authorized":False,
        "needs_bounded_catalog_identity_ingestion":True,
        "non_target_original_icpns_remain_valid":True,
    }
    return rows,summary


IDENTITY_CSV_FIELDS=(
    "manufacturer","icpn","base_device","phase1_identity_status",
    "source_scope","official_material_source_uri",
    "source_observed_at_utc_json","original_mcp_response_sha256_refs",
    "openocd_cfg_research_only","phase2_programming_state",
    "phase3_compatibility_state","executable_mapping_status",
)


def identity_csv(rows):
    """Persist exact official identity without fabricating optional fields."""
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=IDENTITY_CSV_FIELDS,lineterminator="\n")
    writer.writeheader()
    for r in rows:
        writer.writerow({
            "manufacturer":"Microchip",
            "icpn":r["icpn"],
            "base_device":r["base_device"],
            "phase1_identity_status":"IDENTIFIED",
            "source_scope":r["source_scope"],
            "official_material_source_uri":r["official_material_source_uri"],
            "source_observed_at_utc_json":json.dumps(
                r["source_observed_at_utc"],sort_keys=True,separators=(",",":")),
            "original_mcp_response_sha256_refs":"|".join(
                r["original_manufacturer_sha256_refs"]),
            "openocd_cfg_research_only":r["research_only_cfg_lead"],
            "phase2_programming_state":"UNKNOWN",
            "phase3_compatibility_state":"NOT_TESTED",
            "executable_mapping_status":"no_mapping",
        })
    return buf.getvalue()


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--canonical",type=Path,required=True)
    ap.add_argument("--cfg-frozen",type=Path,required=True)
    ap.add_argument("--first-batch-pdf-crosswalk",type=Path,required=True)
    ap.add_argument("--output-jsonl",type=Path,required=True)
    ap.add_argument("--summary-json",type=Path,required=True)
    ap.add_argument("--output-identity-csv",type=Path)
    ap.add_argument("--bootstrap-identity-csv-in-ci-log",action="store_true")
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    for path in (args.output_jsonl,args.summary_json,*([args.output_identity_csv] if args.output_identity_csv else [])):
        require("production" not in {part.casefold() for part in path.resolve().parts},
                "Phase 1 research pipeline cannot publish Production Catalog")
    rows, summary=derive(read(args.canonical),read(args.cfg_frozen),
                         read(args.first_batch_pdf_crosswalk))
    content=("".join(json.dumps(r,sort_keys=True,ensure_ascii=False)+"\n"
                     for r in rows)).encode("utf-8")
    summary["remaining_source_queue_sha256"]=hashlib.sha256(content).hexdigest()
    canonical_csv=identity_csv(rows)
    identity_csv_sha=hashlib.sha256(canonical_csv.encode("utf-8")).hexdigest()
    summary["remaining_research_identity_csv_sha256"]=identity_csv_sha
    require(summary["remaining_icpn_names_sha256"]==EXPECTED_REMAINING_IDS_SHA
            and summary["remaining_source_queue_sha256"]==EXPECTED_QUEUE_JSONL_SHA,
            "2441 original-source material membership/payload SHA freeze drift")
    doc=(json.dumps(summary,indent=2,sort_keys=True,ensure_ascii=False)+"\n").encode("utf-8")
    if args.verify:
        require(args.output_jsonl.read_bytes()==content
                and args.summary_json.read_bytes()==doc,
                "source-locked Phase 1 2441 queue nondeterministic")
        if args.output_identity_csv:
            require(args.output_identity_csv.read_text(encoding="utf-8")==canonical_csv,
                    "source-locked 2441 research identity CSV drift")
    else:
        require(not args.output_jsonl.exists() and not args.summary_json.exists(),
                "refuse overwrite of original-source Phase 1 report")
        args.output_jsonl.parent.mkdir(parents=True,exist_ok=True)
        args.summary_json.parent.mkdir(parents=True,exist_ok=True)
        args.output_jsonl.write_bytes(content)
        args.summary_json.write_bytes(doc)
        if args.output_identity_csv:
            require(not args.output_identity_csv.exists(),
                    "refuse overwrite of exact original manufacturer identity index")
            args.output_identity_csv.parent.mkdir(parents=True,exist_ok=True)
            args.output_identity_csv.write_text(canonical_csv,encoding="utf-8")
    print("MICROCHIP_ADR0002_2441_IDENTITIES_CSV_SHA256",identity_csv_sha)
    if args.bootstrap_identity_csv_in_ci_log:
        for line in canonical_csv.splitlines():
            print("CANONICAL_2441_ROW|"+line)
    print(json.dumps({k:v for k,v in summary.items() if k!="phase1_field_coverage"},
                     indent=2,sort_keys=True,ensure_ascii=False))


if __name__=="__main__":
    main()

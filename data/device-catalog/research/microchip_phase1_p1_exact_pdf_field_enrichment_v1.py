#!/usr/bin/env python3
"""Microchip SAM L10/L11 exact Phase 1 information promotion from pinned vendor evidence.

Uses the *existing*, independently replayed original manufacturer MCP exact
commercial records, DS60001513G printed p.14 Table 1-1 and p.16 Ordering
Information. Promote only ordinary exact vendor order codes that match BOTH
original sources with checked applicability. Four unusual VAO order codes
remain unchanged. NO programming, Production or public Catalog mutation.
"""
from __future__ import annotations

import argparse
from collections import Counter
from copy import deepcopy
import hashlib
import json
from pathlib import Path

import microchip_phase1_cfg2563_st_field_ledger_v1 as frozen
import microchip_phase1_p1_ordering_crosswalk_v1 as pdf

FROZEN_SHA = frozen.FROZEN_IDENTITY_SHA256
EXPECTED = 2563
EXACT = 122
EXCEPTIONS = 4
CFG = "tcl/target/atsaml1x.cfg"
PROMOTE = ("package", "pin_count", "flash", "ram", "temperature", "core_model")
MAX_BYTES = 64*1024*1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(path):
    raw=Path(path).read_bytes()
    require(0<len(raw)<=MAX_BYTES, "Phase 1 original-source report unreadable/oversized")
    return json.loads(raw)


def verified_from_original_sources(key, raw, original_mcp_refs, base, icpn):
    """Field-level source contract: one *real* exact original MCP SKU plus PDF applicability."""
    require(key in PROMOTE, "attempt to infer unrelated electrical/core field")
    require(isinstance(icpn,str) and icpn.startswith(base+"-"),
            "manufacturer exact SKU does not match source-replayed Base")
    pdf_fields={
        "package":("package",None),
        "pin_count":("pin_count","pins"),
        "flash":("flash_kib","KB"),
        "ram":("ram_kib","KB"),
        "temperature":("temperature","°C"),
        "core_model":("core_model",None),
    }
    input_key,unit=pdf_fields[key]
    if input_key=="temperature":
        low,high=raw.get("temperature_min_c"),raw.get("temperature_max_c")
        require(low == -40 and high in (85,125),"undocumented temperature range")
        value={"min":low,"max":high}
    else:
        value=raw.get(input_key)
        if key in ("flash","ram"):
            require(type(value) is int and value>0,
                    "invalid memory or undocumented 0 memory")
        elif key=="pin_count":
            require(value in (24,32),"unexpected SAM L1x pin count")
        elif key=="package":
            require(value in ("TQFP","VQFN","WLCSP","SSOP"),
                    "unexpected SAM L1x package")
        else:
            require(value=="Arm Cortex-M23","unexpected manufacturer CPU core")
    hashes=original_mcp_refs
    require(isinstance(hashes,list) and len(hashes)>0
            and len(set(hashes))==len(hashes)
            and all(frozen.is_sha(x) for x in hashes),
            "original exact material hashes absent")
    return {
        "value":value,
        "state":"VERIFIED",
        "unit":unit,
        "source_authority":"Microchip Technology official",
        "source_scope":"original_exact_MCP_SKU_plus_source_pinned_PDF_ordering_applicability",
        "source_locator":(
            f"Microchip MCP search_products exact partNumber={icpn}; "
            f"DS60001513G printed p.14 Table 1-1 Base {base}; "
            f"p.16 Ordering Information suffix for exact order code {icpn}"),
        "source_sha256_refs":sorted(set(hashes+[pdf.PDF_SHA])),
        "source_revision":"DS60001513G",
        "source_url":pdf.original.URL if hasattr(pdf,"original") else None,
        "notes":(
            "Variant checked against original manufacturer exact order-code MCP "
            "identity and separately replayed official PDF ordering grammar. "
            "Original PDF does not independently enumerate all full order codes; "
            "do not infer programming/hardware readiness."),
    }


def enrich(frozen_report, ordering):
    require(frozen_report.get("schema_version")==1
            and frozen_report.get("manufacturer")=="Microchip"
            and frozen_report.get("scope")=="frozen_5cfg_2563_exact_original_manufacturer_icpns"
            and frozen_report.get("record_count")==EXPECTED
            and frozen_report.get("cfg_identity_freeze_sha256")==FROZEN_SHA
            and frozen_report.get("s1_identified")==EXPECTED
            and frozen_report.get("s1_complete")==0
            and frozen_report.get("production_write_authorized") is False
            and frozen_report.get("catalog_publication_authorized") is False
            and frozen_report.get("phase2_programming_authorized") is False
            and frozen_report.get("phase3_hil_authorized") is False,
            "untrusted or non-frozen five-CFG Phase 1 base")
    original=frozen_report.get("records")
    require(isinstance(original,list) and len(original)==EXPECTED
            and frozen.freeze_digest(original)==FROZEN_SHA,
            "frozen exact ICPN/CFG membership hash mismatch")
    checks=ordering.get("pdf_source_replay")
    require(ordering.get("schema_version")==1
            and ordering.get("p1_original_mcp_exact_icpn_count")==126
            and ordering.get("p1_base_device_count")==12
            and ordering.get("p0_research_icpns_retained_separately")==2437
            and ordering.get("pdf_source_derived_exact_icpn_observations_are_research_only") is True
            and ordering.get("phase1_new_exact_icpn_field_verified_promotions")==0
            and ordering.get("phase1_fully_verified_exact_icpns")==0
            and ordering.get("software_supported_icpns")==0
            and ordering.get("internal_admitted_icpns")==0
            and ordering.get("production_write_authorized") is False
            and ordering.get("catalog_publication_authorized") is False
            and ordering.get("phase2_programming_qualified") is False
            and ordering.get("phase3_hil_qualified") is False
            and isinstance(checks,dict)
            and checks.get("original_pdf_sha256")==pdf.PDF_SHA
            and checks.get("datasheet_revision")=="DS60001513G"
            and checks.get("table_1_1_page")==14
            and checks.get("ordering_page")==16
            and checks.get("all_twelve_table_1_1_memory_rows_verified_in_original") is True
            and checks.get("ordering_code_values_replayed") is True
            and frozen.is_sha(checks.get("original_page14_text_sha256"))
            and frozen.is_sha(checks.get("original_page16_text_sha256")),
            "original publisher PDF source/revision/ordering semantics not replayed")
    rights={}
    exceptions={}
    order_rows=ordering.get("records")
    require(isinstance(order_rows,list) and len(order_rows)==126,
            "source-replayed 126 P1 manufacturer ordering records lost")
    for src in order_rows:
        icpn=src.get("icpn")
        require(type(icpn) is str and icpn not in rights and icpn not in exceptions
                and src.get("source_pdf_original_sha256")==pdf.PDF_SHA
                and src.get("software_supported_claimed") is False
                and src.get("production_write_authorized") is False
                and src.get("phase1_field_verified_promotions")==0,
                "untrusted P1 original ordering evidence")
        if src.get("status")=="MCP_EXACT_CODE_MATCHES_PDF_ORDERING_GRAMMAR":
            require(src.get("is_a_pdf_enumerated_exact_order_code") is False,
                    "PDF grammar cannot masquerade as enumerated order numbers")
            rights[icpn]=src
        elif src.get("status")=="MCP_VAO_SPECIAL_SUFFIX_SEPARATE_SOURCE_REVIEW_REQUIRED":
            require(src.get("special_suffix_observed")=="VAO"
                    and "NO_PPAP_OR_BLANK_PROGRAMMING_ASSUMPTION" in
                        src.get("document_condition_notes",[]),
                    "VAO ordering exception not quarantined")
            exceptions[icpn]=src
        else:
            raise ValueError("unexpected ordering contradiction or uncovered original material")
    require(len(rights)==EXACT and len(exceptions)==EXCEPTIONS,
            "ordinary/VAO original SKU counts drift")

    results=deepcopy(original)
    seen=set()
    promoted=Counter()
    exceptions_preserved=set()
    for row in results:
        icpn=row["icpn"]
        require(icpn not in seen,"duplicate frozen code")
        seen.add(icpn)
        if row["openocd_target_cfg_research_only"]!=CFG:
            require(icpn not in rights and icpn not in exceptions,
                    "other CFG unexpectedly promoted")
            continue
        upstream=rights.get(icpn) or exceptions.get(icpn)
        require(upstream is not None
                and row["base_device"]==upstream["base_device"]
                and row["source_original_mcp_response_sha256_refs"]==
                    upstream["source_original_mcp_response_sha256_refs"]
                and row["openocd_research_priority"]=="P1"
                and row["phase1_identity_status"]=="IDENTIFIED",
                "exact manufacturer identity/DFP/PDF crosswalk conflict")
        if icpn in exceptions:
            exceptions_preserved.add(icpn)
            continue
        observations=upstream["derived_ordering_observations"]
        parsed=pdf.ORDER.fullmatch(icpn)
        require(parsed is not None,"derived original order code not accepted by published grammar")
        prefix,series,group,density,package_code,grade,carrier,kph=parsed.groups()
        expected_family=pdf.table1_family(prefix)
        require(prefix==row["base_device"]
                and observations["package"]==pdf.PACKAGES[package_code]
                and observations["package_code"]==package_code
                and observations["grade_code"]==grade
                and observations["flash_kib"]==expected_family["flash_kib"]
                and observations["ram_kib"]==expected_family["ram_kib"]
                and observations["pin_count"]==expected_family["pin_count"]
                and observations["core_model"]==expected_family["core_model"]
                and observations["temperature_min_c"]==-40
                and observations["temperature_max_c"]==
                    (85 if grade=="U" else 125),
                "official PDF exact-order applicability values differ")
        for name in PROMOTE:
            old=row["fields"][name]
            require(old["state"]=="PARTIAL"
                    and old["source_scope"]=="official_base_device_chart_not_exact_icpn",
                    "cannot overwrite exact VERIFIED/CONFLICT or missing Chart research")
            row["fields"][name]=verified_from_original_sources(
                name,observations,row["source_original_mcp_response_sha256_refs"],
                row["base_device"],icpn)
            promoted[name]+=1
        # Explicitly do NOT promote working_vdd, VDDA, VDDIO or architecture.
        require(row["fields"]["working_vdd"]["state"]=="PARTIAL"
                and row["fields"]["io_supply"]["state"]=="UNKNOWN"
                and row["fields"]["vdda"]["state"]=="UNKNOWN"
                and row["fields"]["core_architecture"]["state"]=="UNKNOWN",
                "cannot infer independent analog/I/O supplies or CPU architecture")
        row["phase1_information_status"]="INFORMATION_INCOMPLETE"
        row["phase1_source_applicability"]={
            "source_pinned_original_pdf_sha256":pdf.PDF_SHA,
            "document_revision":"DS60001513G",
            "manufacturer_ordering_status":upstream["status"],
            "exact_field_verification_scope":list(PROMOTE),
            "information_complete":False,
            "software_supported":False,
        }
    require(len(seen)==EXPECTED
            and set(rights)|set(exceptions)=={
                r["icpn"] for r in results if r["openocd_target_cfg_research_only"]==CFG}
            and len(exceptions_preserved)==EXCEPTIONS
            and promoted==Counter({name:EXACT for name in PROMOTE})
            and frozen.freeze_digest(results)==FROZEN_SHA,
            "freeze or exact manufacturer information promotion drift")
    field_summary={name:{status:0 for status in
                   ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT")}
                   for name in frozen.ST_FIELDS}
    for row in results:
        for field in frozen.ST_FIELDS:
            state=row["fields"][field]["state"]
            require(state in field_summary[field],"unrecognized enhanced field state")
            field_summary[field][state]+=1
        require(row["non_claims"]["production_admission_changed"] is False
                and row["non_claims"]["openocd_software_supported"] is False
                and row["non_claims"]["public_selector_eligibility_changed"] is False
                and row["non_claims"]["programming_profile_authority"] is False
                and row["phase1_information_status"]=="INFORMATION_INCOMPLETE",
                "source-only research inadvertently became production/programming")
    return {
        "schema_version":1,
        "policy":"ADR-0002 bounded Microchip exact-variant Phase 1 field enrichment",
        "manufacturer":"Microchip",
        "phase":"01_IC_INFORMATION",
        "source_2563_identity_freeze_sha256":FROZEN_SHA,
        "source_original_pdf_sha256":pdf.PDF_SHA,
        "source_original_pdf_revision":"DS60001513G",
        "source_original_pdf_ordering_applicability_scope":
            "original_MCP_SKU_identity_plus_manufacturer_PDF_ordering_grammar",
        "source_p1_ordering_original_pdf_replay":checks,
        "frozen_5cfg_exact_icpns":EXPECTED,
        "enriched_cfg":CFG,
        "saml1x_original_mcp_exact_icpns":126,
        "ordinary_ordering_icpns_with_new_field_verifications":EXACT,
        "manufacturer_vao_special_suffix_pending":EXCEPTIONS,
        "verified_fields_promoted_exact_icpn":dict(sorted(promoted.items())),
        "total_new_verified_exact_icpn_fields":sum(promoted.values()),
        "phase1_s1_identified":EXPECTED,
        "phase1_s1_complete":0,
        "field_coverage":field_summary,
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "phase2_programming_authorized":False,
        "phase3_hil_authorized":False,
        "records":results,
    }


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--frozen-field-ledger",required=True,type=Path)
    ap.add_argument("--original-pdf-ordering-crosswalk",required=True,type=Path)
    ap.add_argument("--output",required=True,type=Path)
    ap.add_argument("--verify",action="store_true")
    args=ap.parse_args()
    require("production" not in {s.lower() for s in args.output.resolve().parts},
            "Phase 1 exact variant research cannot write Production")
    report=enrich(read(args.frozen_field_ledger),
                  read(args.original_pdf_ordering_crosswalk))
    if args.verify:
        require(read(args.output)==report,
                "source-locked exact variant field replay not reproducible")
        print("MICROCHIP_SAML1X_122_EXACT_PHASE1_FIELDS_REPLAY_PASS")
    else:
        require(not args.output.exists(),"cannot overwrite existing research output")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,sort_keys=True,
                                          ensure_ascii=False)+"\n",encoding="utf-8")
    print(json.dumps({k:v for k,v in report.items() if k not in ("records","field_coverage","source_p1_ordering_original_pdf_replay")},indent=2,sort_keys=True))


if __name__=="__main__":
    main()

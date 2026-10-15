#!/usr/bin/env python3
"""Microchip P1 126 exact ICPNs: three-source Phase 1 field disagreement audit.

Sources: original MCP exact commercial ICPN+Base, original MicrochipDirect
Base Device chart, SHA-pinned original SAM L10/L11 DS60001513G PDF.
Only research corroboration/conflict, NOT an exact-field VERIFIED promotion.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import re

import microchip_phase1_p1_ordering_crosswalk_v1 as order
import microchip_phase1_p1_saml1x_pdf_custody_v1 as pdf

SCHEMA = 1
EXPECTED = 126
SOURCE_FIELDS = ("package", "pin_count", "flash", "ram",
                 "vdd", "temperature", "core_model")
UNRESOLVED = ("io_supply", "vdda", "core_architecture")
SOURCE_CONSISTENT = "PDF_AND_CHART_CORROBORATED_RESEARCH_ONLY"
CHART_VARIANT_ALLOWED = "CHART_FAMILY_RANGE_INCLUDES_EXACT_VARIANT_RESEARCH_ONLY"
CHART_PACKAGE_SET = "CHART_FAMILY_PACKAGE_SET_INCLUDES_EXACT_VARIANT_RESEARCH_ONLY"
EXACT_MATCH = "CHART_RANGE_EQUALS_ORDERED_GRADE_RESEARCH_ONLY"
SPECIAL = "SPECIAL_VAO_REQUIRES_SEPARATE_SOURCE_REVIEW"
CONFLICT = "MANUFACTURER_CHART_VS_PDF_CONFLICT"
NOT_AVAILABLE = "UNRESOLVED_SOURCE_FIELD"
MAX_BYTES = 16 * 1024 * 1024


def require(value, reason):
    if not value:
        raise ValueError(reason)


def original_bytes(path):
    content = Path(path).read_bytes()
    require(0 < len(content) <= MAX_BYTES, "input evidence out of bounds")
    return json.loads(content), hashlib.sha256(content).hexdigest()


def check_power_page(root):
    """Replay actual publisher PDF power constraints, not guessed VDD aliases."""
    receipt = pdf.audit(root)
    require(receipt.get("status") ==
            "SOURCE_BYTES_CAPTURED_AND_SEMANTICALLY_REPLAYED"
            and receipt.get("original_pdf_sha256") == pdf.PINNED_ORIGINAL_SHA256,
            "publisher original PDF source custody not replayable")
    text = pdf.pdftotext_pages(Path(root)/pdf.FILENAME, 24)
    collapsed = " ".join(text.split())
    mandatory = (
        "SAM L10/L11 Family", "Power Considerations", "Power Supplies",
        "Table 6-1.", "VDDIO", "VDDANA", "VDDCORE",
        "1.62V - 3.63V", "0.9V - 1.2V",
        "The same voltage source must be applied to both VDDIO and VDDANA",
    )
    missing=[name for name in mandatory if name not in collapsed]
    require(not missing and
            re.search(r"DS60001513G\s*-\s*page\s*24", collapsed) is not None,
            "source-locked power supply Table 6-1 no longer matches: "+str(missing))
    require(collapsed.count("1.62V - 3.63V") >= 2,
            "both external supply domains not independently demonstrated")
    return {
        "publisher_original_pdf_sha256": pdf.PINNED_ORIGINAL_SHA256,
        "power_supply_printed_page": 24,
        "original_page24_extracted_text_sha256":
            hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "external_vddio_v": {"min": 1.62, "max": 3.63},
        "external_vddana_v": {"min": 1.62, "max": 3.63},
        "vddio_vddana_same_voltage_source_required": True,
        "internal_core_voltage_v": {"min": 0.9, "max": 1.2},
        "internal_core_voltage_is_an_external_programming_supply": False,
        "external_supply_field_exact_icpn_verified_from_this_page": False,
    }


def check_sources(ledger, crosswalk):
    p1,digest=original_bytes(ledger)
    output,other=original_bytes(crosswalk)
    require(output.get("schema_version")==1
            and output.get("p1_original_mcp_exact_icpn_count")==EXPECTED
            and output.get("p1_base_device_count")==12
            and output.get("p0_research_icpns_retained_separately")==2437
            and output.get("phase1_new_exact_icpn_field_verified_promotions")==0
            and output.get("phase1_fully_verified_exact_icpns")==0
            and output.get("software_supported_icpns")==0
            and output.get("internal_admitted_icpns")==0
            and output.get("production_write_authorized") is False
            and output.get("catalog_publication_authorized") is False
            and output.get("original_p1_information_ledger_sha256")==digest
            and output.get("pdf_source_replay",{}).get("original_pdf_sha256")==
                pdf.PINNED_ORIGINAL_SHA256,
            "crosswalk source or admission gate mismatch")
    require(p1.get("p1_target_only_icpn_count")==EXPECTED
            and p1.get("upstream_original_manufacturer_bytes_replayed") is True
            and p1.get("chart_original_bytes_replayed_by_upstream_chart_builder") is True
            and p1.get("phase1_fully_verified_exact_icpns")==0
            and p1.get("software_supported_icpn_count")==0
            and p1.get("internal_identity_admitted_count")==0
            and p1.get("production_write_authorized") is False,
            "original-MCP evidence ledger invalid")
    audit=p1.get("p1_official_chart_evidence") or {}
    chart_sha=audit.get("official_original_chart_sha256")
    require(isinstance(chart_sha,str)
            and re.fullmatch(r"[a-f0-9]{64}",chart_sha)
            and audit.get("p1_icpns_exact_base_joined_to_chart")==EXPECTED
            and audit.get("p1_icpns_no_chart_base_match")==0
            and audit.get("chart_exact_variant_verified_fields")==0,
            "manufacturer chart Base join or immutable original invalid")
    for field in SOURCE_FIELDS:
        require(p1.get("per_field_coverage",{}).get(field,{}).get("PARTIAL")
                ==EXPECTED,
                "family source chart PARTIAL denominator drift: "+field)
    for field in UNRESOLVED:
        require(p1.get("per_field_coverage",{}).get(field,{}).get("UNKNOWN")
                ==EXPECTED,
                "additional supply/core fields unexpectedly admitted: "+field)
    a=p1.get("records")
    b=output.get("records")
    require(isinstance(a,list) and isinstance(b,list)
            and len(a)==len(b)==EXPECTED,
            "missing original source-linked commercial order rows")
    left={r["icpn"]:r for r in a}
    right={r["icpn"]:r for r in b}
    require(len(left)==len(right)==EXPECTED and set(left)==set(right),
            "exact-ICPN row loss/duplication")
    require(Counter(r["status"] for r in b) == Counter({
            "MCP_EXACT_CODE_MATCHES_PDF_ORDERING_GRAMMAR":122,
            "MCP_VAO_SPECIAL_SUFFIX_SEPARATE_SOURCE_REVIEW_REQUIRED":4,
        }), "original manufacturer cohort ordering classification drift")
    for icpn in left:
        l,r=left[icpn],right[icpn]
        require(l["base_device"] == r["base_device"]
                and l["source_original_mcp_response_sha256_refs"] ==
                    r["source_original_mcp_response_sha256_refs"]
                and r.get("source_pdf_original_sha256")==
                    pdf.PINNED_ORIGINAL_SHA256
                and l.get("internal_identity_admission")=="NOT_ADMITTED"
                and l.get("cfg_candidate_state")==order.P1_STATE
                and l.get("software_supported_claimed") is False
                and r.get("software_supported_claimed") is False
                and r.get("phase1_field_verified_promotions")==0,
                "tampered exact-order original-MCP binding")
        for name in SOURCE_FIELDS:
            evidence=l["fields"].get(name)
            require(evidence is not None
                    and evidence["status"]=="PARTIAL"
                    and evidence["evidence_scope"]==
                        "official_base_device_chart_not_exact_icpn"
                    and evidence["original_response_sha256_refs"]==[chart_sha]
                    and evidence["source_locator"]
                    and evidence["value"] is not None,
                    "Chart family field evidence or source SHA invalid: "+name)
        for name in UNRESOLVED:
            require(l["fields"][name]["status"]=="UNKNOWN"
                    and l["fields"][name]["value"] is None,
                    "unverified Phase 1 field unexpectedly filled")
    return left,right,{
        "original_p1_information_ledger_sha256":digest,
        "original_ordering_crosswalk_sha256":other,
        "original_manufacturer_chart_sha256":chart_sha,
        "original_manufacturer_pdf_sha256":pdf.PINNED_ORIGINAL_SHA256,
    }


def chart_observation(source, part):
    """Never treat a family-wide Chart range/list as exact SKU identity."""
    field=source["fields"][part]
    return {
        "status":field["status"],"value":field["value"],
        "unit":field["unit"],
        "original_chart_row_locator":field["source_locator"],
        "chart_evidence_scope":field["evidence_scope"],
        "chart_original_sha256":field["original_response_sha256_refs"][0],
    }


def adjudicate(field, value, interpreted, special):
    if special:
        return SPECIAL, "VAO automotive extension not in PDF ordering diagram"
    if not interpreted:
        return NOT_AVAILABLE, "source-locked ordering interpretation missing"
    if field=="package":
        # Source chart Package column lists *possible* Base packages.
        # It is NOT the unique commercial order package; exact comes from suffix.
        chart_packages=set(re.findall(r"VQFN|TQFP|SSOP|WLCSP",
                                      str(value).upper()))
        if interpreted["package"] in chart_packages:
            return CHART_PACKAGE_SET, "family list includes exact SKU package"
        return CONFLICT, "ordered package absent from manufacturer family chart"
    if field=="temperature":
        if not isinstance(value,dict):
            return CONFLICT, "invalid chart temperature range"
        lo=value.get("min")
        hi=value.get("max")
        low=interpreted["temperature_min_c"]
        high=interpreted["temperature_max_c"]
        if lo==low and hi==high:
            return EXACT_MATCH, "chart bounds equal exact ordered grade"
        if (isinstance(lo,(int,float)) and isinstance(hi,(int,float))
                and lo<=low and hi>=high):
            return CHART_VARIANT_ALLOWED, (
                "family range contains narrower ordered temperature; "
                "must not equate family max to ordered grade")
        return CONFLICT, "family temperature range excludes ordered grade"
    expected={
        "pin_count":interpreted["pin_count"],
        "flash":interpreted["flash_kib"],
        "ram":interpreted["ram_kib"],
        "vdd":{"min":1.62,"max":3.63},
        "core_model":interpreted["core_model"],
    }[field]
    if field=="core_model":
        text=re.sub(r"[^A-Z0-9]","",str(value).upper())
        good="CORTEXM23" in text and "CORTEXM33" not in text
    elif field=="vdd":
        good=(isinstance(value,dict) and
              value.get("min")==expected["min"] and
              value.get("max")==expected["max"])
    else:
        good=type(value) is int and value==expected
    return (SOURCE_CONSISTENT if good else CONFLICT), (
        "manufacturer chart equals independently documented source"
        if good else f"manufacturer Chart {value!r} differs from PDF {expected!r}"
    )


def run(ledger, crosswalk, pdf_root):
    left,right,inputs=check_sources(ledger,crosswalk)
    power=check_power_page(pdf_root)
    report=[]
    counts=defaultdict(Counter)
    anomalies=[]
    for icpn in sorted(left):
        source,orderrow=left[icpn],right[icpn]
        special=orderrow["status"]==(
            "MCP_VAO_SPECIAL_SUFFIX_SEPARATE_SOURCE_REVIEW_REQUIRED")
        interpretation=orderrow.get("derived_ordering_observations",{})
        require(special or bool(interpretation),
                "ordinary 122 SKU lost PDF ordering semantic extraction")
        fields={}
        for field in SOURCE_FIELDS:
            chart=chart_observation(source,field)
            status,note=adjudicate(field,chart["value"],interpretation,special)
            counts[field][status]+=1
            data={"comparison_state":status,
                  "original_chart_evidence":chart,
                  "source_locator_pdf":(
                    "DS60001513G pp.14 Table 1-1 / p.16 Ordering Information"
                    if field != "vdd" else
                    "DS60001513G p.24 §6.1 Table 6-1 + §6.2"),
                  "source_scope":"research_evidence_corroboration_not_phase1_verified",
                  "notes":note,"phase1_new_verified_promotion":False}
            if status==CONFLICT:
                anomalies.append({"icpn":icpn,"field":field,
                                  "chart_value":chart["value"],
                                  "pdf_order_code_observation":interpretation,
                                  "notes":note})
            fields[field]=data
        # Absent Chart independent supplies must not be silently marked VERIFIED.
        for name in UNRESOLVED:
            fields[name]={
                "comparison_state":NOT_AVAILABLE,
                "original_chart_evidence":None,
                "source_scope":"PDF_family_power_domain_only_or_architecture_unresolved",
                "notes":("Original PDF p.24 separately defines external VDDIO and "
                         "VDDANA, but no exact commercial field attestation"
                         if name in ("io_supply","vdda")
                         else "ARMv8-M Baseline family architecture needs "
                         "separate exact-field qualification"),
                "phase1_new_verified_promotion":False}
            counts[name][NOT_AVAILABLE]+=1
        report.append({
            "icpn":icpn, "base_device":source["base_device"],
            "original_mcp_response_sha256_refs":
                source["source_original_mcp_response_sha256_refs"],
            "original_pdf_sha256":pdf.PINNED_ORIGINAL_SHA256,
            "ordering_source_state":orderrow["status"],
            "fields":fields,
            "phase1_verified_field_promotions":0,
            "openocd_software_supported":False,
            "internal_catalog_admitted":False,
        })
    require(len(report)==EXPECTED and
            all(sum(v.values())==EXPECTED for v in counts.values())
            and all(row["phase1_verified_field_promotions"]==0
                    and row["openocd_software_supported"] is False
                    and row["internal_catalog_admitted"] is False
                    for row in report),
            "Phase 1 field triage silently shrunk/promoted population")
    return {
        "schema_version":SCHEMA,
        "policy":"ADR-0002 Microchip P1 Phase 1 exact-code source-triangulation Research",
        "sources":inputs,
        "power_page_24_source_replay":power,
        "exact_icpn_total":EXPECTED,
        "original_mcp_normal_order_codes":122,
        "original_mcp_vao_special_order_codes":4,
        "manufacturer_base_device_count":12,
        "p0_preserved_separately":2437,
        "per_field_evidence_triage_counts":{
            name:{state:count for state,count in sorted(hist.items())}
            for name,hist in sorted(counts.items())},
        "chart_pdf_conflict_count":len(anomalies),
        "chart_pdf_conflicts":anomalies,
        "phase1_new_exact_icpn_fields_verified":0,
        "phase1_fully_verified_exact_icpns":0,
        "software_supported_icpns":0,
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "phase2_programming_authorized":False,
        "phase3_hil_qualified":False,
        "records":report,
    }


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--p1-ledger",type=Path,required=True)
    p.add_argument("--ordering-crosswalk",type=Path,required=True)
    p.add_argument("--original-pdf-root",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--verify",action="store_true")
    args=p.parse_args()
    require("production" not in {part.lower() for part in
            args.output.resolve().parts},"no writes to Production")
    result=run(args.p1_ledger,args.ordering_crosswalk,
               args.original_pdf_root)
    if args.verify:
        require(json.loads(args.output.read_text(encoding="utf-8"))==result,
                "source triage report changed under replay")
        print("MICROCHIP P1 SOURCE TRIANGULATION REPLAY PASS")
    else:
        require(not args.output.exists(),"cannot overwrite research evidence")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as fd:
            json.dump(result,fd,indent=2,sort_keys=True)
            fd.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k!="records"},
                     indent=2,sort_keys=True))


if __name__=="__main__":
    main()

#!/usr/bin/env python3
"""Microchip SAM L10/L11 P1 126-ICPN manufacturer-ordering applicability audit.

Cross-joins only original-MCP exact part numbers already in the 126-row
Research P1 Phase 1 ledger with source-pinned DS60001513G pp.14/16.
No Phase 1 VERIFIED promotion, Catalog admission, or OpenOCD qualification.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import re

import microchip_phase1_p1_saml1x_pdf_custody_v1 as original

COUNT = 126
CFG = "tcl/target/atsaml1x.cfg"
PDF_SHA = original.PINNED_ORIGINAL_SHA256
ORDER = re.compile(
    r"\A(ATSAML(10|11)(D|E)(14|15|16)A)-([AMUY])([UFZ])(T?)(KPH)?\Z"
)
PACKAGES = {"A":"TQFP", "M":"VQFN", "U":"WLCSP", "Y":"SSOP"}
GRAMMAR_FIELDS = ("package", "pin_count", "flash", "ram",
                  "temperature", "core_model")
MEMORY = {
    "14": 16, "15": 32, "16": 64,
}
MAX_LEDGER = 12 * 1024 * 1024


def require(ok, message):
    if not ok:
        raise ValueError(message)


def table1_family(base):
    """Only documented Table 1-1, NOT an inferred commercial SKU."""
    require(re.fullmatch(r"ATSAML(?:10|11)[DE](?:14|15|16)A", base) is not None,
            "manufacturer Base Device outside twelve source-locked candidates")
    series = base[6:8]
    group = base[8]
    density = base[9:11]
    flash = MEMORY[density]
    ram = 16 if density == "16" else (8 if series == "11" or density == "15" else 4)
    return {"flash_kib":flash, "data_flash_kib":2,
            "ram_kib":ram, "pin_count":24 if group=="D" else 32,
            "core_model":"Arm Cortex-M23", "core_architecture":"ARMv8-M Baseline"}


def replay_pdf_tables(root):
    manifest=original.audit(root)
    require(manifest["status"] ==
            "SOURCE_BYTES_CAPTURED_AND_SEMANTICALLY_REPLAYED"
            and manifest["original_pdf_sha256"] == PDF_SHA,
            "official PDF not independently source-replayed")
    path=Path(root)/original.FILENAME
    raw14=original.pdftotext_pages(path,14)
    raw16=original.pdftotext_pages(path,16)
    a=" ".join(raw14.split())
    b=" ".join(raw16.split())
    # Check actual Table 1-1 row values, not just twelve device-name tokens.
    for base in original.BASES:
        part="AT"+base+"A"
        values=table1_family(part)
        pattern=(r"\b"+re.escape(base)+r"\s+"+
                 str(values["flash_kib"])+r"\s*\+\s*2\s+"+
                 str(values["ram_kib"])+r"\b")
        require(re.search(pattern,a) is not None,
                f"Table 1-1 memory row not replayable: {base}")
    # Independently check the page 16 conditions needed for interpreting
    # order codes. A found filename/page heading is not sufficient.
    codes = (
        r"\bD\s*=\s*24\s+Pins\b", r"\bE\s*=\s*32\s+Pins\b",
        r"\b14\s*=\s*16\s+KB\b", r"\b15\s*=\s*32\s+KB\b",
        r"\b16\s*=\s*64\s+KB\b",
        r"\bA\s*=\s*TQFP\b", r"\bM\s*=\s*VQFN\b",
        r"\bY\s*=\s*SSOP\b", r"\bU\s*=\s*WLCSP\b",
        r"\bKPH\b", r"\bAEC-Q100\b",
    )
    missing=[p for p in codes if re.search(p,b) is None]
    require(not missing, f"official PDF ordering grammar not replayable: {missing}")
    return {"original_pdf_sha256":PDF_SHA,
            "datasheet_revision":"DS60001513G",
            "source_original_pdf_url":original.URL,
            "table_1_1_page":14, "ordering_page":16,
            "original_page14_text_sha256":
                hashlib.sha256(raw14.encode()).hexdigest(),
            "original_page16_text_sha256":
                hashlib.sha256(raw16.encode()).hexdigest(),
            "all_twelve_table_1_1_memory_rows_verified_in_original":True,
            "ordering_code_values_replayed":True,
            "exact_icpn_ordering_rows_in_pdf":False}


def read_source(path):
    raw=Path(path).read_bytes()
    require(0<len(raw)<=MAX_LEDGER, "invalid P1 input ledger size")
    data=json.loads(raw)
    require(data.get("p1_target_only_icpn_count")==COUNT
            and data.get("p1_unique_original_mcp_base_device_count")==12
            and data.get("source_replayed_p0_icpns_retained_separately")==2437
            and data.get("p1_openocd_target_cfg_research_only")==CFG
            and data.get("upstream_original_manufacturer_bytes_replayed") is True
            and data.get("software_supported_icpn_count")==0
            and data.get("internal_identity_admitted_count")==0
            and data.get("production_write_authorized") is False
            and data.get("catalog_publication_authorized") is False
            and data.get("phase1_fully_verified_exact_icpns")==0,
            "unqualified or non-original-source P1 input")
    rows=data.get("records")
    require(isinstance(rows,list) and len(rows)==COUNT,
            "P1 commercial ICPN input cohort not 126")
    seen=set()
    bases=set()
    for row in rows:
        icpn=row.get("icpn")
        base=row.get("base_device")
        require(isinstance(icpn,str) and icpn==icpn.upper()
                and icpn not in seen
                and isinstance(base,str) and base==base.upper()
                and row.get("dfp_name")==base
                and row.get("openocd_target_cfg_research_only")==CFG
                and row.get("cfg_candidate_state")=="P1_TARGET_ONLY_CFG_CANDIDATE"
                and row.get("internal_identity_admission")=="NOT_ADMITTED"
                and row.get("software_supported_claimed") is False
                and row.get("production_write_authorized") is False,
                "invalid/duplicate P1 manufacturer MCP identity")
        hashes=row.get("source_original_mcp_response_sha256_refs")
        require(isinstance(hashes,list) and hashes and
                all(isinstance(h,str) and re.fullmatch(r"[0-9a-f]{64}",h)
                    for h in hashes),
                "missing original MCP response source SHA")
        fields=row.get("fields")
        require(isinstance(fields,dict) and all(fields.get(k,{}).get("status") ==
            "VERIFIED" for k in ("manufacturer","icpn","base_device"))
            and all(fields.get(k,{}).get("status") in ("PARTIAL","UNKNOWN")
                    for k in ("package","pin_count","flash","ram",
                              "temperature","core_model")),
                "P1 Phase 1 original identity/status contract changed")
        seen.add(icpn)
        bases.add(base)
    require(len(bases)==12, "P1 original manufacturer Base set changed")
    return data,hashlib.sha256(raw).hexdigest()


def interpret_one(row):
    """Interpret only manufacturer-existing commercial ICPN, not discover SKUs."""
    icpn=row["icpn"]
    base=row["base_device"]
    parsed=ORDER.fullmatch(icpn)
    result={
        "icpn":icpn,"base_device":base,
        "source_original_mcp_response_sha256_refs":
            row["source_original_mcp_response_sha256_refs"],
        "source_pdf_original_sha256":PDF_SHA,
        "provenance":[
            "original manufacturer MCP exact commercial partNumber/basePartNumber",
            "DS60001513G printed p.14 Table 1-1 family configuration",
            "DS60001513G printed p.16 ordering grammar and restrictions"],
        "is_a_pdf_enumerated_exact_order_code":False,
        "phase1_field_verified_promotions":0,
        "software_supported_claimed":False,
        "production_write_authorized":False,
        "status":"UNPARSED_ORIGINAL_MANUFACTURER_ORDER_CODE",
        "document_condition_notes":[],
        "derived_ordering_observations":{},
    }
    if parsed is None:
        return result
    prefix,series,group,density,package_code,grade,carrier,kph=parsed.groups()
    if base!=prefix:
        result["status"]="BASE_PREFIX_IDENTITY_CONFLICT"
        return result
    package=PACKAGES[package_code]
    restrictions=[]
    if group=="D" and package not in ("VQFN","SSOP"):
        restrictions.append("D_24_PIN_PACKAGE_NOT_IN_P14_TABLE")
    if group=="E" and package not in ("VQFN","TQFP","WLCSP"):
        restrictions.append("E_32_PIN_PACKAGE_NOT_IN_P14_TABLE")
    if grade=="Z" and package not in ("VQFN","TQFP"):
        restrictions.append("AEC_Q100_ONLY_TQFP_VQFN")
    if kph and (series!="11" or package not in ("VQFN","TQFP")):
        restrictions.append("KPH_ONLY_L11_TQFP_VQFN")
    if restrictions:
        result["status"]="ORDERING_PDF_RESTRICTION_CONFLICT"
        result["document_condition_notes"]=restrictions
        return result
    family=table1_family(base)
    notes=[]
    if package=="WLCSP":
        notes.append("WLCSP_FACTORY_PROGRAMMED_BOOTLOADER; manufacturer sales clarification required")
    if kph:
        notes.append("OPTIONAL_KPH_FACTORY_KEY_PROVISIONED; requires independent security review")
    if grade=="Z":
        notes.append("AEC_Q100_GRADE1_VQFN_TQFP_RESTRICTED")
    result["status"]="MCP_EXACT_CODE_MATCHES_PDF_ORDERING_GRAMMAR"
    result["document_condition_notes"]=notes
    result["derived_ordering_observations"]={
        **family,"package":package,"package_code":package_code,
        "temperature_min_c":-40,
        "temperature_max_c":85 if grade=="U" else 125,
        "grade_code":grade,
        "carrier":"tape_and_reel" if carrier=="T" else "tray_or_tube",
        "key_provisioning_suffix":bool(kph),
    }
    return result


def build(ledger,pdf_root):
    upstream,source_sha=read_source(ledger)
    proof=replay_pdf_tables(pdf_root)
    out=[interpret_one(r) for r in upstream["records"]]
    out.sort(key=lambda r:r["icpn"])
    counts=Counter(r["status"] for r in out)
    restrictions=Counter(note for r in out for note in
                         r["document_condition_notes"])
    require(len(out)==COUNT and sum(counts.values())==COUNT,
            "P1 source cohort silently changed")
    require(all(r["phase1_field_verified_promotions"]==0
                and r["software_supported_claimed"] is False
                and r["production_write_authorized"] is False for r in out),
            "ordering interpretations must not promote support")
    return {
        "schema_version":1,
        "policy":"ADR-0002 Phase 1 Research-only manufacturer ordering applicability",
        "p1_original_mcp_exact_icpn_count":COUNT,
        "p1_base_device_count":12,
        "p0_research_icpns_retained_separately":2437,
        "original_p1_information_ledger_sha256":source_sha,
        "pdf_source_replay":proof,
        "status_counts":dict(sorted(counts.items())),
        "document_restriction_or_feature_counts":dict(sorted(restrictions.items())),
        "pdf_source_derived_exact_icpn_observations_are_research_only":True,
        "phase1_new_exact_icpn_field_verified_promotions":0,
        "phase1_fully_verified_exact_icpns":0,
        "software_supported_icpns":0,
        "internal_admitted_icpns":0,
        "production_write_authorized":False,
        "catalog_publication_authorized":False,
        "phase2_programming_qualified":False,
        "phase3_hil_qualified":False,
        "records":out,
    }


def main():
    cli=argparse.ArgumentParser(description=__doc__)
    cli.add_argument("--p1-ledger",type=Path,required=True)
    cli.add_argument("--original-pdf-root",type=Path,required=True)
    cli.add_argument("--output",type=Path,required=True)
    cli.add_argument("--verify",action="store_true")
    args=cli.parse_args()
    require("production" not in {x.casefold() for x in args.output.resolve().parts},
            "research crosswalk cannot overwrite Production")
    result=build(args.p1_ledger,args.original_pdf_root)
    if args.verify:
        require(json.loads(args.output.read_text(encoding="utf-8"))==result,
                "source-bound P1 ordering crosswalk changed on replay")
        print("MICROCHIP P1 EXACT ORDERING CROSSWALK REPLAY PASS")
    else:
        require(not args.output.exists(), "no silent overwrite of research evidence")
        args.output.parent.mkdir(parents=True,exist_ok=True)
        with args.output.open("x",encoding="utf-8") as fd:
            json.dump(result,fd,sort_keys=True,indent=2)
            fd.write("\n")
    print(json.dumps({k:v for k,v in result.items() if k!="records"},
                     sort_keys=True,indent=2))


if __name__=="__main__":
    main()

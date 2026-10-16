#!/usr/bin/env python3
"""Derive source-verified Microchip SAM L10/L11 122 exact canonical admission CSV.

Never invent commercial codes from an ordering grammar. Inputs must be real
original manufacturer MCP exact-order records crosschecked with pinned PDF.
Target CFG is a *research lead*, so new Product entries carry no executable
backend route (mapping_status=no_mapping). This program DOES NOT write the
Production manifest, create Phase2 qualification or authorize a job.
"""
from __future__ import annotations
import argparse, csv, hashlib, io, json
from pathlib import Path
import microchip_phase1_p1_ordering_crosswalk_v1 as original

CSV_FIELDS=(
    "manufacturer","icpn","family","series","base_device","package",
    "pin_count","flash_size","temperature_grade","option_suffix",
    "cmsis_device_name","existing_identifier","existing_identifier_kind",
    "mapping_status","openocd_target_config","source_type",
    "source_reference","source_authority","verification_status",
)
EXPECTED=122
FAMILY="SAML1X"
DOC_URL=original.original.URL
ORIGINAL_SHA=original.PDF_SHA


def require(ok, message):
    if not ok:
        raise ValueError(message)


def generate(crosswalk:dict) -> tuple[list[dict[str,str]],str]:
    proof=crosswalk.get("pdf_source_replay")
    require(crosswalk.get("schema_version")==1
            and crosswalk.get("p1_original_mcp_exact_icpn_count")==126
            and crosswalk.get("p1_base_device_count")==12
            and crosswalk.get("p0_research_icpns_retained_separately")==2437
            and crosswalk.get("status_counts")=={
               "MCP_EXACT_CODE_MATCHES_PDF_ORDERING_GRAMMAR":122,
               "MCP_VAO_SPECIAL_SUFFIX_SEPARATE_SOURCE_REVIEW_REQUIRED":4}
            and crosswalk.get("phase1_new_exact_icpn_field_verified_promotions")==0
            and crosswalk.get("phase1_fully_verified_exact_icpns")==0
            and crosswalk.get("software_supported_icpns")==0
            and crosswalk.get("internal_admitted_icpns")==0
            and crosswalk.get("catalog_publication_authorized") is False
            and crosswalk.get("production_write_authorized") is False
            and isinstance(proof,dict)
            and proof.get("original_pdf_sha256")==ORIGINAL_SHA
            and proof.get("datasheet_revision")=="DS60001513G"
            and proof.get("table_1_1_page")==14
            and proof.get("ordering_page")==16
            and proof.get("all_twelve_table_1_1_memory_rows_verified_in_original") is True
            and proof.get("ordering_code_values_replayed") is True,
            "original manufacturer ordering evidence not qualified")
    rows=crosswalk.get("records")
    require(isinstance(rows,list) and len(rows)==126,"missing exact source materials")
    canonical=[]
    ids=set()
    exceptions=0
    for x in rows:
        icpn=x.get("icpn")
        base=x.get("base_device")
        state=x.get("status")
        require(isinstance(icpn,str) and isinstance(base,str)
                and icpn not in ids,"duplicate/empty source commercial number")
        ids.add(icpn)
        require(x.get("source_pdf_original_sha256")==ORIGINAL_SHA
                and x.get("is_a_pdf_enumerated_exact_order_code") is False
                and x.get("phase1_field_verified_promotions")==0
                and x.get("software_supported_claimed") is False
                and x.get("production_write_authorized") is False,
                "research crosswalk claimed unsupported authority")
        if state=="MCP_VAO_SPECIAL_SUFFIX_SEPARATE_SOURCE_REVIEW_REQUIRED":
            require(icpn.endswith("VAO")
                    and x.get("special_suffix_observed")=="VAO",
                    "exception review state inconsistent")
            exceptions+=1
            continue
        require(state=="MCP_EXACT_CODE_MATCHES_PDF_ORDERING_GRAMMAR",
                "unreviewed or contradictory exact source code")
        m=original.ORDER.fullmatch(icpn)
        require(m is not None and m.group(1)==base,
                "not a real ordinary manufacturer order code")
        fam,series,group,density,package_code,grade,carrier,kph=m.groups()
        data=x.get("derived_ordering_observations")
        require(isinstance(data,dict)
                and data.get("package")==original.PACKAGES[package_code]
                and data.get("pin_count")==(24 if group=="D" else 32)
                and data.get("flash_kib")==original.MEMORY[density]
                and data.get("ram_kib")==original.table1_family(base)["ram_kib"]
                and data.get("temperature_min_c")==-40
                and data.get("temperature_max_c")==(85 if grade=="U" else 125)
                and data.get("core_model")=="Arm Cortex-M23"
                and data.get("grade_code")==grade
                and data.get("key_provisioning_suffix")==bool(kph),
                "official PDF table, variant grade, package or identity mismatch")
        hashes=x.get("source_original_mcp_response_sha256_refs")
        require(isinstance(hashes,list) and hashes
                and len(set(hashes))==len(hashes)
                and all(isinstance(h,str) and len(h)==64
                        and set(h)<=set("0123456789abcdef") for h in hashes),
                "no original manufacturer exact SKU SHA evidence")
        # Retain one canonical manufacturer exact part number per line.
        # No route is supplied: "tcl/target/atsaml1x.cfg" remains a
        # Research-only lead, NOT an executable target configuration.
        canonical.append({
            "manufacturer":"Microchip",
            "icpn":icpn,
            "family":FAMILY,
            "series":"SAML"+series,
            "base_device":base,
            "package":data["package"],
            "pin_count":str(data["pin_count"]),
            "flash_size":f'{data["flash_kib"]} KB',
            "temperature_grade":f'{data["temperature_min_c"]}..{data["temperature_max_c"]} C',
            "option_suffix":kph or "",
            "cmsis_device_name":"",
            "existing_identifier":"",
            "existing_identifier_kind":"",
            "mapping_status":"no_mapping",
            "openocd_target_config":"",
            "source_type":"microchip_official_mcp_exact_material_plus_ds60001513g",
            "source_reference":(
                f'Microchip MCP exact partNumber={icpn} basePartNumber={base} '
                f'original_response_sha256={"|".join(sorted(hashes))}; '
                f'{DOC_URL} revision=DS60001513G original_pdf_sha256={ORIGINAL_SHA} '
                'printed p.14 Table 1-1 + p.16 Ordering Information'),
            "source_authority":"Microchip Technology official",
            "verification_status":"verified_microchip_mcp_exact_ordering_and_pdf_applicability",
        })
    canonical.sort(key=lambda z:z["icpn"])
    require(len(canonical)==EXPECTED and exceptions==4 and
            len({x["icpn"] for x in canonical})==EXPECTED,
            "frozen 122 exact ordered manufacturer rows drift")
    out=io.StringIO(newline="")
    writer=csv.DictWriter(out,fieldnames=CSV_FIELDS,lineterminator="\n")
    writer.writeheader()
    writer.writerows(canonical)
    return canonical,out.getvalue()


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--ordering-crosswalk",type=Path,required=True)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--verify",action="store_true")
    parser.add_argument("--bootstrap-csv-in-ci-log",action="store_true")
    args=parser.parse_args()
    crosswalk=json.loads(args.ordering_crosswalk.read_text("utf-8"))
    _,csv_text=generate(crosswalk)
    raw=csv_text.encode("utf-8")
    digest=hashlib.sha256(raw).hexdigest()
    blob=hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()
    identity_digest=hashlib.sha256(
        ("".join(f'{row["icpn"]}\n' for row in
                  sorted(csv.DictReader(io.StringIO(csv_text)),key=lambda x:x["icpn"])))
        .encode("utf-8")).hexdigest()
    print("MICROCHIP_SAML1X_122_CANONICAL_SHA256",digest)
    print("MICROCHIP_SAML1X_122_CANONICAL_GIT_BLOB",blob)
    print("MICROCHIP_SAML1X_122_IDENTITIES_SHA256",identity_digest)
    if args.output:
        require("production" not in {p.casefold() for p in args.output.resolve().parts},
                "generator cannot directly publish Production")
        if args.verify:
            require(args.output.read_bytes()==raw,
                    "published 122 row CSV does not match manufacturer replay")
        else:
            require(not args.output.exists(),"refuse unapproved source overwrite")
            args.output.parent.mkdir(parents=True,exist_ok=True)
            args.output.write_bytes(raw)
    if args.bootstrap_csv_in_ci_log:
        # One-time reproducible publication preparation: publish ALL original
        # source-derived canonical CSV lines in GitHub CI logs for exact review.
        for line in csv_text.splitlines():
            print("CANONICAL_122_ROW|"+line)


if __name__=="__main__":
    main()

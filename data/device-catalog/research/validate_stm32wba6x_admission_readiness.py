#!/usr/bin/env python3
"""Validate STM32WBA6X catalog admission readiness."""
from __future__ import annotations
import csv,hashlib,io,json
from pathlib import Path
from stm32wba6x_admission_readiness import EXPECTED_EXACT_COUNT,EXPECTED_EXACT_SHA256,EXPECTED_MAPPING_COUNTS,EXPECTED_PRODUCTION_COUNT,EXPECTED_PRODUCTION_FAMILIES,EXPECTED_ROUTE_KIND_COUNTS,FAMILY,PRODUCTION,PRODUCTION_FIELDS,build_readiness,build_rows,csv_text

HERE=Path(__file__).resolve().parent
CSV_PATH=HERE/"stm32wba6x-commercial-icpn.csv"
READINESS_PATH=HERE/"stm32wba6x-admission-readiness.json"
AUTHORITY_PATH=HERE/"stm32wba6x-metadata-authority.json"

def req(ok:bool,msg:str)->None:
    if not ok: raise SystemExit(msg)

def main()->int:
    rows=build_rows(); expected_csv=csv_text(rows); expected_readiness=build_readiness(rows,expected_csv)
    req(CSV_PATH.read_text(encoding="utf-8")==expected_csv,"checked-in canonical CSV differs from renderer")
    checked=json.loads(READINESS_PATH.read_text(encoding="utf-8")); req(checked==expected_readiness,"checked-in readiness differs from renderer")
    parsed=list(csv.DictReader(io.StringIO(expected_csv)))
    req(len(parsed)==EXPECTED_EXACT_COUNT==39,"canonical row count drifted")
    req(tuple(parsed[0].keys())==PRODUCTION_FIELDS if parsed else False,"canonical schema drifted")
    icpns=[r["icpn"] for r in parsed]; req(icpns==sorted(set(icpns)),"canonical ICPNs not sorted unique")
    req(hashlib.sha256(("\n".join(icpns)+"\n").encode()).hexdigest()==EXPECTED_EXACT_SHA256,"exact-set digest drifted")
    req(all(r["existing_identifier_kind"]=="ordering_pattern" for r in parsed),"non-ordering route entered canonical")
    req(all(r["mapping_status"]=="deterministic_ordering_pattern" for r in parsed),"mapping status drifted")
    req(all(r["cmsis_device_name"]=="" for r in parsed),"CMSIS bridge unexpectedly used")
    req(all(r["openocd_target_config"]=="tcl/target/stm32wba6x.cfg" for r in parsed),"target config drifted")
    authority=json.loads(AUTHORITY_PATH.read_text(encoding="utf-8"))
    req(authority.get("authority_id")=="stm32wba6x-ordering-information-v1","authority id drifted")
    docs=authority.get("documents"); req(isinstance(docs,list) and len(docs)==1 and (docs[0].get("document_id"),docs[0].get("revision"))==("DS14736","Rev 3"),"authority document drifted")
    req(all(v is False for v in (authority.get("claims") or {}).values()),"authority claim escaped")
    req(checked.get("catalog_admission_ready") is True,"catalog admission readiness not opened")
    req(checked.get("next_gate")=="stm32wba6x-production-publication-gate","publication gate drifted")
    req(checked.get("identity_ready_count")==39 and checked.get("lifecycle_ready_count")==39 and checked.get("metadata_ready_count")==39 and checked.get("route_ready_count")==39,"readiness counts drifted")
    req(checked.get("manual_review_count")==0 and checked.get("metadata_exception_count")==0 and checked.get("route_bridge_count")==0,"readiness exceptions opened")
    req(checked.get("route_assignment_kind_counts")=={"ordering_pattern":39},"route-kind counts drifted")
    req(checked.get("mapping_status_counts")=={"deterministic_ordering_pattern":39},"mapping counts drifted")
    req(checked.get("excluded_non_active_part_numbers")==["STM32WBA63CGU6TR","STM32WBA65MGF6"],"lifecycle exclusions drifted")
    req(checked.get("canonical_candidate_sha256")=="87e5bde7efc3fd3aee7397a80e9f4f972eb5ff42370b8d54cf1a333b3252004d","canonical SHA drifted")
    req(checked.get("canonical_candidate_git_blob_sha")=="0ab09918b2d845c0f21f10c5edb4a150d0c8c4f5","canonical blob drifted")
    req(all(v is False for v in (checked.get("claims") or {}).values()),"readiness claim escaped")
    prod=json.loads(PRODUCTION.read_text(encoding="utf-8")); sources=prod.get("sources")
    req(isinstance(sources,list) and sum(int(s.get("row_count",0)) for s in sources)==EXPECTED_PRODUCTION_COUNT and len(sources)==EXPECTED_PRODUCTION_FAMILIES,"Production boundary drifted")
    req(all(s.get("family")!=FAMILY for s in sources),"STM32WBA6X leaked into Production")
    print("STM32WBA6X admission readiness validation: PASS")
    print("exact=39 metadata=39 route=39 direct=39 bridge=0 manual=0")
    print("Production=2644/22 next=stm32wba6x-production-publication-gate")
    return 0
if __name__=="__main__":raise SystemExit(main())

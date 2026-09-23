#!/usr/bin/env python3
"""Qualify STM32WBA6X exact-ICPN catalog admission readiness."""
from __future__ import annotations
import argparse,csv,hashlib,io,json
from collections import Counter
from pathlib import Path
from typing import Any

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
SOURCE=HERE/"openocd-parts-canonical.csv"
RECONCILIATION=HERE/"stm32wba6x-commercial-scope-reconciliation.json"
DISCOVERY=HERE/"evidence/stm32wba6x-exact-icpn-live-2026-09-23/discovery-summary.json"
EXACT=HERE/"evidence/stm32wba6x-exact-icpn-live-2026-09-23/exact-icpns.json"
AUTHORITY=HERE/"stm32wba6x-metadata-authority.json"
PRODUCTION=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"

MANUFACTURER="STMicroelectronics"
FAMILY="STM32WBA6X"
SERIES="STM32WBA6X"
TARGET_CONFIG="tcl/target/stm32wba6x.cfg"
EXPECTED_EXACT_COUNT=39
EXPECTED_EXACT_SHA256="b5acc2f981635fa0464456fae74365407492d3345ded9b7c9edf885ffdfeddac"
EXPECTED_EXCLUDED=["STM32WBA63CGU6TR","STM32WBA65MGF6"]
EXPECTED_BASE_COUNT=18
EXPECTED_SOURCE_ROWS=19
EXPECTED_RECONCILED_ROWS=18
EXPECTED_ROUTE_KIND_COUNTS={"ordering_pattern":39}
EXPECTED_MAPPING_COUNTS={"deterministic_ordering_pattern":39}
EXPECTED_PRODUCTION_COUNT=2644
EXPECTED_PRODUCTION_FAMILIES=22
EXPECTED_SOURCE_SHA256="43ca9f9bbd2826aef8cd147a251263255d957dd1bcac7da653905d3bf980b6a3"
EXPECTED_RECONCILIATION_BLOB="e110a230f5759256946b937ac8fcf8e46aa3e643"
EXCLUDED={("STM32WBA6MOIHx","ordering_pattern")}
PRODUCTION_FIELDS=("manufacturer","icpn","family","series","base_device","package","pin_count","flash_size","temperature_grade","option_suffix","cmsis_device_name","existing_identifier","existing_identifier_kind","mapping_status","openocd_target_config","source_type","source_reference","source_authority","verification_status")

def req(ok:bool,msg:str)->None:
    if not ok: raise RuntimeError(msg)
def load(path:Path)->dict[str,Any]:
    v=json.loads(path.read_text(encoding="utf-8")); req(isinstance(v,dict),f"{path.name}: expected object"); return v
def sha256_bytes(data:bytes)->str:return hashlib.sha256(data).hexdigest()
def sha256_text(text:str)->str:return hashlib.sha256(text.encode()).hexdigest()
def git_blob_bytes(data:bytes)->str:return hashlib.sha1(f"blob {len(data)}\0".encode()+data,usedforsecurity=False).hexdigest()
def git_blob_text(text:str)->str:return git_blob_bytes(text.encode())

def pattern_matches(icpn:str,pattern:str)->bool:
    value=icpn[:-2] if icpn.endswith("TR") else icpn
    return len(value)==len(pattern) and all(pc=="x" or pc==vc for vc,pc in zip(value,pattern))

def route_rows()->list[dict[str,str]]:
    req(sha256_bytes(SOURCE.read_bytes())==EXPECTED_SOURCE_SHA256,"source digest drifted")
    req(git_blob_bytes(RECONCILIATION.read_bytes())==EXPECTED_RECONCILIATION_BLOB,"reconciliation blob drifted")
    rec=load(RECONCILIATION)
    req(rec.get("evidence_accessibility_ready") is True and rec.get("catalog_admission_ready") is False,"reconciliation readiness drifted")
    with SOURCE.open(newline="",encoding="utf-8") as h:
        all_rows=[r for r in csv.DictReader(h) if r.get("vendor")==MANUFACTURER and r.get("plasma_series")==SERIES]
    req(len(all_rows)==EXPECTED_SOURCE_ROWS,"source row count drifted")
    rows=[r for r in all_rows if (r.get("part_number"),r.get("identifier_kind")) not in EXCLUDED]
    req(len(rows)==EXPECTED_RECONCILED_ROWS,"reconciled route row count drifted")
    req(all(r.get("identifier_kind")=="ordering_pattern" for r in rows),"non-ordering route row entered surface")
    req(all(r.get("target_config")==TARGET_CONFIG for r in rows),"target config drifted")
    return rows

def validate_inputs()->tuple[list[str],dict[str,str],list[dict[str,str]],dict[str,Any]]:
    discovery,exact_obj,authority,production=map(load,(DISCOVERY,EXACT,AUTHORITY,PRODUCTION))
    req(discovery.get("discovery_id")=="stm32wba6x-bounded-exact-icpn-discovery-v1","discovery id drifted")
    req(discovery.get("status")=="discovered" and discovery.get("bounded_exact_discovery_complete") is True,"discovery incomplete")
    req(discovery.get("base_device_count")==EXPECTED_BASE_COUNT and discovery.get("successful_targets")==EXPECTED_BASE_COUNT,"discovery coverage drifted")
    req(discovery.get("manual_review_targets")==0,"manual review opened")
    req(discovery.get("active_exact_icpn_count")==EXPECTED_EXACT_COUNT,"exact count drifted")
    req(discovery.get("active_exact_icpn_set_sha256")==EXPECTED_EXACT_SHA256,"exact digest drifted")
    req(discovery.get("excluded_non_active_part_numbers")==EXPECTED_EXCLUDED,"lifecycle exclusions drifted")
    req(discovery.get("next_gate")=="stm32wba6x-bounded-exact-icpn-admission-readiness-gate","readiness gate drifted")
    exact=exact_obj.get("exact_icpns")
    req(isinstance(exact,list) and len(exact)==EXPECTED_EXACT_COUNT,"exact snapshot malformed")
    req(exact_obj.get("exact_icpn_set_sha256")==EXPECTED_EXACT_SHA256,"exact snapshot digest drifted")
    req(sha256_text("\n".join(exact)+"\n")==EXPECTED_EXACT_SHA256,"exact digest recompute failed")
    results=discovery.get("results"); req(isinstance(results,list) and len(results)==EXPECTED_BASE_COUNT,"result surface drifted")
    owners={}
    for item in results:
        base=item.get("base_device"); req(isinstance(base,str),"Base Device missing")
        req(item.get("acquisition_status")=="success" and item.get("manual_intervention_required") is False,f"{base}: unresolved discovery")
        for icpn in item.get("active_exact_icpns") or []:
            req(icpn.startswith(base),f"{base}: foreign exact ICPN"); req(icpn not in owners,f"{icpn}: duplicate exact identity"); owners[icpn]=base
    req(sorted(owners)==exact,"per-Base exact set differs from snapshot")
    req(authority.get("authority_id")=="stm32wba6x-ordering-information-v1","authority id drifted")
    docs=authority.get("documents"); req(isinstance(docs,list) and len(docs)==1,"authority document set drifted")
    req((docs[0].get("document_id"),docs[0].get("revision"))==("DS14736","Rev 3"),"authority revision drifted")
    req(all(v is False for v in (authority.get("claims") or {}).values()),"authority claim escaped")
    sources=production.get("sources"); req(isinstance(sources,list),"Production sources missing")
    req(sum(int(x.get("row_count",0)) for x in sources)==EXPECTED_PRODUCTION_COUNT and len(sources)==EXPECTED_PRODUCTION_FAMILIES,"Production boundary drifted")
    req(all(x.get("family")!=FAMILY for x in sources),"STM32WBA6X already in Production")
    return exact,owners,route_rows(),authority

def resolve_route(icpn:str,rows:list[dict[str,str]])->dict[str,str]:
    matches=[r for r in rows if pattern_matches(icpn,r["part_number"])]
    req(len(matches)==1,f"{icpn}: expected one deterministic route, got {len(matches)}")
    row=matches[0]
    return {"series":row["subfamily"],"cmsis_device_name":"","existing_identifier":row["part_number"],"existing_identifier_kind":"ordering_pattern","mapping_status":"deterministic_ordering_pattern","openocd_target_config":row["target_config"]}

def decode_metadata(icpn:str,base:str,subfamily:str,authority:dict[str,Any])->dict[str,str]:
    req(base.startswith(subfamily) and len(base)==len(subfamily)+2,f"{icpn}: unexpected Base Device form")
    pin_code,flash_code=base[-2],base[-1]
    rem=icpn[len(base):]; req(len(rem)>=2,f"{icpn}: suffix too short")
    pkg,temp_code,option=rem[0],rem[1],rem[2:]
    pin={"C":"48","R":"68","M":"88","P":"121"}; flash={"G":"1 MiB","I":"2 MiB"}; package={"U":"UFQFPN","V":"VFQFPN","F":"Thin WLCSP","I":"UFBGA"}; temp={"6":"-40..85 C","7":"-40..105 C"}; expected_pkg={"C":"U","R":"V","M":"F","P":"I"}
    req(pin_code in pin and flash_code in flash and pkg in package and temp_code in temp,f"{icpn}: ordering code outside DS14736")
    req(pkg==expected_pkg[pin_code],f"{icpn}: package/pin combination drifted")
    req(option in {"","TR"},f"{icpn}: unexpected option suffix {option!r}")
    return {"base_device":base,"package":package[pkg],"pin_count":pin[pin_code],"flash_size":flash[flash_code],"temperature_grade":temp[temp_code],"option_suffix":option,"source_type":"official_st_datasheet_ordering_information_plus_retained_exact_identity","source_reference":"DS14736 Rev 3 Ordering information","source_authority":"https://www.st.com/resource/en/datasheet/stm32wba64cg.pdf","verification_status":"verified_st_datasheet_ordering_information_plus_retained_exact_identity"}

def build_rows()->list[dict[str,str]]:
    exact,owners,routes,authority=validate_inputs(); out=[]
    for icpn in exact:
        base=owners[icpn]; route=resolve_route(icpn,routes); meta=decode_metadata(icpn,base,route["series"],authority)
        out.append({"manufacturer":MANUFACTURER,"icpn":icpn,"family":FAMILY,**route,**meta})
    req(len(out)==EXPECTED_EXACT_COUNT and len({r["icpn"] for r in out})==EXPECTED_EXACT_COUNT,"canonical cardinality drifted")
    req(Counter(r["existing_identifier_kind"] for r in out)==Counter(EXPECTED_ROUTE_KIND_COUNTS),"route-kind counts drifted")
    req(Counter(r["mapping_status"] for r in out)==Counter(EXPECTED_MAPPING_COUNTS),"mapping counts drifted")
    return out

def csv_text(rows:list[dict[str,str]])->str:
    b=io.StringIO(newline=""); w=csv.DictWriter(b,fieldnames=PRODUCTION_FIELDS,lineterminator="\n"); w.writeheader(); w.writerows(rows); return b.getvalue()

def build_readiness(rows:list[dict[str,str]],canonical:str)->dict[str,Any]:
    return {"schema_version":1,"readiness_id":"stm32wba6x-bounded-exact-icpn-admission-readiness-v1","scope":"research_only_catalog_admission_readiness","authority":"research_only","manufacturer":MANUFACTURER,"research_series":SERIES,"family":FAMILY,"production_exact_icpn_count":EXPECTED_PRODUCTION_COUNT,"production_family_count":EXPECTED_PRODUCTION_FAMILIES,"frozen_exact_icpn_count":EXPECTED_EXACT_COUNT,"frozen_exact_icpn_set_sha256":EXPECTED_EXACT_SHA256,"excluded_non_active_part_number_count":len(EXPECTED_EXCLUDED),"excluded_non_active_part_numbers":EXPECTED_EXCLUDED,"identity_ready_count":EXPECTED_EXACT_COUNT,"lifecycle_ready_count":EXPECTED_EXACT_COUNT,"metadata_ready_count":EXPECTED_EXACT_COUNT,"route_ready_count":EXPECTED_EXACT_COUNT,"manual_review_count":0,"metadata_exception_count":0,"route_bridge_count":0,"route_assignment_kind_counts":dict(sorted(Counter(r["existing_identifier_kind"] for r in rows).items())),"mapping_status_counts":dict(sorted(Counter(r["mapping_status"] for r in rows).items())),"target_config":TARGET_CONFIG,"package_counts":dict(sorted(Counter(r["package"] for r in rows).items())),"temperature_grade_counts":dict(sorted(Counter(r["temperature_grade"] for r in rows).items())),"metadata_authority":"stm32wba6x-metadata-authority.json","canonical_candidate":"stm32wba6x-commercial-icpn.csv","canonical_candidate_sha256":sha256_text(canonical),"canonical_candidate_git_blob_sha":git_blob_text(canonical),"catalog_admission_ready":True,"next_gate":"stm32wba6x-production-publication-gate","claims":{"production_write_authorized":False,"production_publication_authorized":False,"programming_algorithm_equivalence_claimed":False,"runtime_programming_support_claimed":False,"wireless_radio_operation_authorized":False,"wireless_security_operation_authorized":False,"security_mutation_authorized":False,"debug_attach_supported":False,"target_execution_authorized":False,"physical_validation_claimed":False,"hil_required_for_catalog_admission":False,"remaining_wireless_families_rejected":False,"stm32w108_rejected":False,"cmsis_bridge_authorizes_production_route":False}}

def main()->int:
    p=argparse.ArgumentParser(); p.add_argument("--csv-output",type=Path); p.add_argument("--readiness-output",type=Path); a=p.parse_args()
    rows=build_rows(); canonical=csv_text(rows); readiness=json.dumps(build_readiness(rows,canonical),indent=2,sort_keys=True)+"\n"
    if a.csv_output:a.csv_output.write_text(canonical,encoding="utf-8")
    else:print(canonical,end="")
    if a.readiness_output:a.readiness_output.write_text(readiness,encoding="utf-8")
    else:print(readiness,end="")
    return 0
if __name__=="__main__":raise SystemExit(main())

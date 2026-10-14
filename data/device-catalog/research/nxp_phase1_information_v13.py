#!/usr/bin/env python3
"""ADR-0002 Phase 1 NXP IC Information: exact vendor fields, no programming claims."""
import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LOCK=HERE/"nxp-phase1-source-lock-v13.json"
LEDGER=HERE/"nxp-501-phase1-ic-information-v13.csv"
SUMMARY=HERE/"nxp-phase1-field-coverage-v13.json"
ATTRS=("base_device","package","pin_count","flash","ram","working_vdd","io_supply","vdda","temperature")
FIELDS="icpn identity_state cohort original_disposition source_file source_file_git_blob manufacturer_uri source_observation_sha256 source_document_reference field_source_scope base_device base_device_state package package_state pin_count pin_count_state flash flash_unit flash_state ram ram_unit ram_state working_vdd working_vdd_unit working_vdd_state io_supply io_supply_state vdda vdda_state temperature temperature_state phase".split()

def require(x,m):
    if not x:raise ValueError(m)

def blob(b):
    return hashlib.sha1(b"blob "+str(len(b)).encode()+b"\0"+b).hexdigest()

def read(path):
    with path.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))

def validate_lock():
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    require(lock["schema_version"]==13 and lock["adr"]=="ADR-0002" and lock["phase"]==1
        and lock["scope"]=="IC_INFORMATION_ONLY","Phase 1 policy drift")
    require([x["expected_rows"] for x in lock["input_sources"]]==[277,12,196,16],
        "NXP original cohort changed")
    for x in lock["input_sources"]:
        p=ROOT/x["path"]
        require(p.is_file() and blob(p.read_bytes())==x["blob"],"Original Git object input changed: "+x["path"])
        require(len(read(p))==x["expected_rows"],"original field input count drift")
    require(lock["original_active_bounded_exact_count"]==501
       and lock["production_identity_admitted_count"]==224
       and lock["research_pending_count"]==277,"Phase 1 source cohort drift")
    return lock

def make(s, admitted, source):
    sku=s["icpn"]
    require(bool(sku) and sku.isascii() and sku.isalnum() and sku.upper()==sku,"invalid ICPN")
    htmlsha="" if admitted else s["html_sha256"]
    origin=(s["source_reference"] if admitted else "")
    if admitted:
        import re
        m=re.search(r"[0-9a-f]{64}",origin)
        original_sha=m.group(0) if m else ""
    else:original_sha=htmlsha
    scope=("EXACT_MANUFACTURER_EXISTING_ADMISSION" if admitted else
        "EXACT_PART_HTML_PARTIAL_REVIEW" if htmlsha else "NO_EXACT_HTML_SOURCE_BYTES")
    out=dict(
        icpn=sku,
        identity_state="ADMITTED" if admitted else "RESEARCH_ONLY",
        cohort="existing_production_identity" if admitted else "pending_manufacturer_research",
        original_disposition="MANUFACTURER_IDENTITY_ADMITTED" if admitted else s["review_decision"],
        source_file=source["path"],source_file_git_blob=source["blob"],
        manufacturer_uri=s["source_authority"] if admitted else "https://www.nxp.com/part/"+sku,
        source_observation_sha256=original_sha,
        source_document_reference=origin,field_source_scope=scope,
        base_device=s["base_device"] if admitted else "",
        package=s["package"],pin_count=s["pin_count"] if admitted else s["pins"],
        flash=s["flash_size"] if admitted else s["flash_kb"],
        flash_unit="SOURCE_TEXT_INCLUDES_UNIT" if admitted else (
            "ORIGINAL_V8_LEGACY_KB_FIELD" if s["flash_kb"] else ""),
        ram="" if admitted else s["html_ram_kb"],
        ram_unit="ORIGINAL_V8_LEGACY_KB_FIELD" if s.get("html_ram_kb") else "",
        working_vdd="" if admitted else s["vdd"],
        working_vdd_unit="V" if not admitted and s["vdd"] else "",
        io_supply="",vdda="",
        temperature=s["temperature_grade"] if admitted else s["ambient"],
        phase="1"
    )
    for key in ATTRS:
        observed=bool(out[key])
        require(admitted or not observed or bool(htmlsha),
                "Unhashed candidate source field "+sku+":"+key)
        out[key+"_state"]=("VERIFIED" if admitted else "PARTIAL") if observed else "UNKNOWN"
    return out

def build():
    lock=validate_lock()
    sources=lock["input_sources"]
    result=[]
    for i,src in enumerate(sources):
        admitted=i>0
        for row in read(ROOT/src["path"]):
            result.append(make(row,admitted,src))
    result.sort(key=lambda x:x["icpn"])
    require(len(result)==len({x["icpn"] for x in result})==501,"Phase 1 501 part identity collision")
    require(sum(x["identity_state"]=="ADMITTED" for x in result)==224,"Production identity boundary drift")
    require(sum(x["identity_state"]=="RESEARCH_ONLY" for x in result)==277,"Manufacturer Research boundary drift")
    require(all(x["phase"]=="1" and not any("supported" in k or "h_il" in k for k in x) for x in result),
       "Phase2/3 claims added to Phase1 ledger")
    return result

def csv_bytes(rows):
    out=io.StringIO(newline="")
    writer=csv.DictWriter(out,fieldnames=FIELDS,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    return out.getvalue().encode("utf-8")

def group(rows):
    result={"exact_icpn_records":len(rows),
      "identity_admitted":sum(r["identity_state"]=="ADMITTED" for r in rows),
      "fields":{}}
    for f in ATTRS:
        cnt=Counter(r[f+"_state"] for r in rows)
        result["fields"][f]={k:cnt[k] for k in ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT")}
        require(sum(result["fields"][f].values())==len(rows),"Phase1 count denominator corrupted")
    return result

def coverage(rows):
    lock=validate_lock()
    a=[r for r in rows if r["identity_state"]=="ADMITTED"]
    p=[r for r in rows if r["identity_state"]=="RESEARCH_ONLY"]
    return {
      "schema_version":13,"phase":"IC_INFORMATION","manufacturer":"NXP",
      "generated_from":"pinned manufacturer snapshot inputs, not live search",
      "source_input_sha":[{"path":x["path"],"git_blob":x["blob"]} for x in lock["input_sources"]],
      "units":"Source text preserved, legacy *_kb field not normalized to KiB",
      "existing_production_identity":group(a),"pending_manufacturer_research":group(p),
      "all":group(rows),"software_qualified_exact_icpns":None,
      "physical_hil_validated_configurations":None,
      "note":"Software/physical counts are not measured in Phase 1; null means outside current acceptance, not zero."}

def verify():
    rows=build()
    require(LEDGER.read_bytes()==csv_bytes(rows),"501-row Phase1 exact ledger replay mismatch")
    require(json.loads(SUMMARY.read_text(encoding="utf-8"))==coverage(rows),"Phase1 per-field completeness drift")
    require(sum(1 for x in rows if x["source_observation_sha256"] and x["identity_state"]=="RESEARCH_ONLY")==70,
      "NXP exact original HTML evidence count drift")
    require(coverage(rows)["all"]["fields"]["io_supply"]["UNKNOWN"]==501
        and coverage(rows)["all"]["fields"]["vdda"]["UNKNOWN"]==501,
      "IC Information supply fields invented")
    print("NXP_PHASE1_V13_PASS exact=501 admitted=224 research=277 basic-IC-fields=9; no Programming/HIL claims")

if __name__=="__main__":
    parser=argparse.ArgumentParser()
    parser.parse_args()
    verify()

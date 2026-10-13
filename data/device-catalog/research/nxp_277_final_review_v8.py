#!/usr/bin/env python3
"""NXP 277-source one-batch audit. No Production or programming writes."""
import argparse
import csv
import hashlib
import io
import json
import re
import subprocess
import urllib.request
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
QUEUE=HERE/"nxp-277-manufacturer-gap-review-v6.csv"
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
QUEUE_SHA="6480f04e57dd29d7bd45441c38552dad89107f51"
MANIFEST_SHA="0c252b4d8673f722033302758db4705957f965c5"
PDF_URL="https://www.nxp.com.cn/docs/en/data-sheet/LPC55S0x_LPC550x.pdf"
LPC={"LPC5502JHI48":(64,48),"LPC5504JHI48":(128,80),"LPC5506JHI48":(256,96)}
COLUMNS=["icpn","discovery_cohort","prior_exception","replayed_state","package","pins","flash_kb","html_ram_kb","datasheet_ram_kb","vdd","ambient","html_sha256","datasheet_sha256","review_decision","next_evidence","production_authorized","programming_qualified"]
CANONICAL=["manufacturer","icpn","family","series","base_device","package","pin_count","flash_size","temperature_grade","option_suffix","cmsis_device_name","existing_identifier","existing_identifier_kind","mapping_status","openocd_target_config","source_type","source_reference","source_authority","verification_status"]

def require(ok,msg):
    if not ok: raise ValueError(msg)

def blob(p):
    d=p.read_bytes()
    return hashlib.sha1(b"blob "+str(len(d)).encode()+b"\0"+d).hexdigest()

def read(p):
    with p.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))

def baseline():
    require(blob(QUEUE)==QUEUE_SHA and blob(MANIFEST)==MANIFEST_SHA,"source/Production SHA drift")
    manifest=json.loads(MANIFEST.read_text())
    require(len(manifest["sources"])==31 and sum(x["row_count"] for x in manifest["sources"])==4853 and sum(x["row_count"] for x in manifest["sources"] if x["manufacturer"]=="NXP")==224,"Production baseline changed")
    rows=read(QUEUE)
    require(len(rows)==len({x["icpn"] for x in rows})==277,"277 source queue mismatch")
    return rows

def pdf_table(s):
    require("Ordering options" in s,"not manufacturer ordering table")
    extracted={}
    for sku,expected in LPC.items():
        found=[]
        for line in s.splitlines():
            vals=line.strip().split()
            if len(vals)>=3 and vals[0]==sku and vals[1].isdigit() and vals[2].isdigit():
                found.append((int(vals[1]),int(vals[2])))
        require(len(found)==1 and found[0]==expected,"unverified PDF source: "+sku)
        extracted[sku]=found[0]
    return extracted

def download_pdf(out):
    req=urllib.request.Request(PDF_URL,headers={"User-Agent":"Mozilla/5.0","Accept":"application/pdf"})
    with urllib.request.urlopen(req,timeout=90) as r:
        require(r.geturl()==PDF_URL,"official NXP PDF redirect unexpected")
        raw=r.read(10000001)
    require(raw.startswith(b"%PDF-") and 100000<len(raw)<10000000,"bad NXP PDF")
    digest=hashlib.sha256(raw).hexdigest()
    path=out/"LPC55S0x_LPC550x_Rev1.4_original.pdf"
    path.write_bytes(raw)
    text=subprocess.run(["pdftotext","-f","6","-l","6","-layout",str(path),"-"],check=True,capture_output=True,text=True).stdout
    require("Rev. 1.4" in text and "14 April 2023" in text,"NXP PDF revision unexpected")
    return digest,pdf_table(text)

def csv_text(rows,columns):
    b=io.StringIO(newline="")
    w=csv.DictWriter(b,fieldnames=columns,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return b.getvalue()

def audit(v7,sha,pdf):
    base=baseline();by={r["icpn"]:r for r in v7}
    require(len(by)==len(v7)==277 and set(by)=={r["icpn"] for r in base},"277 v7 replay mismatch")
    output=[];candidate=[];states=Counter();decisions=Counter()
    for old in base:
        sku=old["icpn"];x=by[sku];state=x["refresh_state"]
        require(x["discovery_cohort"]==old["discovery_cohort"] and x["prior_source_state"]==old["source_state"] and x["official_exact_part_url"]==old["official_exact_part_url"] and x["production_publication_authorized"]=="false" and x["programming_profile_qualified"]=="false","identity or permission drift "+sku)
        require(state in ("SOURCE_BLOCKED_OR_SCHEMA","PARTIAL_EXACT_HTML_REPLAYED","FOUR_BASIC_FIELDS_RAM_NOT_VERIFIED"),"unreviewed state "+sku)
        validsha=x["source_html_sha256"]
        require((bool(validsha)!=(state=="SOURCE_BLOCKED_OR_SCHEMA")) and (not validsha or re.fullmatch("[0-9a-f]{64}",validsha)),"html digest bad "+sku)
        states[state]+=1
        decision=("BLOCKED_OR_SCHEMA" if state=="SOURCE_BLOCKED_OR_SCHEMA" else "INCOMPLETE_EXACT_MANUFACTURER_FIELDS")
        needed=old["next_official_evidence"] if state=="SOURCE_BLOCKED_OR_SCHEMA" else old["missing_evidence"]
        pdf_ram=""
        if sku in LPC:
            require(state=="FOUR_BASIC_FIELDS_RAM_NOT_VERIFIED" and
                x["package"]=="H-PQFN48" and x["pin_count"]=="48"
                and x["flash_kb"]==str(pdf[sku][0])
                and x["ambient_temperature"]=="-40 to 105"
                and bool(x["operating_vdd"]) and not x["ram_kb"] and validsha,
                "HTML/PDF field evidence conflict "+sku)
            pdf_ram=str(pdf[sku][1])
            decision="LAYER1_SOURCE_QUALIFIED_UNPUBLISHED"
            needed="owner_approval_after_full_ci"
            candidate.append({
                "manufacturer":"NXP","icpn":sku,"family":"LPC550x","series":"LPC550x",
                "base_device":sku,"package":x["package"],"pin_count":"48",
                "flash_size":x["flash_kb"]+" kB","temperature_grade":"-40 to 105 C",
                "option_suffix":"","cmsis_device_name":"","existing_identifier":"",
                "existing_identifier_kind":"","mapping_status":"no_mapping",
                "openocd_target_config":"",
                "source_type":"official_nxp_exact_html_plus_datasheet_type_row",
                "source_reference":f"HTML SHA256 {validsha}; exact /part/{sku}; PDF Table2 Rev1.4 SHA256 {sha}; run 38366666349",
                "source_authority":f"https://www.nxp.com/part/{sku}",
                "verification_status":"verified_nxp_exact_html_plus_datasheet_flash_ram"
            })
        decisions[decision]+=1
        output.append({"icpn":sku,"discovery_cohort":old["discovery_cohort"],
            "prior_exception":old["source_exception_class"],"replayed_state":state,
            "package":x["package"],"pins":x["pin_count"],"flash_kb":x["flash_kb"],
            "html_ram_kb":x["ram_kb"],"datasheet_ram_kb":pdf_ram,
            "vdd":x["operating_vdd"],"ambient":x["ambient_temperature"],
            "html_sha256":validsha,"datasheet_sha256":sha if pdf_ram else "",
            "review_decision":decision,"next_evidence":needed,
            "production_authorized":"false","programming_qualified":"false"})
    require(states=={"SOURCE_BLOCKED_OR_SCHEMA":207,"PARTIAL_EXACT_HTML_REPLAYED":67,"FOUR_BASIC_FIELDS_RAM_NOT_VERIFIED":3},"v7 source distribution drift")
    require(len(candidate)==3 and {r["icpn"] for r in candidate}==set(LPC),"LPC candidate source drift")
    report={"schema_version":8,"manufacturer":"NXP","reviewed_active_exact":277,
        "observed_active_bounded":501,"production_existing_nxp":224,
        "new_layer1_source_candidates":3,"unadmitted_after_candidate_admission":274,
        "source_states":dict(sorted(states.items())),"decisions":dict(sorted(decisions.items())),
        "manufacturer_pdf_url":PDF_URL,"manufacturer_pdf_sha256":sha,
        "original_277_queue_blob":QUEUE_SHA,"original_manifest_blob":MANIFEST_SHA,
        "global_nxp_active_denominator":None,"production_write_authorized":False,
        "programming_profile_qualified":False,"hardware_runtime_qualified":False}
    return output,candidate,report

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--v7",required=True,type=Path)
    p.add_argument("--out",required=True,type=Path)
    a=p.parse_args()
    a.out.mkdir(parents=True,exist_ok=True)
    sha,pdf=download_pdf(a.out)
    rows,candidates,report=audit(read(a.v7),sha,pdf)
    (a.out/"nxp-277-full-dispositions-v8.csv").write_text(csv_text(rows,COLUMNS),encoding="utf-8")
    (a.out/"nxp-lpc550x-3-unpublished-candidates-v8.csv").write_text(csv_text(candidates,CANONICAL),encoding="utf-8")
    (a.out/"nxp-277-final-summary-v8.json").write_text(json.dumps(report,sort_keys=True,indent=2)+"\n",encoding="utf-8")
    print("NXP_FINAL_277_SUMMARY="+json.dumps(report,sort_keys=True),flush=True)
    print("NXP_LPC3_SOURCE_CSV_BEGIN",flush=True)
    print(csv_text(candidates,CANONICAL),end="",flush=True)
    print("NXP_LPC3_SOURCE_CSV_END",flush=True)
if __name__=="__main__":main()

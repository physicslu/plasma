#!/usr/bin/env python3
"""ADR-0002 Phase1 NXP MCX A3 source-exact SRAM v20, no programming/voltage claims."""
import csv,io,json
from collections import Counter
from pathlib import Path
from nxp_phase1_mcxa1fs_v18 import OUTPUT as OLD,build as old_build,emit as old_emit,headers as old_headers,EXTRA as OLD_EXTRA
from nxp_phase1_information_v13 import blob
DIR=Path(__file__).resolve().parent
SRC=DIR/"nxp-mcxa3fs-32-exact-source-v20.csv"
LOCK=DIR/"nxp-phase1-mcxa3fs-lock-v20.json"
OUT=DIR/"nxp-501-phase1-mcxa3fs-enriched-v20.csv"
COVERAGE=DIR/"nxp-phase1-mcxa3fs-coverage-v20.json"
EXTRA=("mcxa3fs_doc_footer_v20","mcxa3fs_product_listing_rev_v20",
       "mcxa3fs_source_url_v20","mcxa3fs_pdf_page_v20",
       "mcxa3fs_original_binary_sha256_v20")
ATTR=("base_device","package","pin_count","flash","ram","working_vdd","io_supply","vdda","temperature")
def must(t,msg):
    if not t:raise ValueError(msg)
def read(p):
    with p.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
def serialize(rows,keys):
    o=io.StringIO(newline="")
    w=csv.DictWriter(o,fieldnames=keys,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return o.getvalue().encode("utf-8")
def load():
    lk=json.loads(LOCK.read_text(encoding="utf-8"))
    must(lk["schema_version"]==20 and lk["phase"]=="IC_INFORMATION"
         and lk["adr"]=="ADR-0002","Phase1 contract changed")
    older=old_build()
    must(blob(OLD.read_bytes())==lk["v18_source_501_blob"]
         and OLD.read_bytes()==old_emit(older,old_headers(OLD)),
         "previous 501 manufacturer data not replayable")
    must(blob(SRC.read_bytes())==lk["official_source_32_blob"],
         "official exact MCXA3 table blob drift")
    must(lk["source_original_binary_archived"] is False
         and lk["source_original_binary_sha256"] is None,
         "do not fabricate original PDF digest")
    must(lk["expected_501"]==501 and lk["expected_admitted"]==224
         and lk["expected_research_only"]==277
         and lk["expected_exact_official"]==32,"source cohort not approved")
    return lk
def build():
    lk=load();prev=old_build();records=read(SRC)
    must(len(records)==32 and len(set(r["icpn"] for r in records))==32,
         "source 32 exact IDs not unique")
    by={r["icpn"]:r for r in records};found=set();out=[]
    for item in records:
        must(item["source_url"]==lk["official_url"]
             and item["source_visible_footer"]==lk["source_footer"]
             and item["pdf_physical_page"]==lk["source_pdf_page"]
             and item["source_original_pdf_bytes_archived"]=="false"
             and not item["source_original_pdf_sha256"],
             "manufacturer document/version evidence drift")
    for original in prev:
        row=dict(original)
        for k in EXTRA:row[k]=""
        s=by.get(row["icpn"])
        if s:
            must(row["identity_state"]=="ADMITTED"
                 and row["ram_state"]=="UNKNOWN" and not row["ram"]
                 and int(row["flash"].split()[0])==int(s["flash_kb"]),
                 "exact source flash/identity conflict "+row["icpn"])
            row.update(ram=s["sram_kb"],
              ram_unit="KB (NXP MCX A3 official MCU options)",ram_state="VERIFIED",
              mcxa3fs_doc_footer_v20=s["source_visible_footer"],
              mcxa3fs_product_listing_rev_v20=s["source_product_listing"],
              mcxa3fs_source_url_v20=s["source_url"],
              mcxa3fs_pdf_page_v20=s["pdf_physical_page"],
              mcxa3fs_original_binary_sha256_v20="NOT_ARCHIVED")
            found.add(row["icpn"])
        must(row["identity_state"]==original["identity_state"]
             and row["phase"]=="1"
             and all(row[k]==original[k] for k in ("working_vdd","vdda","io_supply","pin_count","package")),
             "unauthorized Phase2/3 or supply field modification")
        out.append(row)
    must(len(out)==501 and found==set(by)
         and sum(r["identity_state"]=="ADMITTED" for r in out)==224
         and sum(r["identity_state"]=="RESEARCH_ONLY" for r in out)==277,
         "source identities or admission changed")
    return out
def states(rows):
    d={"exact_icpn_records":len(rows),
       "identity_admitted":sum(x["identity_state"]=="ADMITTED" for x in rows),"fields":{}}
    for f in ATTR:
        c=Counter(x[f+"_state"] for x in rows)
        d["fields"][f]={s:c[s] for s in ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT")}
        must(sum(d["fields"][f].values())==len(rows),"field denominator drift")
    return d
def report(rows):
    lk=load();old=old_build()
    return {"schema_version":20,"phase":"IC_INFORMATION","adr":"ADR-0002",
      "manufacturer":"NXP","v18_501_blob":lk["v18_source_501_blob"],
      "official_mcxa3_32_blob":lk["official_source_32_blob"],
      "exact_official_rows":32,"matched_admitted_exact":32,
      "source_url":lk["official_url"],"source_pdf_page":3,
      "source_footer":lk["source_footer"],
      "product_page_listing_rev":lk["listing_rev"],
      "revision_discrepancy_explicit":True,
      "original_pdf_bytes_archived":False,"original_pdf_sha256":None,
      "prior_admitted":states([r for r in old if r["identity_state"]=="ADMITTED"]),
      "current_admitted":states([r for r in rows if r["identity_state"]=="ADMITTED"]),
      "all501":states(rows),"software_qualified_count":None,
      "physical_hil_count":None,
      "nonclaims":"No VDD/VDDA/VDDIO inference; no Production admission, Product Catalog UI/Runtime, or Programming support status changes."}
def verify():
    r=build()
    must(OUT.read_bytes()==serialize(r,old_headers(OLD)+list(EXTRA)),
         "v20 501 source-derived row replay mismatch")
    must(json.loads(COVERAGE.read_text(encoding="utf-8"))==report(r),
         "v20 source field coverage report drift")
    print("NXP_PHASE1_V20_PASS: 32 exact MCXA3 official rows, 224 admitted unchanged, RAM only")
if __name__=="__main__":verify()

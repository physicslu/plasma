#!/usr/bin/env python3
"""ADR-0002 Phase1: NXP MCXA1FS 76 explicit official part-row SRAM evidence."""
import csv,io,json
from collections import Counter
from pathlib import Path
from nxp_phase1_selector_v17 import OUT as BASE,generate as original,serialize as old_csv
from nxp_phase1_information_v13 import blob
HERE=Path(__file__).resolve().parent
OFFICIAL=HERE/"nxp-mcxa1fs-76-exact-manufacturer-rows-v18.csv"
LOCK=HERE/"nxp-phase1-mcxa1fs-lock-v18.json"
OUTPUT=HERE/"nxp-501-phase1-mcxa1fs-enriched-v18.csv"
COVERAGE=HERE/"nxp-phase1-mcxa1fs-coverage-v18.json"
EXTRA=("mcxa1fs_rev_v18","mcxa1fs_pdf_page_v18","mcxa1fs_source_url_v18",
       "mcxa1fs_source_scope_v18","mcxa1fs_original_pdf_bytes_v18")
FIELDS=("base_device","package","pin_count","flash","ram","working_vdd","io_supply","vdda","temperature")
def need(ok,message):
    if not ok:raise ValueError(message)
def table(p):
    with p.open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def headers(p):
    with p.open(newline="",encoding="utf-8") as f:return next(csv.reader(f))
def emit(rows,head):
    out=io.StringIO(newline="")
    w=csv.DictWriter(out,fieldnames=head,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return out.getvalue().encode("utf-8")
def load():
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    need(lock["schema_version"]==18 and lock["phase"]=="IC_INFORMATION"
         and lock["adr"]=="ADR-0002","Phase1 contract changed")
    prev,_=original()
    need(blob(BASE.read_bytes())==lock["source_v17_501_git_blob"]
         and BASE.read_bytes()==old_csv(prev,headers(BASE)),
         "v17 exact source-baseline replay mismatch")
    need(blob(OFFICIAL.read_bytes())==lock["official_76_source_git_blob"],
         "original official source transcript SHA drift")
    need(lock["source_pdf_original_bytes_archived"] is False
         and lock["source_pdf_sha256"] is None,"fabricated original PDF binary digest")
    need(lock["exact_official_rows"]==76
         and lock["admitted_exact_matched"]==72 and lock["research_only_not_promoted"]==4,
         "cohort scope changed")
    return lock
def build():
    lk=load()
    previous=original()[0]
    inp=table(OFFICIAL)
    need(len(inp)==76 and len({x["icpn"] for x in inp})==76,
         "official MCU options exact order rows missing")
    by={}
    for x in inp:
        need(x["source_url"]==lk["manufacturer_source_url"]
             and x["official_document"]=="MCXA1FS"
             and x["revision"]=="Rev 0, 30 Mar 2026"
             and x["source_method"]=="VISIBLE_ORIGINAL_NXP_PDF_TABLE_MANUAL_REVIEW"
             and x["source_bytes_archived"]=="false"
             and not x["original_pdf_sha256"],"official source not explicitly evidenced")
        need(x["pdf_page"] in ("2","3","4"),"unverified official PDF page locator")
        by[x["icpn"]]=x
    out=[];admitted=set();research=set()
    for prev in previous:
        x=dict(prev)
        for k in EXTRA:x[k]=""
        s=by.get(x["icpn"])
        if s and x["identity_state"]=="ADMITTED":
            need(x["ram_state"]=="UNKNOWN" and not x["ram"]
                 and int(x["flash"].split()[0])==int(s["flash_kb"]),
                 "original exact order code Flash/SRAM source conflict: "+x["icpn"])
            x.update(
                ram=s["sram_kb"],ram_unit="KB (NXP MCXA1FS official part table)",
                ram_state="VERIFIED",mcxa1fs_rev_v18=s["revision"],
                mcxa1fs_pdf_page_v18=s["pdf_page"],
                mcxa1fs_source_url_v18=s["source_url"],
                mcxa1fs_source_scope_v18="OFFICIAL_EXACT_TABLE_MATCHED_EXISTING_PRODUCTION",
                mcxa1fs_original_pdf_bytes_v18="NOT_ARCHIVED")
            admitted.add(x["icpn"])
        elif s and x["identity_state"]=="RESEARCH_ONLY":
            need(not x["ram"] and x["ram_state"]=="UNKNOWN",
                 "unexpected Research metadata in official source overlap")
            research.add(x["icpn"])
        elif s:raise ValueError("unknown identity state")
        need(x["identity_state"]==prev["identity_state"] and x["phase"]=="1"
             and x["working_vdd"]==prev["working_vdd"] and x["vdda"]==prev["vdda"]
             and x["io_supply"]==prev["io_supply"],
             "unauthorized Phase2/3, identity or voltage mutation")
        out.append(x)
    need(len(out)==501 and len(admitted)==72 and len(research)==4
         and (admitted|research)==set(by),"official exact source cohort overlap changed")
    need(sorted(research)==lk["research_only_exact"],
         "Research-only exact identifiers must not be promoted")
    need(sum(r["identity_state"]=="ADMITTED" for r in out)==224
         and sum(r["identity_state"]=="RESEARCH_ONLY" for r in out)==277,
         "Production identity admission scope drift")
    return out
def stat(rows):
    out={"exact_icpn_records":len(rows),
         "identity_admitted":sum(x["identity_state"]=="ADMITTED" for x in rows),
         "fields":{}}
    for k in FIELDS:
        ct=Counter(x[k+"_state"] for x in rows)
        out["fields"][k]={q:ct[q] for q in ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT")}
        need(sum(out["fields"][k].values())==len(rows),"field count drift")
    return out
def report(rows):
    lk=load();old=original()[0]
    return {"schema_version":18,"adr":"ADR-0002","phase":"IC_INFORMATION","manufacturer":"NXP",
        "input_v17_501_git_blob":lk["source_v17_501_git_blob"],
        "manufacturer_source_76_git_blob":lk["official_76_source_git_blob"],
        "manufacturer_exact_official_rows":76,"admitted_matched_source_exact":72,
        "research_only_matched_source_exact":4,
        "research_only_matched_icpns_unchanged":lk["research_only_exact"],
        "admitted_RAM_newly_verified":72,"pdf_original_bytes_archived":False,
        "pdf_original_sha256":None,
        "prior_admitted":stat([x for x in old if x["identity_state"]=="ADMITTED"]),
        "current_admitted":stat([x for x in rows if x["identity_state"]=="ADMITTED"]),
        "all_501":stat(rows),"software_supported_new":None,"hil_validated_new":None,
        "interpretation":"Exact NXP table part-number SRAM for admitted 72 only. Four existing Research-only identifiers remain untouched; no Production admission, VDD inference, Programming or Hardware claims."}
def verify():
    rows=build()
    need(OUTPUT.read_bytes()==emit(rows,headers(BASE)+list(EXTRA)),
         "501 Phase1 data not deterministic")
    need(json.loads(COVERAGE.read_text(encoding="utf-8"))==report(rows),
         "Phase1 source field audit not deterministic")
    print("NXP_PHASE1_V18_PASS official=76 admitted=72 research=4; no automatic Production admission, VDD or programming")
if __name__=="__main__":verify()

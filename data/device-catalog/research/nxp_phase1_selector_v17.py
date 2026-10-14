#!/usr/bin/env python3
"""ADR-0002 Phase1 v17: source-scoped official NXP selector-first identity evidence."""
from collections import Counter
import csv,io,json
from pathlib import Path
from nxp_phase1_k32l2a_v16 import (
    LEDGER as PREV,build as build_prev,to_csv as prev_csv
)
from nxp_phase1_information_v13 import blob
HERE=Path(__file__).resolve().parent
SRC=HERE/"nxp-39-official-source-rows-v17.csv"
LOCK=HERE/"nxp-phase1-selector-source-lock-v17.json"
OUT=HERE/"nxp-501-phase1-selector-first-v17.csv"
AUD=HERE/"nxp-224-parametric-source-audit-v17.csv"
METRICS=HERE/"nxp-phase1-selector-coverage-v17.json"
FIELDS=("base_device","package","pin_count","flash","ram","working_vdd","io_supply","vdda","temperature")
EXTRA=("selector_evidence_method_v17","selector_evidence_source_id_v17",
       "selector_evidence_source_url_v17","selector_evidence_table_locator_v17",
       "selector_evidence_review_limit_v17","selector_supply_scope_v17")
AUD_COLS=("icpn","source_row_state","manufacturer_group","parametric_export_verified",
          "source_kind","source_id","source_url","ram_state","vdd_state",
          "io_supply_state","evidence_limit")
def require(b,msg):
    if not b:raise ValueError(msg)
def read(path):
    with path.open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def old_columns():
    with PREV.open(encoding="utf-8",newline="") as f:return next(csv.reader(f))
def serialize(rows,keys):
    s=io.StringIO(newline="")
    w=csv.DictWriter(s,fieldnames=keys,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return s.getvalue().encode("utf-8")
def load():
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    require(lock["schema_version"]==17 and lock["adr"]=="ADR-0002"
            and lock["phase"]=="IC_INFORMATION","ADR phase scope violation")
    require(blob(PREV.read_bytes())==lock["source_v16_501_git_blob"]
       and PREV.read_bytes()==prev_csv(build_prev()),"v16 official manufacturer source changed")
    require(blob(SRC.read_bytes())==lock["source_39_exact_rows_git_blob"],
            "unreviewed original official 39 row source changed")
    require(lock["source_group_counts"]=={"MCXCFS_REV0_FALLBACK":18,
        "MCXE24FS_REV1_FALLBACK":8,"MCXC15_C16_INDEXED_PARAMETRIC":9,
        "MCXW71_INDEXED_PARAMETRIC":4},"official exact cohort size drift")
    require(lock["no_source_bytes_sha_claimed"] is True,"source digest fabricated")
    return lock
def generate():
    lk=load(); evidence=read(SRC); prev=build_prev()
    found={}
    for e in evidence:
        p=e["icpn"]
        require(p not in found,"duplicated manufacturer source exact icpn")
        require(e["source_original_bytes_archived"]=="false","source bytes not proven available")
        require(e["source_kind"] in ("OFFICIAL_FACT_SHEET_EXACT_ORDERING_TABLE",
                  "OFFICIAL_PARAMETRIC_INDEXED_EXACT_ROWS"),"unapproved field authority")
        require(e["evidence_state"]==(
                "VERIFIED_OFFICIAL_PDF_VISIBLE_TABLE_NOT_BINARY_ARCHIVED"
                 if e["source_kind"]=="OFFICIAL_FACT_SHEET_EXACT_ORDERING_TABLE"
                 else "PARTIAL_INDEXED_TABLE_NOT_ORIGINAL_HTML"),"unreviewed source confidence")
        require(e["source_url"].startswith("https://www.nxp.com/"),"source not official NXP")
        found[p]=e
    require(len(found)==39,"exact source row count must be 39")
    require(Counter(x["source_id"] for x in evidence)==lk["source_group_counts"],
            "original manufacturer grouped table drift")
    out=[];audit=[]
    for old in prev:
        x=dict(old)
        for k in EXTRA:x[k]=""
        ev=found.get(old["icpn"])
        if ev:
            require(old["identity_state"]=="ADMITTED" and old["ram_state"]=="UNKNOWN"
                and old["ram"]=="" and old["working_vdd_state"]=="UNKNOWN"
                and old["working_vdd"]=="","unexpected previous metadata baseline")
            require(int(old["flash"].split()[0])==int(ev["flash_kb"]),
                "manufacturer source Flash differs from admitted exact identity: "+old["icpn"])
            is_doc=ev["source_kind"]=="OFFICIAL_FACT_SHEET_EXACT_ORDERING_TABLE"
            x["ram"]=ev["sram_kb"];x["ram_unit"]="kB (NXP exact ordering source)"
            x["ram_state"]="VERIFIED" if is_doc else "PARTIAL"
            if ev["working_vdd_value"]:
                require(ev["working_vdd_value"]=="1.71 to 3.6","unreviewed voltage")
                x["working_vdd"]=ev["working_vdd_value"]
                x["working_vdd_unit"]="V";x["working_vdd_state"]="PARTIAL"
            x["selector_evidence_method_v17"]=ev["source_kind"]
            x["selector_evidence_source_id_v17"]=ev["source_id"]
            x["selector_evidence_source_url_v17"]=ev["source_url"]
            x["selector_evidence_table_locator_v17"]=ev["source_table_locator"]
            x["selector_evidence_review_limit_v17"]=ev["evidence_state"]+"; original source bytes not archived; no API/exporter acquired"
            x["selector_supply_scope_v17"]=ev["working_vdd_evidence_scope"]
        require(x["identity_state"]==old["identity_state"] and x["phase"]=="1",
            "unexpected identity admission or programming/hardware claim")
        out.append(x)
        if x["identity_state"]=="ADMITTED":
            group=("KL25" if x["icpn"].startswith("MKL25")
                else "K32L2" if x["icpn"].startswith("K32L2") else x["icpn"][:6])
            audit.append(dict(icpn=x["icpn"],
              source_row_state=("EXACT_OFFICIAL_FACT_SHEET_FALLBACK" if ev and ev["source_kind"]=="OFFICIAL_FACT_SHEET_EXACT_ORDERING_TABLE"
                else "EXACT_INDEXED_PARAMETRIC_UNARCHIVED" if ev
                else "NO_EXACT_ROW_EVIDENCE_IN_V17"),
              manufacturer_group=group,parametric_export_verified="false",
              source_kind=ev["source_kind"] if ev else "",
              source_id=ev["source_id"] if ev else "",
              source_url=ev["source_url"] if ev else "",
              ram_state=x["ram_state"],vdd_state=x["working_vdd_state"],
              io_supply_state=x["io_supply_state"],
              evidence_limit=("Source-specific exact observations, full original HTML/PDF bytes not persisted"
                if ev else "Not tested to exhaustion; cannot infer NXP lacks parametric rows")))
    require(len(out)==501 and len(audit)==224 and len(set(x["icpn"] for x in out))==501,
           "original ICPN universe drift")
    require(sum(1 for r in out if r["identity_state"]=="ADMITTED")==224,
            "new internal admission not authorized")
    require(sum(1 for r in audit if r["source_row_state"]=="EXACT_INDEXED_PARAMETRIC_UNARCHIVED")==13
        and sum(1 for r in audit if r["source_row_state"]=="EXACT_OFFICIAL_FACT_SHEET_FALLBACK")==26,
        "source quality counts changed")
    return out,audit
def field_report(rows):
    result={"exact_icpn_records":len(rows),"identity_admitted":sum(r["identity_state"]=="ADMITTED" for r in rows),"fields":{}}
    for f in FIELDS:
        count=Counter(r[f+"_state"] for r in rows)
        result["fields"][f]={x:count[x] for x in ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT")}
        require(sum(result["fields"][f].values())==len(rows),"field denominator mismatch")
    return result
def coverage(rows,audit):
    lk=load()
    return {
    "schema_version":17,"adr":"ADR-0002","phase":"IC_INFORMATION","manufacturer":"NXP",
    "reviewed_cohort":"224 existing admitted NXP identities only; 277 Research identities unchanged",
    "source_baseline_501_git_blob":lk["source_v16_501_git_blob"],
    "source_observed_rows_39_git_blob":lk["source_39_exact_rows_git_blob"],
    "source_original_pdf_html_export_archive_present":False,
    "admitted_source_access_summary":{
      "admitted_icpns":224,
      "parametric_exact_indexed":13,"official_fact_sheet_exact":26,
      "total_with_source_attested_exact_rows":39,
      "no_retrieved_exact_row_this_pass":185,"verified_nxp_parametric_export_xls_rows":0},
    "prior_admitted_field_summary":field_report(build_prev_admitted()),
    "current_admitted_field_summary":field_report([r for r in rows if r["identity_state"]=="ADMITTED"]),
    "all_501_field_summary":field_report(rows),
    "new_source_backed_ram_rows":39,"new_source_backed_vdd_rows":27,
    "software_programming_supported_new":None,"physical_compatibility_qualified_new":None,
    "distinctions":{
      "indexed_parametric":"Search-indexed official NXP Buy/Parametrics exact row, not successfully replayed or binary archived original dynamic HTML; mark fields PARTIAL.",
      "official_factsheet":"Official exact commercial part number within named table on NXP fact sheet, PDF page manually checked; mark RAM VERIFIED, but original PDF bytes not archived.",
      "voltage_family":"C04/C14/C24/C44 family-level feature 1.71–3.6 V, not per-exact operating electrical specification; label PARTIAL.",
      "voltage_exact_index":"C15/C16 exact parametric search-indexed field 1.71–3.6 V, still PARTIAL because original HTML unavailable.",
      "unknown":"185 uncovered SKUs were not exhaustively searched across NXP's dynamic catalog; not proof values do not exist. VDDIO/VDDA and program operations never inferred."}}
def build_prev_admitted():
    return [r for r in build_prev() if r["identity_state"]=="ADMITTED"]
def verify():
    rows,audit=generate()
    require(OUT.read_bytes()==serialize(rows,old_columns()+list(EXTRA)),"v17 501 output replay mismatch")
    require(AUD.read_bytes()==serialize(audit,list(AUD_COLS)),"v17 224 audit source mismatch")
    require(json.loads(METRICS.read_text(encoding="utf-8"))==coverage(rows,audit),
            "v17 evidence coverage counts mismatch")
    print("NXP_PHASE1_V17_PASS admitted=224 exact indexed=13 official fact=26 no exact row=185; 501 source identities intact")
if __name__=="__main__":
    verify()

#!/usr/bin/env python3
"""ADR-0002 Phase1 v22: 12 K32L2B RAM field partial from NXP grouped ordering codes."""
import csv,io,json,re
from collections import Counter
from pathlib import Path
from nxp_phase1_four_doc_v21 import LEDGER as PREV,build as previous_build,csv_bytes as original_csv,columns as original_cols
from nxp_phase1_information_v13 import blob
DIR=Path(__file__).resolve().parent
SRC=DIR/"nxp-k32l2b-12-pattern-source-v22.csv"
LOCK=DIR/"nxp-phase1-k32l2b-group-lock-v22.json"
LEDGER=DIR/"nxp-501-phase1-k32l2b-partial-v22.csv"
COVERAGE=DIR/"nxp-phase1-k32l2b-coverage-v22.json"
EXTRA=("k32l2b_family_pattern_v22","k32l2b_source_primary_v22",
 "k32l2b_source_independent_v22","k32l2b_exact_list_v22",
 "k32l2b_evidence_limit_v22")
ATTR=("base_device","package","pin_count","flash","ram","working_vdd","io_supply","vdda","temperature")
def need(x,m):
    if not x:raise ValueError(m)
def records(path):
    with path.open(encoding="utf-8",newline="") as f:return list(csv.DictReader(f))
def to_csv(rows,cols):
    io_obj=io.StringIO(newline="")
    w=csv.DictWriter(io_obj,fieldnames=cols,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return io_obj.getvalue().encode("utf-8")
def load():
    lk=json.loads(LOCK.read_text(encoding="utf-8"))
    need(lk["schema_version"]==22 and lk["adr"]=="ADR-0002"
         and lk["phase"]=="IC_INFORMATION","out of scope Phase1")
    old=previous_build()
    need(blob(PREV.read_bytes())==lk["source_v21_501_blob"]
         and PREV.read_bytes()==original_csv(old,original_cols(PREV)),
         "v21 authoritative exact source snapshot changed")
    need(blob(SRC.read_bytes())==lk["source_12_exact_list_plus_wildcard_blob"],
         "K32L2B official group source transcription changed")
    need(lk["source_original_pdf_bytes_archived"] is False
         and lk["original_pdf_sha256"] is None,
         "original PDF binary SHA fabricated")
    need(lk["group_ram_kb"]=={"11":32,"21":32,"31":32}
         and lk["group_flash_kb"]=={"11":64,"21":128,"31":256},
         "RAM/Flash wildcard sources changed")
    return lk
def build():
    lk=load()
    source=records(SRC)
    need(len(source)==12 and len({r["icpn"] for r in source})==12,
         "official source pattern cohort count")
    references={}
    for x in source:
        sku=x["icpn"]
        m=re.fullmatch(r"K32L2B(11|21|31)V(FM|FT|LH|MP)0A",sku)
        need(m is not None,"exact NXP part does not fit bounded official group")
        need(int(x["flash_kb"])==lk["group_flash_kb"][m.group(1)]
             and int(x["ram_kb"])==lk["group_ram_kb"][m.group(1)]
             and x["manufacturer_group_pattern"]=="K32L2B"+m.group(1)+"Vxx0A",
             "manufacturer group Flash/RAM mismatch")
        need(x["grouped_manufacturer_ram_source"]==lk["primary_official_url"]
             and x["independent_family_source"]==lk["second_official_url"]
             and x["exact_manufacturer_list_uri"]==lk["exact_official_supported_parts_url"],
             "group and exact official identity cross-reference drift")
        need(x["field_evidence_state"]=="PARTIAL"
             and x["original_source_binary_archived"]=="false"
             and not x["original_source_pdf_sha256"],"source authority over-asserted")
        references[sku]=x
    need(sorted(references)==lk["required_full_exact_codes"],
         "K32L2B exact 12 source ordering codes changed")
    result=[];seen=set()
    for old in previous_build():
        row=dict(old)
        for k in EXTRA:row[k]=""
        s=references.get(old["icpn"])
        if s:
            need(old["identity_state"]=="ADMITTED"
                 and old["ram_state"]=="UNKNOWN" and not old["ram"]
                 and int(old["flash"].split()[0])==int(s["flash_kb"]),
                 "K32L2B previous exact Flash/identity/source changed")
            row.update(
              ram=s["ram_kb"],ram_unit="KB (NXP official wildcard group cross-source)",
              ram_state="PARTIAL",k32l2b_family_pattern_v22=s["manufacturer_group_pattern"],
              k32l2b_source_primary_v22=s["grouped_manufacturer_ram_source"],
              k32l2b_source_independent_v22=s["independent_family_source"],
              k32l2b_exact_list_v22=s["exact_manufacturer_list_uri"],
              k32l2b_evidence_limit_v22=s["source_semantics"])
            seen.add(old["icpn"])
        need(old["identity_state"]==row["identity_state"] and row["phase"]=="1"
             and all(old[k]==row[k] for k in ("working_vdd","vdda","io_supply","flash","package","pin_count")),
             "unsupported other-phase or IC fields changed")
        result.append(row)
    need(len(result)==501 and seen==set(references)
         and sum(r["identity_state"]=="ADMITTED" for r in result)==224
         and sum(r["identity_state"]=="RESEARCH_ONLY" for r in result)==277,
         "Original 501/224/277 source scope changed")
    return result
def part(rows):
    ans={"exact_icpn_records":len(rows),
         "identity_admitted":sum(x["identity_state"]=="ADMITTED" for x in rows),"fields":{}}
    for key in ATTR:
        cc=Counter(x[key+"_state"] for x in rows)
        ans["fields"][key]={s:cc[s] for s in ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT")}
        need(sum(ans["fields"][key].values())==len(rows),"field denominator corrupted")
    return ans
def coverage(rows):
    lk=load()
    return {"schema_version":22,"adr":"ADR-0002","phase":"IC_INFORMATION","manufacturer":"NXP",
      "v21_input_git_blob":lk["source_v21_501_blob"],
      "source_12_groups_git_blob":lk["source_12_exact_list_plus_wildcard_blob"],
      "exact_admitted_k32l2b_full_order_codes":12,
      "family_pattern_official_RAM_32_KB":12,
      "result_evidence_state":"PARTIAL_NOT_EXACT_ORIGINAL_DATASHEET",
      "prior_admitted":part([x for x in previous_build() if x["identity_state"]=="ADMITTED"]),
      "current_admitted":part([x for x in rows if x["identity_state"]=="ADMITTED"]),
      "all_501":part(rows),"verified_source_exact_RAM_unchanged":199,
      "new_software_supported":None,"physical_hil_qualification":None,
      "source_original_pdf_sha256":None,
      "note":"All 12 remaining K32L2B use 32KB RAM per two NXP wildcard-model tables, backed by exact NXP part applicability. NOT exact-row verified. VDD IO supplies and Programming/HIL unchanged."}
def verify():
    rows=build()
    need(LEDGER.read_bytes()==to_csv(rows,original_cols(PREV)+list(EXTRA)),
         "v22 phase1 K32 grouped source replay mismatch")
    need(json.loads(COVERAGE.read_text(encoding="utf-8"))==coverage(rows),
         "v22 source-field coverage mismatch")
    print("NXP_PHASE1_V22_PASS admitted=224 RAM verified=199 partial=25 unknown=0; 12 K32L2B group-evidenced PARTIAL, not exact verified")
if __name__=="__main__":verify()

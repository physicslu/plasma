#!/usr/bin/env python3
"""ADR-0002 Phase1: 53 exact admitted SRAM rows from four official NXP ordering tables."""
import csv,io,json
from collections import Counter
from pathlib import Path
from nxp_phase1_mcxa3fs_v20 import OUT as PREV, build as old_build, serialize as old_csv
from nxp_phase1_information_v13 import blob

HERE=Path(__file__).resolve().parent
SOURCE=HERE/"nxp-54-exact-ordering-rows-v21.csv"
LOCK=HERE/"nxp-phase1-exact-four-doc-lock-v21.json"
LEDGER=HERE/"nxp-501-phase1-four-doc-enriched-v21.csv"
REPORT=HERE/"nxp-phase1-four-doc-coverage-v21.json"
EXTRA=("manufacturer_exact_source_v21","manufacturer_official_source_url_v21",
 "manufacturer_official_ordering_table_v21","manufacturer_document_revision_v21",
 "manufacturer_document_page_v21","sram_ecc_usable_capacity_kb_v21",
 "source_pdf_original_digest_state_v21")
ATTRS=("base_device","package","pin_count","flash","ram","working_vdd","io_supply","vdda","temperature")
def must(x,m):
    if not x:raise ValueError(m)
def read(path):
    with path.open(newline="",encoding="utf-8") as f:return list(csv.DictReader(f))
def columns(path):
    with path.open(newline="",encoding="utf-8") as f:return next(csv.reader(f))
def csv_bytes(rows,keys):
    sio=io.StringIO(newline="")
    w=csv.DictWriter(sio,fieldnames=keys,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return sio.getvalue().encode("utf-8")
def load():
    lk=json.loads(LOCK.read_text(encoding="utf-8"))
    must(lk["schema_version"]==21 and lk["phase"]=="IC_INFORMATION"
         and lk["adr"]=="ADR-0002","Phase1 contract drift")
    baseline=old_build()
    must(blob(PREV.read_bytes())==lk["input_v20_git_blob"]
         and PREV.read_bytes()==old_csv(baseline,columns(PREV)),
         "v20 source baseline replay error")
    must(blob(SOURCE.read_bytes())==lk["source_54_exact_git_blob"],
         "54 manufacturer exact-source rows were altered")
    must(lk["original_pdf_binary_archived"] is False
         and lk["original_pdf_sha256"] is None,
         "original vendor PDF bytes SHA incorrectly claimed")
    must((lk["expected_501"],lk["expected_admitted"],lk["expected_research_only"],
         lk["expected_exact_source"],lk["expected_exact_admitted_matches"])==
         (501,224,277,54,53),"original 501 identity source scope changed")
    return lk
def build():
    lk=load()
    previous=old_build()
    source=read(SOURCE)
    must(len(source)==54 and len(set(x["icpn"] for x in source))==54,
         "manufacturer exact-source rows not 54 unique")
    docs={x["doc"]:x for x in lk["sources"]}
    seen_doc=Counter()
    table={}
    for x in source:
        doc=docs.get(x["source_id"])
        must(doc is not None and x["manufacturer_uri"]==doc["url"]
             and x["document_revision"]==doc["rev"]
             and int(x["pdf_physical_page"]) in doc["pages"]
             and x["exact_ordering_table_seen"]=="true"
             and x["original_pdf_binary_archived"]=="false"
             and x["original_pdf_sha256"]=="",
             "unreviewed source PDF reference or original document SHA claim")
        seen_doc[x["source_id"]]+=1
        must(x["icpn"].isascii() and x["icpn"].isalnum()
             and x["icpn"]==x["icpn"].upper()
             and int(x["sram_kb"])>0 and int(x["flash_kb"])>0,
             "invalid exact manufacturer order row")
        if x["source_id"] in ("MCXN23x","MCXNP184M150F70"):
            expect={192:160,352:288,512:416}[int(x["sram_kb"])]
            must(int(x["ecc_enabled_usable_sram_kb"])==expect,
                 "SRAM ECC-dependent usable capacity corrupted")
        else:must(not x["ecc_enabled_usable_sram_kb"],
                  "ECC field invented for non-N family")
        table[x["icpn"]]=x
    must(seen_doc=={x["doc"]:x["exact_source_rows"] for x in lk["sources"]},
         "manufacturer per-document group changed")
    rows=[];matched=set();research=set()
    for old in previous:
        row=dict(old)
        for k in EXTRA:row[k]=""
        data=table.get(old["icpn"])
        if data and old["identity_state"]=="ADMITTED":
            must(old["ram_state"]=="UNKNOWN" and not old["ram"]
                 and int(old["flash"].split()[0])==int(data["flash_kb"]),
                 "exact FLASH inconsistent or SRAM previously recorded: "+old["icpn"])
            row.update(ram=data["sram_kb"],
              ram_unit="KB (NXP exact official ordering table)",ram_state="VERIFIED",
              manufacturer_exact_source_v21=data["source_id"],
              manufacturer_official_source_url_v21=data["manufacturer_uri"],
              manufacturer_official_ordering_table_v21=data["locator"],
              manufacturer_document_revision_v21=data["document_revision"],
              manufacturer_document_page_v21=data["pdf_physical_page"],
              sram_ecc_usable_capacity_kb_v21=data["ecc_enabled_usable_sram_kb"],
              source_pdf_original_digest_state_v21="PDF_NOT_ARCHIVED")
            matched.add(old["icpn"])
        elif data:
            must(old["identity_state"]=="RESEARCH_ONLY","unexpected source identity category")
            research.add(old["icpn"])
        must(row["identity_state"]==old["identity_state"] and row["phase"]=="1",
             "new ICPN admission / Phase2 or HIL claim")
        must(all(row[k]==old[k] for k in ("working_vdd","io_supply","vdda","package","pin_count")),
             "unapproved inferred voltage or hardware change")
        rows.append(row)
    must(len(rows)==501 and len(matched)==53
         and sorted(research)==lk["existing_research_only_no_promotion"]
         and matched|research==set(table),"original exact 54 manufacturer source match drift")
    must(sum(r["identity_state"]=="ADMITTED" for r in rows)==224
         and sum(r["identity_state"]=="RESEARCH_ONLY" for r in rows)==277,
         "existing admitted and research NXP cohorts changed")
    return rows
def group(rows):
    data={"exact_icpn_records":len(rows),
      "identity_admitted":sum(r["identity_state"]=="ADMITTED" for r in rows),"fields":{}}
    for f in ATTRS:
        c=Counter(r[f+"_state"] for r in rows)
        data["fields"][f]={state:c[state] for state in ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT")}
        must(sum(data["fields"][f].values())==len(rows),"bad coverage field counts")
    return data
def stats(rows):
    lk=load();before=old_build()
    return {"schema_version":21,"adr":"ADR-0002","phase":"IC_INFORMATION","manufacturer":"NXP",
      "baseline_v20_git_blob":lk["input_v20_git_blob"],
      "official_54_source_git_blob":lk["source_54_exact_git_blob"],
      "official_exact_source_rows":54,"admitted_exact_RAM_rows":53,
      "research_only_source_matched_unchanged":lk["existing_research_only_no_promotion"],
      "documents":{x["doc"]:x["exact_source_rows"] for x in lk["sources"]},
      "original_pdf_bytes_sha256_archived":False,
      "admitted_prior":group([r for r in before if r["identity_state"]=="ADMITTED"]),
      "admitted_after":group([r for r in rows if r["identity_state"]=="ADMITTED"]),
      "all_501":group(rows),"software_programming_qualified":None,"site_hil_qualified":None,
      "note":"Exact manufacturer ordering codes and SRAM for admitted identities; ECC configuration usable capacities separate; unchanged supplies, production and software support."}
def verify():
    records=build()
    must(LEDGER.read_bytes()==csv_bytes(records,columns(PREV)+list(EXTRA)),
         "v21 501 official source evidence replay mismatch")
    must(json.loads(REPORT.read_text(encoding="utf-8"))==stats(records),
         "v21 field coverage report not reproducible")
    print("NXP_PHASE1_V21_PASS: manufacturer 54 exact, 53 existing admitted RAM verified, 1 Research unchanged; baseline=501")
if __name__=="__main__":verify()

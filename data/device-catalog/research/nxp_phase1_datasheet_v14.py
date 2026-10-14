#!/usr/bin/env python3
"""NXP Phase1 v14 official-datasheet IC information overlay, with conflict fidelity."""
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from nxp_phase1_information_v13 import LEDGER as V13_LEDGER, build as build_v13, csv_bytes as v13_csv, blob as git_blob

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LOCK=HERE/"nxp-phase1-datasheet-lock-v14.json"
CSV=HERE/"nxp-501-phase1-enriched-information-v14.csv"
STATS=HERE/"nxp-phase1-enriched-coverage-v14.json"
NEW_KEYS=("document_id","document_revision","document_uri","document_page_evidence",
          "commercial_suffix_evidence_uri","original_document_sha256","phase1_evidence_scope",
          "field_evidence_note")
BASE_KEYS=("icpn identity_state cohort original_disposition source_file source_file_git_blob "
          "manufacturer_uri source_observation_sha256 source_document_reference field_source_scope "
          "base_device base_device_state package package_state pin_count pin_count_state "
          "flash flash_unit flash_state ram ram_unit ram_state working_vdd working_vdd_unit "
          "working_vdd_state io_supply io_supply_state vdda vdda_state temperature temperature_state phase").split()
KEYS=BASE_KEYS+list(NEW_KEYS)
FIELDS=("base_device","package","pin_count","flash","ram","working_vdd","io_supply","vdda","temperature")

def check(test,msg):
    if not test:raise ValueError(msg)

def load():
    lk=json.loads(LOCK.read_text(encoding="utf-8"))
    check(lk["schema_version"]==14 and lk["active_phase"]=="IC_INFORMATION_ONLY" and lk["adr"]=="ADR-0002","Phase1 scope changed")
    check(git_blob(V13_LEDGER.read_bytes())==lk["source_snapshot_v13_git_blob"]
      and V13_LEDGER.read_bytes()==v13_csv(build_v13()),"source v13 original 501 drift")
    check(lk["original_document_bytes_persisted"] is False and lk["original_document_sha256"] is None,
      "source PDF original bytes evidence incorrectly claimed")
    check(len(lk["kl25_sram_by_exact_icpn"])==12 and len(lk["lpc84x_suffix_by_datasheet_type"])==8,
      "datasheet official part tables incomplete")
    check(len(lk["documents"])==3,"document provenance missing")
    for doc in lk["documents"]:
        check(doc["url"].startswith("https://www.nxp."),"non-official input source")
        check(doc["blob_sha256"] is None,"original PDF bytes SHA claimed without archived source")
    return lk

def enrich():
    lk=load()
    suffix={}
    for typ,suf in lk["lpc84x_suffix_by_datasheet_type"].items():
        for q in suf:
            key=typ+q
            check(key not in suffix,"duplicated manufacturer exact suffix")
            suffix[key]=typ
    check(len(suffix)==15,"wrong LPC exact manufacturer SKU set")
    rows=[]
    found={"KL":0,"LPC":0}
    for source in build_v13():
        r=dict(source)
        for key in NEW_KEYS:r[key]=""
        sku=r["icpn"]
        if sku in lk["kl25_sram_by_exact_icpn"]:
            found["KL"]+=1
            check(r["identity_state"]=="ADMITTED","KL admission input unexpected")
            check(sku.startswith("MKL25Z") and sku[6:sku.index("V")]==r["flash"].split()[0],
                  "KL25 exact manufacturer flash/part-number mismatch")
            r.update(
                ram=lk["kl25_sram_by_exact_icpn"][sku],
                ram_unit="KB (NXP datasheet)",ram_state="VERIFIED",
                working_vdd="1.71 to 3.6",working_vdd_unit="V",working_vdd_state="VERIFIED",
                vdda="1.71 to 3.6 V; |VDD-VDDA| <= 0.1 V",vdda_state="VERIFIED",
                document_id="KL25P80M48SF0",document_revision="Rev 5 08/2014",
                document_uri="https://www.nxp.com.cn/docs/en/data-sheet/KL25P80M48SF0.pdf",
                document_page_evidence="page 2 ordering information exact SKU: Flash/SRAM; page 7 table 5: VDD/VDDA and differential",
                phase1_evidence_scope="OFFICIAL_EXACT_ORDERING_TABLE_PLUS_FAMILY_ELECTRICAL_TABLE",
                field_evidence_note="No distinct VDDIO rail independently specified in the examined table; IO Supply remains UNKNOWN.")
        elif sku in suffix:
            found["LPC"]+=1
            check(r["identity_state"]=="RESEARCH_ONLY","LPC exact admission unexpectedly granted")
            typ=suffix[sku]
            spec=lk["lpc84x_type_parameters"][typ]
            def update(key,val,state):
                check(not r[key],"LPC baseline field replaced without review: "+sku+" "+key)
                r[key]=val;r[key+"_state"]=state
            update("base_device",spec["base_device"],"PARTIAL")
            conflict="JHI33" in sku
            update("package",spec["package"],"CONFLICT" if conflict else "VERIFIED")
            update("pin_count",spec["pin_count"],"CONFLICT" if conflict else "VERIFIED")
            update("flash",spec["flash"],"VERIFIED")
            r["flash_unit"]="KB (NXP datasheet)"
            update("ram",spec["ram"],"VERIFIED")
            r["ram_unit"]="KB (NXP datasheet)"
            update("working_vdd","1.8 to 3.6","VERIFIED")
            r["working_vdd_unit"]="V"
            update("temperature","-40 to 105","VERIFIED")
            r.update(
                document_id="LPC84x",document_revision="Rev 2.1 28 Oct 2020",
                document_uri="https://www.nxp.com/docs/en/data-sheet/LPC84x.pdf",
                document_page_evidence="page 4 tables 1-2: package/terminal count, flash/SRAM; page 3: VDD/temp; page 46 table 11: operating VDD",
                commercial_suffix_evidence_uri="https://www.nxp.com/products/LPC84X?tab=Package_Quality_Tab",
                phase1_evidence_scope="OFFICIAL_DATASHEET_ORDERING_TYPE_PLUS_OFFICIAL_PRODUCT_SUFFIX_LIST",
                field_evidence_note=(
                    "NXP datasheet says HVQFN33 / 33 terminals; NXP Quality tab labels the same JHI33 ordering group HVQFN32. Preserve nomenclature conflict; do not auto-release physical pin mapping. VDDA is conditional on ADC/DAC operation (Table 11), not asserted as one generic rail."
                    if conflict else
                    "Base device is a derived type prefix, not an independently verified silicon identity. VDDA depends on analog operating mode (Table 11) and remains UNKNOWN."))
        check(not r["original_document_sha256"],"fabricated source PDF SHA")
        check(r["identity_state"]==source["identity_state"],"manufacturer Research identity wrongly admitted")
        check(r["phase"]=="1","Phases 2/3 mutated")
        rows.append(r)
    check(found=={"KL":12,"LPC":15},"missing manufacturer exact order suffixes")
    check(len(rows)==len({r["icpn"] for r in rows})==501,"exact NXP SKU universe changed")
    check(sum(1 for r in rows if r["package_state"]=="CONFLICT")==5,"JHI33 source discrepancy lost")
    check(all(not r["io_supply"] and r["io_supply_state"]=="UNKNOWN" for r in rows),
          "fabricated I/O rail")
    return rows

def to_csv(rows):
    b=io.StringIO(newline="")
    writer=csv.DictWriter(b,fieldnames=KEYS,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    return b.getvalue().encode("utf-8")

def subset(rows):
    result={"exact_icpn_records":len(rows),"identity_admitted":sum(r["identity_state"]=="ADMITTED" for r in rows),"fields":{}}
    for f in FIELDS:
        tally=Counter(r[f+"_state"] for r in rows)
        result["fields"][f]={n:tally[n] for n in ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT")}
        check(sum(tally.values())==len(rows),"missing or corrupt field status "+f)
    return result

def metrics(rows):
    lock=load()
    return {
        "schema_version":14,"phase":"IC_INFORMATION","manufacturer":"NXP",
        "cohort":"bounded 501 exact observed ordering strings",
        "existing_production_identity":subset([r for r in rows if r["identity_state"]=="ADMITTED"]),
        "pending_manufacturer_research":subset([r for r in rows if r["identity_state"]=="RESEARCH_ONLY"]),
        "all":subset(rows),
        "enriched_source_attested_exact":27,
        "enriched_kl25":12,"enriched_lpc84x":15,
        "unresolved_hvqfn33_vs_hvqfn32_package_nomenclature":sum(r["package_state"]=="CONFLICT" for r in rows),
        "source_binary_sha256_lock_available":False,
        "software_qualified_exact_icpns":None,"physical_hil_validated_configurations":None,
        "underlying_snapshot_v13_blob":lock["source_snapshot_v13_git_blob"],
        "source_evidence_policy":"Original PDF bytes unavailable for Git SHA lock; document URLs/revisions and exact table/page locators recorded. No PDF byte digest inferred. Data is source-document transcription, independently reviewable.",
        "note":"Manufacturer identity admission is independent of metadata verified fields; no Production/public Catalog/runtime/Programming/HIL changes."
    }

def validate():
    rows=enrich()
    check(CSV.read_bytes()==to_csv(rows),"reproducible 501-row manufacturer field ledger mismatch")
    check(json.loads(STATS.read_text(encoding="utf-8"))==metrics(rows),"reproducible Phase 1 source field coverage mismatch")
    print("NXP_PHASE1_V14_PASS: 501 source IDs; 27 manufacturer document enrichments; 5 package nomenclature conflicts; Production unchanged")
if __name__=="__main__":
    validate()

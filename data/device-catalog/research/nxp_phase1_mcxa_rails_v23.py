#!/usr/bin/env python3
"""ADR-0002 NXP Phase1 v23: exact-sourced MCX A working rails, not HIL/programming."""
import csv, io, json
from collections import Counter
from pathlib import Path
from nxp_phase1_k32l2b_v22 import LEDGER as BEFORE, build as old_build, to_csv as old_csv
from nxp_phase1_information_v13 import blob

DIR=Path(__file__).resolve().parent
SOURCE=DIR/"nxp-119-mcxa-operating-rails-source-v23.csv"
LOCK=DIR/"nxp-phase1-mcxa-operating-lock-v23.json"
LEDGER=DIR/"nxp-501-phase1-mcxa-operating-v23.csv"
METRICS=DIR/"nxp-phase1-mcxa-operating-coverage-v23.json"
EXTRA=("operating_source_doc_v23","operating_source_uri_v23",
 "operating_source_revision_v23","operating_table_locator_v23",
 "io_rail_mode_v23","io_port3_supply_v23","usb_analog_supply_v23",
 "vdda_por_constraint_v23","operating_source_pdf_sha256_v23")
ATTR=("base_device","package","pin_count","flash","ram","working_vdd","io_supply","vdda","temperature")

def require(value,msg):
    if not value:raise ValueError(msg)
def records(p):
    with p.open(encoding="utf-8",newline="") as stream:return list(csv.DictReader(stream))
def header(p):
    with p.open(encoding="utf-8",newline="") as stream:return next(csv.reader(stream))
def dump(rows,keys):
    buff=io.StringIO(newline="")
    w=csv.DictWriter(buff,fieldnames=keys,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return buff.getvalue().encode("utf-8")

def load():
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    require(lock["schema_version"]==23 and lock["adr"]=="ADR-0002"
        and lock["phase"]=="IC_INFORMATION","Phase1 schema and scope changed")
    old=old_build()
    require(blob(BEFORE.read_bytes())==lock["baseline_v22_git_blob"]
        and BEFORE.read_bytes()==old_csv(old,header(BEFORE)),
        "v22 manufacturer-research ledger not replayable")
    require(blob(SOURCE.read_bytes())==lock["exact_119_evidence_git_blob"],
        "manufacturer 119 rail source rows changed without review")
    require((lock["expected_501"],lock["expected_admitted"],
        lock["expected_research_only"],lock["expected_119"],
        lock["expected_vdd_p3_alternate"])==(501,224,277,119,26),
        "manufacturer exact ordering population changed")
    require(lock["vendor_pdf_binary_archived"] is False
        and lock["vendor_pdf_sha256"] is None,"unarchived PDF source digest claimed")
    return lock

def build():
    lk=load()
    source=records(SOURCE)
    require(len(source)==119 and len(set(x["icpn"] for x in source))==119,
            "expected 119 distinct manufacturer exact order codes")
    doccounter=Counter()
    by={}
    for s in source:
        doc=s["document_id"]
        require(doc in lk["document_revision"] and
            s["document_revision"]==lk["document_revision"][doc] and
            s["document_uri"].startswith("https://www.nxp.com/docs/en/data-sheet/"),
            "official datasheet identity/edition mismatch")
        require(s["working_vdd_min"]=="1.71" and s["working_vdd_max"]=="3.6" and
            s["vdda_constraint"]=="VDD-0.1 to VDD+0.1 V; POR same voltage as VDD",
            "voltage conditional supply rail drift")
        require(s["source_original_exact_order_table"] in ("MCXA1FS","MCXA3FS","MCXA2FS")
            and s["original_pdf_bytes_archived"]=="false" and
            s["pdf_original_sha256"]=="","manufacturer official exact-source provenance invalid")
        require(s["gpio_power_mode"] in ("VDD_SHARED","VDD_P3_DUAL_MODE"),
                "unsupported supply-domain interpretation")
        if s["gpio_power_mode"]=="VDD_P3_DUAL_MODE":
            require(doc=="MCXAP100M096F60" and
                s["io_supply_port3_extra"]=="VDD_P3 normal 1.71 to 3.6 V or 1.2-V mode 1.14 to 1.32 V",
                "P3 alternate 1.2V conditional missing")
        else:require(not s["io_supply_port3_extra"],"invented alternate P3 rail")
        doccounter[doc]+=1
        by[s["icpn"]]=s
    require(dict(doccounter)==lk["document_exact_counts"],
            "official document/source split count drift")
    out=[];matched=set()
    for old in old_build():
        r=dict(old)
        for key in EXTRA:r[key]=""
        ev=by.get(old["icpn"])
        if ev:
            require(old["identity_state"]=="ADMITTED" and
                    old["working_vdd_state"]=="UNKNOWN" and
                    old["vdda_state"]=="UNKNOWN" and
                    old["io_supply_state"]=="UNKNOWN" and
                    not old["working_vdd"] and not old["vdda"] and not old["io_supply"] and
                    int(old["flash"].split()[0])==int(ev["flash_kb"]),
                    "original exact manufacturer part flash/power field conflict: "+old["icpn"])
            r["working_vdd"]=lk["voltage_vdd"];r["working_vdd_unit"]="V";r["working_vdd_state"]="VERIFIED"
            r["vdda"]=lk["vdda_constraint"];r["vdda_state"]="VERIFIED"
            r["io_supply"]=lk["io_dual"] if ev["gpio_power_mode"]=="VDD_P3_DUAL_MODE" else lk["io_default"]
            r["io_supply_state"]="VERIFIED"
            r.update(operating_source_doc_v23=ev["document_id"],
              operating_source_uri_v23=ev["document_uri"],
              operating_source_revision_v23=ev["document_revision"],
              operating_table_locator_v23=ev["operating_table_locator"],
              io_rail_mode_v23=ev["gpio_power_mode"],
              io_port3_supply_v23=ev["io_supply_port3_extra"],
              usb_analog_supply_v23=ev["usb_analog_vdd"],
              vdda_por_constraint_v23="VDD_ANA must equal VDD at POR",
              operating_source_pdf_sha256_v23="NOT_ARCHIVED")
            matched.add(old["icpn"])
        require(r["identity_state"]==old["identity_state"] and r["phase"]=="1" and
          all(r[k]==old[k] for k in ("base_device","package","pin_count","flash","ram","temperature")),
          "unexpected ICPN admission or Phase2/3 modifications")
        out.append(r)
    require(len(out)==501 and matched==set(by) and len(matched)==119
        and sum(x["identity_state"]=="ADMITTED" for x in out)==224
        and sum(x["identity_state"]=="RESEARCH_ONLY" for x in out)==277,
        "NXP exact 501 / 224 admission policy drift")
    require(sum(1 for x in out if x["io_rail_mode_v23"]=="VDD_P3_DUAL_MODE")==26,
        "conditional P3 rail lost")
    return out

def summary(rows):
    result={"exact_icpn_records":len(rows),
       "identity_admitted":sum(r["identity_state"]=="ADMITTED" for r in rows),
       "fields":{}}
    for k in ATTR:
        t=Counter(r[k+"_state"] for r in rows)
        result["fields"][k]={s:t[s] for s in ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT")}
        require(sum(result["fields"][k].values())==len(rows),"invalid source status totals")
    return result
def stats(rows):
    lock=load();old=old_build()
    return {"schema_version":23,"adr":"ADR-0002","phase":"IC_INFORMATION",
      "manufacturer":"NXP","v22_501_git_blob":lock["baseline_v22_git_blob"],
      "official_119_rail_source_git_blob":lock["exact_119_evidence_git_blob"],
      "exact_official_ordering_code_cross_join":119,
      "document_exact_counts":lock["document_exact_counts"],
      "explicit_independent_vdd_p3_1v2_modes":26,
      "prior_admitted":summary([r for r in old if r["identity_state"]=="ADMITTED"]),
      "current_admitted":summary([r for r in rows if r["identity_state"]=="ADMITTED"]),
      "all_501":summary(rows),"no_original_manufacturer_pdf_binary_sha256":True,
      "voltage_semantics":"Working VDD 1.71–3.6 V normal operation; VDD_ANA conditional VDD±0.1V with POR equal rail; I/O default uses VDD, while 26 A14/15 exact codes explicitly have alternative VDD_P3 normal/1.2V ranges; USB analog is a separate rail and is not generalized to all I/O.",
      "source_scope":"Document applicability and official previous exact manufacturer order-table rows must both match exact admitted SKU and flash. No inference from Absolute Maximum Ratings.",
      "software_flash_programming_supported":None,"physical_site_hil_validated":None}
def verify():
    rows=build()
    require(LEDGER.read_bytes()==dump(rows,header(BEFORE)+list(EXTRA)),
            "v23 501 exact source output mismatch")
    require(json.loads(METRICS.read_text(encoding="utf-8"))==stats(rows),
            "v23 field coverage and rail semantics mismatch")
    print("NXP_PHASE1_V23_PASS admitted=224, exact-MCX-A=119 VDD/VDD_ANA/GPIO rails, 26 dual P3, unchanged 501/Production/Programming/HIL")
if __name__=="__main__":verify()

#!/usr/bin/env python3
"""NXP Phase 1 v16: exact K32L2Ax datasheet SRAM/VDD/VDDA; K32L2B remain unknown."""
from collections import Counter
import csv, io, json
from pathlib import Path
from nxp_phase1_pin_package_v15 import (
    LEDGER as V15_CSV,build as v15_build,csv_bytes as v15_csv,git_blob
)

HERE=Path(__file__).resolve().parent
LOCK=HERE/"nxp-phase1-k32l2a-datasheet-lock-v16.json"
LEDGER=HERE/"nxp-501-phase1-k32l2a-enriched-v16.csv"
METRICS=HERE/"nxp-phase1-k32l2a-coverage-v16.json"
EXTRA=("k32l2ax_exact_datasheet_identified","k32l2ax_ram_document_page",
       "k32l2ax_voltage_document_page","k32l2b_pdf_inaccessible_reason")
BASE=("icpn identity_state cohort original_disposition source_file source_file_git_blob "
      "manufacturer_uri source_observation_sha256 source_document_reference field_source_scope "
      "base_device base_device_state package package_state pin_count pin_count_state flash flash_unit flash_state "
      "ram ram_unit ram_state working_vdd working_vdd_unit working_vdd_state io_supply io_supply_state "
      "vdda vdda_state temperature temperature_state phase document_id document_revision document_uri "
      "document_page_evidence commercial_suffix_evidence_uri original_document_sha256 "
      "phase1_evidence_scope field_evidence_note "
      "peripheral_terminal_count thermal_pad_count thermal_pad_contact_number "
      "thermal_pad_net electrical_contact_count_including_pad manufacturer_commercial_package_alias "
      "package_outline_ref source_reconciliation_reference pin_count_semantics").split()
COLS=BASE+list(EXTRA)
ATTRS=("base_device","package","pin_count","flash","ram","working_vdd","io_supply","vdda","temperature")

def must(test,why):
    if not test:raise ValueError(why)

def load():
    lock=json.loads(LOCK.read_text(encoding="utf-8"))
    must(lock["schema_version"]==16 and lock["adr"]=="ADR-0002"
         and lock["active_phase"]=="IC_INFORMATION","Phase scope not authorized")
    must(lock["input_v15_ledger_git_blob"]==git_blob(V15_CSV.read_bytes())
       and V15_CSV.read_bytes()==v15_csv(v15_build()),
       "previous 501 exact source observations changed")
    specs=lock["K32L2Ax"]
    must(len(specs["known_exact_icpns"])==4 and specs["ram_kb_for_exact"]==128
       and specs["vdd_voltage_min"]==specs["vdda_voltage_min"]==1.71
       and specs["vdd_voltage_max"]==specs["vdda_voltage_max"]==3.6
       and specs["max_vdd_vdda_diff_absolute_volts"]==0.1,
       "K32L2Ax source specs changed")
    must(specs["source_original_pdf_sha256"] is None
       and lock["K32L2B3x"]["unavailable_original_pdf_sha256"] is None,
       "falsely archived original PDF bytes")
    return lock

def build():
    lock=load()
    specific=lock["K32L2Ax"]["known_exact_icpns"]
    output=[]
    a=0;b=0
    for old in v15_build():
        row=dict(old)
        for key in EXTRA:row[key]=""
        if row["icpn"] in specific:
            a+=1
            must(row["identity_state"]=="ADMITTED" and
              row["ram_state"]==row["working_vdd_state"]==row["vdda_state"]=="UNKNOWN"
              and row["flash"]==specific[row["icpn"]],
              "source original identity/Flash mismatch: "+row["icpn"])
            row.update(
              ram="128",ram_unit="KB (NXP K32L2Ax Table 1)",ram_state="VERIFIED",
              working_vdd="1.71 to 3.6",working_vdd_unit="V",working_vdd_state="VERIFIED",
              vdda="1.71 to 3.6 V; |VDD-VDDA| <= 0.1 V",vdda_state="VERIFIED",
              document_id="K32L2Ax",document_revision="Rev 3 02/2021",
              document_uri="https://www.nxp.com/docs/en/data-sheet/K32L2Ax.pdf",
              document_page_evidence="Table 1 ordering information printed page 5: exact ICPN/Flash/SRAM; Table 12 operating requirements printed page 36: VDD VDDA and differential",
              phase1_evidence_scope="OFFICIAL_NXP_EXACT_ORDERING_TABLE_AND_ELECTRICAL_REQUIREMENTS",
              field_evidence_note="K32L2Ax datasheet exact SKU SRAM 128 KB; independent VDD/VDDA 1.71-3.6V with |VDD-VDDA|<=0.1V. No separately evidenced I/O supply rail; remain UNKNOWN. No software/physical qualification.",
              k32l2ax_exact_datasheet_identified="true",
              k32l2ax_ram_document_page="Table 1 p5",k32l2ax_voltage_document_page="Table 12 p36")
        elif row["icpn"].startswith("K32L2B") and row["identity_state"]=="ADMITTED":
            b+=1
            must(row["ram_state"]==row["working_vdd_state"]==row["vdda_state"]=="UNKNOWN",
                 "K32L2B prior fields changed, review source before reclassifying")
            row["k32l2b_pdf_inaccessible_reason"]="Official product page identifies K32L2B3x Rev3 exact parts, but manufacturer-hosted PDF not presently accessible; maintain prior UNKNOWN SRAM/VDD/VDDA until original source verified."
        output.append(row)
    must(len(output)==501 and (a,b)==(4,12),"K32L2A 4 / K32L2B 12 source scope drift")
    must(all(r["phase"]=="1" for r in output),"Phase2/3 leaked")
    must(sum(r["identity_state"]=="ADMITTED" for r in output)==224
          and sum(r["identity_state"]=="RESEARCH_ONLY" for r in output)==277,
          "research admissions altered")
    return output

def to_csv(rows):
    f=io.StringIO(newline="")
    writer=csv.DictWriter(f,fieldnames=COLS,lineterminator="\n")
    writer.writeheader();writer.writerows(rows)
    return f.getvalue().encode("utf-8")

def summary(rows):
    x={"exact_icpn_records":len(rows),"identity_admitted":sum(r["identity_state"]=="ADMITTED" for r in rows),"fields":{}}
    for k in ATTRS:
        c=Counter(r[k+"_state"] for r in rows)
        x["fields"][k]={z:c[z] for z in ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT")}
        must(sum(x["fields"][k].values())==len(rows),"field denominator drift")
    return x

def report(rows):
    lock=load()
    return {"schema_version":16,"phase":"IC_INFORMATION","manufacturer":"NXP",
     "bounded_original_exact_icpns":501,
     "input_v15_source_ledger_git_blob":lock["input_v15_ledger_git_blob"],
     "existing_production_identity":summary([r for r in rows if r["identity_state"]=="ADMITTED"]),
     "pending_manufacturer_research":summary([r for r in rows if r["identity_state"]=="RESEARCH_ONLY"]),
     "all":summary(rows),
     "new_official_exact_K32L2Ax_spec_rows":4,"K32L2B_source_exception_rows":12,
     "new_software_support_or_hil_admissions":0,"pdf_original_bytes_archived":False,
     "software_supported_product_scope":None,"physical_site_socket_compatibility_scope":None,
     "evidence_limitations":"Exact four K32L2A official NXP PDF Table1 p5 and Table12 p36 manually verified; PDF original bytes not durably archived. 12 K32L2B official source index known but manufacturer PDF inaccessible, no field-value promotions.",
     "units":"preserve original KB/kB wording without unjustified binary unit conversions"}
def verify():
    rows=build()
    must(LEDGER.read_bytes()==to_csv(rows),"501-row K32L2 Phase1 audit mismatch")
    must(json.loads(METRICS.read_text(encoding="utf-8"))==report(rows),
        "K32L2 exact four-field source coverage mismatch")
    print("NXP_PHASE1_V16_PASS exact=501 K32L2A=4 VDD/VDDA/RAM; K32L2B=12 blocked, no software/HIL admissions")
if __name__=="__main__":verify()

#!/usr/bin/env python3
"""NXP ADR-0002 Phase1 v15: original official LPC84x 32+1 pad semantics."""
import csv, io, json
from collections import Counter
from pathlib import Path
from nxp_phase1_datasheet_v14 import CSV as V14_CSV, enrich as v14_enrich, to_csv as v14_csv, git_blob

HERE=Path(__file__).resolve().parent
LOCK=HERE/"nxp-phase1-pin-package-evidence-v15.json"
LEDGER=HERE/"nxp-501-phase1-pin-package-reconciled-v15.csv"
METRICS=HERE/"nxp-phase1-pin-package-coverage-v15.json"
EXTRA=("peripheral_terminal_count","thermal_pad_count","thermal_pad_contact_number",
       "thermal_pad_net","electrical_contact_count_including_pad",
       "manufacturer_commercial_package_alias","package_outline_ref",
       "source_reconciliation_reference","pin_count_semantics")
BASE=("icpn identity_state cohort original_disposition source_file source_file_git_blob "
      "manufacturer_uri source_observation_sha256 source_document_reference field_source_scope "
      "base_device base_device_state package package_state pin_count pin_count_state flash flash_unit flash_state "
      "ram ram_unit ram_state working_vdd working_vdd_unit working_vdd_state io_supply io_supply_state "
      "vdda vdda_state temperature temperature_state phase document_id document_revision document_uri "
      "document_page_evidence commercial_suffix_evidence_uri original_document_sha256 "
      "phase1_evidence_scope field_evidence_note").split()
COLUMNS=BASE+list(EXTRA)
SPEC=("base_device","package","pin_count","flash","ram","working_vdd","io_supply","vdda","temperature")

def require(t,m):
    if not t:raise ValueError(m)

def load():
    d=json.loads(LOCK.read_text(encoding="utf-8"))
    require(d["schema_version"]==15 and d["phase"]=="IC_INFORMATION" and d["adr"]=="ADR-0002",
            "Phases 2/3 or incompatible schema")
    require(d["input_v14_ledger_git_blob"]==git_blob(V14_CSV.read_bytes())
            and V14_CSV.read_bytes()==v14_csv(v14_enrich()),"v14 original source evidence drift")
    require(len(d["jhi33_exact_skus"])==5 and len(set(d["jhi33_exact_skus"]))==5,
            "source conflict count changed")
    i=d["interpretation"]
    require(i==dict(canonical_package="HVQFN33",commercial_alias="HVQFN32",
        peripheral_terminal_count=32,exposed_pad_count=1,center_pad_number=33,
        center_pad_net="VSS",electrical_contacts_with_pad=33),
        "Pin/pad interpretation changed")
    require(d["source_original_pdf_bytes_archived"] is False
        and d["source_original_pdf_sha256"] is None,
        "false original-PDF digest qualification")
    return d

def build():
    d=load()
    fixed=set(d["jhi33_exact_skus"])
    out=[]
    count=0
    for old in v14_enrich():
        row=dict(old)
        for name in EXTRA:row[name]=""
        if row["icpn"] in fixed:
            count+=1
            require(row["icpn"].startswith(("LPC844","LPC845")) and "JHI33" in row["icpn"]
                and row["package"]=="HVQFN33" and row["pin_count"]=="33"
                and row["package_state"]==row["pin_count_state"]=="CONFLICT",
                "v14 source mismatch or already promoted")
            row.update(
              package_state="VERIFIED",pin_count="32",pin_count_state="VERIFIED",
              peripheral_terminal_count="32",thermal_pad_count="1",
              thermal_pad_contact_number="33",thermal_pad_net="VSS",
              electrical_contact_count_including_pad="33",
              manufacturer_commercial_package_alias="HVQFN32",
              package_outline_ref="SOT617-11; LPC84x Rev 2.1 Figure 42 page 85",
              source_reconciliation_reference="LPC84x Rev 2.1 Table 1 p4 HVQFN33/33 terminals; Figure 7 p11 pad #33 VSS; Figure 42 p85 32 peripheral terminals; NXP LPC84x Package/Quality page alias HVQFN32",
              pin_count_semantics="32 numbered perimeter package contacts; #33 central exposed VSS thermal pad tracked independently"
            )
            row["document_page_evidence"] += "; Figure 7 page 11 center VSS #33; Figure 42 page 85 32 perimeter terminals"
            row["field_evidence_note"]="Package naming reconciled without treating 32 versus 33 as a silicon conflict: NXP datasheet package HVQFN33 = 32 peripheral contacts + one center ground pad #33; NXP Quality-tab lists perimeter package as HVQFN32. Pin Count is peripheral contacts (32). Adapter pad qualification remains Phase 3."
        out.append(row)
    require(len(out)==501 and count==5,"manufacturer 501 identities / 5 exact JHI33 source change")
    require(all(x["identity_state"]==old["identity_state"]
                and x["phase"]=="1" for x,old in zip(out,v14_enrich())),
            "unapproved identity admission or Phase2/3 contamination")
    require(not any(x["package_state"]=="CONFLICT" or x["pin_count_state"]=="CONFLICT"
                    for x in out),"package conflict falsely left unresolved")
    return out

def csv_bytes(rows):
    s=io.StringIO(newline="")
    w=csv.DictWriter(s,fieldnames=COLUMNS,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return s.getvalue().encode("utf-8")

def group(rows):
    out={"exact_icpn_records":len(rows),"identity_admitted":sum(x["identity_state"]=="ADMITTED" for x in rows),"fields":{}}
    for f in SPEC:
        ct=Counter(x[f+"_state"] for x in rows)
        out["fields"][f]={k:ct[k] for k in ("VERIFIED","PARTIAL","UNKNOWN","CONFLICT")}
        require(sum(out["fields"][f].values())==len(rows),"invalid coverage denominator")
    return out

def report(rows):
    d=load()
    return {"schema_version":15,"phase":"IC_INFORMATION","manufacturer":"NXP",
      "cohort":"same 501 source-bounded commercial code observations",
      "input_v14_source_ledger_git_blob":d["input_v14_ledger_git_blob"],
      "existing_production_identity":group([r for r in rows if r["identity_state"]=="ADMITTED"]),
      "pending_manufacturer_research":group([r for r in rows if r["identity_state"]=="RESEARCH_ONLY"]),
      "all":group(rows),"reconciled_dual_naming_exact_skus":5,
      "unresolved_package_nomenclature_conflicts_in_current_snapshot":0,
      "physical_peripheral_contacts_for_jhi33":32,"center_ground_thermal_pad_count_for_jhi33":1,
      "previous_v14_source_disagreement_retained":True,
      "original_pdf_sha256_archived":False,
      "source_evidence_completeness":"Official document URL + revision + Fig. 7/42 + Quality tab noted; original PDF bytes not stored/locked",
      "software_qualified_exact_icpns":None,"physical_hil_qualified_configurations":None,
      "source_semantics":"Pin Count=perimeter package contacts, excludes center thermal exposed ground pad. HVQFN33 is NXP datasheet package name and HVQFN32 vendor marketplace alias. A documented 32+1 naming reconciliation is not a missing or incompatible pin layout."}

def verify():
    rows=build()
    require(LEDGER.read_bytes()==csv_bytes(rows),"v15 exact source-derived CSV mismatch")
    require(json.loads(METRICS.read_text(encoding="utf-8"))==report(rows),
            "v15 per-field coverage mismatch")
    print("NXP_PHASE1_V15_PASS exact=501, JHI33=5, perimeter=32, center VSS pad=1; package conflicts reconciled, Phase2/3 untouched")
if __name__=="__main__":verify()

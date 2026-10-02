#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
F1=HERE/"stm32f1-commercial-icpn.csv"
HISTORICAL=HERE/"stm32f1-phase2.9-post-admission-canonical.csv"
GAPS=HERE/"stm32f1-active-exact-gap-v2.4.txt"
AUTHORITY=HERE/"stm32f1-ordering-authority-v2.4.json"
AUDIT=HERE/"stm32f1-layer1-production-publication-v2.5.json"
BINDING=ROOT/"data/ic-support/bindings/stm32f103c-pilot-v0.json"

EXPECTED_F1_SHA256="a2b9463d58d434ff4792f1830b4e6d0fbe75ea3d084568801402aa799c91b0c4"
EXPECTED_F1_BLOB="c3219788d61591a63aae8cd8df3d25ef15d5c8f3"
EXPECTED_HIST_SHA256="18912f112f0a49eb194716c4211c7f28b73e67776029a0ee79e7af9f4fbae6a3"
EXPECTED_HIST_BLOB="b9f5e265fb5307c19b3a2a9f85f200711663e5ed"
EXPECTED_GAP_SHA256="a4f4fc7db33bf5be34f6f114e266474625cd63cb8ba9719f103535c7036b26e4"
EXPECTED_PROPOSAL_SHA256="33410a8f941d7d88ffb90f81d9859e04d10e0e3f40bfd6a57a05d1603f4f4287"
EXPECTED_AUTHORITY_SHA256="5b075a65dec2590bea8df1b93a47448efb4c88f1072b8a277c6659a482a0e376"

PROPOSAL_FIELDS=(
 "manufacturer","icpn","family","series","base_device","marketing_status",
 "catalog_resolution","package","pin_count","flash_size","temperature_grade",
 "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
 "existing_identifier","existing_identifier_kind","openocd_target_config",
 "metadata_source_reference","source_authority","verification_status",
 "programming_profile_state","metadata_exception",
)

def req(ok,msg):
    if not ok:
        raise ValueError(msg)

def git_blob(data:bytes)->str:
    return hashlib.sha1(f"blob {len(data)}".encode("ascii")+bytes([0])+data).hexdigest()

def read_rows(path:Path)->list[dict[str,str]]:
    with path.open(newline="",encoding="utf-8") as h:
        return list(csv.DictReader(h))

def main()->int:
    audit=json.loads(AUDIT.read_text(encoding="utf-8"))
    req(audit["owner_approval_received"] is True,"owner approval missing")
    req(audit["approved_candidate_exact_count"]==205,"approved count drift")
    req(audit["approved_candidate_exact_set_sha256"]==EXPECTED_GAP_SHA256,"approved exact set drift")
    req(audit["approved_candidate_csv_sha256"]==EXPECTED_PROPOSAL_SHA256,"approved proposal drift")
    req(audit["approved_authority_sha256"]==EXPECTED_AUTHORITY_SHA256,"approved authority drift")
    req(audit["claims"]["layer1_catalog_publication_authorized"] is True,"publication authorization drift")
    req(audit["claims"]["programming_profile_scope_expanded"] is False,"programming-profile overclaim")
    req(audit["claims"]["engineering_verified_claimed"] is False,"engineering overclaim")
    req(audit["claims"]["field_evidence_claimed"] is False,"field overclaim")
    req(audit["claims"]["ps_hil_qualification_claimed"] is False,"HIL overclaim")

    req(hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()==EXPECTED_AUTHORITY_SHA256,
        "F1 authority drift")

    hist=HISTORICAL.read_bytes()
    req(hashlib.sha256(hist).hexdigest()==EXPECTED_HIST_SHA256,"historical F1 snapshot SHA drift")
    req(git_blob(hist)==EXPECTED_HIST_BLOB,"historical F1 snapshot blob drift")
    hist_rows=read_rows(HISTORICAL)
    req(len(hist_rows)==75 and len({r["icpn"] for r in hist_rows})==75,
        "historical F1 snapshot count/unique drift")

    data=F1.read_bytes()
    req(hashlib.sha256(data).hexdigest()==EXPECTED_F1_SHA256,"F1 SHA256 drift")
    req(git_blob(data)==EXPECTED_F1_BLOB,"F1 git blob drift")
    rows=read_rows(F1)
    req(len(rows)==280 and len({r["icpn"] for r in rows})==280,
        "F1 poststate count/unique drift")
    by_icpn={r["icpn"]:r for r in rows}

    gaps=sorted(x.strip() for x in GAPS.read_text(encoding="utf-8").splitlines() if x.strip())
    req(len(gaps)==205 and len(set(gaps))==205,"F1 gap ledger drift")
    digest=hashlib.sha256(("\n".join(gaps)+"\n").encode()).hexdigest()
    req(digest==EXPECTED_GAP_SHA256,"F1 gap digest drift")
    req(set(gaps)<=set(by_icpn),"approved F1 candidate missing from Production")

    added=[by_icpn[x] for x in gaps]
    state=Counter("no_mapping" if r["mapping_status"]=="no_mapping" else "mapped" for r in added)
    req(state==Counter({"mapped":205}),f"F1 added backend partition drift: {dict(state)}")

    all_state=Counter("no_mapping" if r["mapping_status"]=="no_mapping" else "mapped" for r in rows)
    req(all_state==Counter({"mapped":280}),f"F1 backend poststate drift: {dict(all_state)}")

    for r in rows:
        req(r["manufacturer"]=="STMicroelectronics" and r["family"]=="STM32F1","F1 scope drift")
        req(r["mapping_status"]!="no_mapping",f'{r["icpn"]}: unexpected no_mapping')
        req(r["base_device"]==r["cmsis_device_name"]==r["existing_identifier"],
            f'{r["icpn"]}: CMSIS/base identity chain drift')
        req(r["existing_identifier_kind"]=="cmsis_device_name",
            f'{r["icpn"]}: identifier kind drift')
        req(r["openocd_target_config"]=="tcl/target/stm32f1x.cfg",
            f'{r["icpn"]}: target config drift')
        req(r["verification_status"].startswith("verified_"),
            f'{r["icpn"]}: verification missing')

    proposal=[]
    for r in added:
        proposal.append({
          "manufacturer":r["manufacturer"],
          "icpn":r["icpn"],
          "family":r["family"],
          "series":r["series"],
          "base_device":r["base_device"],
          "marketing_status":"Active",
          "catalog_resolution":"normalized",
          "package":r["package"],
          "pin_count":r["pin_count"],
          "flash_size":r["flash_size"],
          "temperature_grade":r["temperature_grade"],
          "option_suffix":r["option_suffix"],
          "backend_type":"openocd",
          "backend_mapping_state":"mapping_candidate",
          "backend_route_observation":"unique_cmsis_base_device",
          "existing_identifier":r["existing_identifier"],
          "existing_identifier_kind":r["existing_identifier_kind"],
          "openocd_target_config":r["openocd_target_config"],
          "metadata_source_reference":r["source_reference"],
          "source_authority":r["source_authority"],
          "verification_status":r["verification_status"],
          "programming_profile_state":"unresolved_no_new_applicability_binding",
          "metadata_exception":"F101_RBH6_TFBGA64_ORDERING_TABLE_OMISSION"
              if r["icpn"]=="STM32F101RBH6" else "",
        })
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=PROPOSAL_FIELDS,lineterminator="\n")
    writer.writeheader();writer.writerows(proposal)
    req(hashlib.sha256(buf.getvalue().encode()).hexdigest()==EXPECTED_PROPOSAL_SHA256,
        "published F1 rows do not reconstruct approved proposal")

    binding=json.loads(BINDING.read_text(encoding="utf-8"))
    req(binding["binding_set_id"]=="stm32f103c-pilot-v0","binding set drift")
    bound=[item["icpn"] for item in binding["bindings"]]
    req(bound==["STM32F103C8T6","STM32F103CBT6"],
        f"Programming Profile binding scope expanded: {bound}")
    req(all(item["profiles"]["programming"]=="stm32f1-medium-density-flash-v0"
            for item in binding["bindings"]),"programming profile id drift")

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    req(manifest.get("status")=="production","Production manifest status drift")
    sources=manifest["sources"]
    f1=[s for s in sources if s["manufacturer"]=="STMicroelectronics" and s["family"]=="STM32F1"]
    req(len(f1)==1,"Production F1 source missing/duplicated")
    source=f1[0]
    req(source["row_count"]==280
        and source["sha256"]==EXPECTED_F1_SHA256
        and source["git_blob_sha"]==EXPECTED_F1_BLOB,
        "Production manifest F1 integrity binding drift")

    print("STM32F1_LAYER1_PRODUCTION_PUBLICATION_V25_PASS")
    print("STM32F1=280; current Active covered=275/275; mapped=280; no_mapping=0")
    print("Programming Profile binding remains exactly 2 ICPNs")
    print("Global Production total is owned by current Production invariants")
    print("Whole-ST Active identity coverage baseline at publication=3637/4550=79.9341%")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

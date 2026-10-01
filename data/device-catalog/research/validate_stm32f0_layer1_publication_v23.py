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
F0=HERE/"stm32f0-commercial-icpn.csv"
GAPS=HERE/"stm32f0-active-exact-gap-v2.2.txt"
AUTHORITY=HERE/"stm32f0-ordering-authority-v2.2.json"
AUDIT=HERE/"stm32f0-layer1-production-publication-v2.3.json"

EXPECTED_F0_SHA256="03cc4593ee607162702451caf0be583efcf8eacdde0d63c03918e3333c9cd45e"
EXPECTED_F0_BLOB="a55048aa21d54cb958dad277ee34a0f7f491a123"
EXPECTED_GAP_SHA256="66023d672322045e9301245a3b6c5fcaa5637bbcc6a83ca98919923468d0fdb0"
EXPECTED_PROPOSAL_SHA256="8f876a2b4f127ca2c86705a0589901ce08c373b56015d928a58847b03dbe3c06"
EXPECTED_AUTHORITY_SHA256="986d8cea5d8a68377491c9adc2b6e893b3fdd0f3ce333af822fa7f03b4361e09"

PROPOSAL_FIELDS=(
    "manufacturer","icpn","family","series","base_device","marketing_status",
    "catalog_resolution","package","pin_count","flash_size","temperature_grade",
    "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
    "existing_identifier","openocd_target_config","metadata_source_reference",
    "source_authority","verification_status",
)

def req(ok,msg):
    if not ok:
        raise ValueError(msg)

def git_blob(data:bytes)->str:
    return hashlib.sha1(f"blob {len(data)}".encode("ascii")+bytes([0])+data).hexdigest()

def main()->int:
    audit=json.loads(AUDIT.read_text(encoding="utf-8"))
    req(audit["owner_approval_received"] is True,"owner approval record missing")
    req(audit["approved_candidate_exact_count"]==221,"approved count drift")
    req(audit["approved_candidate_exact_set_sha256"]==EXPECTED_GAP_SHA256,"approved exact-set drift")
    req(audit["approved_candidate_csv_sha256"]==EXPECTED_PROPOSAL_SHA256,"approved proposal digest drift")
    req(audit["approved_authority_sha256"]==EXPECTED_AUTHORITY_SHA256,"approved authority digest drift")
    req(audit["claims"]["layer1_catalog_publication_authorized"] is True,"publication authorization drift")
    req(audit["claims"]["all_added_rows_have_deterministic_openocd_route"] is True,"route claim drift")
    req(audit["claims"]["engineering_verified_claimed"] is False,"engineering overclaim")
    req(audit["claims"]["field_evidence_claimed"] is False,"field evidence overclaim")
    req(audit["claims"]["ps_hil_qualification_claimed"] is False,"HIL overclaim")

    req(hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()==EXPECTED_AUTHORITY_SHA256,
        "F0 ordering authority drift")

    data=F0.read_bytes()
    req(hashlib.sha256(data).hexdigest()==EXPECTED_F0_SHA256,"F0 SHA256 drift")
    req(git_blob(data)==EXPECTED_F0_BLOB,"F0 git blob drift")
    with F0.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    req(len(rows)==263 and len({r["icpn"] for r in rows})==263,
        "F0 poststate count/unique drift")
    by_icpn={r["icpn"]:r for r in rows}

    gaps=sorted(x.strip() for x in GAPS.read_text(encoding="utf-8").splitlines() if x.strip())
    req(len(gaps)==221 and len(set(gaps))==221,"F0 gap ledger drift")
    gap_hash=hashlib.sha256((chr(10).join(gaps)+chr(10)).encode()).hexdigest()
    req(gap_hash==EXPECTED_GAP_SHA256,"F0 gap digest drift")
    req(set(gaps)<=set(by_icpn),"approved F0 candidate missing from Production")

    added=[by_icpn[x] for x in gaps]
    added_state=Counter("no_mapping" if r["mapping_status"]=="no_mapping" else "mapped" for r in added)
    req(added_state==Counter({"mapped":221}),
        f"approved F0 backend partition drift: {dict(added_state)}")
    all_state=Counter("no_mapping" if r["mapping_status"]=="no_mapping" else "mapped" for r in rows)
    req(all_state==Counter({"mapped":263}),
        f"F0 backend poststate drift: {dict(all_state)}")

    for r in rows:
        req(r["manufacturer"]=="STMicroelectronics" and r["family"]=="STM32F0",
            "F0 identity scope drift")
        req(r["verification_status"].startswith("verified_"),
            f'{r["icpn"]}: verification missing')
        req(r["mapping_status"]!="no_mapping",f'{r["icpn"]}: unexpected F0 no_mapping state')
        req(r["openocd_target_config"]=="tcl/target/stm32f0x.cfg",
            f'{r["icpn"]}: mapped F0 target config drift')

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
            "backend_route_observation":"unique_ordering_pattern",
            "existing_identifier":r["existing_identifier"],
            "openocd_target_config":r["openocd_target_config"],
            "metadata_source_reference":r["source_reference"],
            "source_authority":r["source_authority"],
            "verification_status":r["verification_status"],
        })
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=PROPOSAL_FIELDS,lineterminator="\n")
    writer.writeheader()
    writer.writerows(proposal)
    req(hashlib.sha256(buf.getvalue().encode()).hexdigest()==EXPECTED_PROPOSAL_SHA256,
        "published F0 rows do not reconstruct the approved proposal artifact")

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    req(manifest.get("status")=="production","Production manifest status drift")
    f0=[s for s in manifest["sources"]
        if s["manufacturer"]=="STMicroelectronics" and s["family"]=="STM32F0"]
    req(len(f0)==1,"Production F0 source missing/duplicated")
    source=f0[0]
    req(source["row_count"]==263
        and source["sha256"]==EXPECTED_F0_SHA256
        and source["git_blob_sha"]==EXPECTED_F0_BLOB,
        "Production manifest F0 integrity binding drift")

    print("STM32F0_LAYER1_PRODUCTION_PUBLICATION_V23_PASS")
    print("STM32F0=263; mapped=263; no_mapping=0")
    print("Global Production total is owned by current Production invariants")
    print("Whole-ST Active identity coverage baseline at publication=3432/4550=75.4286%")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

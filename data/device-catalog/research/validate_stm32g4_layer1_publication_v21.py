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
G4=HERE/"stm32g4-commercial-icpn.csv"
GAPS=HERE/"stm32g4-active-exact-gap-v2.0.txt"
AUTHORITY=HERE/"stm32g4-ordering-authority-v2.0.json"
AUDIT=HERE/"stm32g4-layer1-production-publication-v2.1.json"

EXPECTED_G4_SHA256="e1d2b369e02560d52d56a91c230eef2cc65b93394a2cfdb41915d5b5407cb2fd"
EXPECTED_G4_BLOB="83a7e6f20256ca10e6fb1c3452bca8c5b9e39f56"
EXPECTED_GAP_SHA256="d6b7f8dbec3869b9e71d414773305b2d7bc2d9a57eb7a2987a8114f14b5bd270"
EXPECTED_PROPOSAL_SHA256="97d1c2725a45decfb4c0c43cb54e68c23e4c6e2b18e0452d7d8f51a47cb51be1"
EXPECTED_AUTHORITY_SHA256="9e8fb79ac60372c3caf4066d15a597ad8953a9043e18a70dcad98a85899c8d7a"

PROPOSAL_FIELDS=(
    "manufacturer","icpn","family","series","base_device","marketing_status",
    "catalog_resolution","package","pin_count","flash_size","temperature_grade",
    "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
    "existing_identifier","openocd_target_config","metadata_source_reference",
    "source_authority","verification_status","metadata_exception",
)

def req(ok,msg):
    if not ok:
        raise ValueError(msg)

def git_blob(data:bytes)->str:
    return hashlib.sha1(f"blob {len(data)}".encode("ascii")+bytes([0])+data).hexdigest()

def main()->int:
    audit=json.loads(AUDIT.read_text(encoding="utf-8"))
    req(audit["owner_approval_received"] is True,"owner approval record missing")
    req(audit["approved_candidate_exact_count"]==248,"approved count drift")
    req(audit["approved_candidate_exact_set_sha256"]==EXPECTED_GAP_SHA256,"approved exact-set drift")
    req(audit["approved_candidate_csv_sha256"]==EXPECTED_PROPOSAL_SHA256,"approved proposal digest drift")
    req(audit["approved_authority_sha256"]==EXPECTED_AUTHORITY_SHA256,"approved authority digest drift")
    req(audit["claims"]["layer1_catalog_publication_authorized"] is True,"publication authorization drift")
    req(audit["claims"]["backend_route_claimed_for_no_mapping_rows"] is False,"backend overclaim")
    req(audit["claims"]["engineering_verified_claimed"] is False,"engineering overclaim")
    req(audit["claims"]["field_evidence_claimed"] is False,"field evidence overclaim")
    req(audit["claims"]["ps_hil_qualification_claimed"] is False,"HIL overclaim")

    req(hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()==EXPECTED_AUTHORITY_SHA256,
        "G4 ordering authority drift")

    data=G4.read_bytes()
    req(hashlib.sha256(data).hexdigest()==EXPECTED_G4_SHA256,"G4 SHA256 drift")
    req(git_blob(data)==EXPECTED_G4_BLOB,"G4 git blob drift")
    with G4.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    req(len(rows)==273 and len({r["icpn"] for r in rows})==273,"G4 poststate count/unique drift")
    by_icpn={r["icpn"]:r for r in rows}

    gaps=sorted(x.strip() for x in GAPS.read_text(encoding="utf-8").splitlines() if x.strip())
    req(len(gaps)==248 and len(set(gaps))==248,"G4 gap ledger drift")
    gap_hash=hashlib.sha256((chr(10).join(gaps)+chr(10)).encode()).hexdigest()
    req(gap_hash==EXPECTED_GAP_SHA256,"G4 gap digest drift")
    req(set(gaps)<=set(by_icpn),"approved G4 candidate missing from Production")

    added=[by_icpn[x] for x in gaps]
    added_state=Counter("no_mapping" if r["mapping_status"]=="no_mapping" else "mapped" for r in added)
    req(added_state==Counter({"mapped":247,"no_mapping":1}),
        f"approved G4 backend partition drift: {dict(added_state)}")
    all_state=Counter("no_mapping" if r["mapping_status"]=="no_mapping" else "mapped" for r in rows)
    req(all_state==Counter({"mapped":272,"no_mapping":1}),
        f"G4 backend poststate drift: {dict(all_state)}")

    no_mapping=[r for r in rows if r["mapping_status"]=="no_mapping"]
    req([r["icpn"] for r in no_mapping]==["STM32G491RCY6TR"],"G4 no_mapping identity drift")
    for r in rows:
        req(r["manufacturer"]=="STMicroelectronics" and r["family"]=="STM32G4",
            "G4 identity scope drift")
        req(r["verification_status"].startswith("verified_"),
            f'{r["icpn"]}: verification missing')
        if r["mapping_status"]=="no_mapping":
            req(not r["openocd_target_config"] and not r["existing_identifier"] and not r["existing_identifier_kind"],
                f'{r["icpn"]}: no_mapping row carries backend route')
        else:
            req(r["openocd_target_config"]=="tcl/target/stm32g4x.cfg",
                f'{r["icpn"]}: mapped G4 target config drift')

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
            "backend_mapping_state":"no_mapping" if r["mapping_status"]=="no_mapping" else "mapping_candidate",
            "backend_route_observation":"unmapped" if r["mapping_status"]=="no_mapping" else "unique_ordering_pattern",
            "existing_identifier":r["existing_identifier"],
            "openocd_target_config":r["openocd_target_config"],
            "metadata_source_reference":r["source_reference"],
            "source_authority":r["source_authority"],
            "verification_status":r["verification_status"],
            "metadata_exception":"G484_UFBGA121_ORDERING_TABLE_OMISSION"
                if r["icpn"]=="STM32G484PEI6" else "",
        })
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=PROPOSAL_FIELDS,lineterminator="\n")
    writer.writeheader()
    writer.writerows(proposal)
    req(hashlib.sha256(buf.getvalue().encode()).hexdigest()==EXPECTED_PROPOSAL_SHA256,
        "published G4 rows do not reconstruct the approved proposal artifact")

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources=manifest["sources"]
    req(len(sources)==23 and sum(int(s["row_count"]) for s in sources)==3290,
        "Production totals drift")
    g4=[s for s in sources if s["manufacturer"]=="STMicroelectronics" and s["family"]=="STM32G4"]
    req(len(g4)==1,"Production G4 source missing/duplicated")
    s=g4[0]
    req(s["row_count"]==273 and s["sha256"]==EXPECTED_G4_SHA256 and s["git_blob_sha"]==EXPECTED_G4_BLOB,
        "Production manifest G4 integrity binding drift")

    print("STM32G4_LAYER1_PRODUCTION_PUBLICATION_V21_PASS")
    print("Production exact=3290; STM32G4=273; mapped=272; no_mapping=1")
    print("Whole-ST Active identity coverage baseline after publication=3211/4550=70.5714%")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

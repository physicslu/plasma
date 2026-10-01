#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
G0=HERE/"stm32g0-commercial-icpn.csv"
GAPS=HERE/"stm32g0-active-exact-gap-v1.5.txt"
AUDIT=HERE/"stm32g0-layer1-production-publication-v1.9.json"

EXPECTED_G0_SHA256="48f097d7d06c1af4497fba4bc3e4b24b50bab120f4fdb98e4e584583ef90c233"
EXPECTED_G0_BLOB="48ee24d55581ebda1ac4386f1f73890b2db058a7"
EXPECTED_GAP_SHA256="a6240e4a34e3834cba7195be306d449386dcac1b3e66189f6bfac8fdc7557a5d"

def req(ok,msg):
    if not ok: raise ValueError(msg)

def git_blob(data:bytes)->str:
    return hashlib.sha1(f"blob {len(data)}".encode("ascii")+bytes([0])+data).hexdigest()

def main():
    audit=json.loads(AUDIT.read_text(encoding="utf-8"))
    req(audit["owner_approval_received"] is True,"owner approval record missing")
    req(audit["approved_candidate_exact_count"]==359,"approved count drift")
    req(audit["approved_candidate_exact_set_sha256"]==EXPECTED_GAP_SHA256,"approved exact set drift")
    req(audit["claims"]["layer1_catalog_publication_authorized"] is True,"publication authorization drift")
    req(audit["claims"]["backend_route_claimed_for_no_mapping_rows"] is False,"backend overclaim")
    req(audit["claims"]["engineering_verified_claimed"] is False,"engineering overclaim")
    req(audit["claims"]["field_evidence_claimed"] is False,"field evidence overclaim")
    req(audit["claims"]["ps_hil_qualification_claimed"] is False,"HIL overclaim")

    data=G0.read_bytes()
    req(hashlib.sha256(data).hexdigest()==EXPECTED_G0_SHA256,"G0 SHA256 drift")
    req(git_blob(data)==EXPECTED_G0_BLOB,"G0 git blob drift")
    with G0.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    req(len(rows)==406 and len({r["icpn"] for r in rows})==406,"G0 poststate count/unique drift")

    gaps=[x.strip() for x in GAPS.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(len(gaps)==359 and len(set(gaps))==359,"gap ledger drift")
    gap_hash=hashlib.sha256(("\\n".join(sorted(gaps))+"\\n").encode()).hexdigest()
    req(gap_hash==EXPECTED_GAP_SHA256,"gap set digest drift")
    by_icpn={r["icpn"]:r for r in rows}
    req(set(gaps) <= set(by_icpn),"approved candidate missing from Production G0")

    added=[by_icpn[x] for x in gaps]
    added_state=Counter("no_mapping" if r["mapping_status"]=="no_mapping" else "mapped" for r in added)
    req(added_state==Counter({"mapped":317,"no_mapping":42}),f"approved backend partition drift: {dict(added_state)}")
    all_state=Counter("no_mapping" if r["mapping_status"]=="no_mapping" else "mapped" for r in rows)
    req(all_state==Counter({"mapped":364,"no_mapping":42}),f"G0 backend poststate drift: {dict(all_state)}")

    for r in rows:
        req(r["manufacturer"]=="STMicroelectronics" and r["family"]=="STM32G0","G0 identity scope drift")
        req(r["verification_status"].startswith("verified_"),f'{r["icpn"]}: verification missing')
        if r["mapping_status"]=="no_mapping":
            req(not r["openocd_target_config"] and not r["existing_identifier"] and not r["existing_identifier_kind"],
                f'{r["icpn"]}: no_mapping row carries a route')
        else:
            req(r["openocd_target_config"]=="tcl/target/stm32g0x.cfg",
                f'{r["icpn"]}: mapped G0 target config drift')

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources=manifest["sources"]
    req(len(sources)==23 and sum(int(s["row_count"]) for s in sources)==3042,"Production totals drift")
    g0=[s for s in sources if s["manufacturer"]=="STMicroelectronics" and s["family"]=="STM32G0"]
    req(len(g0)==1,"Production G0 source missing/duplicated")
    s=g0[0]
    req(s["row_count"]==406 and s["sha256"]==EXPECTED_G0_SHA256 and s["git_blob_sha"]==EXPECTED_G0_BLOB,
        "Production manifest G0 integrity binding drift")

    print("STM32G0_LAYER1_PRODUCTION_PUBLICATION_V19_PASS")
    print("Production exact=3042; STM32G0=406; mapped=364; no_mapping=42")
    print("Whole-ST Active identity coverage baseline after publication=2963/4550=65.1209%")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

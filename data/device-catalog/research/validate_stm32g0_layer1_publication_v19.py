#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, io, json
from collections import Counter
from pathlib import Path

from openocd_backend_evolution_v616 import rewind_v616_backend
from openocd_backend_evolution_v621 import rewind_v621_backend

ROOT=Path(__file__).resolve().parents[3]
HERE=Path(__file__).resolve().parent
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
G0=HERE/"stm32g0-commercial-icpn.csv"
GAPS=HERE/"stm32g0-active-exact-gap-v1.5.txt"
AUDIT=HERE/"stm32g0-layer1-production-publication-v1.9.json"

EXPECTED_G0_SHA256="f858b5befc228e9ed9d288606c2f19d42303d5cff19b603dd5af165f010ba855"
EXPECTED_G0_BLOB="4b1758ee6ca91a814ad128585a871843d4d0afd4"
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
    with G0.open(newline="",encoding="utf-8") as f:
        rows=list(csv.DictReader(f))
    v616_current_rows=rewind_v621_backend(rows,"STM32G0")
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=list(v616_current_rows[0]),lineterminator="\n")
    writer.writeheader(); writer.writerows(v616_current_rows)
    v616_current_data=buf.getvalue().encode()
    req(hashlib.sha256(v616_current_data).hexdigest()==EXPECTED_G0_SHA256,
        "G0 post-v6.16 historical snapshot SHA256 drift")
    req(git_blob(v616_current_data)==EXPECTED_G0_BLOB,
        "G0 post-v6.16 historical snapshot git blob drift")
    publication_rows=rewind_v616_backend(v616_current_rows,"STM32G0")
    req(len(rows)==406 and len({r["icpn"] for r in rows})==406,"G0 poststate count/unique drift")

    gaps=[x.strip() for x in GAPS.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(len(gaps)==359 and len(set(gaps))==359,"gap ledger drift")
    gap_hash=hashlib.sha256((chr(10).join(sorted(gaps))+chr(10)).encode()).hexdigest()
    req(gap_hash==EXPECTED_GAP_SHA256,"gap set digest drift")
    by_icpn={r["icpn"]:r for r in rows}
    publication_by_icpn={r["icpn"]:r for r in publication_rows}
    req(set(gaps) <= set(by_icpn),"approved candidate missing from Production G0")

    added=[publication_by_icpn[x] for x in gaps]
    added_state=Counter("no_mapping" if r["mapping_status"]=="no_mapping" else "mapped" for r in added)
    req(added_state==Counter({"mapped":317,"no_mapping":42}),f"approved backend partition drift: {dict(added_state)}")
    all_state=Counter("no_mapping" if r["mapping_status"]=="no_mapping" else "mapped" for r in publication_rows)
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
    req(manifest.get("status")=="production","Production manifest status drift")
    sources=manifest["sources"]
    g0=[s for s in sources if s["manufacturer"]=="STMicroelectronics" and s["family"]=="STM32G0"]
    req(len(g0)==1,"Production G0 source missing/duplicated")
    s=g0[0]
    req(s["row_count"]==406
        and s["sha256"]==hashlib.sha256(data).hexdigest()
        and s["git_blob_sha"]==git_blob(data),
        "Production manifest G0 current integrity binding drift")

    print("STM32G0_LAYER1_PRODUCTION_PUBLICATION_V19_PASS")
    print("STM32G0=406; mapped=364; no_mapping=42; global Production total owned by current invariants")
    print("Whole-ST Active identity coverage baseline after publication=2963/4550=65.1209%")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

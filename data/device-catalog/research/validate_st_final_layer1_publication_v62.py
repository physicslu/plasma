#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
GAP=HERE/"st-final-active-tail-gap-v6.0.txt"
PROPOSAL=HERE/"st-final-layer1-admission-proposal-v6.1.json"
PUBLICATION=HERE/"st-final-layer1-production-publication-v6.2.json"

FAMILIES={
    "STM32F4":{
        "path":HERE/"stm32f4-commercial-icpn.csv","before":384,"after":387,
        "old_blob":"2f2a9edec7f7a9024a184ec363d5dd1b9d8c8863",
        "old_sha":"3ab4793d67f1b70e8c8f4c883bd9c24430f25b7a11a199ba32bb50fc48f39359",
        "new_blob":"8983052017cca2c98caaaf899359c2fead33f40d",
        "new_sha":"6a2fa67f58f4edc7bcf1c79a7077ca5e954c74ad2e223f0effdb600dc948d1cd",
        "delta":3,
    },
    "STM32L4":{
        "path":HERE/"stm32l4-commercial-icpn.csv","before":446,"after":449,
        "old_blob":"6cbb7ee5f5189c7d510623940a8945a2bde38399",
        "old_sha":"f9ab12f70221a7a6fd934e977d2bed2fed7bdca8fdee9208aaf0a5082533793c",
        "new_blob":"a39514712d8e27be344bd5837813d1c9d19c34c6",
        "new_sha":"64e5f493581c5a2a06d86490c704dcb79f744369f1ddb8349f20a956b145f70f",
        "delta":3,
    },
    "STM32L1":{
        "path":HERE/"stm32l1-commercial-icpn.csv","before":144,"after":146,
        "old_blob":"8c4ff4b3331f6fe21f04c117fa952802ed587f71",
        "old_sha":"72fcaf7e50537749f101e80cab7a403f3b3878006fe4019b99b99dadd2f409ec",
        "new_blob":"a8120b7064832f4db81850e3e4764a13ef531754",
        "new_sha":"ae0b13da9282d64b17d182af14ae9d151a55a512879b34cd20c810ea926699da",
        "delta":2,
    },
    "STM32U3":{
        "path":HERE/"stm32u3-commercial-icpn.csv","before":106,"after":107,
        "old_blob":"c35e5e4e10c6c514ee82b099cc7ca3d1b7cf79af",
        "old_sha":"171cc7344ee65da9fd89052f2e7a0f0cd6e9ccbc8da02d20f8e33bbc1c1eeaff",
        "new_blob":"5913ed0ff3817b41dd81f12edead60e9dead32ee",
        "new_sha":"49a6a72460d8f025ab5fb7bfe30a2eb372e4255143b6d3345c083f3fab831f4e",
        "delta":1,
    },
}

EXPECTED_GAP_SHA="891831ec21f6f65e5332667bf30440f321039740709d697312afd38a821ac801"

def blob(raw:bytes)->str:
    return hashlib.sha1(b"blob "+str(len(raw)).encode()+b"\0"+raw).hexdigest()

def req(ok:bool,msg:str)->None:
    if not ok:
        raise SystemExit(msg)

def rows_and_raw(path:Path):
    raw=path.read_bytes()
    rows=list(csv.DictReader(io.StringIO(raw.decode("utf-8"))))
    return rows,raw

def main()->int:
    gap=[x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(len(gap)==9 and gap==sorted(gap),"v6.2 gap ledger drift")
    req(hashlib.sha256(("\n".join(gap)+"\n").encode()).hexdigest()==EXPECTED_GAP_SHA,
        "v6.2 gap digest drift")
    gap_set=set(gap)

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources=manifest["sources"]
    req(len(sources)==28,"v6.2 Production source-count drift")
    req(sum(int(s["row_count"]) for s in sources)==4629,"v6.2 Production exact-total drift")

    all_delta=[]
    for family,spec in FAMILIES.items():
        rows,raw=rows_and_raw(spec["path"])
        req(len(rows)==spec["after"],f"{family}: current row-count drift")
        req(len({r["icpn"] for r in rows})==spec["after"],f"{family}: duplicate identity")
        req(hashlib.sha256(raw).hexdigest()==spec["new_sha"],f"{family}: current SHA drift")
        req(blob(raw)==spec["new_blob"],f"{family}: current blob drift")

        delta=[r for r in rows if r["icpn"] in gap_set]
        req(len(delta)==spec["delta"],f"{family}: delta cardinality drift")
        all_delta.extend(delta)
        req(all(
            r["mapping_status"]=="no_mapping"
            and r["existing_identifier"]==""
            and r["existing_identifier_kind"]==""
            and r["openocd_target_config"]==""
            for r in delta
        ),f"{family}: v6.2 delta inherited backend mapping")

        # Remove only v6.2 rows and require the historical family file to be byte-identical.
        header=raw.decode("utf-8").splitlines()[0]
        historical_lines=[
            line for line in raw.decode("utf-8").splitlines()[1:]
            if line.split(",",2)[1] not in gap_set
        ]
        historical=(header+"\n"+"\n".join(historical_lines)+"\n").encode()
        req(len(historical_lines)==spec["before"],f"{family}: historical subset row-count drift")
        req(hashlib.sha256(historical).hexdigest()==spec["old_sha"],f"{family}: historical subset SHA drift")
        req(blob(historical)==spec["old_blob"],f"{family}: historical subset blob drift")

        src=[s for s in sources if s.get("manufacturer")=="STMicroelectronics" and s.get("family")==family]
        req(len(src)==1,f"{family}: manifest source missing/duplicated")
        req(src[0]["row_count"]==spec["after"],f"{family}: manifest row-count drift")
        req(src[0]["sha256"]==spec["new_sha"],f"{family}: manifest SHA binding drift")
        req(src[0]["git_blob_sha"]==spec["new_blob"],f"{family}: manifest blob binding drift")

    req(len(all_delta)==9 and {r["icpn"] for r in all_delta}==gap_set,
        "v6.2 delta exact set drift")
    req(all(r["source_authority"]=="STMicroelectronics official" for r in all_delta),
        "v6.2 delta source authority drift")
    req(all(r["verification_status"].startswith("verified_") for r in all_delta),
        "v6.2 delta verification provenance missing")

    proposal=json.loads(PROPOSAL.read_text(encoding="utf-8"))
    pub=json.loads(PUBLICATION.read_text(encoding="utf-8"))
    req(proposal["proposal_id"]=="st-final-layer1-admission-proposal-v6.1","proposal identity drift")
    req(proposal["proposal_addition_count"]==9,"proposal cardinality drift")
    req(proposal["proposal_exact_set_sha256"]==EXPECTED_GAP_SHA,"proposal exact-set drift")
    req(proposal["backend_state_for_new_rows"]=={"no_mapping":9},"proposal backend boundary drift")
    req(proposal["existing_family_backend_mapping_inherited"] is False,
        "proposal family mapping inheritance drift")

    req(pub["owner_approval_received"] is True,"v6.2 owner approval missing")
    req(pub["production_poststate"]=={"exact_total":4629,"source_count":28},
        "v6.2 publication poststate drift")
    req(pub["catalog_backend_state_after"]=={"mapped":3673,"no_mapping":956},
        "v6.2 backend partition drift")
    cov=pub["coverage_effect"]
    req(cov["whole_st_active_exact_denominator"]==4550,"v6.2 denominator drift")
    req(cov["whole_st_active_intersection_after"]==4550,"v6.2 intersection drift")
    req(cov["whole_st_active_gap_after"]==0,"v6.2 residual gap drift")
    req(cov["whole_st_active_identity_coverage_after_percent"]==100.0,
        "v6.2 coverage percent drift")
    for key in (
        "backend_scope_evaluated_for_9_additions",
        "existing_family_backend_mapping_inherited_by_9_additions",
        "backend_type_claimed_for_no_mapping_rows",
        "backend_route_claimed_for_no_mapping_rows",
        "programming_profile_scope_expanded",
        "engineering_verified_claimed",
        "field_evidence_claimed",
        "ps_hil_qualification_claimed",
    ):
        req(pub["claims"][key] is False,f"v6.2 overclaim: {key}")

    print("ST_FINAL_LAYER1_PRODUCTION_PUBLICATION_V62_PASS")
    print("Production=4629; sources=28; backend=3673 mapped / 956 no_mapping")
    print("Scoped ST Active identity coverage=4550/4550=100%")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

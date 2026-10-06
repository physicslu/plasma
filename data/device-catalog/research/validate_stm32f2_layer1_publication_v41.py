#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent

MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
F2 = HERE / "stm32f2-commercial-icpn.csv"
ACTIVE = HERE / "st-stm32f2-active-exact-mpn-v3.8.txt"
GAP = HERE / "stm32f2-active-exact-gap-v3.8.txt"
AUTHORITY = HERE / "stm32f2-ordering-authority-v3.9.json"
PROPOSAL_LOCK = HERE / "stm32f2-layer1-admission-proposal-v4.0.json"
AUDIT = HERE / "stm32f2-layer1-production-publication-v4.1.json"

EXPECTED_F2_SHA256 = "c2e07ea181b88cfeca2772e7d0c4b00d1a0529805e5e82f3d9af8a7a981de5b6"
EXPECTED_F2_BLOB = "15072e5a816f1749cd476aa85c6d27b94ae4aa74"
EXPECTED_ACTIVE_SHA256 = "60bf4cfcc07c5ec13bb11b290ea5e71da95f56f0fc4b1cdc2a05beaabe17986a"
EXPECTED_GAP_SHA256 = "1ba037ac5bba68ab4907742e97be0d9d56fd15f5e32b89899a67359c6703f584"
EXPECTED_PROPOSAL_SHA256 = "8bd6dce8d0e6f1d976a7708ac7afef785d214797567c12ef6a56bbc63d31e2a3"
EXPECTED_AUTHORITY_SHA256 = "b4dbee7bc5c22d9b4d472637af9d32fdb54c22fb5e554a3e817db4ec716b4abd"

PROPOSAL_FIELDS = (
    "manufacturer","icpn","family","series","base_device","marketing_status",
    "catalog_resolution","package","pin_count","flash_size","temperature_grade",
    "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
    "existing_identifier","existing_identifier_kind","openocd_target_config",
    "metadata_source_reference","source_authority","verification_status",
    "programming_profile_state","metadata_exception",
)

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)

def read_rows(path: Path) -> list[dict[str,str]]:
    with path.open(newline="", encoding="utf-8") as h:
        return list(csv.DictReader(h))

def lines(path: Path) -> list[str]:
    return sorted(x.strip() for x in path.read_text(encoding="utf-8").splitlines() if x.strip())

def digest_lines(rows: list[str]) -> str:
    return hashlib.sha256(("\n".join(rows)+"\n").encode()).hexdigest()

def git_blob(data: bytes) -> str:
    return hashlib.sha1(f"blob {len(data)}".encode("ascii")+bytes([0])+data).hexdigest()

def reconstruct_proposal(rows: list[dict[str,str]]) -> bytes:
    out=[]
    for row in sorted(rows,key=lambda r:r["icpn"]):
        out.append({
            "manufacturer":row["manufacturer"],"icpn":row["icpn"],"family":row["family"],
            "series":row["series"],"base_device":row["base_device"],"marketing_status":"Active",
            "catalog_resolution":"normalized","package":row["package"],"pin_count":row["pin_count"],
            "flash_size":row["flash_size"],"temperature_grade":row["temperature_grade"],
            "option_suffix":row["option_suffix"],"backend_type":"openocd",
            "backend_mapping_state":"no_mapping",
            "backend_route_observation":"backend_not_evaluated_for_layer1_catalog_only_scope",
            "existing_identifier":"","existing_identifier_kind":"","openocd_target_config":"",
            "metadata_source_reference":row["source_reference"],
            "source_authority":row["source_authority"],
            "verification_status":row["verification_status"],
            "programming_profile_state":"unresolved_no_applicability_binding",
            "metadata_exception":"",
        })
    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=PROPOSAL_FIELDS,lineterminator="\n")
    w.writeheader(); w.writerows(out)
    return buf.getvalue().encode()

def main() -> int:
    audit=json.loads(AUDIT.read_text(encoding="utf-8"))
    req(audit["owner_approval_received"] is True,"owner approval missing")
    req(audit["approved_proposal_id"]=="stm32f2-layer1-admission-proposal-v4.0","proposal id drift")
    req(audit["approved_proposal_pr"]==722,"proposal PR drift")
    req(audit["approved_proposal_head_sha"]=="6af8e7fe3a7e95f6ed08d703fcce2e8372e0a959","proposal head drift")
    req(audit["approved_proposal_merge_commit"]=="91c2d178b4a49a367cd41143e48014ffc814b253","proposal merge drift")
    req(audit["approved_proposal_workflow_run_id"]==37417332738,"proposal run drift")
    req(audit["approved_proposal_artifact_id"]==11391406791,"proposal artifact drift")
    req(audit["approved_proposal_artifact_zip_sha256"]=="afd06d9406e1e5ac31cb054d33932c9f138ed9268e0a499360ff6abacc39b2f4","artifact digest drift")
    req(audit["approved_candidate_exact_count"]==72,"approved count drift")
    req(audit["approved_candidate_exact_set_sha256"]==EXPECTED_GAP_SHA256,"approved exact-set drift")
    req(audit["approved_candidate_csv_sha256"]==EXPECTED_PROPOSAL_SHA256,"approved proposal CSV drift")
    req(audit["approved_authority_sha256"]==EXPECTED_AUTHORITY_SHA256,"approved authority drift")

    claims=audit["claims"]
    req(claims["layer1_catalog_publication_authorized"] is True,"publication authorization missing")
    for key in (
        "backend_scope_evaluated_for_72_additions","backend_route_claimed_for_no_mapping_rows",
        "programming_profile_scope_expanded","engineering_verified_claimed",
        "field_evidence_claimed","ps_hil_qualification_claimed",
    ):
        req(claims[key] is False,f"{key} overclaim")

    proposal=json.loads(PROPOSAL_LOCK.read_text(encoding="utf-8"))
    req(proposal["proposal_exact_set_sha256"]==EXPECTED_GAP_SHA256,"proposal exact-set drift")
    req(proposal["proposal_csv_sha256"]==EXPECTED_PROPOSAL_SHA256,"proposal CSV drift")
    req(proposal["authority_sha256"]==EXPECTED_AUTHORITY_SHA256,"proposal authority drift")
    req(proposal["backend_scope_evaluated"] is False,"proposal backend scope drift")
    req(proposal["backend_state_for_new_rows"]=={"no_mapping":72},"proposal backend state drift")
    req(proposal["metadata_exception_exact_icpns"]==[],"proposal metadata exception drift")
    req(proposal["production_write_authorized"] is False,"research proposal self-authorized")

    req(hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()==EXPECTED_AUTHORITY_SHA256,"authority file drift")

    active=lines(ACTIVE); gap=lines(GAP)
    req(len(active)==105 and len(set(active))==105,"F2 Active count drift")
    req(len(gap)==72 and len(set(gap))==72,"F2 gap count drift")
    req(digest_lines(active)==EXPECTED_ACTIVE_SHA256,"F2 Active digest drift")
    req(digest_lines(gap)==EXPECTED_GAP_SHA256,"F2 gap digest drift")
    legacy=sorted(set(active)-set(gap))
    req(len(legacy)==33,"derived legacy mapped count drift")

    data=F2.read_bytes()
    req(hashlib.sha256(data).hexdigest()==EXPECTED_F2_SHA256,"F2 Production SHA256 drift")
    req(git_blob(data)==EXPECTED_F2_BLOB,"F2 Production git blob drift")
    rows=read_rows(F2)
    req(len(rows)==105 and len({r["icpn"] for r in rows})==105,"F2 Production count/unique drift")
    req(sorted(r["icpn"] for r in rows)==active,"F2 Production identities differ from locked Active set")

    mapped=[r for r in rows if r["mapping_status"]!="no_mapping"]
    unmapped=[r for r in rows if r["mapping_status"]=="no_mapping"]
    req(sorted(r["icpn"] for r in mapped)==legacy,"legacy mapped F2 set drift")
    req(sorted(r["icpn"] for r in unmapped)==gap,"new F2 no_mapping set differs from approved additions")

    for row in mapped:
        req(row["existing_identifier_kind"]=="ordering_pattern",f'{row["icpn"]}: legacy mapping kind drift')
        req(row["mapping_status"]=="deterministic_ordering_pattern",f'{row["icpn"]}: legacy mapping status drift')
        req(row["openocd_target_config"]=="tcl/target/stm32f2x.cfg",f'{row["icpn"]}: legacy route drift')
    for row in unmapped:
        req(not row["cmsis_device_name"] and not row["existing_identifier"] and
            not row["existing_identifier_kind"] and not row["openocd_target_config"],
            f'{row["icpn"]}: no_mapping row carries backend route')
        req(row["source_type"]=="official_st_ordering_information_plus_estore_active_exact_identity",
            f'{row["icpn"]}: source type drift')
        req(row["source_authority"]=="STMicroelectronics official",f'{row["icpn"]}: source authority drift')
        req(row["verification_status"]=="verified_st_ordering_information_codes_plus_current_estore_active_identity",
            f'{row["icpn"]}: verification status drift')

    req(hashlib.sha256(reconstruct_proposal(unmapped)).hexdigest()==EXPECTED_PROPOSAL_SHA256,
        "published F2 additions do not reconstruct approved proposal CSV")

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources=manifest["sources"]
    f2s=[s for s in sources if s["manufacturer"]=="STMicroelectronics" and s["family"]=="STM32F2"]
    req(len(f2s)==1,"Production F2 source missing/duplicated")
    source=f2s[0]
    req(source["row_count"]==105 and source["sha256"]==EXPECTED_F2_SHA256 and
        source["git_blob_sha"]==EXPECTED_F2_BLOB,"Production manifest F2 binding drift")
    current_total=sum(int(s["row_count"]) for s in sources)
    req(len(sources)>=24,"Production source count regressed below F2 publication poststate")
    req(current_total>=4314,"Production exact total regressed below F2 publication poststate")

    backend=Counter()
    for source in sources:
        path=(MANIFEST.parent/source["path"]).resolve()
        for row in read_rows(path):
            backend["no_mapping" if row["mapping_status"]=="no_mapping" else "mapped"]+=1
    req(backend["mapped"]>=3673 and backend["no_mapping"]>=641,
        f"Production backend partition regressed below F2 publication poststate: {dict(backend)}")
    req(backend["mapped"]+backend["no_mapping"]==current_total,
        "current Production backend partition does not equal current exact total")

    req(audit["production_prestate"]=={"exact_total":4242,"source_count":24,"stm32f2_exact":33},"prestate audit drift")
    req(audit["production_poststate"]["exact_total"]==4314 and
        audit["production_poststate"]["source_count"]==24 and
        audit["production_poststate"]["stm32f2_exact"]==105,"poststate audit drift")
    req(audit["stm32f2_backend_state_after"]=={"mapped":33,"no_mapping":72},"F2 backend audit drift")
    req(audit["catalog_backend_state_after"]=={"mapped":3673,"no_mapping":641},"catalog backend audit drift")
    req(audit["coverage_effect"]["whole_st_active_intersection_after"]==4235 and
        audit["coverage_effect"]["whole_st_active_gap_after"]==315 and
        audit["coverage_effect"]["whole_st_active_identity_coverage_after_percent"]==93.0769,
        "coverage audit drift")

    print("STM32F2_LAYER1_PRODUCTION_PUBLICATION_V41_PASS")
    print(f"STM32F2=105; mapped=33; no_mapping=72; current_Production={current_total}; current_sources={len(sources)}")
    print("Production backend partition=3673 mapped / 641 no_mapping")
    print("Whole-ST Active identity coverage=4235/4550=93.0769%")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

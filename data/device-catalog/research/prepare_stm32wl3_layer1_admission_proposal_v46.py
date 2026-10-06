#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from collections import Counter
from pathlib import Path
from typing import Any

import analyze_stm32wl3_metadata_replay_v45 as metadata

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
AUTHORITY = HERE / "stm32wl3-ordering-authority-v4.5.json"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
C5_PUBLICATION = HERE / "stm32c5-layer1-production-publication-v4.4.json"

EXPECTED_ACTIVE = 47
EXPECTED_PRODUCTION_TOTAL = 4486
EXPECTED_SOURCE_COUNT = 25
EXPECTED_ACTIVE_DENOMINATOR = 4550
EXPECTED_ACTIVE_INTERSECTION = 4407

FIELDS = (
    "manufacturer","icpn","family","series","base_device","marketing_status",
    "catalog_resolution","package","pin_count","flash_size","temperature_grade",
    "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
    "existing_identifier","existing_identifier_kind","openocd_target_config",
    "metadata_source_reference","source_authority","verification_status",
    "programming_profile_state","metadata_exception",
)

class ProposalError(RuntimeError):
    pass

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ProposalError(msg)

def production_prestate() -> dict[str, int]:
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources=manifest["sources"]
    total=sum(int(s["row_count"]) for s in sources)
    req(total==EXPECTED_PRODUCTION_TOTAL,f"Production exact total drift: {total}")
    req(len(sources)==EXPECTED_SOURCE_COUNT,f"Production source count drift: {len(sources)}")
    wl3=[s for s in sources if s.get("manufacturer")=="STMicroelectronics" and s.get("family")=="STM32WL3"]
    req(wl3==[],"STM32WL3 unexpectedly already present in Production")
    c5=json.loads(C5_PUBLICATION.read_text(encoding="utf-8"))
    cov=c5["coverage_effect"]
    req(int(cov["whole_st_active_exact_denominator"])==EXPECTED_ACTIVE_DENOMINATOR,
        "whole-ST Active denominator drift")
    req(int(cov["whole_st_active_intersection_after"])==EXPECTED_ACTIVE_INTERSECTION,
        "whole-ST Active intersection prestate drift")
    req(int(cov["whole_st_active_gap_after"])==143,"whole-ST Active gap prestate drift")
    return {
        "production_exact_total":total,
        "production_source_count":len(sources),
        "whole_st_active_exact_denominator":EXPECTED_ACTIVE_DENOMINATOR,
        "whole_st_active_intersection":EXPECTED_ACTIVE_INTERSECTION,
    }

def row_for(decoded: dict[str, Any]) -> dict[str,str]:
    exception=decoded["metadata_exception"]
    return {
        "manufacturer":"STMicroelectronics",
        "icpn":decoded["icpn"],
        "family":"STM32WL3",
        "series":decoded["series"],
        "base_device":decoded["base_device"],
        "marketing_status":"Active",
        "catalog_resolution":"normalized",
        "package":decoded["package"],
        "pin_count":str(decoded["pin_count"]),
        "flash_size":f'{decoded["flash_kib"]} KiB',
        "temperature_grade":decoded["temperature_grade"],
        "option_suffix":decoded["option_suffix"],
        "backend_type":"openocd",
        "backend_mapping_state":"no_mapping",
        "backend_route_observation":"backend_not_evaluated_for_layer1_catalog_only_scope",
        "existing_identifier":"",
        "existing_identifier_kind":"",
        "openocd_target_config":"",
        "metadata_source_reference":decoded["metadata_source_url"],
        "source_authority":"STMicroelectronics official",
        "verification_status":(
            "verified_direct_st_exact_product_metadata_override"
            if exception
            else "verified_st_ordering_information_codes_plus_current_active_exact_identity"
        ),
        "programming_profile_state":"unresolved_no_applicability_binding",
        "metadata_exception":exception,
    }

def render_csv(rows:list[dict[str,str]])->str:
    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return buf.getvalue()

def build()->tuple[list[dict[str,str]],str,dict[str,Any]]:
    pre=production_prestate()
    replay=metadata.analyze()
    authority=metadata.load_authority()
    exact=metadata.load_exact()
    exact_set=set(exact)

    req(replay["metadata_decodable_exact_count"]==EXPECTED_ACTIVE,"WL3 metadata replay incomplete")
    req(replay["metadata_blocked_exact_count"]==0,"WL3 metadata replay blocked identities")
    req(replay["direct_ordering_information_exact_count"]==45,"WL3 direct decode count drift")
    req(replay["bounded_exact_exception_count"]==2,"WL3 exception count drift")
    req(replay["claims"]["backend_scope_evaluated"] is False,"backend scope overclaim")
    req(replay["claims"]["backend_route_ready"] is False,"backend route overclaim")

    decoded=[metadata.decode_one(icpn,authority,exact_set) for icpn in exact]
    rows=[row_for(x) for x in decoded]
    req(len(rows)==EXPECTED_ACTIVE and len({r["icpn"] for r in rows})==EXPECTED_ACTIVE,
        "WL3 proposal count/unique drift")
    req(all(r["backend_mapping_state"]=="no_mapping" and not r["openocd_target_config"] for r in rows),
        "WL3 proposal synthesized backend route")

    csv_text=render_csv(rows)
    exact_hash=hashlib.sha256(("\n".join(exact)+"\n").encode()).hexdigest()
    csv_hash=hashlib.sha256(csv_text.encode()).hexdigest()
    authority_hash=hashlib.sha256(AUTHORITY.read_bytes()).hexdigest()
    intersection=pre["whole_st_active_intersection"]+EXPECTED_ACTIVE

    summary={
        "schema_version":1,
        "proposal_id":"stm32wl3-layer1-admission-proposal-v4.6",
        "record_state":"RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
        "production_write_authorized":False,
        "production_exact_prestate":pre["production_exact_total"],
        "production_source_count_prestate":pre["production_source_count"],
        "production_wl3_exact_prestate":0,
        "current_wl3_active_exact":EXPECTED_ACTIVE,
        "current_wl3_active_intersection_prestate":0,
        "proposal_addition_count":EXPECTED_ACTIVE,
        "proposal_exact_set_sha256":exact_hash,
        "proposal_csv_sha256":csv_hash,
        "authority_id":authority["authority_id"],
        "authority_sha256":authority_hash,
        "layer1_catalog_resolution":{"normalized":EXPECTED_ACTIVE},
        "metadata_direct_ordering_information_exact_count":45,
        "metadata_bounded_exception_exact_count":2,
        "metadata_exception_exact_icpns":replay["bounded_exact_exception_icpns"],
        "backend_scope_evaluated":False,
        "backend_state_for_new_rows":{"no_mapping":EXPECTED_ACTIVE},
        "backend_state_semantics":"no route bound; backend capability not evaluated in catalog-only scope",
        "backend_mapping_required_for_layer1_admission":False,
        "programming_profile_binding_claimed":False,
        "programming_profile_scope_expanded":False,
        "series_counts":dict(sorted(Counter(r["series"] for r in rows).items())),
        "package_counts":dict(sorted(Counter(r["package"] for r in rows).items())),
        "production_wl3_exact_after_if_approved":EXPECTED_ACTIVE,
        "production_source_count_after_if_approved":pre["production_source_count"]+1,
        "wl3_current_active_identity_coverage_after_if_published":"47/47 = 100%",
        "production_exact_after_if_approved":pre["production_exact_total"]+EXPECTED_ACTIVE,
        "whole_st_active_exact_denominator":pre["whole_st_active_exact_denominator"],
        "whole_st_active_intersection_prestate":pre["whole_st_active_intersection"],
        "whole_st_active_intersection_after_if_approved":intersection,
        "whole_st_active_gap_after_if_approved":pre["whole_st_active_exact_denominator"]-intersection,
        "whole_st_active_coverage_after_if_approved_percent":round(
            intersection/pre["whole_st_active_exact_denominator"]*100,4),
        "engineering_verified_claimed":False,
        "field_evidence_claimed":False,
        "ps_hil_claimed":False,
    }
    return rows,csv_text,summary

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--proposal",type=Path)
    p.add_argument("--summary",type=Path)
    args=p.parse_args()
    _,csv_text,summary=build()
    if args.proposal: args.proposal.write_text(csv_text,encoding="utf-8")
    if args.summary: args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("STM32WL3_LAYER1_ADMISSION_PROPOSAL_V46_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

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

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
GAP=HERE/"stm32f1-active-exact-gap-v2.4.txt"
AUTHORITY=HERE/"stm32f1-ordering-authority-v2.4.json"
CANONICAL=HERE/"stm32f1-commercial-icpn.csv"
OPENOCD=HERE/"openocd-parts-canonical.csv"
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_GAP_COUNT=205
EXPECTED_GAP_SHA256="a4f4fc7db33bf5be34f6f114e266474625cd63cb8ba9719f103535c7036b26e4"
EXPECTED_CURRENT_F1=75
EXPECTED_ACTIVE_F1=275
EXPECTED_CURRENT_ACTIVE_INTERSECTION=70

FIELDS=(
 "manufacturer","icpn","family","series","base_device","marketing_status",
 "catalog_resolution","package","pin_count","flash_size","temperature_grade",
 "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
 "existing_identifier","existing_identifier_kind","openocd_target_config",
 "metadata_source_reference","source_authority","verification_status",
 "programming_profile_state","metadata_exception",
)

class RefreshError(RuntimeError):
    pass

def req(ok: bool,msg: str)->None:
    if not ok:
        raise RefreshError(msg)

def read_csv(path: Path)->list[dict[str,str]]:
    with path.open(newline="",encoding="utf-8") as h:
        return list(csv.DictReader(h))

def load_gap()->list[str]:
    values=sorted(x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip())
    req(len(values)==EXPECTED_GAP_COUNT and len(set(values))==EXPECTED_GAP_COUNT,"F1 gap count/unique drift")
    digest=hashlib.sha256(("\n".join(values)+"\n").encode()).hexdigest()
    req(digest==EXPECTED_GAP_SHA256,"F1 gap exact-set digest drift")
    return values

def load_authority()->tuple[dict[str,Any],dict[str,dict[str,Any]],dict[str,dict[str,Any]]]:
    payload=json.loads(AUTHORITY.read_text(encoding="utf-8"))
    req(payload.get("authority_id")=="stm32f1-ordering-authority-v2.4","F1 authority id drift")
    req(payload["governance"]["production_write_authorized"] is False,"research authority cannot authorize Production")
    records=payload["records"]
    req(set(records)=={"STM32F100","STM32F101","STM32F102","STM32F103","STM32F105","STM32F107"},
        "F1 authority series drift")
    exceptions={r["exact_icpn"]:r for r in payload.get("exact_exceptions",[])}
    return payload,records,exceptions

def band_for(rule:dict[str,Any],flash_code:str)->dict[str,Any]:
    hits=[b for b in rule["bands"] if flash_code in b["flash_codes"]]
    req(len(hits)==1,f"flash code {flash_code}: expected one density band, got {len(hits)}")
    return hits[0]

def decode(icpn:str,records:dict[str,dict[str,Any]],exceptions:dict[str,dict[str,Any]])->dict[str,str]:
    req(len(icpn)>=13 and icpn.startswith("STM32F1"),f"{icpn}: invalid F1 exact identity")
    series=icpn[:9]
    req(series in records,f"{icpn}: series outside authority")
    pin_code,flash_code,pkg_code,temp_code=icpn[9],icpn[10],icpn[11],icpn[12]
    tail=icpn[13:]
    base=icpn[:11]
    band=band_for(records[series],flash_code)
    req(tail in band["allowed_tails"],f"{icpn}: option/internal tail {tail!r} outside {band['name']} authority")
    flash=band["flash_kib"].get(flash_code)
    pin=band["pin_count"].get(pin_code)
    temp=band["temperature_c"].get(temp_code)
    req(isinstance(flash,int),f"{icpn}: flash code outside authority")
    req(isinstance(pin,int),f"{icpn}: pin code outside authority")
    req(isinstance(temp,str),f"{icpn}: temperature code outside authority")

    exception=exceptions.get(icpn)
    package=band["package"].get(pkg_code)
    if package is None and exception:
        req(exception["package_code"]==pkg_code,f"{icpn}: exception package code drift")
        package=exception["package"]
        req(int(exception["pin_count"])==pin,f"{icpn}: exception pin count drift")
    req(isinstance(package,str) and package,f"{icpn}: package code outside authority")
    override=band.get("package_pin_overrides",{}).get(f"{pkg_code}/{pin_code}")
    if override:
        package=override

    source=band["source_url"]
    metadata_exception=""
    if exception:
        source=source+";"+exception["source_url"]
        metadata_exception="F101_RBH6_TFBGA64_ORDERING_TABLE_OMISSION"

    return {
      "manufacturer":"STMicroelectronics","icpn":icpn,"family":"STM32F1",
      "series":series,"base_device":base,"marketing_status":"Active",
      "catalog_resolution":"normalized","package":package,"pin_count":str(pin),
      "flash_size":f"{flash} KiB","temperature_grade":temp,"option_suffix":tail,
      "metadata_source_reference":source,"source_authority":"STMicroelectronics official",
      "verification_status":"verified_st_ordering_information_codes_plus_current_estore_active_identity",
      "metadata_exception":metadata_exception,
    }

def mapping_index()->dict[str,dict[str,str]]:
    rows=read_csv(OPENOCD)
    selected=[r for r in rows if
        r.get("vendor")=="STMicroelectronics"
        and r.get("plasma_series")=="STM32F1"
        and r.get("identifier_kind")=="cmsis_device_name"]
    req(len(selected)==95,"F1 guarded CMSIS/base mapping surface drift")
    by={}
    for row in selected:
        key=row["part_number"]
        req(key not in by,f"duplicate F1 CMSIS/base mapping {key}")
        req(row["target_config"]=="tcl/target/stm32f1x.cfg",f"{key}: target config drift")
        by[key]=row
    return by

def build()->tuple[list[dict[str,str]],dict[str,Any]]:
    gaps=load_gap()
    authority,records,exceptions=load_authority()

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    total=sum(int(s["row_count"]) for s in manifest["sources"])
    f1=[s for s in manifest["sources"] if s["manufacturer"]=="STMicroelectronics" and s["family"]=="STM32F1"]
    req(len(f1)==1 and f1[0]["row_count"]==EXPECTED_CURRENT_F1,"current Production F1 prestate drift")
    current=read_csv(CANONICAL)
    req(len(current)==EXPECTED_CURRENT_F1,"F1 canonical prestate drift")
    existing={r["icpn"] for r in current}
    req(existing.isdisjoint(gaps),"F1 gap overlaps current Production")
    req(EXPECTED_CURRENT_ACTIVE_INTERSECTION+len(gaps)==EXPECTED_ACTIVE_F1,"F1 Active-set arithmetic drift")

    mappings=mapping_index()
    proposal=[]
    series_counts=Counter()
    band_counts=Counter()
    package_counts=Counter()
    base_devices=set()
    exceptions_seen=[]
    for icpn in gaps:
        row=decode(icpn,records,exceptions)
        base=row["base_device"]
        req(base in mappings,f"{icpn}: no unique guarded CMSIS/base-device route")
        series_counts[row["series"]]+=1
        base_devices.add(base)
        package_counts[row["package"]]+=1
        band=band_for(records[row["series"]],icpn[10])
        band_counts[f"{row['series']}:{band['name']}"]+=1
        if row["metadata_exception"]:
            exceptions_seen.append(icpn)
        row.update({
          "backend_type":"openocd",
          "backend_mapping_state":"mapping_candidate",
          "backend_route_observation":"unique_cmsis_base_device",
          "existing_identifier":base,
          "existing_identifier_kind":"cmsis_device_name",
          "openocd_target_config":"tcl/target/stm32f1x.cfg",
          "programming_profile_state":"unresolved_no_new_applicability_binding",
        })
        proposal.append(row)

    req(len(proposal)==205,"F1 proposal count drift")
    req(len(base_devices)==77,"F1 gap Base Device count drift")
    req(exceptions_seen==["STM32F101RBH6"],f"F1 exception set drift: {exceptions_seen}")
    proposal.sort(key=lambda r:r["icpn"])

    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader();w.writerows(proposal)
    proposal_bytes=buf.getvalue().encode()

    summary={
      "schema_version":1,
      "proposal_id":"stm32f1-layer1-admission-proposal-v2.4",
      "record_state":"RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
      "production_write_authorized":False,
      "production_exact_prestate":total,
      "production_f1_exact_prestate":EXPECTED_CURRENT_F1,
      "current_active_exact_total":EXPECTED_ACTIVE_F1,
      "current_active_intersection_prestate":EXPECTED_CURRENT_ACTIVE_INTERSECTION,
      "current_production_not_active":EXPECTED_CURRENT_F1-EXPECTED_CURRENT_ACTIVE_INTERSECTION,
      "proposal_addition_count":len(proposal),
      "proposal_unique_base_device_count":len(base_devices),
      "proposal_exact_set_sha256":EXPECTED_GAP_SHA256,
      "proposal_csv_sha256":hashlib.sha256(proposal_bytes).hexdigest(),
      "authority_id":authority["authority_id"],
      "authority_sha256":hashlib.sha256(AUTHORITY.read_bytes()).hexdigest(),
      "backend_state_counts":{"mapping_candidate":205,"no_mapping":0},
      "backend_mapping_kind":"cmsis_device_name",
      "programming_profile_binding_claimed":False,
      "programming_profile_scope_expanded":False,
      "metadata_exception_exact_icpns":exceptions_seen,
      "series_counts":dict(sorted(series_counts.items())),
      "density_band_counts":dict(sorted(band_counts.items())),
      "package_counts":dict(sorted(package_counts.items())),
      "production_f1_exact_after_if_approved":EXPECTED_CURRENT_F1+len(proposal),
      "f1_current_active_identity_coverage_after_if_published":"275/275 = 100%",
      "production_exact_after_if_approved":total+len(proposal),
      "whole_st_active_exact_denominator":4550,
      "whole_st_active_intersection_after_if_approved":3637,
      "whole_st_active_gap_after_if_approved":913,
      "whole_st_active_coverage_after_if_approved_percent":round(3637/4550*100,4),
      "engineering_verified_claimed":False,
      "field_evidence_claimed":False,
      "ps_hil_claimed":False,
    }
    return proposal,summary

def main()->int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--proposal",type=Path)
    ap.add_argument("--summary",type=Path)
    args=ap.parse_args()
    proposal,summary=build()
    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    w.writeheader();w.writerows(proposal)
    if args.proposal:
        args.proposal.write_text(buf.getvalue(),encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("STM32F1_LAYER1_REFRESH_V24_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

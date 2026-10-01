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

from stm32f0_foundation import read_catalog
from stm32f0_phase4_5b_discovery import resolve_mapping

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
GAP=HERE/"stm32f0-active-exact-gap-v2.2.txt"
AUTHORITY=HERE/"stm32f0-ordering-authority-v2.2.json"
CANONICAL=HERE/"stm32f0-commercial-icpn.csv"
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"

EXPECTED_GAP_COUNT=221
EXPECTED_GAP_SHA256="66023d672322045e9301245a3b6c5fcaa5637bbcc6a83ca98919923468d0fdb0"
EXPECTED_CURRENT_F0=42
EXPECTED_ACTIVE_F0=263
EXPECTED_ROUTE_UNIQUE=221

FIELDS=(
 "manufacturer","icpn","family","series","base_device","marketing_status",
 "catalog_resolution","package","pin_count","flash_size","temperature_grade",
 "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
 "existing_identifier","openocd_target_config","metadata_source_reference",
 "source_authority","verification_status",
)

class F0RefreshError(RuntimeError):
    pass

def req(ok: bool,msg: str)->None:
    if not ok:
        raise F0RefreshError(msg)

def load_gap()->list[str]:
    vals=sorted(x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip())
    req(len(vals)==EXPECTED_GAP_COUNT and len(set(vals))==EXPECTED_GAP_COUNT,"F0 gap count/unique drift")
    digest=hashlib.sha256(("\n".join(vals)+"\n").encode()).hexdigest()
    req(digest==EXPECTED_GAP_SHA256,"F0 gap exact-set digest drift")
    return vals

def load_authority()->tuple[dict[str,Any],dict[str,dict[str,Any]]]:
    payload=json.loads(AUTHORITY.read_text(encoding="utf-8"))
    req(payload.get("authority_id")=="stm32f0-ordering-authority-v2.2","authority id drift")
    records={r["series"]:r for r in payload["records"]}
    req(len(records)==13,"F0 authority series count drift")
    req(payload["governance"]["production_write_authorized"] is False,"research authority cannot authorize Production")
    return payload,records

def decode(icpn:str,records:dict[str,dict[str,Any]])->dict[str,str]:
    series=icpn[:9]
    req(series in records,f"{icpn}: series outside authority")
    rule=records[series]
    req(len(icpn)>=13,f"{icpn}: exact identity too short")
    pin_code,flash_code,pkg_code,temp_code=icpn[9],icpn[10],icpn[11],icpn[12]
    option=icpn[13:]
    req(option in {"","TR"},f"{icpn}: unsupported option suffix {option!r}")
    base=icpn[:11]

    flash=rule["flash_kib"].get(flash_code)
    package=rule["package"].get(pkg_code)
    temp=rule["temperature_c"].get(temp_code)
    req(isinstance(flash,int),f"{icpn}: flash code outside authority")
    req(isinstance(package,str),f"{icpn}: package code outside authority")
    req(isinstance(temp,str),f"{icpn}: temperature code outside authority")

    raw_pin=rule["pin_count"].get(pin_code)
    override=rule.get("pin_package_overrides",{}).get(f"{pin_code}/{pkg_code}")
    if isinstance(raw_pin,int):
        pin=raw_pin
    elif isinstance(raw_pin,list):
        req(isinstance(override,int) and override in raw_pin,
            f"{icpn}: ambiguous pin code lacks package-specific authority")
        pin=override
    else:
        raise F0RefreshError(f"{icpn}: pin code outside authority")

    return {
      "manufacturer":"STMicroelectronics","icpn":icpn,"family":"STM32F0",
      "series":series,"base_device":base,"marketing_status":"Active",
      "catalog_resolution":"normalized","package":package,"pin_count":str(pin),
      "flash_size":f"{flash} KiB","temperature_grade":temp,"option_suffix":option,
      "metadata_source_reference":rule["source_url"],
      "source_authority":"STMicroelectronics official",
      "verification_status":"verified_st_ordering_information_codes_plus_current_estore_active_identity",
    }

def build()->tuple[list[dict[str,str]],dict[str,Any]]:
    gaps=load_gap()
    authority,records=load_authority()

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    total=sum(int(s["row_count"]) for s in manifest["sources"])
    g0=[s for s in manifest["sources"] if s["manufacturer"]=="STMicroelectronics" and s["family"]=="STM32F0"]
    req(len(g0)==1 and g0[0]["row_count"]==EXPECTED_CURRENT_F0,"current Production F0 prestate drift")
    with CANONICAL.open(newline="",encoding="utf-8") as h:
        current=list(csv.DictReader(h))
    req(len(current)==EXPECTED_CURRENT_F0,"F0 canonical prestate drift")
    existing={r["icpn"] for r in current}
    req(existing.isdisjoint(gaps),"F0 gap overlaps Production")
    req(len(existing)+len(gaps)==EXPECTED_ACTIVE_F0,"F0 Active arithmetic drift")

    catalog=read_catalog()
    proposal=[]
    route_counts=Counter()
    series_counts=Counter()
    base_devices=set()
    packages=Counter()
    for icpn in gaps:
        row=decode(icpn,records)
        series_counts[row["series"]]+=1
        base_devices.add(row["base_device"])
        packages[row["package"]]+=1
        mapping=resolve_mapping(icpn,catalog)
        if (
            mapping.get("status")=="unique"
            and mapping.get("match_count")==1
            and mapping.get("identifier_kind")=="ordering_pattern"
            and mapping.get("target_configs")==["tcl/target/stm32f0x.cfg"]
        ):
            route_counts["mapping_candidate"]+=1
            row.update({
              "backend_type":"openocd",
              "backend_mapping_state":"mapping_candidate",
              "backend_route_observation":"unique_ordering_pattern",
              "existing_identifier":str(mapping["existing_identifier"]),
              "openocd_target_config":"tcl/target/stm32f0x.cfg",
            })
        else:
            route_counts["no_mapping"]+=1
            row.update({
              "backend_type":"openocd","backend_mapping_state":"no_mapping",
              "backend_route_observation":"unmapped","existing_identifier":"",
              "openocd_target_config":"",
            })
        proposal.append(row)

    req(route_counts==Counter({"mapping_candidate":EXPECTED_ROUTE_UNIQUE}),
        f"F0 route partition drift: {dict(route_counts)}")
    proposal.sort(key=lambda r:r["icpn"])

    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=FIELDS,lineterminator="\n")
    writer.writeheader(); writer.writerows(proposal)
    csv_bytes=buf.getvalue().encode()

    summary={
      "schema_version":1,
      "proposal_id":"stm32f0-layer1-admission-proposal-v2.2",
      "record_state":"RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
      "production_write_authorized":False,
      "production_exact_prestate":total,
      "production_f0_exact_prestate":EXPECTED_CURRENT_F0,
      "current_active_exact_total":EXPECTED_ACTIVE_F0,
      "proposal_addition_count":len(proposal),
      "proposal_unique_base_device_count":len(base_devices),
      "proposal_exact_set_sha256":EXPECTED_GAP_SHA256,
      "proposal_csv_sha256":hashlib.sha256(csv_bytes).hexdigest(),
      "authority_id":authority["authority_id"],
      "authority_sha256":hashlib.sha256(AUTHORITY.read_bytes()).hexdigest(),
      "backend_state_counts":dict(route_counts),
      "series_counts":dict(sorted(series_counts.items())),
      "package_counts":dict(sorted(packages.items())),
      "catalog_identity_coverage_after_if_published":"263/263 = 100%",
      "production_exact_after_if_approved":total+len(proposal),
      "whole_st_active_exact_denominator":4550,
      "whole_st_active_intersection_after_if_approved":3432,
      "whole_st_active_gap_after_if_approved":1118,
      "whole_st_active_coverage_after_if_approved_percent":round(3432/4550*100,4),
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
    print("STM32F0_LAYER1_REFRESH_V22_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

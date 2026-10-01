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

from stm32g4_foundation import read_catalog
from stm32g4_phase4_9b_discovery import resolve_mapping

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
GAP = HERE / "stm32g4-active-exact-gap-v2.0.txt"
AUTHORITY = HERE / "stm32g4-ordering-authority-v2.0.json"
CANONICAL = HERE / "stm32g4-commercial-icpn.csv"
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
EXPECTED_GAP_COUNT = 248
EXPECTED_GAP_SHA256 = "d6b7f8dbec3869b9e71d414773305b2d7bc2d9a57eb7a2987a8114f14b5bd270"
EXPECTED_CURRENT_G4 = 25
EXPECTED_ACTIVE_G4 = 273
EXPECTED_MAPPED = 247
EXPECTED_NO_MAPPING = {"STM32G491RCY6TR"}
PROPOSAL_FIELDS = (
    "manufacturer","icpn","family","series","base_device","marketing_status",
    "catalog_resolution","package","pin_count","flash_size","temperature_grade",
    "option_suffix","backend_type","backend_mapping_state","backend_route_observation",
    "existing_identifier","openocd_target_config","metadata_source_reference",
    "source_authority","verification_status","metadata_exception",
)

class RefreshError(RuntimeError):
    pass

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise RefreshError(msg)

def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def load_gap() -> list[str]:
    values=[x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(len(values)==EXPECTED_GAP_COUNT and len(set(values))==EXPECTED_GAP_COUNT,"G4 gap count/unique drift")
    normalized=("\n".join(sorted(values))+"\n").encode()
    req(sha256(normalized)==EXPECTED_GAP_SHA256,"G4 gap exact-set digest drift")
    return sorted(values)

def load_authority() -> tuple[dict[str,Any], dict[str,dict[str,Any]], dict[str,dict[str,Any]]]:
    payload=json.loads(AUTHORITY.read_text(encoding="utf-8"))
    req(payload.get("authority_id")=="stm32g4-ordering-authority-v2.0","ordering authority id drift")
    req(payload.get("governance",{}).get("production_write_authorized") is False,"research authority must not authorize Production")
    records={r["series"]:r for r in payload["records"]}
    req(set(records)=={"STM32G431","STM32G441","STM32G473","STM32G474","STM32G483","STM32G484","STM32G491","STM32G4A1"},"G4 authority series drift")
    exceptions={r["exact_icpn"]:r for r in payload.get("exact_exceptions",[])}
    return payload,records,exceptions

def decode(icpn: str, records: dict[str,dict[str,Any]], exceptions: dict[str,dict[str,Any]]) -> dict[str,str]:
    req(icpn.startswith("STM32G4") and len(icpn)>=13,f"{icpn}: invalid G4 exact identity")
    series=icpn[:9]
    req(series in records,f"{icpn}: unsupported series")
    rule=records[series]
    pin_code,flash_code,pkg_code,temp_code=icpn[9],icpn[10],icpn[11],icpn[12]
    option=icpn[13:]
    req(option in {"","TR"},f"{icpn}: unsupported option suffix {option!r}")
    base=icpn[:11]

    flash=rule["flash_kib"].get(flash_code)
    temp=rule["temperature_c"].get(temp_code)
    req(isinstance(flash,int),f"{icpn}: flash code not authorized")
    req(isinstance(temp,str),f"{icpn}: temperature code not authorized")

    exception=exceptions.get(icpn)
    package=rule["package"].get(pkg_code)
    if package is None and exception is not None:
        req(exception.get("package_code")==pkg_code,f"{icpn}: exception package-code mismatch")
        package=exception.get("package")
    req(isinstance(package,str) and package,f"{icpn}: package code not authorized")

    raw_pin=rule["pin_count"].get(pin_code)
    override=rule.get("pin_package_overrides",{}).get(f"{pin_code}/{pkg_code}")
    if isinstance(raw_pin,int):
        pin=raw_pin
    elif isinstance(raw_pin,list):
        req(isinstance(override,int) and override in raw_pin,f"{icpn}: ambiguous pin count lacks package override")
        pin=override
    else:
        raise RefreshError(f"{icpn}: pin code not authorized")
    if exception is not None:
        req(int(exception["pin_count"])==pin,f"{icpn}: exception pin-count mismatch")

    return {
        "manufacturer":"STMicroelectronics",
        "icpn":icpn,
        "family":"STM32G4",
        "series":series,
        "base_device":base,
        "marketing_status":"Active",
        "catalog_resolution":"normalized",
        "package":package,
        "pin_count":str(pin),
        "flash_size":f"{flash} KiB",
        "temperature_grade":temp,
        "option_suffix":option,
        "metadata_source_reference":rule["datasheet_url"] + (f"#exception={exception['authority_section']}" if exception else ""),
        "source_authority":"STMicroelectronics official",
        "verification_status":"verified_st_ordering_information_codes_plus_current_estore_active_identity",
        "metadata_exception":"G484_UFBGA121_ORDERING_TABLE_OMISSION" if exception else "",
    }

def production_state() -> tuple[int,set[str]]:
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources=manifest.get("sources",[])
    total=sum(int(s["row_count"]) for s in sources)
    g4=[s for s in sources if s.get("manufacturer")=="STMicroelectronics" and s.get("family")=="STM32G4"]
    req(len(g4)==1 and g4[0].get("row_count")==EXPECTED_CURRENT_G4,"current Production G4 prestate drift")
    with CANONICAL.open(newline="",encoding="utf-8") as h:
        rows=list(csv.DictReader(h))
    req(len(rows)==EXPECTED_CURRENT_G4,"G4 canonical prestate row-count drift")
    return total,{r["icpn"] for r in rows}

def build() -> tuple[list[dict[str,str]],dict[str,Any]]:
    gaps=load_gap()
    authority,records,exceptions=load_authority()
    total,existing=production_state()
    req(existing.isdisjoint(gaps),"G4 gap overlaps current Production")
    req(len(existing)+len(gaps)==EXPECTED_ACTIVE_G4,"G4 Active total drift")

    catalog=read_catalog()
    proposal=[]
    mapped=0
    no_mapping=[]
    series_counts=Counter()
    package_counts=Counter()
    exception_count=0
    for icpn in gaps:
        row=decode(icpn,records,exceptions)
        series_counts[row["series"]]+=1
        package_counts[row["package"]]+=1
        if row["metadata_exception"]:
            exception_count+=1
        mapping=resolve_mapping(icpn,catalog)
        if (
            mapping.get("status")=="unique"
            and mapping.get("match_count")==1
            and mapping.get("identifier_kind")=="ordering_pattern"
            and mapping.get("target_configs")==["tcl/target/stm32g4x.cfg"]
        ):
            row.update({
                "backend_type":"openocd",
                "backend_mapping_state":"mapping_candidate",
                "backend_route_observation":"unique_ordering_pattern",
                "existing_identifier":str(mapping["existing_identifier"]),
                "openocd_target_config":"tcl/target/stm32g4x.cfg",
            })
            mapped+=1
        else:
            row.update({
                "backend_type":"openocd",
                "backend_mapping_state":"no_mapping",
                "backend_route_observation":"unmapped",
                "existing_identifier":"",
                "openocd_target_config":"",
            })
            no_mapping.append(icpn)
        proposal.append(row)

    req(mapped==EXPECTED_MAPPED,"G4 mapped count drift")
    req(set(no_mapping)==EXPECTED_NO_MAPPING,f"G4 no_mapping set drift: {no_mapping}")
    req(exception_count==1,"G4 metadata exception count drift")
    proposal.sort(key=lambda r:r["icpn"])

    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=PROPOSAL_FIELDS,lineterminator="\n")
    writer.writeheader(); writer.writerows(proposal)
    proposal_bytes=buf.getvalue().encode("utf-8")

    summary={
        "schema_version":1,
        "proposal_id":"stm32g4-layer1-admission-proposal-v2.0",
        "family":"STM32G4",
        "production_write_authorized":False,
        "production_exact_prestate":total,
        "production_g4_exact_prestate":len(existing),
        "current_active_exact_total":EXPECTED_ACTIVE_G4,
        "proposal_addition_count":len(proposal),
        "proposal_exact_set_sha256":EXPECTED_GAP_SHA256,
        "proposal_csv_sha256":sha256(proposal_bytes),
        "authority_id":authority["authority_id"],
        "authority_sha256":sha256(AUTHORITY.read_bytes()),
        "backend_state_counts":{"mapping_candidate":mapped,"no_mapping":len(no_mapping)},
        "no_mapping_exact_icpns":sorted(no_mapping),
        "metadata_exception_count":exception_count,
        "metadata_exception_exact_icpns":sorted(exceptions),
        "series_counts":dict(sorted(series_counts.items())),
        "package_counts":dict(sorted(package_counts.items())),
        "catalog_identity_coverage_after_if_published":"273/273 = 100%",
        "engineering_verified_claimed":False,
        "field_evidence_claimed":False,
        "ps_hil_claimed":False,
    }
    return proposal,summary

def main() -> int:
    ap=argparse.ArgumentParser()
    ap.add_argument("--proposal",type=Path)
    ap.add_argument("--summary",type=Path)
    args=ap.parse_args()
    proposal,summary=build()
    buf=io.StringIO(newline="")
    writer=csv.DictWriter(buf,fieldnames=PROPOSAL_FIELDS,lineterminator="\n")
    writer.writeheader(); writer.writerows(proposal)
    if args.proposal:
        args.proposal.write_text(buf.getvalue(),encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("STM32G4_LAYER1_REFRESH_V20_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

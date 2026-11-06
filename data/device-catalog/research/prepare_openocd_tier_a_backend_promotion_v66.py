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

import qualify_openocd_tier_a_identifiers_v65 as v65

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
V65_LOCK = HERE / "openocd-tier-a-identifier-qualification-v6.5.json"

EXPECTED_PRODUCTION_TOTAL = 4629
EXPECTED_SOURCE_COUNT = 28
EXPECTED_MAPPED_BEFORE = 3673
EXPECTED_NO_MAPPING_BEFORE = 956
EXPECTED_PROMOTION_COUNT = 320
EXPECTED_MAPPED_AFTER = 3993
EXPECTED_NO_MAPPING_AFTER = 636

EXPECTED_FAMILY_PROMOTIONS = {
    "STM32C0": 1,
    "STM32F2": 72,
    "STM32F3": 168,
    "STM32F7": 62,
    "STM32H7": 14,
    "STM32L1": 1,
    "STM32L4": 1,
    "STM32U3": 1,
}

DELTA_FIELDS = (
    "manufacturer","icpn","family","series","base_device",
    "before_mapping_status","after_mapping_status",
    "after_existing_identifier","after_existing_identifier_kind",
    "after_cmsis_device_name","after_openocd_target_config",
    "route_validation_status","programming_profile_state",
    "programming_verified","engineering_verified","hil_verified",
    "production_write_authorized",
)

class ProposalError(RuntimeError):
    pass

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ProposalError(msg)

def read_rows(path: Path) -> tuple[list[str], list[dict[str,str]]]:
    with path.open(newline="",encoding="utf-8") as stream:
        reader=csv.DictReader(stream)
        fields=list(reader.fieldnames or [])
        rows=list(reader)
    return fields,rows

def render(fields:list[str], rows:list[dict[str,str]]) -> str:
    buf=io.StringIO(newline="")
    w=csv.DictWriter(buf,fieldnames=fields,lineterminator="\n")
    w.writeheader()
    w.writerows(rows)
    return buf.getvalue()

def build() -> tuple[list[dict[str,str]],dict[str,str],dict[str,Any]]:
    lock=json.loads(V65_LOCK.read_text(encoding="utf-8"))
    qualified,blocked,_,_,live=v65.build()
    req(lock["identifier_qualified_exact_count"]==EXPECTED_PROMOTION_COUNT,
        "v6.5 frozen qualified count drift")
    req(live["identifier_qualified_exact_count"]==EXPECTED_PROMOTION_COUNT,
        "v6.5 live qualified count drift")
    req(live["qualified_exact_set_sha256"]==lock["qualified_exact_set_sha256"],
        "v6.5 qualified set differs from frozen lock")
    req(live["qualified_csv_sha256"]==lock["qualified_csv_sha256"],
        "v6.5 qualified CSV differs from frozen lock")
    req(len(blocked)==69, "v6.5 blocked partition drift")

    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    sources=manifest["sources"]
    req(len(sources)==EXPECTED_SOURCE_COUNT, "Production source count drift")
    req(sum(int(s["row_count"]) for s in sources)==EXPECTED_PRODUCTION_TOTAL,
        "Production exact total drift")

    by_family={s["family"]:s for s in sources}
    q_by_icpn={r["icpn"]:r for r in qualified}
    q_by_family=Counter(r["family"] for r in qualified)
    req(dict(sorted(q_by_family.items()))==dict(sorted(EXPECTED_FAMILY_PROMOTIONS.items())),
        "v6.5 qualified family partition drift")

    proposed_files: dict[str,str] = {}
    deltas: list[dict[str,str]] = []
    mapped_before=no_mapping_before=0
    mapped_after=no_mapping_after=0

    for source in sources:
        path=(MANIFEST.parent/source["path"]).resolve()
        fields,rows=read_rows(path)
        req(len(rows)==int(source["row_count"]), f"{source['family']}: manifest row count drift")
        changed=0
        proposed=[]
        for original in rows:
            row=dict(original)
            is_no_mapping=row["mapping_status"]=="no_mapping"
            if is_no_mapping:
                no_mapping_before+=1
            else:
                mapped_before+=1

            q=q_by_icpn.get(row["icpn"])
            if q is not None:
                req(row["family"]==q["family"], f"{row['icpn']}: family mismatch")
                req(is_no_mapping, f"{row['icpn']}: v6.5 candidate no longer no_mapping")
                req(row["existing_identifier"]=="", f"{row['icpn']}: prestate identifier not empty")
                req(row["existing_identifier_kind"]=="", f"{row['icpn']}: prestate identifier kind not empty")
                req(row["openocd_target_config"]=="", f"{row['icpn']}: prestate target config not empty")
                req(row.get("cmsis_device_name","")=="", f"{row['icpn']}: prestate CMSIS name not empty")

                kind=q["resolved_existing_identifier_kind"]
                identifier=q["resolved_existing_identifier"]
                target=q["candidate_openocd_target_config"]
                req(kind in {"ordering_pattern","cmsis_device_name"}, f"{row['icpn']}: unsupported identifier kind")
                row["existing_identifier"]=identifier
                row["existing_identifier_kind"]=kind
                row["mapping_status"]=(
                    "deterministic_cmsis_device_name"
                    if kind=="cmsis_device_name"
                    else "deterministic_ordering_pattern"
                )
                row["openocd_target_config"]=target
                row["cmsis_device_name"]=identifier if kind=="cmsis_device_name" else ""
                changed+=1

                deltas.append({
                    "manufacturer":row["manufacturer"],
                    "icpn":row["icpn"],
                    "family":row["family"],
                    "series":row["series"],
                    "base_device":row["base_device"],
                    "before_mapping_status":"no_mapping",
                    "after_mapping_status":row["mapping_status"],
                    "after_existing_identifier":identifier,
                    "after_existing_identifier_kind":kind,
                    "after_cmsis_device_name":row["cmsis_device_name"],
                    "after_openocd_target_config":target,
                    "route_validation_status":q["route_validation_status"],
                    "programming_profile_state":"unresolved",
                    "programming_verified":"false",
                    "engineering_verified":"false",
                    "hil_verified":"false",
                    "production_write_authorized":"false",
                })

            if row["mapping_status"]=="no_mapping":
                no_mapping_after+=1
            else:
                mapped_after+=1
            proposed.append(row)

        if source["family"] in EXPECTED_FAMILY_PROMOTIONS:
            req(changed==EXPECTED_FAMILY_PROMOTIONS[source["family"]],
                f"{source['family']}: proposed promotion count drift: {changed}")
            proposed_files[source["family"]]=render(fields,proposed)
        else:
            req(changed==0, f"{source['family']}: unexpected promotion outside v6.5 set")

    req(len(deltas)==EXPECTED_PROMOTION_COUNT, "promotion delta count drift")
    req(mapped_before==EXPECTED_MAPPED_BEFORE and no_mapping_before==EXPECTED_NO_MAPPING_BEFORE,
        f"Production backend prestate drift: mapped={mapped_before} no_mapping={no_mapping_before}")
    req(mapped_after==EXPECTED_MAPPED_AFTER and no_mapping_after==EXPECTED_NO_MAPPING_AFTER,
        f"proposed backend poststate drift: mapped={mapped_after} no_mapping={no_mapping_after}")
    req(len(proposed_files)==len(EXPECTED_FAMILY_PROMOTIONS), "affected family file set drift")

    deltas.sort(key=lambda r:r["icpn"])
    delta_csv=render(list(DELTA_FIELDS),deltas)
    exact_set_sha=hashlib.sha256(
        ("\n".join(r["icpn"] for r in deltas)+"\n").encode()
    ).hexdigest()
    req(exact_set_sha==lock["qualified_exact_set_sha256"],
        "promotion exact set differs from v6.5 frozen qualified set")

    proposed_file_bindings={}
    for family,text in sorted(proposed_files.items()):
        raw=text.encode()
        proposed_file_bindings[family]={
            "row_count":int(by_family[family]["row_count"]),
            "sha256":hashlib.sha256(raw).hexdigest(),
            "git_blob_sha":hashlib.sha1(
                f"blob {len(raw)}\0".encode("ascii")+raw,
                usedforsecurity=False,
            ).hexdigest(),
        }

    summary={
        "schema_version":1,
        "proposal_id":"openocd-tier-a-backend-promotion-proposal-v6.6",
        "record_state":"RESEARCH_PROPOSAL_REQUIRES_OWNER_APPROVAL",
        "production_write_authorized":False,
        "source_qualification_id":"openocd-tier-a-identifier-qualification-v6.5",
        "promotion_exact_count":EXPECTED_PROMOTION_COUNT,
        "promotion_exact_set_sha256":exact_set_sha,
        "promotion_delta_csv_sha256":hashlib.sha256(delta_csv.encode()).hexdigest(),
        "family_promotion_counts":dict(sorted(EXPECTED_FAMILY_PROMOTIONS.items())),
        "identifier_kind_counts":dict(sorted(Counter(
            r["after_existing_identifier_kind"] for r in deltas
        ).items())),
        "affected_family_source_bindings_after_if_approved":proposed_file_bindings,
        "production_exact_total_before":EXPECTED_PRODUCTION_TOTAL,
        "production_exact_total_after_if_approved":EXPECTED_PRODUCTION_TOTAL,
        "production_source_count_before":EXPECTED_SOURCE_COUNT,
        "production_source_count_after_if_approved":EXPECTED_SOURCE_COUNT,
        "catalog_backend_partition_before":{
            "mapped":EXPECTED_MAPPED_BEFORE,
            "no_mapping":EXPECTED_NO_MAPPING_BEFORE,
        },
        "catalog_backend_partition_after_if_approved":{
            "mapped":EXPECTED_MAPPED_AFTER,
            "no_mapping":EXPECTED_NO_MAPPING_AFTER,
        },
        "active_openocd_route_before":3594,
        "active_openocd_route_after_if_approved":3914,
        "scoped_active_denominator":4550,
        "active_openocd_route_coverage_after_if_approved_percent":86.0220,
        "active_openocd_route_gap_after_if_approved":636,
        "programming_profile_state_for_promotions":"unresolved",
        "route_evidence_validation_status":"not_verified",
        "claims":{
            "programming_verified":False,
            "engineering_verified":False,
            "hil_verified":False,
            "erase_program_verify_success_claimed":False,
            "production_write_authorized":False,
        }
    }
    return deltas,proposed_files,summary

def main()->int:
    p=argparse.ArgumentParser()
    p.add_argument("--delta",type=Path)
    p.add_argument("--summary",type=Path)
    p.add_argument("--patched-dir",type=Path)
    args=p.parse_args()
    deltas,files,summary=build()
    delta_csv=render(list(DELTA_FIELDS),deltas)
    if args.delta:
        args.delta.write_text(delta_csv,encoding="utf-8")
    if args.summary:
        args.summary.write_text(json.dumps(summary,indent=2,sort_keys=True)+"\n",encoding="utf-8")
    if args.patched_dir:
        args.patched_dir.mkdir(parents=True,exist_ok=True)
        manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
        by_family={s["family"]:Path(s["path"]).name for s in manifest["sources"]}
        for family,text in files.items():
            (args.patched_dir/by_family[family]).write_text(text,encoding="utf-8")
    print(json.dumps(summary,indent=2,sort_keys=True))
    print("OPENOCD_TIER_A_BACKEND_PROMOTION_PROPOSAL_V66_PASS")
    return 0

if __name__=="__main__":
    raise SystemExit(main())

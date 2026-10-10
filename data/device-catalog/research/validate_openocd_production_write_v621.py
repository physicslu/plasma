#!/usr/bin/env python3
from __future__ import annotations

import csv,hashlib,io,json
from pathlib import Path

from openocd_backend_evolution_v631 import (
    backend_state as backend_state_v631,
    rewind_v631_backend,
)

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
POLICY=HERE/"openocd-bounded-identifier-bridge-v6.19.json"
EVIDENCE=HERE/"openocd-production-backend-mapping-v6.21.json"

EXPECTED_POST={
    "STM32F3":{
        "sha256":"0c48633a81ff6eb8785d5e730ee06f6f596a30f2264b4fea374d8df62b3f1573",
        "git_blob_sha":"42e3cab58f7863e1cf44502cb15c5d85086e2a0e",
    },
    "STM32G0":{
        "sha256":"8d6a556364835a00aa479434ebd10977721fb61b2d45485e4e662620a33fcdef",
        "git_blob_sha":"504623e5f7dd459336cc805d00af5636901dc19e",
    },
    "STM32L1":{
        "sha256":"8271258806e3ef240c33818c975f0a3928c27312999b4c1c737f7fc3e2a1e99c",
        "git_blob_sha":"ace1ca1d0be56b24e1ab7fc9a388c7da518eeead",
    },
}

def req(ok:bool,msg:str)->None:
    if not ok: raise SystemExit(msg)

def sha256(data:bytes)->str:
    return hashlib.sha256(data).hexdigest()

def git_blob_sha(data:bytes)->str:
    return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data,usedforsecurity=False).hexdigest()

def render(rows:list[dict[str,str]])->bytes:
    s=io.StringIO(newline="")
    w=csv.DictWriter(s,fieldnames=list(rows[0]),lineterminator="\n")
    w.writeheader();w.writerows(rows)
    return s.getvalue().encode()

def main()->int:
    policy=json.loads(POLICY.read_text(encoding="utf-8"))
    evidence=json.loads(EVIDENCE.read_text(encoding="utf-8"))
    manifest=json.loads(MANIFEST.read_text(encoding="utf-8"))
    req(manifest.get("status")=="production","manifest status drift")
    req(len(manifest["sources"])==28,"Production source count drift")
    req(sum(int(s["row_count"]) for s in manifest["sources"])==4629,"Production exact total drift")

    rows_by_icpn={}
    rows_by_family={}
    mapped=no_mapping=0
    for source in manifest["sources"]:
        path=(MANIFEST.parent/source["path"]).resolve()
        raw=path.read_bytes()
        req(source["sha256"]==sha256(raw),f"{source['family']}: current manifest SHA binding drift")
        req(source["git_blob_sha"]==git_blob_sha(raw),f"{source['family']}: current manifest blob binding drift")
        with path.open(newline="",encoding="utf-8") as h:
            rows=list(csv.DictReader(h))
        req(len(rows)==int(source["row_count"]),f"{source['family']}: row-count drift")
        rows_by_family[source["family"]]=rows
        for row in rows:
            req(row["icpn"] not in rows_by_icpn,f"{row['icpn']}: duplicate Production ICPN")
            rows_by_icpn[row["icpn"]]=row
            if row["mapping_status"]=="no_mapping": no_mapping+=1
            else: mapped+=1

    states={
        family:backend_state_v631(rows_by_family[family],family)
        for family in ("STM32F3","STM32F7","STM32G4")
    }
    req(len(set(states.values()))==1,f"v6.31 cross-family partial application: {states}")
    v631_state=next(iter(states.values()))
    req(v631_state in {"pre","post"},f"unexpected v6.31 state: {v631_state}")

    # Reconstruct the exact v6.21 family postimages from today's Production.
    f3_hist=rewind_v631_backend(rows_by_family["STM32F3"],"STM32F3")
    f3_raw=render(f3_hist)
    req(sha256(f3_raw)==EXPECTED_POST["STM32F3"]["sha256"],"STM32F3: v6.21 historical SHA drift")
    req(git_blob_sha(f3_raw)==EXPECTED_POST["STM32F3"]["git_blob_sha"],"STM32F3: v6.21 historical blob drift")
    for family in ("STM32G0","STM32L1"):
        source=next(s for s in manifest["sources"] if s["family"]==family)
        path=(MANIFEST.parent/source["path"]).resolve()
        raw=path.read_bytes()
        req(sha256(raw)==EXPECTED_POST[family]["sha256"],f"{family}: v6.21 historical SHA drift")
        req(git_blob_sha(raw)==EXPECTED_POST[family]["git_blob_sha"],f"{family}: v6.21 historical blob drift")

    bridges=policy["bridges"]
    req(len(bridges)==17,"v6.19 bridge scope drift")
    for icpn,bridge in bridges.items():
        row=rows_by_icpn[icpn]
        req(row["cmsis_device_name"]=="",f"{icpn}: unexpected CMSIS binding")
        req(row["existing_identifier"]==bridge["existing_identifier"],f"{icpn}: identifier drift")
        req(row["existing_identifier_kind"]==bridge["existing_identifier_kind"],f"{icpn}: identifier kind drift")
        req(row["openocd_target_config"]==bridge["openocd_target_config"],f"{icpn}: target config drift")
        req(row["mapping_status"]=="deterministic_ordering_pattern",f"{icpn}: mapping status drift")

    expected_partition=(4061,568) if v631_state=="pre" else (4164,465)
    req((mapped,no_mapping)==expected_partition,
        f"current Production backend partition drift: {(mapped,no_mapping)} != {expected_partition}")

    req(evidence["promotion_exact_count"]==17,"evidence exact count drift")
    req(evidence["poststate"]["mapped"]==4054,"historical evidence mapped drift")
    req(evidence["poststate"]["no_mapping"]==575,"historical evidence no_mapping drift")
    req(evidence["poststate"]["active_openocd_route"]==3975,"historical evidence active route drift")
    req(evidence["poststate"]["active_openocd_route_coverage_percent"]==87.3626,
        "historical evidence coverage drift")

    gov=evidence["governance"]
    req(gov["merge_requires_explicit_owner_approval"] is True,"merge gate opened")
    req(gov["backend_fields_only"] is True,"backend-only boundary drift")
    req(gov["identity_fields_immutable"] is True,"identity immutability drift")
    req(gov["generic_one_char_generalization_authorized"] is False,"generic one-char rule authorized")
    for key in (
        "programming_profile_binding_claimed","programming_verified_claimed",
        "engineering_verified_claimed","hil_verified_claimed",
    ):
        req(gov[key] is False,f"v6.21 overclaim: {key}")

    print("OPENOCD_PRODUCTION_WRITE_V621_PASS")
    print("V631_BACKEND_EVOLUTION_STATE",v631_state)
    return 0

if __name__=="__main__":
    raise SystemExit(main())

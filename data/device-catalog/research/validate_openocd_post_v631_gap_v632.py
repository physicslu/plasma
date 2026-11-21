#!/usr/bin/env python3
from __future__ import annotations
import csv, hashlib, json
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
LEDGER=HERE/"openocd-post-v631-gap-disposition-v6.32.json"
MANIFEST=ROOT/"data/device-catalog/production/icpn-v1-manifest.json"
RUNTIME_GAP=HERE/"st-h5-c5-runtime-gap-v1.json"

EXPECTED={
    "STM32H5": ("stm32h5-commercial-icpn.csv",190,"5d95f712445e94ef800dd54a26739203b2f2b412"),
    "STM32C5": ("stm32c5-commercial-icpn.csv",172,"1e0559ded8cde86a210097d9bcfce34708978e5c"),
    "STM32N6": ("stm32n6-commercial-icpn.csv",32,"937aeb4468fa7babd0c7b84d0bee72468d445002"),
    "STM32WB0": ("stm32wb0-commercial-icpn.csv",24,"b4754420d0a6342f63c3edb368c96fc7f9bf864b"),
    "STM32WL3": ("stm32wl3-commercial-icpn.csv",47,"0a774823e5236e011a105cde355942821e9ebe48"),
}
EXPECTED_MANIFEST_BLOB="3f66a14212fbf82aa9faa16e9434892f649f736d"

def req(ok: bool,msg: str)->None:
    if not ok: raise RuntimeError(msg)

def git_blob_sha(data: bytes)->str:
    return hashlib.sha1(b"blob "+str(len(data)).encode()+b"\0"+data).hexdigest()

def read_rows(path: Path):
    with path.open(newline="",encoding="utf-8") as f:
        return list(csv.DictReader(f))

def validate()->dict:
    ledger=json.loads(LEDGER.read_text(encoding="utf-8"))
    manifest_bytes=MANIFEST.read_bytes()
    req(git_blob_sha(manifest_bytes)==EXPECTED_MANIFEST_BLOB,"manifest blob drift")
    manifest=json.loads(manifest_bytes)
    req(len(manifest["sources"])==28,"Production source count drift")
    req(sum(int(x["row_count"]) for x in manifest["sources"])==4629,"Production total drift")

    runtime=json.loads(RUNTIME_GAP.read_text(encoding="utf-8"))
    base=runtime["catalog_baseline"]
    req((base["mapped"],base["no_mapping"],base["active_openocd_routes"],base["active_denominator"])==(4164,465,4085,4550),"post-v6.31 runtime-gap baseline drift")

    total=0
    exact=set()
    counts={}
    for family,(name,count,blob) in EXPECTED.items():
        path=HERE/name
        data=path.read_bytes()
        req(git_blob_sha(data)==blob,f"{family}: Production blob drift")
        rows=read_rows(path)
        req(len(rows)==count,f"{family}: row count drift")
        req(all(r["family"]==family for r in rows),f"{family}: family drift")
        req(all(r["mapping_status"]=="no_mapping" for r in rows),f"{family}: mapping state changed")
        req(all(not r["openocd_target_config"] for r in rows),f"{family}: unexpected target config")
        for r in rows:
            req(r["icpn"] not in exact,f"duplicate ICPN {r['icpn']}")
            exact.add(r["icpn"])
        total+=len(rows); counts[family]=len(rows)

    req(total==465 and len(exact)==465,"465-row gap cardinality drift")
    req(sum(x["exact_count"] for x in ledger["dispositions"].values())==465,"ledger disposition sum drift")
    req(ledger["totals"]=={"disposition_exact_count":465,"runtime_candidate_exact_count":190,"blocked_backend_exact_count":275},"ledger totals drift")
    req(ledger["dispositions"]["STM32H5"]["disposition"]=="runtime_candidate_not_production_admissible","H5 disposition drift")
    for family in ("STM32C5","STM32N6","STM32WB0","STM32WL3"):
        req(ledger["dispositions"][family]["disposition"].startswith("blocked_"),f"{family}: must remain fail-closed")
    claims=ledger["claims"]
    for field in ("production_write_authorized","programming_profile_verified","electrical_profile_verified","erase_program_verify_qualified","engineering_verified","hil_verified","hardware_runtime_ready"):
        req(claims[field] is False,f"{field}: overclaim")
    return {"result":"PASS","exact_count":total,"family_counts":counts,"runtime_candidate_exact_count":190,"blocked_backend_exact_count":275}

if __name__=="__main__":
    print(json.dumps(validate(),indent=2,sort_keys=True))
    print("OPENOCD_POST_V631_GAP_DISPOSITION_V632_PASS")

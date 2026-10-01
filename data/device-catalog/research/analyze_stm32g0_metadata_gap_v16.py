#!/usr/bin/env python3
from __future__ import annotations
import json
from collections import Counter
from pathlib import Path

from stm32g0_foundation import EXPECTED_SUBFAMILIES
from stm32g0_metadata_policy import (
    DATASHEET_AUTHORITIES, FLASH_BY_CODE, N_VERSION_BASES, OPTION_SUFFIXES,
    PACKAGE_BY_CODE, PIN_COUNT_BY_CODE, SUPPORTED_BASE_DEVICES, TEMPERATURE_BY_CODE,
)

HERE=Path(__file__).resolve().parent
GAPS=HERE/"stm32g0-active-exact-gap-v1.5.txt"

def req(ok,msg):
    if not ok: raise ValueError(msg)

def parse(icpn:str):
    subs=[s for s in EXPECTED_SUBFAMILIES if icpn.startswith(s)]
    req(len(subs)==1,f"{icpn}: subfamily resolution failed")
    sub=subs[0]
    base=icpn[:len(sub)+2]
    suffix=icpn[len(base):]
    req(len(suffix)>=2,f"{icpn}: missing package/temp suffix")
    return sub,base,base[-2],base[-1],suffix[0],suffix[1],suffix[2:]

def analyze():
    gaps=[x.strip() for x in GAPS.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(len(gaps)==359 and len(set(gaps))==359,"G0 gap ledger drift")
    blockers=Counter(); pins=Counter(); flashes=Counter(); packages=Counter(); temps=Counter(); opts=Counter()
    new_bases=set(); n_bases=set(); full=[]
    for icpn in gaps:
        sub,base,pin,flash,pkg,temp,opt=parse(icpn)
        pins[pin]+=1; flashes[flash]+=1; packages[pkg]+=1; temps[temp]+=1; opts[opt]+=1
        checks={
            "base_scope":base in SUPPORTED_BASE_DEVICES,
            "pin_code":pin in PIN_COUNT_BY_CODE,
            "flash_code":flash in FLASH_BY_CODE,
            "package_code":pkg in PACKAGE_BY_CODE,
            "temperature_code":temp in TEMPERATURE_BY_CODE,
            "option_suffix":opt in OPTION_SUFFIXES,
            "n_version_scope":("N" not in opt) or base in N_VERSION_BASES,
        }
        for k,v in checks.items():
            if not v: blockers[k]+=1
        if base not in SUPPORTED_BASE_DEVICES: new_bases.add(base)
        if "N" in opt: n_bases.add(base)
        if all(checks.values()): full.append(icpn)
    req(set(DATASHEET_AUTHORITIES)==set(EXPECTED_SUBFAMILIES),
        "not all G0 subfamilies have a bound ST ordering-information authority")
    return {
      "audit_id":"stm32g0-metadata-policy-gap-v1.6",
      "layer1_gap_exact":359,
      "new_base_device_count":len(new_bases),
      "current_policy_fully_decodable_gap_exact":len(full),
      "current_policy_fully_decodable_gap_identities":full,
      "overlapping_blocker_exact_counts":dict(sorted(blockers.items())),
      "observed_code_counts":{
        "pin_code":dict(sorted(pins.items())),
        "flash_code":dict(sorted(flashes.items())),
        "package_code":dict(sorted(packages.items())),
        "temperature_code":dict(sorted(temps.items())),
        "option_suffix":dict(sorted(opts.items())),
      },
      "n_version_exact_count":sum(v for k,v in opts.items() if "N" in k),
      "n_version_base_count":len(n_bases),
      "ordering_authority_subfamilies_bound":len(DATASHEET_AUTHORITIES),
      "claims":{
        "code_letter_semantics_inferred_from_identity_only":False,
        "production_write_authorized":False,
        "metadata_complete_for_357_new_base_exact_rows":False,
      },
      "next_gate":"Revalidate the 12 bound official ST G0 ordering-information authorities against observed pin/package/N-version codes, then extend metadata policy without making backend route a Layer-1 identity gate."
    }

if __name__=="__main__":
    print(json.dumps(analyze(),indent=2,sort_keys=True))

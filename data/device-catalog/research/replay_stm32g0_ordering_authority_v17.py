#!/usr/bin/env python3
from __future__ import annotations
import csv, json, hashlib
from collections import Counter
from pathlib import Path

HERE=Path(__file__).resolve().parent
AUTH=HERE/"stm32g0-ordering-authority-v1.7.json"
GAPS=HERE/"stm32g0-active-exact-gap-v1.5.txt"
PROD=HERE/"stm32g0-commercial-icpn.csv"
OUT_FIELDS=("manufacturer","icpn","family","series","base_device","package","pin_count",
            "flash_size","temperature_grade","option_suffix","source_type",
            "source_reference","source_authority","verification_status")

def req(ok,msg):
    if not ok: raise ValueError(msg)

def load():
    a=json.loads(AUTH.read_text(encoding="utf-8"))
    req(a["authority_id"]=="stm32g0-ordering-authority-v1.7","authority drift")
    req(len(a["subfamilies"])==12,"subfamily authority count drift")
    gaps=[x.strip() for x in GAPS.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(len(gaps)==359 and len(set(gaps))==359,"gap ledger drift")
    return a,gaps

def decode(icpn,a):
    subs=[s for s in a["subfamilies"] if icpn.startswith(s)]
    req(len(subs)==1,f"{icpn}: subfamily ambiguity")
    sub=subs[0]; rule=a["subfamilies"][sub]
    base=icpn[:len(sub)+2]
    req(len(icpn)>len(base)+1,f"{icpn}: incomplete exact code")
    pin,flash=base[-2],base[-1]
    suffix=icpn[len(base):]
    pkg,temp,opt=suffix[0],suffix[1],suffix[2:]
    req(pin in rule["pin_count"],f"{icpn}: pin code {pin} outside {sub} authority")
    req(flash in rule["flash_kib"],f"{icpn}: flash code {flash} outside {sub} authority")
    req(pkg in rule["package"],f"{icpn}: package code {pkg} outside {sub} authority")
    req(temp in rule["temperature_c"],f"{icpn}: temperature code {temp} outside {sub} authority")
    req(opt in ("","TR","N","NTR"),f"{icpn}: unsupported option suffix {opt!r}")
    if "N" in opt:
        req(rule["n_product_version_allowed"],f"{icpn}: N version outside {sub} authority")
    return {
      "manufacturer":"STMicroelectronics","icpn":icpn,"family":"STM32G0","series":sub,
      "base_device":base,"package":rule["package"][pkg],
      "pin_count":str(rule["pin_count"][pin]),
      "flash_size":f'{rule["flash_kib"][flash]} KiB',
      "temperature_grade":rule["temperature_c"][temp],
      "option_suffix":opt,
      "source_type":"official_st_ordering_information_plus_estore_active_exact_identity",
      "source_reference":rule["source_url"],
      "source_authority":"STMicroelectronics official",
      "verification_status":"verified_st_ordering_information_codes_plus_current_estore_active_identity"
    }

def build():
    a,gaps=load()
    rows=[decode(x,a) for x in gaps]
    req(len({r["icpn"] for r in rows})==359,"decoded duplicate")
    with PROD.open(newline="",encoding="utf-8") as f:
        prod={r["icpn"] for r in csv.DictReader(f)}
    req(not (prod & {r["icpn"] for r in rows}),"candidate overlaps Production")
    base_counts=Counter(r["base_device"] for r in rows)
    series_counts=Counter(r["series"] for r in rows)
    payload="\n".join(r["icpn"] for r in rows)+"\n"
    return rows,{
      "audit_id":"stm32g0-ordering-authority-replay-v1.7",
      "gap_exact_input":359,
      "fully_metadata_decoded_exact":len(rows),
      "unique_base_devices":len(base_counts),
      "series_counts":dict(sorted(series_counts.items())),
      "metadata_candidate_set_sha256":hashlib.sha256(payload.encode()).hexdigest(),
      "production_write_authorized":False,
      "backend_route_gates_metadata_decode":False
    }

def main():
    rows,summary=build()
    print(json.dumps(summary,indent=2,sort_keys=True))
    return 0

if __name__=="__main__":
    raise SystemExit(main())

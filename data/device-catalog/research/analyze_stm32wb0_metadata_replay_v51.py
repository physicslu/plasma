#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EXACT = HERE / "st-stm32wb0-active-exact-mpn-v1.2.txt"
LOCK = HERE / "st-missing-family-active-evidence-lock-v1.2.json"
AUTHORITY = HERE / "stm32wb0-ordering-authority-v5.1.json"

EXPECTED_COUNT = 24
EXPECTED_EXACT_SHA256 = "5f6adbd574ca751487c256a806764b1046cd5150cba757f73fd9d3269d167447"
EXPECTED_SERIES = {
    "STM32WB05N": 4,
    "STM32WB05Z": 4,
    "STM32WB06C": 6,
    "STM32WB07C": 6,
    "STM32WB09E": 4,
}
EXPECTED_PINS = {"32": 10, "36": 6, "48": 4, "49": 4}
EXPECTED_PACKAGES = {"VFQFPN": 14, "WLCSP": 10}
EXPECTED_TEMPS = {"-40 to 105 C": 12, "-40 to 85 C": 12}
EXPECTED_FLASH = {
    "192 KiB": 4,
    "256 KiB": 12,
    "512 KiB": 4,
    "N/A (network coprocessor)": 4,
}

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)

def load_exact() -> list[str]:
    rows = [x.strip().upper() for x in EXACT.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(rows == sorted(rows), "WB0 exact identity ledger must remain sorted")
    req(len(rows) == EXPECTED_COUNT and len(set(rows)) == EXPECTED_COUNT,
        "WB0 exact identity count/unique drift")
    digest = hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()
    req(digest == EXPECTED_EXACT_SHA256, "WB0 exact identity digest drift")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    fam = lock["families"]["STM32WB0"]
    req(fam["exact_active_count"] == EXPECTED_COUNT, "WB0 evidence-lock count drift")
    req(fam["exact_set_sha256"] == EXPECTED_EXACT_SHA256, "WB0 evidence-lock hash drift")
    return rows

def load_authority() -> dict[str, Any]:
    value = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    req(value["schema_version"] == 1, "authority schema drift")
    req(value["authority_id"] == "stm32wb0-ordering-authority-v5.1", "authority id drift")
    req(
        {v["document"] for v in value["documents"].values()}
        == {"DS14620", "DS14591", "DS14676", "DS14210"},
        "WB0 authority document set drift",
    )
    gov = value["governance"]
    req(gov["decode_only_locked_exact_identity_set"] is True, "authority exact-set scope drift")
    req(gov["backend_scope_evaluated"] is False, "metadata replay cannot claim backend evaluation")
    req(gov["programming_profile_scope_expanded"] is False,
        "metadata replay cannot expand Programming Profile scope")
    req(gov["production_write_authorized"] is False,
        "research authority cannot authorize Production")
    return value

def parse_codes(icpn: str) -> dict[str, str]:
    req(icpn.endswith("TR"), f"{icpn}: locked WB0 identity lacks TR suffix")
    core = icpn[:-2]
    req(len(core) == 13, f"{icpn}: unexpected ordering-code length")
    req(core.startswith("STM32WB"), f"{icpn}: non-WB identity")
    return {
        "subfamily": core[7:9],
        "pin_code": core[9],
        "product_code": core[10],
        "package_code": core[11],
        "temperature_code": core[12],
        "packing_code": "TR",
    }

def product_key(codes: dict[str, str]) -> str:
    key = f"STM32WB{codes['subfamily']}{codes['product_code']}"
    req(key in {"STM32WB05N", "STM32WB05Z", "STM32WB06C", "STM32WB07C", "STM32WB09E"},
        f"unsupported WB0 product key {key}")
    return key

def authority_document_for(key: str, authority: dict[str, Any]) -> dict[str, str]:
    if key in {"STM32WB06C", "STM32WB07C"}:
        return authority["documents"]["STM32WB06C_STM32WB07C"]
    return authority["documents"][key]

def decode_one(icpn: str, authority: dict[str, Any], exact_set: set[str]) -> dict[str, Any]:
    req(icpn in exact_set, f"{icpn}: not in locked Active WB0 set")
    codes = parse_codes(icpn)
    key = product_key(codes)
    rule = authority["product_codes"][key]
    req(codes["subfamily"] == rule["subfamily"], f"{icpn}: subfamily authority drift")
    req(codes["product_code"] == rule["product_code"], f"{icpn}: product-code authority drift")

    pair = f"{codes['pin_code']}:{codes['package_code']}"
    req(pair in authority["package_resolution"], f"{icpn}: unknown pin/package pair {pair}")
    physical = authority["package_resolution"][pair]
    req(codes["temperature_code"] in authority["temperature_c"], f"{icpn}: unknown temperature code")
    req(codes["packing_code"] in authority["packing"], f"{icpn}: unknown packing suffix")

    doc = authority_document_for(key, authority)
    return {
        "icpn": icpn,
        "family": "STM32WB0",
        "series": key,
        "base_device": icpn[:-4],
        "package": physical["package"],
        "pin_count": int(physical["pin_count"]),
        "flash_size": rule["flash_size"],
        "temperature_grade": authority["temperature_c"][codes["temperature_code"]],
        "option_suffix": "TR",
        "network_coprocessor": bool(rule["network_coprocessor"]),
        "authority_document": doc["document"],
        "authority_url": doc["url"],
        "metadata_source_url": doc["url"],
        "metadata_basis": "official_st_ordering_information",
        "metadata_exception": "",
    }

def analyze() -> dict[str, Any]:
    exact = load_exact()
    exact_set = set(exact)
    authority = load_authority()
    decoded = [decode_one(icpn, authority, exact_set) for icpn in exact]

    series = dict(sorted(Counter(r["series"] for r in decoded).items()))
    pins = dict(sorted(Counter(str(r["pin_count"]) for r in decoded).items(), key=lambda x: int(x[0])))
    packages = dict(sorted(Counter(r["package"] for r in decoded).items()))
    temps = dict(sorted(Counter(r["temperature_grade"] for r in decoded).items()))
    flash = dict(sorted(Counter(r["flash_size"] for r in decoded).items()))

    req(series == EXPECTED_SERIES, "WB0 series distribution drift")
    req(pins == EXPECTED_PINS, "WB0 physical pin/ball distribution drift")
    req(packages == EXPECTED_PACKAGES, "WB0 package distribution drift")
    req(temps == EXPECTED_TEMPS, "WB0 temperature distribution drift")
    req(flash == EXPECTED_FLASH, "WB0 product/Flash distribution drift")
    req(sum(1 for r in decoded if r["network_coprocessor"]) == 4,
        "WB0 network-coprocessor partition drift")
    req(not any(r["metadata_exception"] for r in decoded),
        "WB0 metadata replay unexpectedly requires exceptions")

    return {
        "audit_id": "stm32wb0-metadata-authority-replay-v5.1",
        "input_active_exact_count": len(exact),
        "metadata_decodable_exact_count": len(decoded),
        "metadata_blocked_exact_count": 0,
        "direct_ordering_information_exact_count": len(decoded),
        "bounded_exact_exception_count": 0,
        "network_coprocessor_exact_count": 4,
        "exact_set_sha256": EXPECTED_EXACT_SHA256,
        "authority_id": authority["authority_id"],
        "authority_sha256": hashlib.sha256(AUTHORITY.read_bytes()).hexdigest(),
        "series_counts": series,
        "physical_pin_counts": pins,
        "package_counts": packages,
        "temperature_counts": temps,
        "flash_or_role_counts": flash,
        "claims": {
            "layer1_identity_set_locked": True,
            "metadata_authority_replay_complete": True,
            "layer1_admission_proposal_ready": True,
            "backend_scope_evaluated": False,
            "backend_route_ready": False,
            "programming_profile_scope_expanded": False,
            "engineering_verified": False,
            "field_evidence": False,
            "ps_hil_qualification": False,
            "production_write_authorized": False
        },
        "next_gate": (
            "Prepare a reviewable 24-row STM32WB0 Layer-1 admission proposal with all "
            "backend routes unbound. Preserve STM32WB05xN network-coprocessor semantics "
            "and do not reinterpret N as Flash density."
        )
    }

if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, sort_keys=True))

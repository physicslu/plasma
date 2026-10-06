#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EXACT = HERE / "st-stm32n6-active-exact-mpn-v1.2.txt"
LOCK = HERE / "st-missing-family-active-evidence-lock-v1.2.json"
AUTHORITY = HERE / "stm32n6-ordering-authority-v4.8.json"

EXPECTED_COUNT = 32
EXPECTED_EXACT_SHA256 = "f3ae0640f7e28c14b40b7b2ff83570e0bd95c7d0bd3bd98baac6edbcfc78bd50"
EXPECTED_SERIES = {"STM32N645": 7, "STM32N647": 7, "STM32N655": 7, "STM32N657": 11}
EXPECTED_PINS = {"142": 5, "169": 9, "178": 5, "198": 4, "223": 5, "264": 4}
EXPECTED_DEDICATED = {"Q": 28, "QG": 4}
EXPECTED_PACKING = {"none": 28, "TR": 4}
EXPECTED_OPTION_SUFFIX = {"Q": 24, "QG": 4, "QTR": 4}
EXPECTED_CRYPTO = {"false": 14, "true": 18}
EXPECTED_NEURAL_ART = {"false": 14, "true": 18}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def load_exact() -> list[str]:
    rows = [x.strip().upper() for x in EXACT.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(rows == sorted(rows), "N6 exact identity ledger must remain sorted")
    req(len(rows) == EXPECTED_COUNT and len(set(rows)) == EXPECTED_COUNT,
        "N6 exact identity count/unique drift")
    digest = hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()
    req(digest == EXPECTED_EXACT_SHA256, "N6 exact identity digest drift")

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    fam = lock["families"]["STM32N6"]
    req(fam["exact_active_count"] == EXPECTED_COUNT, "N6 evidence-lock count drift")
    req(fam["exact_set_sha256"] == EXPECTED_EXACT_SHA256, "N6 evidence-lock hash drift")
    return rows


def load_authority() -> dict[str, Any]:
    value = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    req(value["schema_version"] == 1, "authority schema drift")
    req(value["authority_id"] == "stm32n6-ordering-authority-v4.8", "authority id drift")
    req(value["datasheet"]["document"] == "DS14791", "N6 authority document drift")
    req(value["datasheet"]["revision"] == 11, "N6 authority revision drift")
    gov = value["governance"]
    req(gov["decode_only_locked_exact_identity_set"] is True, "authority exact-set scope drift")
    req(gov["backend_scope_evaluated"] is False, "metadata replay cannot claim backend evaluation")
    req(gov["programming_profile_scope_expanded"] is False,
        "metadata replay cannot expand Programming Profile scope")
    req(gov["production_write_authorized"] is False,
        "research authority cannot authorize Production")
    return value


def parse_codes(icpn: str) -> dict[str, str]:
    core = icpn
    packing = ""
    if core.endswith("TR"):
        packing = "TR"
        core = core[:-2]

    req(core.startswith("STM32N6"), f"{icpn}: non-N6 identity")
    series = core[:9]
    tail = core[9:]
    req(len(tail) in {5, 6}, f"{icpn}: unexpected ordering-code length")

    pin_code = tail[0]
    flash_code = tail[1]
    package_code = tail[2]
    temperature_code = tail[3]
    dedicated_pinout = tail[4:]

    return {
        "series": series,
        "pin_code": pin_code,
        "flash_code": flash_code,
        "package_code": package_code,
        "temperature_code": temperature_code,
        "dedicated_pinout": dedicated_pinout,
        "packing_code": packing,
    }


def decode_one(icpn: str, authority: dict[str, Any], exact_set: set[str]) -> dict[str, Any]:
    req(icpn in exact_set, f"{icpn}: not in locked Active N6 set")
    codes = parse_codes(icpn)
    common = authority["common"]
    series = codes["series"]

    req(series in authority["series"], f"{icpn}: series lacks authority")
    req(codes["pin_code"] in common["pin_codes"], f"{icpn}: unknown pin/ball code")
    req(codes["flash_code"] in common["flash_kib"], f"{icpn}: unknown Flash code")
    req(codes["package_code"] in common["package_codes"], f"{icpn}: unknown package code")
    req(codes["temperature_code"] in common["temperature_c"], f"{icpn}: unknown temperature code")
    req(codes["dedicated_pinout"] in common["dedicated_pinout"],
        f"{icpn}: unknown dedicated pinout")
    req(codes["packing_code"] in common["packing"], f"{icpn}: unknown packing suffix")

    rule = authority["series"][series]
    expected_die = series[7]
    expected_line = series[8]
    req(rule["die_code"] == expected_die, f"{icpn}: die-code authority drift")
    req(rule["line_code"] == expected_line, f"{icpn}: line-code authority drift")

    option_suffix = codes["dedicated_pinout"] + codes["packing_code"]
    return {
        "icpn": icpn,
        "family": "STM32N6",
        "series": series,
        "base_device": series + codes["pin_code"] + codes["flash_code"],
        "package": common["package_codes"][codes["package_code"]],
        "pin_count": int(common["pin_codes"][codes["pin_code"]]),
        "flash_size": common["flash_kib"][codes["flash_code"]],
        "temperature_grade": common["temperature_c"][codes["temperature_code"]],
        "dedicated_pinout": codes["dedicated_pinout"],
        "packing_code": codes["packing_code"],
        "option_suffix": option_suffix,
        "crypto": bool(rule["crypto"]),
        "neural_art": bool(rule["neural_art"]),
        "authority_document": authority["datasheet"]["document"],
        "authority_revision": authority["datasheet"]["revision"],
        "authority_url": authority["datasheet"]["url"],
        "metadata_source_url": authority["datasheet"]["url"],
        "metadata_basis": "official_st_ordering_information",
        "metadata_exception": "",
    }


def analyze() -> dict[str, Any]:
    exact = load_exact()
    exact_set = set(exact)
    authority = load_authority()
    decoded = [decode_one(icpn, authority, exact_set) for icpn in exact]

    series = dict(sorted(Counter(r["series"] for r in decoded).items()))
    pins = dict(sorted(
        Counter(str(r["pin_count"]) for r in decoded).items(),
        key=lambda x: int(x[0]),
    ))
    dedicated = dict(sorted(Counter(r["dedicated_pinout"] for r in decoded).items()))
    packing = dict(sorted(Counter(r["packing_code"] or "none" for r in decoded).items()))
    suffix = dict(sorted(Counter(r["option_suffix"] for r in decoded).items()))
    crypto = dict(sorted(Counter(str(r["crypto"]).lower() for r in decoded).items()))
    neural = dict(sorted(Counter(str(r["neural_art"]).lower() for r in decoded).items()))

    req(series == EXPECTED_SERIES, "N6 series distribution drift")
    req(pins == EXPECTED_PINS, "N6 pin distribution drift")
    req(dedicated == EXPECTED_DEDICATED, "N6 dedicated-pinout distribution drift")
    req(packing == EXPECTED_PACKING, "N6 packing distribution drift")
    req(suffix == EXPECTED_OPTION_SUFFIX, "N6 option-suffix distribution drift")
    req(crypto == EXPECTED_CRYPTO, "N6 crypto distribution drift")
    req(neural == EXPECTED_NEURAL_ART, "N6 Neural-ART distribution drift")
    req(all(r["package"] == "VFBGA" for r in decoded), "N6 package distribution drift")
    req(all(r["flash_size"] == "0-1 KiB" for r in decoded), "N6 Flash metadata drift")
    req(all(r["temperature_grade"] == "-40 to 125 C" for r in decoded),
        "N6 temperature distribution drift")
    req(not any(r["metadata_exception"] for r in decoded),
        "N6 metadata replay unexpectedly requires exceptions")

    return {
        "audit_id": "stm32n6-metadata-authority-replay-v4.8",
        "input_active_exact_count": len(exact),
        "metadata_decodable_exact_count": len(decoded),
        "metadata_blocked_exact_count": 0,
        "direct_ordering_information_exact_count": len(decoded),
        "bounded_exact_exception_count": 0,
        "exact_set_sha256": EXPECTED_EXACT_SHA256,
        "authority_id": authority["authority_id"],
        "authority_sha256": hashlib.sha256(AUTHORITY.read_bytes()).hexdigest(),
        "series_counts": series,
        "pin_counts": pins,
        "dedicated_pinout_counts": dedicated,
        "packing_counts": packing,
        "option_suffix_counts": suffix,
        "crypto_counts": crypto,
        "neural_art_counts": neural,
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
            "production_write_authorized": False,
        },
        "next_gate": (
            "Prepare a reviewable 32-row STM32N6 Layer-1 admission proposal with all "
            "backend routes unbound and Programming Profile unresolved. Production "
            "publication remains a separate explicit owner-approval transaction."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, sort_keys=True))

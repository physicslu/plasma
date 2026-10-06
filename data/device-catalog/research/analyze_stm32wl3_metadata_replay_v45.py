#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EXACT = HERE / "st-stm32wl3-active-exact-mpn-v1.2.txt"
LOCK = HERE / "st-missing-family-active-evidence-lock-v1.2.json"
AUTHORITY = HERE / "stm32wl3-ordering-authority-v4.5.json"

EXPECTED_COUNT = 47
EXPECTED_EXACT_SHA256 = "4d7a67a26dbe6fe65ed492f0143116ae1898e183c9f57001f724a12af654b60d"
EXPECTED_SERIES = {"STM32WL30": 2, "STM32WL31": 4, "STM32WL33": 36, "STM32WL3R": 5}
EXPECTED_PINS = {"32": 27, "48": 20}
EXPECTED_FLASH = {"64 KiB": 17, "128 KiB": 15, "256 KiB": 15}
EXPECTED_TEMP = {"-40 to 85 C": 33, "-40 to 105 C": 14}
EXPECTED_FREQ = {"none": 33, "A": 6, "X": 8}
EXPECTED_SUFFIX = {"none": 20, "TR": 13, "A": 3, "ATR": 3, "X": 7, "XTR": 1}
EXPECTED_EXCEPTIONS = {"STM32WL31C8V6", "STM32WL31CBV6"}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def load_exact() -> list[str]:
    rows = [x.strip().upper() for x in EXACT.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(rows == sorted(rows), "WL3 exact identity ledger must remain sorted")
    req(len(rows) == EXPECTED_COUNT and len(set(rows)) == EXPECTED_COUNT,
        "WL3 exact identity count/unique drift")
    digest = hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()
    req(digest == EXPECTED_EXACT_SHA256, "WL3 exact identity digest drift")

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    fam = lock["families"]["STM32WL3"]
    req(fam["exact_active_count"] == EXPECTED_COUNT, "WL3 evidence-lock count drift")
    req(fam["exact_set_sha256"] == EXPECTED_EXACT_SHA256, "WL3 evidence-lock hash drift")
    return rows


def load_authority() -> dict[str, Any]:
    value = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    req(value["schema_version"] == 1, "authority schema drift")
    req(value["authority_id"] == "stm32wl3-ordering-authority-v4.5", "authority id drift")
    gov = value["governance"]
    req(gov["decode_only_locked_exact_identity_set"] is True, "authority exact-set scope drift")
    req(gov["exception_scope_exact_mpn_only"] is True, "exception scope drift")
    req(gov["backend_scope_evaluated"] is False, "metadata replay cannot claim backend evaluation")
    req(gov["production_write_authorized"] is False, "research authority cannot authorize Production")
    req(set(value["bounded_exact_exceptions"]) == EXPECTED_EXCEPTIONS,
        "WL3 bounded exception set drift")
    return value


def parse_codes(icpn: str) -> dict[str, str]:
    core = icpn
    packing = ""
    if core.endswith("TR"):
        packing = "TR"
        core = core[:-2]
    req(core.startswith("STM32WL3"), f"{icpn}: non-WL3 identity")
    series = core[:9]
    tail = core[9:]
    req(len(tail) in {4, 5}, f"{icpn}: unexpected ordering-code length")
    pin_code, flash_code, package_code, temperature_code = tail[:4]
    frequency_option = tail[4:] if len(tail) == 5 else ""
    return {
        "series": series,
        "pin_code": pin_code,
        "flash_code": flash_code,
        "package_code": package_code,
        "temperature_code": temperature_code,
        "frequency_option": frequency_option,
        "packing_code": packing,
    }


def decode_one(icpn: str, authority: dict[str, Any], exact_set: set[str]) -> dict[str, Any]:
    req(icpn in exact_set, f"{icpn}: not in locked Active WL3 set")
    codes = parse_codes(icpn)
    series = codes["series"]
    req(series in authority["series"], f"{icpn}: series lacks authority")
    rule = authority["series"][series]
    common = authority["common"]

    pin_code = codes["pin_code"]
    exception = authority["bounded_exact_exceptions"].get(icpn)
    if pin_code in rule["pin_codes"]:
        pin_count = int(rule["pin_codes"][pin_code])
        req(exception is None, f"{icpn}: unexpected bounded pin exception")
        metadata_exception = ""
        metadata_basis = "official_st_ordering_information"
        metadata_source_url = rule["url"]
    else:
        req(exception is not None, f"{icpn}: unsupported pin code without exact exception")
        req(exception["field"] == "pin_count", f"{icpn}: exception field drift")
        pin_count = int(exception["value"])
        metadata_exception = "WL31_C_PIN48_EXACT_PRODUCT_EXCEPTION"
        metadata_basis = "official_st_ordering_information_plus_exact_product_pin_exception"
        metadata_source_url = exception["source_url"]

    req(codes["flash_code"] in rule["flash_kib"], f"{icpn}: unknown Flash code")
    req(codes["package_code"] in common["package_codes"], f"{icpn}: unknown package code")
    req(codes["temperature_code"] in common["temperature_c"], f"{icpn}: unknown temperature code")
    req(codes["frequency_option"] in rule["frequency_band_options"],
        f"{icpn}: frequency option outside {series} authority")
    req(codes["packing_code"] in common["packing"], f"{icpn}: unknown packing code")

    option_suffix = codes["frequency_option"] + codes["packing_code"]
    return {
        "icpn": icpn,
        "family": "STM32WL3",
        "series": series,
        "base_device": series + pin_code + codes["flash_code"],
        "package": common["package_codes"][codes["package_code"]],
        "pin_count": pin_count,
        "flash_kib": int(rule["flash_kib"][codes["flash_code"]]),
        "temperature_grade": common["temperature_c"][codes["temperature_code"]],
        "frequency_option": codes["frequency_option"],
        "packing_code": codes["packing_code"],
        "option_suffix": option_suffix,
        "authority_document": rule["document"],
        "authority_revision": rule["revision"],
        "authority_url": rule["url"],
        "metadata_source_url": metadata_source_url,
        "metadata_basis": metadata_basis,
        "metadata_exception": metadata_exception,
    }


def analyze() -> dict[str, Any]:
    exact = load_exact()
    exact_set = set(exact)
    authority = load_authority()
    decoded = [decode_one(icpn, authority, exact_set) for icpn in exact]

    series = dict(sorted(Counter(r["series"] for r in decoded).items()))
    pins = dict(sorted(Counter(str(r["pin_count"]) for r in decoded).items(), key=lambda x: int(x[0])))
    flash = dict(sorted(Counter(f'{r["flash_kib"]} KiB' for r in decoded).items()))
    temps = dict(sorted(Counter(r["temperature_grade"] for r in decoded).items()))
    freq = dict(sorted(Counter(r["frequency_option"] or "none" for r in decoded).items()))
    suffix = dict(sorted(Counter(r["option_suffix"] or "none" for r in decoded).items()))
    exceptions = sorted(r["icpn"] for r in decoded if r["metadata_exception"])

    req(series == EXPECTED_SERIES, "WL3 series distribution drift")
    req(pins == EXPECTED_PINS, "WL3 pin distribution drift")
    req(flash == EXPECTED_FLASH, "WL3 Flash distribution drift")
    req(temps == EXPECTED_TEMP, "WL3 temperature distribution drift")
    req(freq == EXPECTED_FREQ, "WL3 frequency-option distribution drift")
    req(suffix == EXPECTED_SUFFIX, "WL3 option-suffix distribution drift")
    req(set(exceptions) == EXPECTED_EXCEPTIONS, "WL3 exact exception replay drift")

    return {
        "audit_id": "stm32wl3-metadata-authority-replay-v4.5",
        "input_active_exact_count": len(exact),
        "metadata_decodable_exact_count": len(decoded),
        "metadata_blocked_exact_count": 0,
        "direct_ordering_information_exact_count": len(decoded) - len(exceptions),
        "bounded_exact_exception_count": len(exceptions),
        "bounded_exact_exception_icpns": exceptions,
        "exact_set_sha256": EXPECTED_EXACT_SHA256,
        "authority_id": authority["authority_id"],
        "authority_sha256": hashlib.sha256(AUTHORITY.read_bytes()).hexdigest(),
        "series_counts": series,
        "pin_counts": pins,
        "flash_counts": flash,
        "temperature_counts": temps,
        "frequency_option_counts": freq,
        "option_suffix_counts": suffix,
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
            "Prepare a reviewable 47-row STM32WL3 Layer-1 admission proposal with all "
            "backend routes unbound. Production publication remains a separate explicit "
            "owner-approval transaction."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, sort_keys=True))

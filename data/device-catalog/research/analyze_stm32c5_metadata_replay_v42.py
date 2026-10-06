#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
EXACT = HERE / "st-c5-estore-172-active-exact-mpn-v0.7.txt"
ESTORE_LOCK = HERE / "st-c5-estore-evidence-lock-v0.7.json"
CROSSWALK = HERE / "st-c5-dfp-commercial-loader-crosswalk-v0.9.csv"
AUTHORITY = HERE / "stm32c5-ordering-authority-v4.2.json"

EXPECTED_EXACT_COUNT = 172
EXPECTED_EXACT_SHA256 = "32d81e2491f1c8973a778cf62828a0c76662f4fb1813bc611d8b8959607b36a3"
EXPECTED_SERIES = {
    "STM32C531": 29,
    "STM32C532": 22,
    "STM32C542": 12,
    "STM32C551": 29,
    "STM32C552": 19,
    "STM32C562": 12,
    "STM32C591": 20,
    "STM32C593": 19,
    "STM32C5A3": 10,
}
EXPECTED_PACKAGES = {"LQFP": 106, "UFQFPN": 66}
EXPECTED_FLASH = {"128 KiB": 27, "256 KiB": 61, "512 KiB": 55, "1024 KiB": 29}
EXPECTED_TEMPS = {"-40 to 85 C": 119, "-40 to 105 C": 2, "-40 to 125 C": 51}
EXPECTED_PINS = {"20": 5, "24": 5, "32": 49, "48": 54, "64": 30, "80": 11, "100": 13, "144": 5}
EXPECTED_EXCEPTIONS = {"STM32C551CCT7", "STM32C551CCT7TR"}


def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)


def load_exact() -> list[str]:
    rows = [x.strip().upper() for x in EXACT.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(rows == sorted(rows), "C5 exact identity ledger must remain sorted")
    req(len(rows) == EXPECTED_EXACT_COUNT and len(set(rows)) == EXPECTED_EXACT_COUNT,
        "C5 exact identity count/unique drift")
    digest = hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()
    req(digest == EXPECTED_EXACT_SHA256, "C5 exact identity digest drift")
    lock = json.loads(ESTORE_LOCK.read_text(encoding="utf-8"))
    req(lock["observed_active_exact_mpn_count"] == EXPECTED_EXACT_COUNT, "eStore count drift")
    req(lock["observed_exact_set_sha256"] == EXPECTED_EXACT_SHA256, "eStore exact-set lock drift")
    return rows


def load_authority() -> dict[str, Any]:
    value = json.loads(AUTHORITY.read_text(encoding="utf-8"))
    req(value.get("schema_version") == 1, "authority schema drift")
    req(value.get("authority_id") == "stm32c5-ordering-authority-v4.2", "authority id drift")
    gov = value["governance"]
    req(gov["decode_only_locked_exact_identity_set"] is True, "authority scope must remain exact-set bounded")
    req(gov["exception_scope_exact_mpn_only"] is True, "exceptions must remain exact-MPN bounded")
    req(gov["backend_scope_evaluated"] is False, "Layer-1 metadata replay cannot claim backend evaluation")
    req(gov["production_write_authorized"] is False, "research authority cannot authorize Production")
    req(set(value["bounded_exact_exceptions"]) == EXPECTED_EXCEPTIONS, "bounded exception set drift")
    return value


def decode_one(icpn: str, authority: dict[str, Any], exact_set: set[str]) -> dict[str, Any]:
    req(icpn in exact_set, f"{icpn}: not in locked exact Active C5 set")
    core = icpn
    suffix = ""
    if core.endswith("TR"):
        suffix = "TR"
        core = core[:-2]
    req(len(core) == 13, f"{icpn}: unexpected C5 ordering-code length")
    series = core[:9]
    tail = core[9:]
    pin_code, flash_code, package_code, temperature_code = tail
    req(series in authority["series"], f"{icpn}: series lacks authority")
    rule = authority["series"][series]
    req(pin_code in rule["pin_codes"], f"{icpn}: unknown pin code")
    req(flash_code in rule["flash_kib"], f"{icpn}: flash code outside series authority")
    req(package_code in rule["package_codes"], f"{icpn}: unknown package code")
    req(suffix in authority["common"]["packing"], f"{icpn}: unknown packing suffix")

    exception = authority["bounded_exact_exceptions"].get(icpn)
    if temperature_code in authority["common"]["temperature_c"]:
        temperature_grade = authority["common"]["temperature_c"][temperature_code]
        req(exception is None, f"{icpn}: unexpected bounded exception")
        metadata_basis = "official_st_ordering_information"
        source_url = rule["url"]
    else:
        req(exception is not None, f"{icpn}: unsupported temperature code without exact exception")
        req(exception["field"] == "temperature_grade", f"{icpn}: exception field drift")
        temperature_grade = exception["value"]
        metadata_basis = "official_st_ordering_information_plus_exact_estore_temperature_exception"
        source_url = exception["source_url"]

    return {
        "icpn": icpn,
        "family": "STM32C5",
        "series": series,
        "base_device": series + pin_code + flash_code,
        "package": rule["package_codes"][package_code],
        "pin_count": int(rule["pin_codes"][pin_code]),
        "flash_kib": int(rule["flash_kib"][flash_code]),
        "temperature_grade": temperature_grade,
        "option_suffix": suffix,
        "authority_document": rule["document"],
        "authority_revision": rule["revision"],
        "authority_url": rule["url"],
        "metadata_source_url": source_url,
        "metadata_basis": metadata_basis,
        "metadata_exception": (
            "C551_TEMP7_EXACT_ESTORE_EXCEPTION" if exception is not None else ""
        ),
    }


def read_crosswalk() -> list[dict[str, str]]:
    with CROSSWALK.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def analyze() -> dict[str, Any]:
    exact = load_exact()
    exact_set = set(exact)
    authority = load_authority()
    decoded = [decode_one(icpn, authority, exact_set) for icpn in exact]

    series = dict(sorted(Counter(r["series"] for r in decoded).items()))
    packages = dict(sorted(Counter(r["package"] for r in decoded).items()))
    flash = dict(sorted(Counter(f'{r["flash_kib"]} KiB' for r in decoded).items()))
    temps = dict(sorted(Counter(r["temperature_grade"] for r in decoded).items()))
    pins = dict(sorted(Counter(str(r["pin_count"]) for r in decoded).items(), key=lambda x: int(x[0])))
    exceptions = sorted(r["icpn"] for r in decoded if r["metadata_exception"])

    req(series == EXPECTED_SERIES, "C5 series distribution drift")
    req(packages == EXPECTED_PACKAGES, "C5 package distribution drift")
    req(flash == EXPECTED_FLASH, "C5 Flash distribution drift")
    req(temps == EXPECTED_TEMPS, "C5 temperature distribution drift")
    req(pins == EXPECTED_PINS, "C5 pin distribution drift")
    req(set(exceptions) == EXPECTED_EXCEPTIONS, "C5 exact exception replay drift")
    req(sum(r["option_suffix"] == "TR" for r in decoded) == 40, "C5 TR count drift")

    crosswalk = read_crosswalk()
    req(len(crosswalk) == EXPECTED_EXACT_COUNT, "C5 DFP crosswalk count drift")
    req([r["icpn"] for r in crosswalk] == exact, "C5 DFP crosswalk exact-set order drift")
    dfp_counts = Counter(r["dfp_evidence_state"] for r in crosswalk)
    req(dfp_counts == Counter({"EXACT_DFP_VARIANT": 139, "BASE_DEVICE_ONLY_NOT_EXACT": 33}),
        f"C5 DFP evidence partition drift: {dict(dfp_counts)}")
    req(all(r["plasma_route_ready"] == "false" for r in crosswalk),
        "C5 DFP crosswalk unexpectedly claims backend route readiness")

    base_only = {r["icpn"] for r in crosswalk if r["dfp_evidence_state"] == "BASE_DEVICE_ONLY_NOT_EXACT"}
    req(len(base_only) == 33, "C5 DFP base-only set drift")
    req(all(r["icpn"] in base_only or r["icpn"] not in base_only for r in decoded), "internal set error")
    req(all(decode_one(icpn, authority, exact_set) for icpn in sorted(base_only)),
        "C5 DFP base-only cohort not fully metadata decodable")

    return {
        "audit_id": "stm32c5-metadata-authority-replay-v4.2",
        "input_active_exact_count": len(exact),
        "metadata_decodable_exact_count": len(decoded),
        "metadata_blocked_exact_count": 0,
        "direct_ordering_information_exact_count": len(decoded) - len(exceptions),
        "bounded_exact_exception_count": len(exceptions),
        "bounded_exact_exception_icpns": exceptions,
        "dfp_exact_variant_observed_count": dfp_counts["EXACT_DFP_VARIANT"],
        "dfp_parent_only_count": dfp_counts["BASE_DEVICE_ONLY_NOT_EXACT"],
        "dfp_parent_only_metadata_decodable_count": len(base_only),
        "exact_set_sha256": EXPECTED_EXACT_SHA256,
        "authority_id": authority["authority_id"],
        "authority_sha256": hashlib.sha256(AUTHORITY.read_bytes()).hexdigest(),
        "series_counts": series,
        "package_counts": packages,
        "flash_counts": flash,
        "temperature_counts": temps,
        "pin_counts": pins,
        "tr_exact_count": 40,
        "non_tr_exact_count": 132,
        "claims": {
            "layer1_identity_set_locked": True,
            "metadata_authority_replay_complete": True,
            "layer1_admission_proposal_ready": True,
            "dfp_exact_variant_required_for_layer1_metadata": False,
            "backend_scope_evaluated": False,
            "backend_route_ready": False,
            "programming_profile_scope_expanded": False,
            "engineering_verified": False,
            "field_evidence": False,
            "ps_hil_qualification": False,
            "production_write_authorized": False,
        },
        "next_gate": (
            "Prepare a reviewable 172-row STM32C5 Layer-1 admission proposal with all "
            "backend routes unbound. Production publication remains a separate explicit "
            "owner-approval transaction."
        ),
    }


if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, sort_keys=True))

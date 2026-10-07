#!/usr/bin/env python3
from __future__ import annotations

import csv
import hashlib
import json
from collections import Counter
from copy import deepcopy
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GAP = HERE / "st-stm32h7-active-gap-v5.7.txt"
LOCK = HERE / "stm32h7-active-gap-lock-v5.7.json"
BASE_AUTHORITY = HERE / "stm32h7-classic-metadata-authority.json"
DELTA_AUTHORITY = HERE / "stm32h7-active-gap-ordering-authority-v5.7.json"
PRODUCTION = HERE / "stm32h7-classic-commercial-icpn.csv"

EXPECTED_GAP = 14
EXPECTED_GAP_SHA256 = "22587c53a237fe3d2d4a208641e6109dd4d1b67bab1e39c9da86c4233b76b834"
EXPECTED_BASE_AUTHORITY_BLOB = "4e01d06fee1318c35390ad7707f884b3203d3d3f"

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)

def load_gap() -> list[str]:
    rows = [x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(rows == sorted(rows), "H7 gap ledger must remain sorted")
    req(len(rows) == EXPECTED_GAP and len(set(rows)) == EXPECTED_GAP,
        "H7 gap count/unique drift")
    digest = hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()
    req(digest == EXPECTED_GAP_SHA256, "H7 gap digest drift")

    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    req(lock["stm32h7_active_exact_count"] == 205, "H7 Active denominator drift")
    req(lock["stm32h7_production_exact_prestate"] == 191, "H7 Production prestate drift")
    req(lock["stm32h7_active_gap_count"] == EXPECTED_GAP, "H7 gap lock count drift")
    req(lock["stm32h7_active_gap_exact_set_sha256"] == EXPECTED_GAP_SHA256,
        "H7 gap lock digest drift")

    with PRODUCTION.open(newline="", encoding="utf-8") as stream:
        prod = {row["icpn"] for row in csv.DictReader(stream)}
    req(len(prod) == 191, "H7 Production prestate row count drift")
    req(not (set(rows) & prod), "H7 gap overlaps current Production")
    return rows

def load_authority() -> dict[str, Any]:
    base = json.loads(BASE_AUTHORITY.read_text(encoding="utf-8"))
    delta = json.loads(DELTA_AUTHORITY.read_text(encoding="utf-8"))
    req(base["authority_id"] == "stm32h7-classic-ordering-information-v1",
        "H7 base authority id drift")
    req(delta["base_authority_git_blob_sha"] == EXPECTED_BASE_AUTHORITY_BLOB,
        "H7 base authority Git binding drift")

    pin_counts = deepcopy(base["pin_count_by_series"])
    allowed_options = deepcopy(base["allowed_functional_options_by_series"])
    documents = {series: doc for doc in base["documents"] for series in doc["scope"]}

    for series, ext in delta["official_ordering_information_extensions"].items():
        req(series in pin_counts, f"{series}: missing base authority series")
        pin_counts[series].update(ext["pin_count"])
        allowed_options.setdefault(series, [])
        for option in ext["functional_options"]:
            if option not in allowed_options[series]:
                allowed_options[series].append(option)
        documents[series] = {
            "document_id": ext["document_id"],
            "revision": ext["revision"],
            "url": ext["url"],
        }

    gov = delta["governance"]
    req(gov["decode_only_locked_gap_set"] is True, "H7 delta scope drift")
    req(gov["metadata_exception_authorized"] is False, "H7 exception gate opened")
    req(gov["backend_scope_evaluated"] is False, "H7 backend scope overclaim")
    req(gov["existing_family_backend_mapping_inherited"] is False,
        "H7 existing backend mapping improperly inherited")
    req(gov["programming_profile_scope_expanded"] is False,
        "H7 Programming Profile scope overclaim")
    req(gov["production_write_authorized"] is False, "H7 Production overclaim")

    return {
        "common": base["common_semantics"],
        "pin_counts": pin_counts,
        "allowed_options": allowed_options,
        "documents": documents,
        "delta": delta,
    }

def decode_one(icpn: str, authority: dict[str, Any], gap_set: set[str]) -> dict[str, str]:
    req(icpn in gap_set, f"{icpn}: outside locked H7 gap")
    req(len(icpn) >= 13, f"{icpn}: malformed H7 ordering code")

    series = icpn[:9]
    pin_code = icpn[9]
    flash_code = icpn[10]
    package_code = icpn[11]
    temp_code = icpn[12]
    suffix = icpn[13:]
    base_device = icpn[:11]

    common = authority["common"]
    req(series in authority["pin_counts"], f"{icpn}: unsupported H7 series")
    req(pin_code in authority["pin_counts"][series], f"{icpn}: unknown pin-count code")
    req(flash_code in common["flash_size"], f"{icpn}: unknown Flash code")
    req(package_code in common["package"], f"{icpn}: unknown package code")
    req(temp_code in common["temperature_grade"], f"{icpn}: unknown temperature code")

    functional_option = "Q" if suffix.startswith("Q") else ""
    packing = "TR" if suffix.endswith("TR") else ""
    remainder = suffix
    if functional_option:
        remainder = remainder[1:]
        req("Q" in authority["allowed_options"].get(series, []),
            f"{icpn}: Q option is not authority-admitted for series")
    if packing:
        remainder = remainder[:-2]
        req("TR" in common["packing"], f"{icpn}: TR packing not authorized")
    req(remainder == "", f"{icpn}: unparsed ordering suffix {remainder!r}")

    doc = authority["documents"][series]
    return {
        "icpn": icpn,
        "family": "STM32H7",
        "series": series,
        "base_device": base_device,
        "package": common["package"][package_code],
        "pin_count": authority["pin_counts"][series][pin_code],
        "flash_size": common["flash_size"][flash_code],
        "temperature_grade": common["temperature_grade"][temp_code],
        "option_suffix": suffix,
        "functional_option": functional_option,
        "packing": packing,
        "metadata_source_reference":
            f'{doc["document_id"]} {doc["revision"]} Ordering Information',
        "metadata_source_url": doc["url"],
        "metadata_exception": "",
    }

def analyze() -> dict[str, Any]:
    gap = load_gap()
    authority = load_authority()
    decoded = [decode_one(x, authority, set(gap)) for x in gap]
    req(len(decoded) == EXPECTED_GAP, "H7 replay cardinality drift")
    req(all(not r["metadata_exception"] for r in decoded),
        "H7 replay unexpectedly opened metadata exception")

    result = {
        "audit_id": "stm32h7-active-gap-metadata-replay-v5.7",
        "input_active_gap_count": EXPECTED_GAP,
        "metadata_decodable_exact_count": EXPECTED_GAP,
        "metadata_blocked_exact_count": 0,
        "bounded_exact_exception_count": 0,
        "exact_set_sha256": EXPECTED_GAP_SHA256,
        "series_counts": dict(sorted(Counter(r["series"] for r in decoded).items())),
        "package_counts": dict(sorted(Counter(r["package"] for r in decoded).items())),
        "pin_counts": dict(sorted(Counter(r["pin_count"] for r in decoded).items(), key=lambda x: int(x[0]))),
        "flash_counts": dict(sorted(Counter(r["flash_size"] for r in decoded).items())),
        "option_suffix_counts": dict(sorted(Counter(r["option_suffix"] for r in decoded).items())),
        "authority_extensions": {
            "STM32H730": ["A=169", "I=176", "Q=with SMPS"],
            "STM32H7A3": ["Q=132", "A=169", "L=225"],
            "STM32H7B0": ["A=169"],
            "STM32H7B3": ["Q=132", "A=169", "L=225"],
        },
        "claims": {
            "metadata_replay_complete": True,
            "backend_scope_evaluated": False,
            "existing_family_backend_mapping_inherited": False,
            "programming_profile_scope_expanded": False,
            "engineering_verified": False,
            "field_evidence": False,
            "ps_hil_qualification": False,
            "production_write_authorized": False,
        },
    }
    req(result["series_counts"] == {
        "STM32H730": 4, "STM32H743": 1, "STM32H7A3": 5,
        "STM32H7B0": 1, "STM32H7B3": 3,
    }, "H7 series distribution drift")
    req(result["package_counts"] == {
        "LQFP": 2, "TFBGA": 3, "UFBGA": 7, "WLCSP": 2,
    }, "H7 package distribution drift")
    req(result["pin_counts"] == {"132": 2, "169": 5, "176": 4, "225": 3},
        "H7 pin-count distribution drift")
    req(result["flash_counts"] == {
        "1024 KiB": 2, "128 KiB": 5, "2048 KiB": 7,
    }, "H7 Flash distribution drift")
    req(result["option_suffix_counts"] == {"Q": 10, "QTR": 3, "TR": 1},
        "H7 option-suffix distribution drift")
    return result

if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, sort_keys=True))

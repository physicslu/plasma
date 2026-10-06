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
ROOT = HERE.parents[2]
GAP = HERE / "st-stm32c0-active-gap-v5.4.txt"
LOCK = HERE / "stm32c0-active-gap-lock-v5.4.json"
BASE_AUTHORITY = HERE / "stm32c0-phase-c0.3-ordering-authority.json"
DELTA_AUTHORITY = HERE / "stm32c0-active-gap-ordering-authority-v5.4.json"
PRODUCTION = HERE / "stm32c0-commercial-icpn.csv"

EXPECTED_GAP = 17
EXPECTED_GAP_SHA256 = "03b7202842b52aaa6362386864d60c62f64d9cefea74d2d039691ea170b79097"

def req(ok: bool, msg: str) -> None:
    if not ok:
        raise ValueError(msg)

def load_gap() -> list[str]:
    rows = [x.strip() for x in GAP.read_text(encoding="utf-8").splitlines() if x.strip()]
    req(rows == sorted(rows), "C0 gap ledger must remain sorted")
    req(len(rows) == EXPECTED_GAP and len(set(rows)) == EXPECTED_GAP,
        "C0 gap count/unique drift")
    digest = hashlib.sha256(("\n".join(rows) + "\n").encode()).hexdigest()
    req(digest == EXPECTED_GAP_SHA256, "C0 gap digest drift")
    lock = json.loads(LOCK.read_text(encoding="utf-8"))
    req(lock["stm32c0_active_gap_count"] == EXPECTED_GAP, "C0 gap lock count drift")
    req(lock["stm32c0_active_gap_exact_set_sha256"] == EXPECTED_GAP_SHA256,
        "C0 gap lock hash drift")
    with PRODUCTION.open(newline="", encoding="utf-8") as stream:
        prod = {r["icpn"] for r in csv.DictReader(stream)}
    req(len(prod) == 209, "C0 Production prestate drift")
    req(not (set(rows) & prod), "C0 gap overlaps current Production")
    return rows

def load_authority() -> dict[str, dict[str, Any]]:
    base = json.loads(BASE_AUTHORITY.read_text(encoding="utf-8"))
    delta = json.loads(DELTA_AUTHORITY.read_text(encoding="utf-8"))
    req(delta["authority_id"] == "stm32c0-active-gap-ordering-authority-v5.4",
        "C0 delta authority id drift")
    req(delta["base_authority_sha256"]
        == "691733479e7f89ac9f9fe1dbd7cd95a7db6be8b27e7d75a77ae38b853d3899b0",
        "C0 base authority binding drift")
    gov = delta["governance"]
    req(gov["decode_only_locked_gap_set"] is True, "C0 authority scope drift")
    req(gov["backend_scope_evaluated"] is False, "C0 backend overclaim")
    req(gov["production_write_authorized"] is False, "C0 Production overclaim")

    by = {r["series"]: deepcopy(r) for r in base["records"]}
    for series, ext in delta["authority_extensions"].items():
        req(by[series]["document_id"] == ext["document_id"], f"{series}: document drift")
        req(by[series]["revision"] == ext["revision"], f"{series}: revision drift")
        req(by[series]["datasheet_url"] == ext["datasheet_url"], f"{series}: URL drift")
        by[series]["retained_semantics"]["pin_package"].update(ext["pin_package"])
    return by

def decode_one(icpn: str, authority: dict[str, dict[str, Any]], gap_set: set[str]) -> dict[str, str]:
    req(icpn in gap_set, f"{icpn}: outside locked C0 gap")
    base = icpn[:11]
    series = base[:9]
    req(series in authority, f"{icpn}: unsupported C0 series")
    suffix = icpn[11:]
    req(len(suffix) >= 2, f"{icpn}: malformed suffix")
    package_code, temp_code, option = suffix[0], suffix[1], suffix[2:]
    pin_code, flash_code = base[-2], base[-1]
    sem = authority[series]["retained_semantics"]
    package = sem["package"].get(package_code)
    pin = sem["pin_package"].get(f"{pin_code}/{package_code}")
    flash = sem["flash"].get(flash_code)
    temp = sem["temperature"].get(temp_code)
    option_sem = sem["option"].get(option)
    req(package is not None, f"{icpn}: unknown package code")
    req(pin is not None, f"{icpn}: unknown pin/package pair")
    req(flash is not None, f"{icpn}: unknown Flash code")
    req(temp is not None, f"{icpn}: unknown temperature code")
    req(option_sem is not None, f"{icpn}: unknown option suffix")
    return {
        "icpn": icpn,
        "family": "STM32C0",
        "series": series,
        "base_device": base,
        "package": package,
        "pin_count": pin,
        "flash_size": flash,
        "temperature_grade": temp,
        "option_suffix": option,
        "metadata_source_url": authority[series]["datasheet_url"],
        "metadata_exception": "",
    }

def analyze() -> dict[str, Any]:
    gap = load_gap()
    authority = load_authority()
    rows = [decode_one(x, authority, set(gap)) for x in gap]
    req(len(rows) == 17, "C0 replay cardinality drift")
    req(all(not r["metadata_exception"] for r in rows), "C0 replay exception opened")
    return {
        "audit_id": "stm32c0-active-gap-metadata-replay-v5.4",
        "input_active_gap_count": 17,
        "metadata_decodable_exact_count": 17,
        "metadata_blocked_exact_count": 0,
        "bounded_exact_exception_count": 0,
        "exact_set_sha256": EXPECTED_GAP_SHA256,
        "series_counts": dict(sorted(Counter(r["series"] for r in rows).items())),
        "package_counts": dict(sorted(Counter(r["package"] for r in rows).items())),
        "pin_counts": dict(sorted(Counter(r["pin_count"] for r in rows).items(), key=lambda x: int(x[0]))),
        "flash_counts": dict(sorted(Counter(r["flash_size"] for r in rows).items())),
        "temperature_counts": dict(sorted(Counter(r["temperature_grade"] for r in rows).items())),
        "option_suffix_counts": dict(sorted(Counter(r["option_suffix"] for r in rows).items())),
        "new_authority_semantics": {
            "STM32C011_D_Y": "WLCSP12",
            "STM32C051_D_Y": "WLCSP15"
        },
        "lifecycle_delta": {
            "STM32C091KBT3": "Preview -> Active in locked 2026-10-01 eStore set"
        },
        "claims": {
            "metadata_replay_complete": True,
            "backend_scope_evaluated": False,
            "programming_profile_scope_expanded": False,
            "engineering_verified": False,
            "field_evidence": False,
            "ps_hil_qualification": False,
            "production_write_authorized": False
        }
    }

if __name__ == "__main__":
    print(json.dumps(analyze(), indent=2, sort_keys=True))

#!/usr/bin/env python3
"""Validate Microchip ADR-0002 Phase 1 Research IC Information evidence only.

No Product/Production admission, OpenOCD qualification, Programming Profile,
public selector, Socket, PPU or HIL activity. Standard library only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
DEFAULT_PATH = HERE / "microchip-adr0002-phase1-ic-information-pilot-v1.json"
FIELDS = (
    "manufacturer", "icpn", "base_device", "package", "pin_count",
    "flash", "ram", "vdd", "io_supply", "vdda", "temperature",
    "core_architecture", "core_model",
)
STATUSES = ("VERIFIED", "PARTIAL", "UNKNOWN", "CONFLICT")
EXACT_SCOPE = "exact_part_catalog_row"
FAMILY_SCOPE = "base_device_family_parametrics"
FORBIDDEN = {
    "openocd_software_support", "flash_driver", "programming_profile",
    "debug_transport", "software_qualified", "hardware_ready",
    "erase", "program", "verify", "read", "socket_hil",
    "ppu_hil", "target_config",
}


def require(condition, reason):
    if not condition:
        raise ValueError(reason)


def check_numeric_value(field, entry):
    status = entry["status"]
    if status in ("UNKNOWN", "CONFLICT"):
        return
    value = entry["value"]
    if field == "pin_count":
        require(type(value) is int and 1 <= value <= 2000
                and entry["unit"] == "pins", "invalid pin count")
    if field in ("flash", "ram"):
        require(type(value) is int and value > 0
                and entry["unit"] in ("KB", "KiB", "B", "MB", "MiB"),
                f"invalid source memory quantity: {field}")
    if field in ("vdd", "io_supply", "vdda", "temperature"):
        if field in ("io_supply", "vdda") and value is None:
            raise ValueError("supply cannot be known without numeric evidence")
        require(isinstance(value, dict) and set(value) == {"min", "max"},
                f"range required: {field}")
        lo, hi = value["min"], value["max"]
        require(type(lo) in (int, float) and type(hi) in (int, float)
                and lo < hi, f"invalid range: {field}")
        require(entry["unit"] == ("°C" if field == "temperature" else "V"),
                f"source units missing/incorrect: {field}")


def check(dataset):
    require(dataset.get("schema_version") == 1
            and dataset.get("policy") == "ADR-0002 Phase 1 - IC Information"
            and dataset.get("phase") == 1
            and dataset.get("scope") ==
            "research_only_bounded_phase1_information_pilot"
            and dataset.get("manufacturer") == "Microchip",
            "wrong Phase 1 scope")
    for key in ("phase2_programming_authorized",
                "phase3_compatibility_authorized", "production_write_authorized",
                "catalog_publication_authorized", "software_supported_claimed",
                "hardware_verified_claimed"):
        require(dataset.get(key) is False, f"unauthorized claim: {key}")
    require(dataset.get("field_contract") == list(FIELDS),
            "Phase 1 field contract altered")
    sources = dataset.get("source_records")
    require(isinstance(sources, list) and sources, "source evidence required")
    by_id = {}
    for source in sources:
        sid = source.get("id")
        require(isinstance(sid, str) and sid not in by_id,
                "invalid/duplicate source ID")
        url = source.get("url", "")
        product_url = "https://www.microchip.com/en-us/product/ATSAMD21G18"
        datasheet_url = (
            "https://ww1.microchip.com/downloads/aemDocuments/documents/"
            "MCU32/ProductDocuments/DataSheets/"
            "SAM-D21-DA1-Family-Data-Sheet-DS40001882H.pdf"
        )
        require(source.get("publisher") == "Microchip Technology"
                and url in (product_url, datasheet_url),
                "official manufacturer source required")
        if url == datasheet_url:
            require(source.get("source_version") == "DS40001882H"
                    and source.get("scopes") == [FAMILY_SCOPE],
                    "datasheet identity/revision/family scope mismatch")
        else:
            require(source.get("source_version") is None
                    and EXACT_SCOPE in source.get("scopes", []),
                    "product catalog source scope mismatch")
        try:
            date.fromisoformat(source["research_review_date"])
        except (TypeError, ValueError, KeyError):
            raise ValueError("source review date missing")
        digest = source.get("raw_capture_sha256")
        require(digest is None or
                (type(digest) is str and re.fullmatch(r"[0-9a-f]{64}", digest)),
                "invalid original capture digest")
        require(source.get("raw_capture_retained") is (digest is not None),
                "raw source evidence integrity falsely claimed")
        require(source.get("document_id") and source.get("scopes"),
                "source document/scope absent")
        by_id[sid] = source

    records = dataset.get("records")
    require(isinstance(records, list) and 1 <= len(records) <= 10,
            "pilot exceeds approved bounded research scope")
    identities = set()
    results = {k: Counter() for k in FIELDS}
    admission = Counter()
    family_count = Counter()
    for record in records:
        require(set(record["fields"]) == set(FIELDS),
                "missing/extra Phase 1 field")
        icpn = record.get("icpn")
        require(isinstance(icpn, str)
                and re.fullmatch(r"[A-Z0-9][A-Z0-9-]{3,64}", icpn),
                "invalid exact ICPN identifier")
        require(icpn not in identities, "duplicate/conflicting exact ICPN")
        identities.add(icpn)
        require(record.get("manufacturer") == "Microchip"
                and record.get("record_scope") ==
                "phase1_ic_information_research_only"
                and record.get("internal_identity_state") ==
                "SOURCE_LINKED_EXACT_PART_OBSERVED"
                and record.get("internal_admission_state") == "NOT_ADMITTED"
                and record.get("all_specifications_qualified") is False
                and record.get("raw_evidence_complete") is False,
                "Phase 1 research row falsely admitted/qualified")
        require(not FORBIDDEN.intersection(record.keys()),
                "Phase 2/3 programming fields forbidden")
        require(set(record.get("source_ids", [])) <= set(by_id),
                "unknown source reference")
        family_count[record["family"]] += 1
        admission[record["internal_admission_state"]] += 1
        for field in FIELDS:
            entry = record["fields"][field]
            require(set(entry) == {"status", "value", "unit", "source_id",
                                   "evidence_scope", "source_locator", "notes"},
                    f"incomplete field evidence for {field}")
            status, value = entry["status"], entry["value"]
            require(status in STATUSES, f"invalid evidence state: {field}")
            if status in ("UNKNOWN", "CONFLICT"):
                require(value is None and entry["source_id"] is None
                        and entry["evidence_scope"] is None
                        and entry["source_locator"] is None,
                        f"unknown/conflict falsely populated: {field}")
            else:
                require(value is not None
                        and entry["source_id"] in by_id
                        and entry["evidence_scope"] in by_id[entry["source_id"]]["scopes"]
                        and isinstance(entry["source_locator"], str)
                        and bool(entry["source_locator"].strip()),
                        f"missing traceable manufacturer evidence: {field}")
                if status == "VERIFIED":
                    require(entry["evidence_scope"] == EXACT_SCOPE,
                            "family-level fact cannot be exact VERIFIED")
                    require(icpn in entry["source_locator"],
                            "exact scope lacks exact ICPN row locator")
                if status == "PARTIAL":
                    require(entry["evidence_scope"] == FAMILY_SCOPE,
                            "PARTIAL status must name a family source")
                if field == "icpn":
                    require(value == icpn, "observed exact ICPN mismatch")
                if field == "manufacturer":
                    require(value == "Microchip", "manufacturer mismatch")
            check_numeric_value(field, entry)
            if status == "PARTIAL" and field in ("io_supply", "vdda"):
                expected_pin = "VDDIO" if field == "io_supply" else "VDDANA"
                require(entry["source_id"] ==
                        "microchip-sam-d21-da1-family-datasheet-ds40001882h"
                        and expected_pin in entry["source_locator"]
                        and "§8.2.1" in entry["source_locator"]
                        and entry["value"] == {"min": 1.62, "max": 3.63},
                        "unverified Phase 1 supply pin/source alias")
            results[field][status] += 1
    return {
        "policy": "ADR-0002 Phase 1",
        "manufacturer": "Microchip",
        "research_exact_identity_observations": len(records),
        "internal_admission_states": dict(sorted(admission.items())),
        "manufacturer_family_denominator": dict(sorted(family_count.items())),
        "per_field_coverage": {
            name: {s: results[name][s] for s in STATUSES} for name in FIELDS
        },
        "manufacturer_source_count": len(sources),
        "sources_with_original_raw_bytes": sum(
            bool(s["raw_capture_retained"]) for s in sources),
        "production_rows_written": 0,
        "phase2_or_phase3_activity": False,
        "software_supported_count": None,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dataset", type=Path, default=DEFAULT_PATH)
    ap.add_argument("--report", type=Path)
    args = ap.parse_args()
    result = check(json.loads(args.dataset.read_text(encoding="utf-8")))
    if args.report:
        target = args.report.resolve()
        require("production" not in {p.lower() for p in target.parts},
                "cannot output to Production")
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(result, ensure_ascii=False,
                                     indent=2, sort_keys=True) + "\n",
                          encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

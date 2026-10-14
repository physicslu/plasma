#!/usr/bin/env python3
"""ADR-0002 Phase 1: manufacturer HTML chart -> PARTIAL Base Device fields.

Only align declared chart headers with a *single exact family row*.
Do NOT promote family information into exact ordering-ICPN VERIFIED fields.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re

from microchip_phase1_chart_html_source_v1 import replay
from microchip_phase1_chart_html_row_probe_v1 import RowProbe
from microchip_phase1_information_v1 import DEFAULT_PATH, check

HERE = Path(__file__).resolve().parent
LOCK = HERE / "microchip-openocd-first-source-lock-v1.json"
BASE = "ATSAMD21G18"
HEADERS = {
    "base_device": "Device Name",
    "core_model": "CPU",
    "flash": "Flash (KB)",
    "ram": "RAM (KB)",
    "vdd": "Operation Voltage Range",
    "temperature": "Temperature Range",
    "pin_count": "Pin count",
    "package": "Packages",
}


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def parse_value(field, raw):
    if field in ("base_device", "core_model", "package"):
        require(raw != "", f"blank {field} chart field")
        return raw
    if field in ("flash", "ram", "pin_count"):
        require(re.fullmatch(r"[1-9][0-9]{0,5}", raw) is not None,
                f"invalid original {field} scalar")
        return int(raw)
    if field == "temperature":
        match = re.fullmatch(r"(-?[0-9]+)\s+to\s+(-?[0-9]+)", raw)
        require(match is not None and int(match[1]) < int(match[2]),
                "invalid manufacturer temperature range")
        return {"min": int(match[1]), "max": int(match[2])}
    if field == "vdd":
        match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)V\s*-\s*"
                             r"([0-9]+(?:\.[0-9]+)?)V", raw)
        require(match is not None and float(match[1]) < float(match[2]),
                "invalid original manufacturer VDD range")
        return {"min": float(match[1]), "max": float(match[2])}
    raise ValueError("undeclared Phase 1 chart field")


def extract_family(original_root, dataset_path=DEFAULT_PATH, lock_path=LOCK):
    info = replay(original_root)
    raw = (Path(original_root) / "original-chart.html").read_bytes()
    probe = RowProbe()
    probe.feed(raw.decode("utf-8", errors="replace"))
    probe.close()
    headers = [
        s for s in probe.header_samples
        if len(s["headers_observed"]) == len(set(s["headers_observed"]))
        and set(HEADERS.values()) <= set(s["headers_observed"])
    ]
    require(len(headers) == 1, "chart header contract missing/ambiguous")
    names = headers[0]["headers_observed"]
    rows = []
    for candidate in probe.target_rows:
        cells = [c["text"] for c in candidate["raw_cells_not_mapped"]]
        if len(cells) != len(names):
            continue
        raw_device = cells[names.index(HEADERS["base_device"])]
        # Chart names a base device, not a complete orderable suffix.
        normalized = raw_device.split(" [More Info]", 1)[0].strip().upper()
        if normalized == BASE:
            rows.append((candidate["source_tr_ordinal"], cells))
    require(len(rows) == 1, "single exact manufacturer Base Device chart row not established")
    tr_no, cells = rows[0]
    lock_bytes = Path(lock_path).read_bytes()
    lock = json.loads(lock_bytes)
    require(lock.get("manufacturer") == "Microchip"
            and lock.get("provider", {}).get("version") == "0.12.0"
            and lock["provider"]["commit"] ==
            "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
            and lock.get("p0_source_leads_are_not_software_supported") is True,
            "untrusted OpenOCD research source lock")
    matches = [
        x["id"] for x in lock["p0_research_leads"]
        if re.match(x["matcher"], "ATSAMD21G18A")
    ]
    require(matches == ["sam-d-c-r-l0"],
            "unexpected/missing pinned OpenOCD P0 research lead")
    fields = {}
    units = {"flash": "KB", "ram": "KB", "pin_count": "pins",
             "vdd": "V", "temperature": "°C"}
    for key, name in HEADERS.items():
        raw_value = cells[names.index(name)]
        value = BASE if key == "base_device" else parse_value(key, raw_value)
        fields[key] = {
            "status": "PARTIAL",
            "value": value, "original_raw_value": raw_value,
            "original_header": name, "unit": units.get(key),
            "evidence_scope": "official_base_device_parametric_chart_not_exact_sku",
            "source_tr_ordinal": tr_no,
            "source_column_number_1based": names.index(name) + 1,
            "source_original_sha256": info["original_byte_sha256"],
        }
    for key in ("io_supply", "vdda"):
        fields[key] = {
            "status": "UNKNOWN", "value": None,
            "source_explanation": "not independently specified by this chart",
        }

    dataset = json.loads(Path(dataset_path).read_text(encoding="utf-8"))
    check(dataset)
    linked = []
    for entry in dataset["records"]:
        base_field = entry["fields"]["base_device"]
        if (base_field["status"] == "VERIFIED"
                and base_field["value"].upper() == BASE):
            linked.append({
                "icpn": entry["icpn"],
                "base_device_from_existing_reviewed_mcp_pilot": BASE,
                "chart_family_field_evidence_status": "PARTIAL",
                "mcp_original_bytes_replayed_in_this_step": False,
                "internal_admission_state": "NOT_ADMITTED",
                "openocd_software_supported_claimed": False,
            })
    return {
        "schema_version": 1,
        "policy": "ADR-0002 Phase 1 - IC Information",
        "manufacturer": "Microchip",
        "source_url": info["source_url"],
        "source_original_byte_sha256": info["original_byte_sha256"],
        "source_original_bytes": info["size_bytes"],
        "base_device": BASE,
        "chart_header_tr_ordinal": headers[0]["source_tr_ordinal"],
        "chart_family_tr_ordinal": tr_no,
        "chart_semantic_header_alignment_replayed": True,
        "research_priority": "P0",
        "openocd_pinned_source_commit": lock["provider"]["commit"],
        "openocd_research_lead": matches[0],
        "openocd_research_lock_sha256": hashlib.sha256(lock_bytes).hexdigest(),
        "fields_family_scope_only": fields,
        "linked_existing_exact_icpns_not_admitted": linked,
        "exact_icpn_verified_from_chart": 0,
        "exact_variant_temperature_qualified_from_chart": False,
        "internal_admission_count": 0,
        "software_support_qualified": False,
        "production_write_authorized": False,
        "catalog_publication_authorized": False,
        "phase2_programming_authorized": False,
        "phase3_compatibility_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--original-root", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = extract_family(args.original_root)
    if args.output:
        require("production" not in {p.casefold() for p in args.output.resolve().parts},
                "Production output forbidden")
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

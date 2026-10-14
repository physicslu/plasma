#!/usr/bin/env python3
"""ADR-0002 Phase 1: offline Microchip Parametric Search XLSX Research importer.

A manually exported manufacturer chart is NOT an exact commercial-ICPN list.
All reported specifications remain PARTIAL family/chart observations.
No network access, Production write, programming or HIL capability.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import posixpath
import re
from urllib.parse import urlparse
from xml.etree import ElementTree as ET
from zipfile import ZipFile, BadZipFile

HERE = Path(__file__).resolve().parent
LOCK = HERE / "microchip-openocd-first-source-lock-v1.json"
MAIN_NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
OFFICE_REL_NS = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
PACKAGE_REL_NS = "http://schemas.openxmlformats.org/package/2006/relationships"
F = tuple("flash ram vdd io_supply vdda package pin_count temperature core_architecture core_model".split())
RANK = {"P0": 0, "P1": 1, "P2": 2}
MAX_FILE = 25 * 1024 * 1024
MAX_XML = 16 * 1024 * 1024
MAX_ROWS = 30000
MAX_COLS = 150


def require(value, message):
    if not value:
        raise ValueError(message)


def xml_part(archive, part):
    require(part in archive.namelist(), "missing XLSX part: " + part)
    info = archive.getinfo(part)
    require(info.file_size <= MAX_XML, "oversized XML part")
    data = archive.read(part)
    require(b"<!DOCTYPE" not in data.upper() and b"<!ENTITY" not in data.upper(),
            "XML entity declarations prohibited")
    try:
        return ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError("invalid worksheet XML") from exc


def col_number(ref):
    match = re.fullmatch(r"([A-Z]{1,3})([1-9][0-9]*)", ref or "")
    require(match is not None, "malformed XLSX cell address")
    n = 0
    for char in match.group(1):
        n = n * 26 + ord(char) - 64
    require(n <= MAX_COLS, "excessive XLSX column")
    return int(match.group(2)), n


def cell_value(cell, shared):
    require(cell.find(f"{{{MAIN_NS}}}f") is None, "formula cell prohibited")
    typ = cell.attrib.get("t")
    require(typ != "e", "error cell prohibited")
    if typ == "inlineStr":
        return "".join(x.text or "" for x in cell.iter(f"{{{MAIN_NS}}}t")).strip()
    val = cell.find(f"{{{MAIN_NS}}}v")
    if val is None:
        return ""
    raw = (val.text or "").strip()
    if typ == "s":
        require(raw.isdigit() and int(raw) < len(shared), "invalid shared string index")
        return shared[int(raw)]
    require(typ in (None, "n", "str", "b"), "unhandled XLSX cell type")
    return raw


def read_chart(path, sheet_name):
    path = Path(path)
    require(path.is_file() and 0 < path.stat().st_size <= MAX_FILE,
            "missing/oversized original XLSX")
    try:
        with ZipFile(path) as archive:
            entries = archive.infolist()
            names = [x.filename for x in entries]
            require(len(names) == len(set(names)), "duplicate XLSX ZIP entries")
            require(len(entries) <= 300, "excessive XLSX entries")
            require(all(x.file_size <= MAX_XML for x in entries), "oversized XLSX member")
            require(sum(x.file_size for x in entries) <= 60 * 1024 * 1024,
                    "oversized uncompressed XLSX")
            require(not any(n.startswith(("xl/externalLinks/", "xl/vbaProject")) for n in names),
                    "external links/macros are not permitted")
            book = xml_part(archive, "xl/workbook.xml")
            rels = xml_part(archive, "xl/_rels/workbook.xml.rels")
            sheets = book.find(f"{{{MAIN_NS}}}sheets")
            require(sheets is not None, "XLSX has no sheets")
            matches = [s for s in sheets if s.attrib.get("name") == sheet_name]
            require(len(matches) == 1, "required worksheet missing/ambiguous")
            require(matches[0].attrib.get("state", "visible") == "visible",
                    "hidden worksheet not accepted")
            rid = matches[0].attrib.get(f"{{{OFFICE_REL_NS}}}id")
            relation = [r for r in rels
                        if r.attrib.get("Id") == rid
                        and r.attrib.get("Type", "").endswith("/worksheet")]
            require(len(relation) == 1 and not relation[0].attrib.get("TargetMode"),
                    "worksheet relationship missing/external")
            target = relation[0].attrib["Target"]
            part = (target.lstrip("/") if target.startswith("/")
                    else posixpath.normpath(posixpath.join("xl", target)))
            require(part.startswith("xl/worksheets/") and ".." not in part.split("/"),
                    "unexpected worksheet path")
            strings = []
            if "xl/sharedStrings.xml" in names:
                xml = xml_part(archive, "xl/sharedStrings.xml")
                strings = ["".join(t.text or "" for t in si.iter(f"{{{MAIN_NS}}}t"))
                           for si in xml.findall(f"{{{MAIN_NS}}}si")]
            root = xml_part(archive, part)
            data = root.find(f"{{{MAIN_NS}}}sheetData")
            require(data is not None, "worksheet missing sheetData")
            rows = []
            seen_row = set()
            for row in data.findall(f"{{{MAIN_NS}}}row"):
                index = int(row.attrib.get("r", "0"))
                require(1 <= index <= MAX_ROWS and index not in seen_row,
                        "duplicate/out-of-range row")
                seen_row.add(index)
                values = {}
                for cell in row.findall(f"{{{MAIN_NS}}}c"):
                    r, c = col_number(cell.attrib.get("r"))
                    require(r == index and c not in values, "duplicate/misaddressed cell")
                    values[c] = cell_value(cell, strings)
                if any(values.values()):
                    rows.append((index, values))
            require(2 <= len(rows) <= MAX_ROWS, "chart requires header and data rows")
            return sorted(rows)
    except (BadZipFile, KeyError, OSError) as exc:
        raise ValueError("invalid XLSX source archive") from exc


def validate_config(cfg):
    require(set(cfg) == {"chart_url", "chart_scope", "worksheet",
                         "captured_at_utc", "columns"}, "configuration keys mismatch")
    parsed = urlparse(cfg["chart_url"])
    require(parsed.scheme == "https" and parsed.hostname in
            ("microchip.com", "www.microchip.com") and not parsed.username
            and not parsed.password and not parsed.port,
            "official Microchip chart URL required")
    require(isinstance(cfg["chart_scope"], str) and len(cfg["chart_scope"].strip()) >= 8,
            "chart/category scope missing")
    require(isinstance(cfg["worksheet"], str) and cfg["worksheet"].strip(),
            "worksheet selection required")
    try:
        when = datetime.fromisoformat(cfg["captured_at_utc"].replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError("capture timestamp invalid") from exc
    require(when.tzinfo is not None and when.utcoffset() == timezone.utc.utcoffset(when),
            "UTC capture timestamp required")
    columns = cfg["columns"]
    require(isinstance(columns, dict) and "base_device" in columns
            and set(columns) <= set(F) | {"base_device"}, "invalid chart field mapping")
    names = []
    for field, item in columns.items():
        require(isinstance(item, dict) and set(item) == {"header", "unit"}
                and isinstance(item["header"], str) and item["header"].strip(),
                "explicit header/unit mapping required")
        require(item["unit"] is None or
                (isinstance(item["unit"], str) and item["unit"].strip()),
                "original unit must be specified or null")
        if field in ("base_device", "package", "core_architecture", "core_model"):
            require(item["unit"] is None, "categorical field cannot declare a unit")
        else:
            require(isinstance(item["unit"], str) and item["unit"].strip(),
                    "numeric/range chart fields require their original source unit")
        names.append(item["header"])
    require(len(set(names)) == len(names), "duplicate source header mapping")


def classify(name, source_lock):
    found = []
    for priority, key in (("P0", "p0_research_leads"), ("P1", "p1_bounded_leads")):
        for lead in source_lock[key]:
            if re.match(lead["matcher"], name):
                found.append((priority, lead["id"]))
    require(len(found) <= 1, "ambiguous P0/P1 research lead: " + name)
    return found[0] if found else ("P2", None)


def generate(xlsx_path, cfg, lock_path=LOCK):
    validate_config(cfg)
    raw = Path(xlsx_path).read_bytes()
    source_lock_bytes = Path(lock_path).read_bytes()
    lock = json.loads(source_lock_bytes)
    require(lock.get("schema_version") == 2 and lock.get("manufacturer") == "Microchip"
            and lock.get("policy") == "ADR-0002/Issue-851"
            and lock["provider"]["version"] == "0.12.0"
            and lock["provider"]["commit"] ==
            "9ea7f3d647c8ecf6b0f1424002dfc3f4504a162c"
            and lock.get("p0_source_leads_are_not_software_supported") is True
            and lock.get("production_write_authorized") is False,
            "untrusted/mismatched OpenOCD research source lock")
    rows = read_chart(xlsx_path, cfg["worksheet"])
    header_index, headers = rows[0]
    require(header_index <= 10, "unexpected header location")
    header_names = [v for v in headers.values() if v]
    require(len(header_names) == len(set(header_names)), "duplicate chart headers")
    positions = {}
    for field, item in cfg["columns"].items():
        matches = [col for col, text in headers.items() if text == item["header"]]
        require(len(matches) == 1, "required chart column missing: " + field)
        positions[field] = matches[0]
    records = []
    seen = set()
    for row_num, cells in rows[1:]:
        device = cells.get(positions["base_device"], "").strip()
        require(bool(re.fullmatch(r"[A-Z0-9][A-Z0-9_-]{2,79}", device)),
                "invalid/blank base-device chart identity")
        require(device not in seen, "duplicate chart base device (cannot silently collapse)")
        seen.add(device)
        priority, lead = classify(device, lock)
        record = {"base_device_observed": device, "worksheet_row": row_num,
                  "priority": priority, "pinned_source_lead_id": lead,
                  "research_only": True, "exact_icpn_verified": False,
                  "software_supported_claimed": False,
                  "internal_admission_state": "NOT_ADMITTED"}
        if priority in ("P0", "P1"):
            fields = {}
            for field in F:
                if field not in positions:
                    fields[field] = {"status": "UNKNOWN", "raw_value": None,
                                     "source_column": None, "unit": None}
                    continue
                raw_value = cells.get(positions[field], "").strip()
                fields[field] = {
                    "status": "PARTIAL" if raw_value else "UNKNOWN",
                    "raw_value": raw_value or None,
                    "source_column": cfg["columns"][field]["header"],
                    "unit": cfg["columns"][field]["unit"],
                    "source_locator": f"{cfg['worksheet']}!row{row_num}",
                    "source_scope": "chart_family_row_not_exact_icpn"
                }
            record["fields"] = fields
        else:
            record["archive_only"] = True
        records.append(record)
    records.sort(key=lambda x: (RANK[x["priority"]], x["base_device_observed"]))
    counts = Counter(x["priority"] for x in records)
    coverage = {field: Counter(r["fields"][field]["status"]
              for r in records if "fields" in r) for field in F}
    return {
        "schema_version": 1, "policy": "ADR-0002 Phase 1 - IC Information",
        "manufacturer": "Microchip",
        "scope": "source_bound_chart_family_research_only",
        "chart": {"url": cfg["chart_url"], "scope": cfg["chart_scope"],
                  "worksheet": cfg["worksheet"], "captured_at_utc": cfg["captured_at_utc"],
                  "original_file_name": Path(xlsx_path).name,
                  "original_byte_sha256": hashlib.sha256(raw).hexdigest(),
                  "original_byte_size": len(raw), "original_bytes_embedded": False,
                  "official_export_origin_independently_verified": False,
                  "manufacturer_complete": False},
        "classification": {"pinned_openocd_version": lock["provider"]["version"],
                           "pinned_openocd_commit": lock["provider"]["commit"],
                           "research_leads_sha256": hashlib.sha256(source_lock_bytes).hexdigest(),
                           "p0_p1_are_not_supported": True},
        "counts": {"chart_base_device_rows": len(records),
                   "P0": counts["P0"], "P1": counts["P1"], "P2": counts["P2"],
                   "exact_icpn_rows_verified": 0, "production_admitted": 0},
        "field_coverage_p0_p1_only": {
            f: {"PARTIAL": coverage[f]["PARTIAL"], "UNKNOWN": coverage[f]["UNKNOWN"],
                "VERIFIED": 0} for f in F},
        "records": records,
        "manufacturer_population_complete": False,
        "exact_icpn_software_supported_count": None,
        "production_write_authorized": False,
        "catalog_publication_authorized": False,
        "phase2_programming_authorized": False,
        "phase3_compatibility_authorized": False
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--xlsx", type=Path, required=True, help="unaltered official XLSX file")
    parser.add_argument("--config", type=Path, required=True, help="explicit chart/source/header map")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--output", type=Path)
    mode.add_argument("--verify", type=Path, help="compare to a saved Phase 1 report")
    args = parser.parse_args()
    cfg = json.loads(args.config.read_text(encoding="utf-8"))
    report = generate(args.xlsx, cfg)
    destination = args.output or args.verify
    require("production" not in {part.casefold() for part in destination.resolve().parts},
            "Production path prohibited")
    if args.verify:
        require(report == json.loads(args.verify.read_text(encoding="utf-8")),
                "XLSX/config/lock replay mismatch")
        print("Phase 1 source-byte replay PASS")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n",
                               encoding="utf-8")
        print(json.dumps(report["counts"], sort_keys=True))


if __name__ == "__main__":
    main()

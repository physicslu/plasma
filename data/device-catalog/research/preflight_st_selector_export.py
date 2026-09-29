#!/usr/bin/env python3
"""Fail-closed preflight for a dated official ST STM32 MCU selector export.

Reads CSV or XLSX without expanding CubeMX wildcard/pattern device names.
Replays the v0.2 integrity-bound 23-family ST Production baseline.
This is an INPUT QUALITY preflight, never a complete-ST coverage admission.
No network call, GitHub changes, production write, or runtime action.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import posixpath
import re
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from xml.etree import ElementTree as ET

import audit_st_portfolio_coverage_gap as frozen

HERE = Path(__file__).resolve().parent
M = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
R = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}"
P = "{http://schemas.openxmlformats.org/package/2006/relationships}"
MAX_INPUT_BYTES = 30 * 1024 * 1024
MAX_XLSX_UNCOMPRESSED = 100 * 1024 * 1024
MAX_ROWS = 30000
HEADER_SCAN_ROWS = 20
PART_HEADERS = ("partnumber", "commercialpartnumber", "mcupartnumber", "mcumpupartnumber",
                "orderingcode", "ordercode", "orderingpartnumber")
STATUS_HEADERS = ("marketingstatus", "lifecycle", "lifecyclestatus", "productstatus")
FAMILY_HEADERS = ("series", "mcuseries", "family", "mcufamily")
PERMITTED_ORIGINS = ("STM32CubeMX_MCU_Selector", "ST_MCU_FINDER_PC_MCU_Selector",
                     "ST_Public_Product_Selector", "ST_eStore_Current_Catalog")
KNOWN_STATUSES = {
    "ACTIVE": "Active", "NRND": "NRND",
    "NOTRECOMMENDEDFORNEWDESIGNS": "NRND",
    "OBSOLETE": "Obsolete", "DISCONTINUED": "Discontinued",
    "PROPOSAL": "Proposal", "EVALUATION": "Evaluation",
    "PREVIEW": "Preview", "COMINGSOON": "Coming Soon",
    "NA": "NA", "NOTAVAILABLE": "NA",
}
SENTINELS = (
    "STM32H503CBT6", "STM32C531CBT6", "STM32N657A0H3Q",
    "STM32WB05KZV6TR", "STM32WL33CCV6",
)

def require(ok: bool, message: str) -> None:
    if not ok:
        raise ValueError(message)

def hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def normalize_header(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).lower())

def normalize_status(value: str) -> str | None:
    token = normalize_header(value).upper()
    return KNOWN_STATUSES.get(token)

def excel_column_index(reference: str) -> int:
    column = re.match(r"^[A-Z]+", reference.upper())
    require(column is not None, f"Invalid XLSX cell reference: {reference}")
    result = 0
    for character in column.group():
        result = result * 26 + ord(character) - ord("A") + 1
    return result - 1

def shared_text(element: ET.Element) -> str:
    return "".join(t.text or "" for t in element.findall(".//" + M + "t"))

def xlsx_sheets(content: bytes) -> list[tuple[str, list[list[str]]]]:
    result = []
    with zipfile.ZipFile(io.BytesIO(content)) as archive:
        files = archive.namelist()
        require(all(".." not in posixpath.normpath(name).split("/") for name in files),
                "Unsafe ZIP entry path")
        require(sum(i.file_size for i in archive.infolist()) <= MAX_XLSX_UNCOMPRESSED,
                "XLSX uncompressed size exceeds limit")
        require("xl/workbook.xml" in files and "xl/_rels/workbook.xml.rels" in files,
                "Not an XLSX workbook")
        workbook = ET.fromstring(archive.read("xl/workbook.xml"))
        rels = ET.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
        rid_to_path = {}
        for rel in rels.findall(P + "Relationship"):
            rid = rel.attrib.get("Id", "")
            target = rel.attrib.get("Target", "")
            if rel.attrib.get("TargetMode") == "External":
                continue
            path = (target.lstrip("/") if target.startswith("/") else
                    posixpath.normpath(posixpath.join("xl", target)))
            if path.startswith("xl/worksheets/") and path in files:
                rid_to_path[rid] = path
        shared = []
        if "xl/sharedStrings.xml" in files:
            root = ET.fromstring(archive.read("xl/sharedStrings.xml"))
            shared = [shared_text(si) for si in root.findall(M + "si")]
        for sheet in workbook.findall(".//" + M + "sheets/" + M + "sheet"):
            name, rid = sheet.attrib.get("name", ""), sheet.attrib.get(R + "id", "")
            require(rid in rid_to_path, f"Cannot resolve worksheet: {name}")
            xml = ET.fromstring(archive.read(rid_to_path[rid]))
            rows = []
            for row in xml.findall(".//" + M + "sheetData/" + M + "row"):
                require(len(rows) < MAX_ROWS + HEADER_SCAN_ROWS, "XLSX row limit exceeded")
                cells = {}
                for cell in row.findall(M + "c"):
                    index = excel_column_index(cell.attrib.get("r", ""))
                    v = cell.find(M + "v")
                    t = cell.attrib.get("t", "")
                    if cell.find(M + "f") is not None:
                        value = "=FORMULA_UNTRUSTED"
                    elif t == "inlineStr":
                        inline = cell.find(M + "is")
                        value = shared_text(inline) if inline is not None else ""
                    elif t == "s":
                        require(v is not None and (v.text or "").isdigit(),
                                "Invalid XLSX shared string reference")
                        si = int(v.text)
                        require(0 <= si < len(shared), "XLSX shared string out of range")
                        value = shared[si]
                    else:
                        value = v.text or "" if v is not None else ""
                    require(index < 128, "XLSX has excessive columns")
                    cells[index] = value
                if cells:
                    end = max(cells)
                    rows.append([cells.get(index, "") for index in range(end + 1)])
            result.append((name, rows))
    return result

def table_from_export(name: str, data: bytes, chosen_sheet: str | None = None
                      ) -> tuple[str, list[str], list[dict[str, str]], bool]:
    extension = Path(name).suffix.lower()
    if extension == ".csv":
        require(chosen_sheet is None, "--sheet is only valid for XLSX")
        sheets = [("CSV", list(csv.reader(io.StringIO(data.decode("utf-8-sig")))))]
    elif extension == ".xlsx":
        sheets = xlsx_sheets(data)
    else:
        raise ValueError("Only official CSV or XLSX exports are supported")
    candidates = []
    for sheet_name, rows in sheets:
        if chosen_sheet is not None and chosen_sheet != sheet_name:
            continue
        for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
            h = [normalize_header(x) for x in row]
            part = next((p for p in PART_HEADERS if h.count(p) == 1), None)
            if part is None:
                continue
            # If workbook has more than one candidate table, operator must
            # choose a named sheet instead of silently taking a partial subset.
            require(h.count(part) == 1, "Ambiguous part number column")
            pi = h.index(part)
            status = next((s for s in STATUS_HEADERS if h.count(s) == 1), None)
            family = next((s for s in FAMILY_HEADERS if h.count(s) == 1), None)
            raw = []
            for no, values in enumerate(rows[i + 1:], i + 2):
                require(len(raw) < MAX_ROWS, "Selector export row limit exceeded")
                if not any(str(c).strip() for c in values):
                    continue
                get = lambda idx: str(values[idx]).strip() if idx is not None and idx < len(values) else ""
                raw.append({
                    "source_row": str(no), "mpn": get(pi),
                    "marketing_status": get(h.index(status)) if status else "",
                    "family": get(h.index(family)) if family else "",
                })
            candidates.append((sheet_name, row, raw, status is not None))
            break
    require(len(candidates) == 1,
            "Expected exactly one selector table (use --sheet when multiple candidate worksheets exist)")
    return candidates[0]

def validate_provenance(provenance: dict, data: bytes) -> None:
    require(provenance.get("schema_version") == 1, "Provenance schema mismatch")
    require(provenance.get("source_kind") in PERMITTED_ORIGINS, "Unsupported vendor export source")
    url = provenance.get("official_source_url", "")
    require(bool(re.match(r"^https://([a-z0-9-]+\.)*st\.com(?:[:/]|$)", url, re.I)),
            "Provenance must cite official ST domain")
    require(isinstance(provenance.get("tool_version"), str) and
            bool(provenance["tool_version"].strip()), "Tool/export version required")
    stamp = provenance.get("acquired_at_utc", "")
    try:
        acquired = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (ValueError, AttributeError) as exc:
        raise ValueError("Invalid acquisition UTC timestamp") from exc
    require(acquired.utcoffset() is not None and acquired.utcoffset().total_seconds() == 0,
            "Acquisition timestamp must explicitly be UTC")
    require(provenance.get("raw_export_sha256") == hash_bytes(data),
            "Raw export provenance digest mismatch")
    filter_info = provenance.get("filter_disclosure")
    require(isinstance(filter_info, dict) and
            filter_info.get("device_scope") in ("STM32 MCU only", "STM32 MCU + Wireless MCU") and
            filter_info.get("marketing_status") in ("all", "Active only", "unknown"),
            "Export filters must be disclosed")
    require(provenance.get("full_portfolio_completeness_reviewed") is False,
            "This preflight is not a qualified complete-vendor-population gate")

def analyze_rows(rows: list[dict[str, str]], production_icpns: set[str]) -> dict:
    identity_records: dict[str, list[dict]] = defaultdict(list)
    nonexact, nonstm32, invalid_status, empty = [], [], [], []
    total = 0
    for row in rows:
        total += 1
        sku = str(row.get("mpn", "")).strip().upper()
        status_text = str(row.get("marketing_status", "")).strip()
        if not sku:
            empty.append(row.get("source_row", ""))
            continue
        if not sku.startswith("STM32"):
            nonstm32.append({"row": row.get("source_row"), "raw_identifier": sku})
            continue
        # Do not synthesize orderable suffixes from CubeMX names like
        # STM32F103C8Tx, 'xx' patterns, aliases, or marketing family labels.
        if not re.fullmatch(r"STM32[A-Z0-9]{7,22}", sku) or "X" in sku:
            nonexact.append({"row": row.get("source_row"), "raw_identifier": sku})
            continue
        status = normalize_status(status_text)
        entry = {
            "row": row.get("source_row"), "status": status,
            "raw_status": status_text,
            "series": str(row.get("family", "")).strip(),
        }
        if status is None:
            invalid_status.append({"icpn": sku, **entry})
        identity_records[sku].append(entry)
    accepted, excluded, conflicts, unknown = [], [], [], []
    for sku, instances in sorted(identity_records.items()):
        statuses = {r["status"] for r in instances}
        if len(statuses) > 1:
            conflicts.append({"icpn": sku, "observed_statuses": sorted(
                "UNKNOWN" if x is None else x for x in statuses)})
        elif statuses == {"Active"}:
            accepted.append(sku)
        elif None in statuses:
            unknown.append(sku)
        else:
            excluded.append({"icpn": sku, "status": next(iter(statuses))})
    exact_active = set(accepted)
    overlap = exact_active & production_icpns
    sample_only_missing = exact_active - production_icpns
    return {
        "total_nonblank_data_rows": total,
        "exact_candidate_identity_count": len(identity_records),
        "observed_active_exact_count": len(exact_active),
        "observed_active_exact_sha256": hash_bytes(("\n".join(sorted(exact_active))+"\n").encode("ascii")),
        "observed_active_exact_icpns": sorted(exact_active),
        "observed_active_in_production_count": len(overlap),
        "observed_active_not_in_production_count": len(sample_only_missing),
        "observed_active_not_in_production": sorted(sample_only_missing),
        "observed_nonactive": excluded,
        "unknown_lifecycle_identities": unknown,
        "conflicting_lifecycle": conflicts,
        "unrecognized_lifecycle_rows": invalid_status,
        "pattern_or_nonexact_rows": nonexact,
        "non_stm32_rows": nonstm32,
        "empty_identity_rows": empty,
        "known_v02_sentinels_observed_active": [s for s in SENTINELS if s in exact_active],
        "known_v02_sentinels_not_in_this_export": [s for s in SENTINELS if s not in exact_active],
        "input_quality_ready_for_review": not conflicts and not invalid_status and not nonexact and not empty,
        "is_complete_active_st_portfolio": False,
        "actual_active_st_coverage_percent": None,
        "actual_active_st_gap_count": None,
        "production_absent_from_observed_input_is_lifecycle_gap": False,
    }

def production_set() -> tuple[set[str], dict]:
    baseline = frozen.render()
    require(baseline["production_baseline"]["unique_exact_icpns"] == 2683,
            "Frozen ST Production baseline drifted")
    import csv as csv_module
    entries = set()
    manifest = json.loads(frozen.MANIFEST.read_text(encoding="utf-8"))
    for source in manifest["sources"]:
        if source["manufacturer"] != "STMicroelectronics":
            continue
        path = (frozen.MANIFEST.parent / source["path"]).resolve()
        with path.open(newline="", encoding="utf-8-sig") as handle:
            for row in csv_module.DictReader(handle):
                sku = row["icpn"].strip().upper()
                require(sku not in entries, f"Duplicate Production ICPN: {sku}")
                entries.add(sku)
    require(len(entries) == 2683, "Production exact identity set drifted")
    return entries, baseline

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--export", type=Path, required=True, help="Raw official ST selector CSV/XLSX")
    parser.add_argument("--provenance", type=Path, required=True, help="Sidecar JSON with raw SHA-256 and filter disclosure")
    parser.add_argument("--sheet", help="Named XLSX MCU selection worksheet, if needed")
    parser.add_argument("--output", type=Path, required=True, help="Research-only JSON report destination")
    args = parser.parse_args()
    require(args.export.is_file(), "Official export file not found")
    data = args.export.read_bytes()
    require(0 < len(data) <= MAX_INPUT_BYTES, "Export exceeds size bound or is empty")
    provenance = json.loads(args.provenance.read_text(encoding="utf-8"))
    validate_provenance(provenance, data)
    sheet, headers, rows, has_status = table_from_export(args.export.name, data, args.sheet)
    production, baseline = production_set()
    audit = analyze_rows(rows, production)
    audit.update({
        "schema_version": 1,
        "artifact_type": "st_stm32_official_selector_export_preflight",
        "source_kind": provenance["source_kind"],
        "source_tool_version": provenance["tool_version"],
        "source_url": provenance["official_source_url"],
        "source_acquired_at_utc": provenance["acquired_at_utc"],
        "export_raw_sha256": hash_bytes(data),
        "export_table_name": sheet,
        "export_header": headers,
        "marketing_status_column_present": has_status,
        "disclosed_filters": provenance["filter_disclosure"],
        "production_st_exact_count": len(production),
        "production_frozen_baseline_manifest_blob": baseline["production_baseline"]["original_manifest_git_blob_sha"],
        "claim_scope": "Partial source preflight and sample-only exact intersection. NOT full Active-ST coverage.",
        "next_gate": "manufacturer-authoritative full exact-MPN + lifecycle completeness reconciliation and reviewer-locked source acquisition",
        "production_write_authorized": False,
        "programming_backend_or_hil_authorized": False,
    })
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(audit, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({
        "source_sha256": hash_bytes(data),
        "observed_active_exact": audit["observed_active_exact_count"],
        "observed_active_missing_production": audit["observed_active_not_in_production_count"],
        "nonexact_pattern_rows": len(audit["pattern_or_nonexact_rows"]),
        "unrecognized_status_rows": len(audit["unrecognized_lifecycle_rows"]),
        "lifecycle_conflicts": len(audit["conflicting_lifecycle"]),
        "full_st_coverage": "NOT_AUTHORIZED",
    }, sort_keys=True))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())

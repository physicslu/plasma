#!/usr/bin/env python3
"""Bounded original-byte Microchip SAM R30 *online* ordering-table probe.

Research only. Online Microchip manual is courtesy material and explicitly
requires confirmation against official device PDF. Its exact order-code rows
are SOURCE OBSERVATIONS, not Phase1 VERIFIED, Production or support claims.
"""
from __future__ import annotations
import argparse
from datetime import datetime, timezone
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

URLS = {
    "SAMR30E": ("https://onlinedocs.microchip.com/oxy/"
               "GUID-4B3D771E-5647-4191-AD45-C897B0D23071-en-US-3/"
               "GUID-051A9F8A-61B6-46C4-B797-9AEEA6BDCC57.html"),
    "SAMR30G": ("https://onlinedocs.microchip.com/oxy/"
               "GUID-4B3D771E-5647-4191-AD45-C897B0D23071-en-US-3/"
               "GUID-FA1F01D6-601F-4646-B4E1-644BC34093EE.html"),
}
PDF_DOCUMENT = "Microchip SAM R30 Data Sheet DS70005303B (PDF verification pending)"
MAX_BYTES = 3 * 1024 * 1024
EXPECTED = {
    "SAMR30E": {
        "ATSAMR30E18A-MU": ("256K", "32K", "QFN32", "Tray"),
        "ATSAMR30E18A-MUT": ("256K", "32K", "QFN32", "Tape & Reel"),
    },
    "SAMR30G": {
        "ATSAMR30G18A-MU": ("256K", "32K", "QFN48", "Tray"),
        "ATSAMR30G18A-MUT": ("256K", "32K", "QFN48", "Tape & Reel"),
    },
}
SKU = re.compile(r"ATSAMR30[EG]18A-MUT?\Z")
SHA = re.compile(r"[0-9a-f]{64}\Z")


def require(value, reason):
    if not value:
        raise ValueError(reason)


class OrderingTable(HTMLParser):
    """Extract displayed original HTML table cells; never regex full markup."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.table_depth = 0
        self.in_row = False
        self.in_cell = False
        self.cells = []
        self.rows = []
        self.text = []

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        if tag == "table":
            self.table_depth += 1
        if not self.table_depth:
            return
        if tag == "tr":
            require(not self.in_row, "nested original HTML table rows unsupported")
            self.in_row = True
            self.cells = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.text = []

    def handle_data(self, data):
        if self.in_cell:
            self.text.append(data)

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag in ("td", "th") and self.in_cell:
            value = " ".join(" ".join(self.text).split())
            self.cells.append(value)
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.cells:
                self.rows.append(tuple(self.cells))
            self.in_row = False
        elif tag == "table" and self.table_depth:
            self.table_depth -= 1


def parse_original_html(raw, lane):
    require(lane in URLS, "unreviewed manufacturer documentation lane")
    require(0 < len(raw) <= MAX_BYTES
            and (b"<html" in raw[:50000].lower() or
                 b"<!doctype html" in raw[:50000].lower()),
            "not bounded original official HTML")
    source = OrderingTable()
    source.feed(raw.decode("utf-8", errors="replace"))
    rows = {}
    found_header = False
    for idx, cells in enumerate(source.rows):
        if (len(cells) >= 5 and
            all(expected in " ".join(cells).casefold() for expected in
                ("ordering code", "flash", "sram", "package", "carrier"))):
            found_header = True
        if not cells or not SKU.fullmatch(cells[0]):
            continue
        ident = cells[0]
        require(ident in EXPECTED[lane], "foreign ordering code in source table")
        require(ident not in rows and len(cells) == 5,
                "duplicate/unrecognized exact manufacturer table row")
        actual = cells[1:]
        require(tuple(actual) == EXPECTED[lane][ident],
                "source table differs from separately reviewed official SAM R30 ordering values")
        rows[ident] = {
            "icpn": ident, "flash_original": cells[1], "ram_original": cells[2],
            "package_original": cells[3], "carrier_original": cells[4],
            "original_row_index": idx,
            "source_scope": "official_online_docs_exact_ordering_row_pdf_check_pending",
            "original_pdf_crosscheck_completed": False,
            "phase1_verified_authorized": False,
        }
    require(found_header and set(rows) == set(EXPECTED[lane]),
            "official ordering header or exact-code rows missing")
    return [rows[k] for k in sorted(rows)]


def is_official_endpoint(uri, lane):
    parsed = urllib.parse.urlsplit(uri)
    return (lane in URLS and uri == URLS[lane]
            and parsed.scheme == "https"
            and parsed.hostname == "onlinedocs.microchip.com"
            and not parsed.username and not parsed.password
            and parsed.port is None)


def fetch_exact(uri, lane):
    require(is_official_endpoint(uri, lane), "off-domain or altered official source")
    request = urllib.request.Request(
        uri, headers={"User-Agent": "PLASMA-Research-SourceCapture/1.0",
                      "Accept": "text/html"})
    with urllib.request.urlopen(request, timeout=22) as response:
        require(response.status == 200 and
                is_official_endpoint(response.geturl(), lane),
                "blocked HTTP or redirected manufacturer document")
        raw = response.read(MAX_BYTES + 1)
    require(0 < len(raw) <= MAX_BYTES, "manufacturer HTML source size invalid")
    return raw


def capture(root, getter=fetch_exact):
    root = Path(root)
    require("production" not in {part.casefold() for part in root.resolve().parts},
            "Production directory prohibited")
    require(not root.exists(), "capture path already exists")
    root.mkdir(parents=True)
    sources = []
    for lane, uri in URLS.items():
        record = {"lane": lane, "url": uri,
                  "status": "SOURCE_NOT_AVAILABLE", "file": None,
                  "original_sha256": None, "bytes": None,
                  "exact_ordering_row_count": 0, "error": None,
                  "captured_at_utc": datetime.now(timezone.utc).isoformat()}
        try:
            raw = getter(uri, lane)
            require(0 < len(raw) <= MAX_BYTES and
                    (b"<html" in raw[:50000].lower() or
                     b"<!doctype html" in raw[:50000].lower()),
                    "HTTP response not official HTML")
            target = f"manufacturer-{lane.lower()}-original.html"
            (root / target).write_bytes(raw)
            record.update(status="SOURCE_BYTES_CAPTURED_TABLE_NOT_REPLAYABLE",
                          file=target,
                          original_sha256=hashlib.sha256(raw).hexdigest(),
                          bytes=len(raw),
                          manufacturer_order_code_tokens_present={
                              key: key.encode() in raw for key in EXPECTED[lane]})
            try:
                rows = parse_original_html(raw, lane)
                record.update(status="SOURCE_BYTES_CAPTURED_AND_REPLAYED",
                              exact_ordering_row_count=len(rows))
            except ValueError as exc:
                record["error"] = f"ORIGINAL_HTML_SCHEMA_NOT_REPLAYABLE: {exc}"
        except (OSError, ValueError, TimeoutError, urllib.error.URLError) as exc:
            record["error"] = f"{type(exc).__name__}: {str(exc)[:250]}"
        sources.append(record)
    manifest = {
        "schema_version": 1, "manufacturer": "Microchip",
        "scope": "samr30_official_online_ordering_rows_original_bytes_only",
        "pdf_document_to_crosscheck": PDF_DOCUMENT,
        "pdf_semantic_crosscheck_completed": False,
        "live_original_source_observation_complete": all(
            r["status"] == "SOURCE_BYTES_CAPTURED_AND_REPLAYED" for r in sources),
        "sources": sources,
        "production_write_authorized": False,
        "software_supported_claimed": False,
        "phase1_icpn_fields_verified_by_this_source_only": False,
    }
    (root / "manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    audit_original_receipt(root)
    require(manifest["live_original_source_observation_complete"],
            "SOURCE_NOT_AVAILABLE_OR_UNREPLAYABLE; check preserved original HTML and receipt")
    return replay(root)


def audit_original_receipt(root):
    """Hash-audit any downloaded HTML, even if the semantic table was missing.

    HTTP 200 from a publisher may return a JS-only shell. Keep those bytes
    as diagnostics, but never count them as four exact ordering rows.
    """
    root = Path(root)
    receipt = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    require(receipt.get("schema_version") == 1
            and receipt.get("manufacturer") == "Microchip"
            and receipt.get("production_write_authorized") is False
            and receipt.get("phase1_icpn_fields_verified_by_this_source_only") is False
            and receipt.get("pdf_semantic_crosscheck_completed") is False,
            "untrusted original source-only receipt")
    sources = receipt.get("sources")
    require(isinstance(sources, list) and len(sources) == 2
            and {x.get("lane") for x in sources} == set(URLS),
            "incomplete original source receipt")
    for event in sources:
        lane = event["lane"]
        require(event["url"] == URLS[lane], "source endpoint changed")
        state = event["status"]
        require(state in ("SOURCE_NOT_AVAILABLE",
                          "SOURCE_BYTES_CAPTURED_TABLE_NOT_REPLAYABLE",
                          "SOURCE_BYTES_CAPTURED_AND_REPLAYED"),
                "unrecognized manufacturer source state")
        if state == "SOURCE_NOT_AVAILABLE":
            require(event["file"] is None and event["original_sha256"] is None
                    and event["bytes"] is None
                    and event["exact_ordering_row_count"] == 0,
                    "failed source cannot claim captured original bytes")
            continue
        filename = f"manufacturer-{lane.lower()}-original.html"
        path = root / filename
        require(event["file"] == filename and path.is_file()
                and not path.is_symlink(), "missing original HTML or altered filename")
        raw = path.read_bytes()
        require(0 < len(raw) <= MAX_BYTES
                and event["original_sha256"] == hashlib.sha256(raw).hexdigest()
                and event["bytes"] == len(raw), "original HTML SHA mismatch")
        required = {k: k.encode() in raw for k in EXPECTED[lane]}
        require(event.get("manufacturer_order_code_tokens_present") == required,
                "observed exact SKU tokens differ from original HTML")
        if state == "SOURCE_BYTES_CAPTURED_AND_REPLAYED":
            require(len(parse_original_html(raw, lane)) ==
                    event["exact_ordering_row_count"], "replayed source changed")
        else:
            require(event["exact_ordering_row_count"] == 0,
                    "unreplayable HTML cannot claim exact manufacturer rows")
    return receipt


def replay(root):
    root = Path(root)
    manifest = audit_original_receipt(root)
    require(manifest.get("schema_version") == 1
            and manifest.get("manufacturer") == "Microchip"
            and manifest.get("scope") ==
                "samr30_official_online_ordering_rows_original_bytes_only"
            and manifest.get("pdf_semantic_crosscheck_completed") is False
            and manifest.get("phase1_icpn_fields_verified_by_this_source_only") is False
            and manifest.get("production_write_authorized") is False
            and manifest.get("software_supported_claimed") is False
            and manifest.get("live_original_source_observation_complete") is True,
            "source-only manufacturer capture cannot establish qualified fields")
    records = manifest.get("sources")
    require(isinstance(records, list) and len(records) == len(URLS)
            and {r.get("lane") for r in records} == set(URLS),
            "missing or duplicated source document")
    rows = []
    for record in records:
        lane = record["lane"]
        name = f"manufacturer-{lane.lower()}-original.html"
        require(record.get("url") == URLS[lane] and record.get("file") == name
                and record.get("status") == "SOURCE_BYTES_CAPTURED_AND_REPLAYED",
                "untrusted source scope or filename")
        original = root / name
        require(original.is_file() and not original.is_symlink(),
                "source HTML missing or symlinked")
        raw = original.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        require(SHA.fullmatch(digest) and digest == record.get("original_sha256")
                and len(raw) == record.get("bytes"),
                "original manufacturer HTML source SHA256 mismatch")
        observed = parse_original_html(raw, lane)
        require(record.get("exact_ordering_row_count") == len(observed),
                "source table record count disagrees")
        for row in observed:
            rows.append({**row,
                         "original_manufacturer_html_sha256": digest,
                         "original_manufacturer_html_url": URLS[lane],
                         "original_source_file": name})
    require(len(rows) == 4 and len({r["icpn"] for r in rows}) == 4,
            "four exact SAM R30 ordering observations unavailable")
    return {
        "manufacturer": "Microchip", "original_html_source_replay_pass": True,
        "original_pdf_semantics_replayed": False,
        "exact_ordering_code_observations": sorted(rows, key=lambda r:r["icpn"]),
        "exact_rows_observed": len(rows),
        "phase1_exact_fields_verified": 0,
        "production_write_authorized": False,
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture", type=Path)
    mode.add_argument("--replay", type=Path)
    p.add_argument("--report", type=Path)
    args = p.parse_args()
    result = capture(args.capture) if args.capture else replay(args.replay)
    if args.report is not None:
        require("production" not in {x.casefold() for x in
                                    args.report.resolve().parts},
                "Production report forbidden")
        require(not args.report.exists(), "Research report output already exists")
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(result, indent=2, sort_keys=True)+"\n",
                               encoding="utf-8")
    print(json.dumps(result, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

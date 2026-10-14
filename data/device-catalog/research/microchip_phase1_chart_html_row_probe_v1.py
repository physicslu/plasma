#!/usr/bin/env python3
"""Read-only MicrochipDirect chart original-HTML row discovery (NOT spec parsing)."""
from __future__ import annotations

import argparse
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re

from microchip_phase1_chart_html_source_v1 import replay

DEVICE_PATTERN = re.compile(r"(?<![A-Z0-9])ATSAMD21G18[A-Z0-9]*(?![A-Z0-9])", re.I)
FAMILY_PATTERN = re.compile(r"\bATSAMD21[A-Z0-9]+", re.I)


class RowProbe(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.current_cells = []
        self.cell_tag = None
        self.cell_parts = []
        self.cell_count = 0
        self.total_rows = 0
        self.header_samples = []
        self.target_rows = []
        self.family_device_name_samples = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            if self.depth == 0:
                self.current_cells = []
                self.total_rows += 1
            self.depth += 1
        elif tag in ("td", "th") and self.depth and self.cell_tag is None:
            self.cell_tag = tag
            self.cell_parts = []
        elif tag in ("br", "p") and self.cell_tag:
            self.cell_parts.append(" ")

    def handle_data(self, data):
        if self.cell_tag:
            self.cell_parts.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.cell_tag == tag:
            text = unescape(re.sub(r"\s+", " ", "".join(self.cell_parts))).strip()
            self.current_cells.append({"kind": tag, "text": text[:500]})
            self.cell_tag = None
            self.cell_parts = []
        elif tag == "tr" and self.depth:
            self.depth -= 1
            if not self.depth:
                self._finalize()

    def _finalize(self):
        cells = self.current_cells
        if len(cells) > 2 and any(x["kind"] == "th" for x in cells):
            if len(self.header_samples) < 12:
                self.header_samples.append({
                    "source_tr_ordinal": self.total_rows,
                    "headers_observed": [x["text"] for x in cells[:100]]
                })
        if len(self.family_device_name_samples) < 60:
            for cell in cells:
                for match in FAMILY_PATTERN.findall(cell["text"]):
                    name = match.upper()
                    if name not in self.family_device_name_samples:
                        self.family_device_name_samples.append(name)
                    if len(self.family_device_name_samples) >= 60:
                        break
        if len(self.target_rows) < 10 and any(
            DEVICE_PATTERN.search(x["text"]) for x in cells):
            self.target_rows.append({
                "source_tr_ordinal": self.total_rows,
                "raw_cell_count": len(cells),
                "raw_cells_not_mapped": cells[:120],
            })
        self.current_cells = []


def inspect(original_root):
    root = Path(original_root)
    integrity = replay(root)
    raw = (root / "original-chart.html").read_bytes()
    html_text = raw.decode("utf-8", errors="replace")
    parser = RowProbe()
    parser.feed(html_text)
    parser.close()
    return {
        "schema_version": 1, "policy": "ADR-0002 Phase 1",
        "manufacturer": "Microchip", "source_url": integrity["source_url"],
        "original_html_sha256": integrity["original_byte_sha256"],
        "original_html_bytes": integrity["size_bytes"],
        "source_tr_nodes_seen": parser.total_rows,
        "header_samples": parser.header_samples,
        "target": "ATSAMD21G18-family chart row",
        "family_name_samples_from_raw_table": parser.family_device_name_samples,
        "target_raw_row_candidates": parser.target_rows,
        "source_capture_replayed": True,
        "semantic_field_alignment_verified": False,
        "chart_row_commercial_icpn_verified": False,
        "phase1_specifications_verified": 0,
        "internal_admission_count": 0,
        "production_write_authorized": False,
        "catalog_publication_authorized": False,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--original-root", type=Path, required=True)
    ap.add_argument("--report", type=Path)
    a = ap.parse_args()
    value = inspect(a.original_root)
    if a.report:
        if "production" in {p.casefold() for p in a.report.resolve().parts}:
            raise ValueError("Production report path prohibited")
        a.report.parent.mkdir(parents=True, exist_ok=True)
        a.report.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
    print(json.dumps(value, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

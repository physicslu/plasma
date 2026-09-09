#!/usr/bin/env python3
"""Generic ST product-page dual-surface commercial identity evidence.

Current ST product pages may split authoritative commercial facts across two
rendered tables:

- Quality and Reliability owns exact orderable Part Number identity.
- Sample & Buy owns Marketing Status / lifecycle for those exact identities.

This module joins those surfaces only when their exact Part Number sets match.
It is deliberately family-neutral and does not define a retained parser profile;
family adapters own parser-profile identity so historical provenance cannot be
silently reinterpreted.
"""

from __future__ import annotations

import hashlib
import re
from html.parser import HTMLParser
from typing import Any

from st_browser_acquisition import BROWSER_TRANSPORT
from st_product_page_acquisition import (
    ACTIVE_MARKETING_STATUS,
    AcquisitionError,
    ICPN_TOKEN_RE,
    PARSER_VERSION,
    SCHEMA_VERSION,
    normalize_text,
)

QUALITY_HEADING = "Quality and Reliability"
SAMPLE_BUY_HEADING = "Sample & Buy"
PART_NUMBER_LABEL = "Part Number"
MARKETING_STATUS_LABEL = "Marketing Status"
EVIDENCE_SURFACE = "quality_and_reliability_identity_plus_sample_and_buy_lifecycle"


class SectionTableParser(HTMLParser):
    """Collect parser-visible text/table rows under one exact H2 heading."""

    def __init__(self, heading: str) -> None:
        super().__init__(convert_charrefs=True)
        self.heading = heading.casefold()
        self._hidden_depth = 0
        self._heading_depth = 0
        self._heading_parts: list[str] = []
        self._in_section = False
        self._seen = False
        self._done = False
        self._row_depth = 0
        self._cell_depth = 0
        self._row_cells: list[str] = []
        self._cell_parts: list[str] = []
        self.section_parts: list[str] = []
        self.table_rows: list[list[str]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        del attrs
        tag = tag.lower()
        if tag in {"script", "style", "noscript"}:
            self._hidden_depth += 1
        if tag == "h2" and self._hidden_depth == 0:
            self._heading_depth += 1
            self._heading_parts = []
            return
        if self._hidden_depth or not self._in_section:
            return
        if tag == "tr":
            if self._row_depth == 0:
                self._row_cells = []
            self._row_depth += 1
        elif tag in {"th", "td"} and self._row_depth:
            self._cell_depth += 1
            if self._cell_depth == 1:
                self._cell_parts = []

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in {"th", "td"} and self._cell_depth:
            if self._cell_depth == 1:
                self._row_cells.append(normalize_text(" ".join(self._cell_parts)))
                self._cell_parts = []
            self._cell_depth -= 1
        elif tag == "tr" and self._row_depth:
            self._row_depth -= 1
            if self._row_depth == 0 and self._row_cells:
                self.table_rows.append(list(self._row_cells))
                self._row_cells = []

        if tag == "h2" and self._heading_depth:
            heading = normalize_text(" ".join(self._heading_parts))
            self._heading_depth -= 1
            if heading.casefold() == self.heading:
                self._seen = True
                self._in_section = True
            elif self._in_section:
                self._in_section = False
                self._done = True
            self._heading_parts = []
        if tag in {"script", "style", "noscript"} and self._hidden_depth:
            self._hidden_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._hidden_depth or self._done:
            return
        if self._heading_depth:
            self._heading_parts.append(data)
            return
        if self._in_section:
            self.section_parts.append(data)
            if self._cell_depth:
                self._cell_parts.append(data)

    @property
    def seen(self) -> bool:
        return self._seen


def parse_section(html_text: str, heading: str) -> SectionTableParser:
    parser = SectionTableParser(heading)
    parser.feed(html_text)
    parser.close()
    return parser


def _header_indices(
    rows: list[list[str]],
    *,
    required: tuple[str, ...],
    surface: str,
) -> tuple[int, dict[str, int]]:
    for row_index, row in enumerate(rows):
        normalized = [normalize_text(cell) for cell in row]
        if all(label in normalized for label in required):
            return row_index, {label: normalized.index(label) for label in required}
    raise AcquisitionError(
        f"{surface} table missing required column(s): {', '.join(required)}"
    )


def _part_number_tokens(
    rows: list[list[str]],
    *,
    row_index: int,
    part_index: int,
    base_device: str,
    surface: str,
) -> list[str]:
    values: list[str] = []
    for row in rows[row_index + 1 :]:
        if len(row) <= part_index:
            continue
        tokens = ICPN_TOKEN_RE.findall(row[part_index])
        if not tokens:
            continue
        if len(tokens) != 1:
            raise AcquisitionError(f"{surface} row contains multiple STM32 part numbers")
        icpn = tokens[0]
        if not icpn.startswith(base_device):
            raise AcquisitionError(f"{surface} contains foreign STM32 token: {icpn}")
        if icpn == base_device:
            continue
        if icpn in values:
            raise AcquisitionError(f"{surface} contains duplicate exact ICPN: {icpn}")
        values.append(icpn)
    if not values:
        raise AcquisitionError(f"{surface} contains no exact ICPN for {base_device}")
    return values


def extract_dual_surface_part_number_records(
    html_text: str,
    base_device: str,
) -> tuple[list[dict[str, object]], str]:
    """Join Q&R exact identity to Sample & Buy lifecycle fail-closed."""

    if re.fullmatch(r"STM32[A-Z0-9]+", base_device) is None:
        raise AcquisitionError(f"invalid STM32 base device: {base_device!r}")

    quality = parse_section(html_text, QUALITY_HEADING)
    sample = parse_section(html_text, SAMPLE_BUY_HEADING)
    if not quality.seen:
        raise AcquisitionError("Quality and Reliability section not found")
    if not sample.seen:
        raise AcquisitionError("Sample & Buy section not found")

    quality_text = normalize_text(" ".join(quality.section_parts))
    quality_foreign = [
        token
        for token in dict.fromkeys(ICPN_TOKEN_RE.findall(quality_text))
        if not token.startswith(base_device)
    ]
    if quality_foreign:
        raise AcquisitionError(
            "Quality and Reliability contains foreign STM32 token(s): "
            + ", ".join(quality_foreign)
        )

    q_header, q_indices = _header_indices(
        quality.table_rows,
        required=(PART_NUMBER_LABEL,),
        surface="Quality and Reliability",
    )
    q_icpns = _part_number_tokens(
        quality.table_rows,
        row_index=q_header,
        part_index=q_indices[PART_NUMBER_LABEL],
        base_device=base_device,
        surface="Quality and Reliability",
    )

    s_header, s_indices = _header_indices(
        sample.table_rows,
        required=(PART_NUMBER_LABEL, MARKETING_STATUS_LABEL),
        surface="Sample & Buy",
    )
    status_by_icpn: dict[str, str] = {}
    for row in sample.table_rows[s_header + 1 :]:
        if len(row) <= max(s_indices.values()):
            continue
        tokens = ICPN_TOKEN_RE.findall(row[s_indices[PART_NUMBER_LABEL]])
        if not tokens:
            continue
        if len(tokens) != 1:
            raise AcquisitionError("Sample & Buy row contains multiple STM32 part numbers")
        icpn = tokens[0]
        if not icpn.startswith(base_device):
            raise AcquisitionError(f"Sample & Buy contains foreign STM32 token: {icpn}")
        if icpn == base_device:
            continue
        status = normalize_text(row[s_indices[MARKETING_STATUS_LABEL]])
        if not status:
            raise AcquisitionError(f"{icpn}: Sample & Buy Marketing Status is empty")
        prior = status_by_icpn.get(icpn)
        if prior is not None:
            if prior != status:
                raise AcquisitionError(f"{icpn}: conflicting Sample & Buy Marketing Status rows")
            raise AcquisitionError(f"Sample & Buy contains duplicate exact ICPN: {icpn}")
        status_by_icpn[icpn] = status

    quality_set = set(q_icpns)
    lifecycle_set = set(status_by_icpn)
    if quality_set != lifecycle_set:
        missing = sorted(quality_set - lifecycle_set)
        extra = sorted(lifecycle_set - quality_set)
        raise AcquisitionError(
            "ST dual-surface exact ICPN set mismatch: "
            f"missing_lifecycle={missing} extra_lifecycle={extra}"
        )

    records = [
        {
            "icpn": icpn,
            "marketing_status": status_by_icpn[icpn],
            "active": status_by_icpn[icpn].casefold().startswith(ACTIVE_MARKETING_STATUS),
        }
        for icpn in q_icpns
    ]
    lifecycle_projection = " ".join(
        f"{record['icpn']} | {record['marketing_status']}" for record in records
    )
    canonical_evidence_text = (
        quality_text
        + " | Sample & Buy lifecycle projection | "
        + lifecycle_projection
    )
    return records, canonical_evidence_text


def dual_surface_ready(html_text: str, base_device: str) -> bool:
    try:
        extract_dual_surface_part_number_records(html_text, base_device)
    except AcquisitionError:
        return False
    return True


def build_dual_surface_browser_evidence_record(
    *,
    body: bytes,
    source_url: str,
    final_url: str,
    base_device: str,
    retrieved_at_utc: str,
    parser_profile: str,
    http_etag: str | None = None,
    http_last_modified: str | None = None,
) -> dict[str, object]:
    """Build browser evidence while leaving profile identity to the family adapter."""

    if not parser_profile or not re.fullmatch(r"[a-z0-9_.-]+", parser_profile):
        raise AcquisitionError("dual-surface parser_profile is required")
    if http_etag is not None or http_last_modified is not None:
        raise AcquisitionError("browser evidence must not claim raw HTTP cache headers")
    try:
        html_text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AcquisitionError("rendered ST product DOM is not valid UTF-8") from exc

    records, canonical_text = extract_dual_surface_part_number_records(html_text, base_device)
    exact_icpns = [str(record["icpn"]) for record in records if record["active"] is True]
    excluded = [
        {"icpn": str(record["icpn"]), "marketing_status": str(record["marketing_status"])}
        for record in records
        if record["active"] is not True
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "parser_profile": parser_profile,
        "acquisition_transport": BROWSER_TRANSPORT,
        "source_url": source_url,
        "final_url": final_url,
        "base_device": base_device,
        "retrieved_at_utc": retrieved_at_utc,
        "http_etag": None,
        "http_last_modified": None,
        "rendered_dom_sha256": hashlib.sha256(body).hexdigest(),
        "evidence_section_sha256": hashlib.sha256(canonical_text.encode("utf-8")).hexdigest(),
        "evidence_surface": EVIDENCE_SURFACE,
        "part_number_records": records,
        "excluded_non_active_part_numbers": excluded,
        "exact_icpns": exact_icpns,
    }

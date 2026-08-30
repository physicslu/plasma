#!/usr/bin/env python3
"""Fail-closed probe for exact STM32 commercial ICPNs on official ST product pages.

This is a research acquisition tool, not a production crawler and not a dataset writer.
It emits candidate evidence only. Checked-in commercial ICPNs still require the normal
Phase 2 provenance and deterministic mapping review.
"""

from __future__ import annotations

import argparse
import hashlib
from html.parser import HTMLParser
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen

SCHEMA_VERSION = 1
PARSER_VERSION = 2
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
APPROVED_HOST = "www.st.com"
ICPN_TOKEN_RE = re.compile(r"\bSTM32[A-Z0-9]+\b")
BASE_DEVICE_RE = re.compile(r"^STM32[A-Z0-9]+$")
ACTIVE_MARKETING_STATUS = "active"


class AcquisitionError(RuntimeError):
    pass


class QualitySectionParser(HTMLParser):
    """Collect text and table cells from the Quality and Reliability H2 section."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._hidden_depth = 0
        self._heading_depth = 0
        self._heading_parts: list[str] = []
        self._in_quality = False
        self._quality_seen = False
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
        if self._hidden_depth or not self._in_quality:
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
            if heading.casefold() == "quality and reliability":
                self._quality_seen = True
                self._in_quality = True
            elif self._in_quality:
                self._in_quality = False
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
        if self._in_quality:
            self.section_parts.append(data)
            if self._cell_depth:
                self._cell_parts.append(data)

    @property
    def quality_seen(self) -> bool:
        return self._quality_seen


def normalize_text(text: str) -> str:
    return " ".join(text.split())


def validate_source_url(source_url: str) -> None:
    parsed = urlparse(source_url)
    if parsed.scheme != "https":
        raise AcquisitionError("source URL must use HTTPS")
    if parsed.hostname != APPROVED_HOST:
        raise AcquisitionError(f"source host must be {APPROVED_HOST}")
    if not parsed.path.startswith("/en/") or not parsed.path.endswith(".html"):
        raise AcquisitionError("source must be a canonical English ST product HTML page")


def validate_base_device(base_device: str) -> None:
    if not BASE_DEVICE_RE.fullmatch(base_device):
        raise AcquisitionError(f"invalid STM32 base device: {base_device!r}")


def _extract_quality_part_number_records(
    html_text: str,
    base_device: str,
) -> tuple[list[dict[str, object]], str]:
    validate_base_device(base_device)
    parser = QualitySectionParser()
    parser.feed(html_text)
    parser.close()

    if not parser.quality_seen:
        raise AcquisitionError("Quality and Reliability section not found")

    section_text = normalize_text(" ".join(parser.section_parts))
    if "Part Number" not in section_text:
        raise AcquisitionError("Part Number marker not found in Quality and Reliability section")
    if "Marketing Status" not in section_text:
        raise AcquisitionError("Marketing Status marker not found in Quality and Reliability section")

    all_tokens = list(dict.fromkeys(ICPN_TOKEN_RE.findall(section_text)))
    foreign_tokens = [token for token in all_tokens if not token.startswith(base_device)]
    if foreign_tokens:
        raise AcquisitionError(
            "unexpected foreign STM32 token(s) in evidence section: " + ", ".join(foreign_tokens)
        )

    header: list[str] | None = None
    part_index = -1
    status_index = -1
    header_row_index = -1
    for index, row in enumerate(parser.table_rows):
        normalized = [normalize_text(cell) for cell in row]
        if "Part Number" in normalized and "Marketing Status" in normalized:
            header = normalized
            part_index = normalized.index("Part Number")
            status_index = normalized.index("Marketing Status")
            header_row_index = index
            break
    if header is None:
        raise AcquisitionError(
            "Quality and Reliability table with Part Number and Marketing Status columns not found"
        )

    by_icpn: dict[str, dict[str, object]] = {}
    for row in parser.table_rows[header_row_index + 1 :]:
        if len(row) <= max(part_index, status_index):
            continue
        tokens = ICPN_TOKEN_RE.findall(row[part_index])
        if not tokens:
            continue
        if len(tokens) != 1:
            raise AcquisitionError("Quality and Reliability row contains multiple STM32 part numbers")
        icpn = tokens[0]
        if not icpn.startswith(base_device):
            raise AcquisitionError(f"unexpected foreign STM32 token in table row: {icpn}")
        if icpn == base_device:
            continue
        marketing_status = normalize_text(row[status_index])
        if not marketing_status:
            raise AcquisitionError(f"{icpn}: Marketing Status is empty")
        record = {
            "icpn": icpn,
            "marketing_status": marketing_status,
            "active": marketing_status.casefold().startswith(ACTIVE_MARKETING_STATUS),
        }
        existing = by_icpn.get(icpn)
        if existing is not None and existing != record:
            raise AcquisitionError(f"{icpn}: conflicting duplicate Marketing Status rows")
        by_icpn[icpn] = record

    if not by_icpn:
        raise AcquisitionError(f"no exact commercial ICPN records found for {base_device}")
    active_records = [record for record in by_icpn.values() if record["active"] is True]
    if not active_records:
        raise AcquisitionError(f"no Active commercial ICPN candidates found for {base_device}")
    return list(by_icpn.values()), section_text


def extract_part_number_records(html_text: str, base_device: str) -> tuple[list[dict[str, object]], str]:
    """Return audited Q&R part-number rows including Marketing Status."""
    return _extract_quality_part_number_records(html_text, base_device)


def extract_exact_icpns(html_text: str, base_device: str) -> tuple[list[str], str]:
    """Return only exact ICPNs whose official ST Marketing Status is Active."""
    records, section_text = _extract_quality_part_number_records(html_text, base_device)
    return [str(record["icpn"]) for record in records if record["active"] is True], section_text


def fetch_html(source_url: str, timeout_seconds: float) -> tuple[bytes, str, str | None, str | None]:
    validate_source_url(source_url)
    request = Request(
        source_url,
        headers={
            "User-Agent": "Plasma-ICPN-Research/1.0 (+https://github.com/physicslu/plasma)",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - URL is validated above
        final_url = response.geturl()
        validate_source_url(final_url)
        content_type = response.headers.get_content_type()
        if content_type not in {"text/html", "application/xhtml+xml"}:
            raise AcquisitionError(f"unexpected content type: {content_type}")
        body = response.read(MAX_RESPONSE_BYTES + 1)
        if len(body) > MAX_RESPONSE_BYTES:
            raise AcquisitionError(f"response exceeds {MAX_RESPONSE_BYTES} bytes")
        return (
            body,
            final_url,
            response.headers.get("ETag"),
            response.headers.get("Last-Modified"),
        )


def build_evidence_record(
    *,
    body: bytes,
    source_url: str,
    final_url: str,
    base_device: str,
    retrieved_at_utc: str,
    http_etag: str | None = None,
    http_last_modified: str | None = None,
) -> dict[str, object]:
    try:
        html_text = body.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise AcquisitionError("ST product page is not valid UTF-8") from exc

    records, section_text = extract_part_number_records(html_text, base_device)
    exact_icpns = [str(record["icpn"]) for record in records if record["active"] is True]
    excluded = [
        {"icpn": str(record["icpn"]), "marketing_status": str(record["marketing_status"])}
        for record in records
        if record["active"] is not True
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "parser_version": PARSER_VERSION,
        "source_url": source_url,
        "final_url": final_url,
        "base_device": base_device,
        "retrieved_at_utc": retrieved_at_utc,
        "http_etag": http_etag,
        "http_last_modified": http_last_modified,
        "raw_sha256": hashlib.sha256(body).hexdigest(),
        "evidence_section_sha256": hashlib.sha256(section_text.encode("utf-8")).hexdigest(),
        "evidence_surface": "quality_and_reliability_part_number_marketing_status",
        "part_number_records": records,
        "excluded_non_active_part_numbers": excluded,
        "exact_icpns": exact_icpns,
    }


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-device", required=True, help="Expected base device, e.g. STM32F103RB")
    parser.add_argument("--source-url", required=True, help="Canonical official www.st.com product URL")
    parser.add_argument("--input-html", type=Path, help="Parse a saved HTML file instead of live HTTP")
    parser.add_argument("--output", type=Path, help="Write evidence JSON to this file; stdout if omitted")
    parser.add_argument("--timeout", type=float, default=30.0, help="Live HTTP timeout in seconds")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        validate_source_url(args.source_url)
        validate_base_device(args.base_device)
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        if args.input_html:
            body = args.input_html.read_bytes()
            if len(body) > MAX_RESPONSE_BYTES:
                raise AcquisitionError(f"input exceeds {MAX_RESPONSE_BYTES} bytes")
            final_url = args.source_url
            etag = None
            last_modified = None
        else:
            body, final_url, etag, last_modified = fetch_html(args.source_url, args.timeout)

        record = build_evidence_record(
            body=body,
            source_url=args.source_url,
            final_url=final_url,
            base_device=args.base_device,
            retrieved_at_utc=retrieved_at,
            http_etag=etag,
            http_last_modified=last_modified,
        )
        payload = json.dumps(record, indent=2, sort_keys=True) + "\n"
        if args.output:
            args.output.write_text(payload, encoding="utf-8")
        else:
            sys.stdout.write(payload)
        return 0
    except (AcquisitionError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

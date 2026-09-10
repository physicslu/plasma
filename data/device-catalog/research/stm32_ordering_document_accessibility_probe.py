#!/usr/bin/env python3
"""Bounded official-ST ordering-document accessibility comparison for STM32U0/C0.

This gate compares evidence accessibility only. It does not select a next family,
admit canonical data, define programming equivalence, or authorize Production.
"""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin, urlparse

from st_product_page_acquisition import AcquisitionError, validate_source_url

HERE = Path(__file__).resolve().parent
DEFAULT_MANIFEST = HERE / "stm32-ordering-document-accessibility-manifest.json"
IDENTITY_MANIFEST = HERE / "stm32-evidence-accessibility-probe-manifest.json"
IDENTITY_BASELINE = HERE / "stm32-evidence-accessibility-probe-baseline.json"
PROBE_ID = "stm32-u0-c0-official-st-ordering-document-accessibility-v1"
TARGET_SERIES = ("STM32U0", "STM32C0")
EXPECTED_TARGET_COUNT = 9
REQUIRED_ORDERING_LABELS = (
    "device family",
    "product type",
    "device subfamily",
    "pin count",
    "flash memory size",
    "package",
    "temperature range",
)
OPTIONAL_TERMINAL_LABELS = ("packing", "option")


@dataclass(frozen=True)
class Target:
    series: str
    subfamily: str
    base_device: str
    product_url: str


ProductFetcher = Callable[[str, float], tuple[bytes, str, str | None, str | None]]
PdfFetcher = Callable[[str, float], tuple[bytes, str, str | None]]
TextExtractor = Callable[[bytes], str]


class DocumentUnavailable(RuntimeError):
    pass


class _HrefParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() != "a":
            return
        for key, value in attrs:
            if key.lower() == "href" and value:
                self.hrefs.append(value)


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise AcquisitionError(f"{path}: object required")
    return value


def _expected_targets() -> list[tuple[str, str, str, str]]:
    identity_manifest = _read_json(IDENTITY_MANIFEST)
    identity_baseline = _read_json(IDENTITY_BASELINE)
    raw = identity_manifest.get("targets")
    retained = identity_baseline.get("targets")
    if not isinstance(raw, list) or not isinstance(retained, list):
        raise AcquisitionError("identity probe target bindings unavailable")
    active_bases = {
        str(item.get("base_device"))
        for item in retained
        if isinstance(item, dict)
        and item.get("series") in TARGET_SERIES
        and item.get("disposition") == "active_candidates"
    }
    expected: list[tuple[str, str, str, str]] = []
    for item in raw:
        if not isinstance(item, dict) or item.get("series") not in TARGET_SERIES:
            continue
        base = str(item.get("base_device"))
        if base not in active_bases:
            raise AcquisitionError(f"{base}: U0/C0 ordering probe target is not retained Active identity evidence")
        expected.append((str(item["series"]), str(item["subfamily"]), base, str(item["source_url"])))
    if len(expected) != EXPECTED_TARGET_COUNT:
        raise AcquisitionError(f"expected {EXPECTED_TARGET_COUNT} U0/C0 targets, got {len(expected)}")
    return expected


def read_manifest(path: Path = DEFAULT_MANIFEST) -> tuple[str, list[Target]]:
    payload = _read_json(path)
    if payload.get("schema_version") != 1 or payload.get("probe_id") != PROBE_ID:
        raise AcquisitionError("unsupported ordering-document accessibility manifest")
    pilot = payload.get("pilot_id")
    raw = payload.get("targets")
    if not isinstance(pilot, str) or not pilot.strip() or not isinstance(raw, list):
        raise AcquisitionError("ordering-document manifest missing pilot_id/targets")
    targets: list[Target] = []
    for item in raw:
        if not isinstance(item, dict):
            raise AcquisitionError("ordering-document target must be an object")
        series = item.get("series"); sub = item.get("subfamily"); base = item.get("base_device"); url = item.get("product_url")
        if series not in TARGET_SERIES or not all(isinstance(v, str) and v for v in (sub, base, url)):
            raise AcquisitionError("invalid ordering-document target")
        validate_source_url(url)
        targets.append(Target(series, sub, base, url))
    observed = [(t.series, t.subfamily, t.base_device, t.product_url) for t in targets]
    if observed != _expected_targets():
        raise AcquisitionError("ordering-document target selection drifted from retained U0/C0 identity probe")
    return pilot, targets


def datasheet_urls_from_html(html_text: str, product_url: str) -> list[str]:
    parser = _HrefParser(); parser.feed(html_text); parser.close()
    values: list[str] = []
    for href in parser.hrefs:
        absolute = urljoin(product_url, href)
        parsed = urlparse(absolute)
        if parsed.scheme != "https" or parsed.hostname not in {"www.st.com", "st.com"}:
            continue
        if "/resource/en/datasheet/" not in parsed.path or not parsed.path.lower().endswith(".pdf"):
            continue
        normalized = f"https://www.st.com{parsed.path}"
        if normalized not in values:
            values.append(normalized)
    return values


def choose_datasheet_url(urls: list[str], base_device: str) -> tuple[str, bool]:
    expected_name = f"{base_device.lower()}.pdf"
    exact = [url for url in urls if urlparse(url).path.rsplit("/", 1)[-1].lower() == expected_name]
    if len(exact) == 1:
        return exact[0], False
    if len(exact) > 1:
        raise AcquisitionError(f"{base_device}: duplicate canonical datasheet links")
    if len(urls) == 1:
        return urls[0], True
    if not urls:
        raise DocumentUnavailable(f"{base_device}: product page exposes no official ST datasheet PDF link")
    raise AcquisitionError(f"{base_device}: multiple datasheet links but no deterministic canonical match: {urls}")


def normalize_pdf_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def document_identity(text: str) -> tuple[str | None, int | None]:
    pairs = re.findall(r"\b(DS\d+)\s*-\s*Rev\s*(\d+)\b", text, flags=re.IGNORECASE)
    if not pairs:
        return None, None
    doc, rev = Counter((a.upper(), int(b)) for a, b in pairs).most_common(1)[0][0]
    return doc, rev


def inspect_pdf_text(text: str, subfamily: str) -> dict[str, object]:
    normalized = normalize_pdf_text(text)
    folded = normalized.casefold()
    labels = {label: label in folded for label in REQUIRED_ORDERING_LABELS}
    terminal = {label: label in folded for label in OPTIONAL_TERMINAL_LABELS}
    ordering_present = "ordering information" in folded
    subfamily_present = subfamily.casefold() in folded
    document_id, revision = document_identity(normalized)
    return {
        "ordering_information_present": ordering_present,
        "subfamily_text_present": subfamily_present,
        "required_label_presence": labels,
        "required_label_count": sum(labels.values()),
        "required_label_total": len(REQUIRED_ORDERING_LABELS),
        "terminal_label_presence": terminal,
        "terminal_semantics_present": any(terminal.values()),
        "ordering_schema_complete": ordering_present and subfamily_present and all(labels.values()) and any(terminal.values()),
        "document_id": document_id,
        "revision": revision,
    }


def run_probe(*, pilot_id: str, targets: list[Target], product_fetcher: ProductFetcher, pdf_fetcher: PdfFetcher, text_extractor: TextExtractor, timeout_seconds: float = 90.0) -> dict[str, object]:
    results: list[dict[str, object]] = []
    counters: dict[str, Counter[str]] = {series: Counter() for series in TARGET_SERIES}
    unique_pdf_hashes: dict[str, set[str]] = {series: set() for series in TARGET_SERIES}

    for target in targets:
        c = counters[target.series]; c["attempted"] += 1
        result: dict[str, object] = {"series": target.series, "subfamily": target.subfamily, "base_device": target.base_device, "product_url": target.product_url}
        try:
            body, final_url, _, _ = product_fetcher(target.product_url, timeout_seconds)
            validate_source_url(final_url)
            html_text = body.decode("utf-8")
            urls = datasheet_urls_from_html(html_text, final_url)
            datasheet_url, shared_slug = choose_datasheet_url(urls, target.base_device)
            pdf, pdf_final_url, content_type = pdf_fetcher(datasheet_url, timeout_seconds)
            parsed = urlparse(pdf_final_url)
            if parsed.scheme != "https" or parsed.hostname not in {"www.st.com", "st.com"} or "/resource/en/datasheet/" not in parsed.path:
                raise AcquisitionError(f"{target.base_device}: datasheet redirect escaped official ST resource boundary")
            if not pdf.startswith(b"%PDF-"):
                raise AcquisitionError(f"{target.base_device}: datasheet response is not PDF")
            digest = hashlib.sha256(pdf).hexdigest()
            inspection = inspect_pdf_text(text_extractor(pdf), target.subfamily)
            if inspection["ordering_schema_complete"] is not True:
                raise AcquisitionError(f"{target.base_device}: ordering-information text contract incomplete")
            result.update(
                disposition="accessible",
                product_page_status="success",
                datasheet_url=datasheet_url,
                datasheet_final_url=pdf_final_url,
                shared_datasheet_slug=shared_slug,
                pdf_content_type=content_type,
                pdf_sha256=digest,
                pdf_size_bytes=len(pdf),
                **inspection,
            )
            c["accessible"] += 1; c["schema_complete"] += 1; c["dispositioned"] += 1
            unique_pdf_hashes[target.series].add(digest)
        except DocumentUnavailable as exc:
            result.update(disposition="document_unavailable", error=str(exc), manual_intervention_required=False)
            c["unavailable"] += 1; c["dispositioned"] += 1
        except (AcquisitionError, UnicodeDecodeError, OSError, RuntimeError) as exc:
            result.update(disposition="manual_review", error_type=type(exc).__name__, error=str(exc), manual_intervention_required=True)
            c["manual_review"] += 1
        results.append(result)

    by_series: dict[str, object] = {}
    for series in TARGET_SERIES:
        c = counters[series]; attempted = c["attempted"]
        by_series[series] = {
            "attempted_targets": attempted,
            "dispositioned_targets": c["dispositioned"],
            "accessible_targets": c["accessible"],
            "document_unavailable_targets": c["unavailable"],
            "manual_review_targets": c["manual_review"],
            "ordering_schema_complete_targets": c["schema_complete"],
            "accessibility_fraction": round(c["accessible"] / attempted, 6) if attempted else 0.0,
            "ordering_schema_complete_fraction": round(c["schema_complete"] / attempted, 6) if attempted else 0.0,
            "unique_pdf_document_count": len(unique_pdf_hashes[series]),
            "document_access_clean": c["dispositioned"] == attempted and c["manual_review"] == 0,
        }
    dispositioned = sum(c["dispositioned"] for c in counters.values())
    manual = sum(c["manual_review"] for c in counters.values())
    return {
        "schema_version": 1,
        "probe_id": PROBE_ID,
        "pilot_id": pilot_id,
        "scope": "bounded read-only official-ST product-page-to-datasheet Ordering Information accessibility comparison",
        "candidate_series": list(TARGET_SERIES),
        "attempted_targets": len(targets),
        "dispositioned_targets": dispositioned,
        "manual_review_targets": manual,
        "bounded_probe_clean": len(targets) == EXPECTED_TARGET_COUNT and dispositioned == EXPECTED_TARGET_COUNT and manual == 0,
        "by_series": by_series,
        "results": results,
        "selected_next_research_family": None,
        "claims": {
            "ordering_document_probe_is_metadata_policy": False,
            "ordering_document_probe_is_admission": False,
            "manufacturer_document_access_implies_programming_equivalence": False,
            "production_write_authorized": False,
            "programming_policy_defined": False,
            "runtime_support_claimed": False,
            "selected_next_research_family": False,
        },
    }


def probe_is_clean(summary: dict[str, object]) -> bool:
    claims = summary.get("claims")
    return (
        summary.get("attempted_targets") == EXPECTED_TARGET_COUNT
        and summary.get("dispositioned_targets") == EXPECTED_TARGET_COUNT
        and summary.get("manual_review_targets") == 0
        and summary.get("bounded_probe_clean") is True
        and summary.get("selected_next_research_family") is None
        and isinstance(claims, dict) and bool(claims) and set(claims.values()) == {False}
    )

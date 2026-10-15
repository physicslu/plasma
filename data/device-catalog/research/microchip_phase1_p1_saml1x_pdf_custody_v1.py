#!/usr/bin/env python3
"""Capture/replay original Microchip SAM L10/L11 DS60001513G PDF evidence.

RESEARCH ONLY. This can attest a manufacturer PDF and locate its two tables;
it cannot mark any exact ICPN field VERIFIED, admit Catalog records, or qualify
OpenOCD programming. The manufacturer MCP 126-ICPN join is a separate gate.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.parse
import urllib.request

URL = ("https://ww1.microchip.com/downloads/en/DeviceDoc/"
       "SAM-L10L11-Family-Data-Sheet-DS60001513G.pdf")
REVISION = "DS60001513G"
FILENAME = "original-saml10l11-ds60001513g.pdf"
MAX_BYTES = 50 * 1024 * 1024
MIN_BYTES = 10000
BASES = tuple(sorted(
    "SAML" + family + group + density
    for family in ("10", "11")
    for group in ("D", "E")
    for density in ("14", "15", "16")
))
VALID_STATUS = (
    "SOURCE_NOT_AVAILABLE",
    "SOURCE_BYTES_CAPTURED_SEMANTICS_NOT_REPLAYABLE",
    "SOURCE_BYTES_CAPTURED_AND_SEMANTICALLY_REPLAYED",
)


def require(ok, reason):
    if not ok:
        raise ValueError(reason)


def allowed_redirect(actual):
    parsed = urllib.parse.urlsplit(actual)
    return (parsed.scheme == "https"
            and parsed.hostname == "ww1.microchip.com"
            and parsed.username is None and parsed.password is None
            and parsed.port is None
            and parsed.path.startswith("/downloads/")
            and not parsed.query and not parsed.fragment)


def download_original(uri=URL):
    require(uri == URL, "unreviewed source URL")
    req = urllib.request.Request(
        uri, headers={"User-Agent": "PLASMA-Research-PDF-Custody/1.0",
                      "Accept": "application/pdf"})
    with urllib.request.urlopen(req, timeout=35) as response:
        require(response.status == 200 and
                allowed_redirect(response.geturl()),
                "publisher response redirected to unreviewed source")
        data = response.read(MAX_BYTES + 1)
    return data


def validate_pdf_bytes(raw):
    require(isinstance(raw, bytes) and MIN_BYTES <= len(raw) <= MAX_BYTES,
            "manufacturer PDF byte size out of bounds")
    require(raw.startswith(b"%PDF-") and b"%%EOF" in raw[-4096:],
            "source is not a complete original PDF (possibly HTML shell)")


def pdftotext_pages(path, page):
    # Poppler is an extraction tool, not the original evidence source.
    result = subprocess.run(
        ["pdftotext", "-f", str(page), "-l", str(page),
         "-layout", str(path), "-"],
        capture_output=True, text=True, timeout=35, check=True)
    require(result.stdout.strip(), "PDF text extraction returned no content")
    return result.stdout


def page_evidence(page14, page16):
    c14 = " ".join(page14.split())
    c16 = " ".join(page16.split())
    require("SAM L10/L11 Family" in c14 and
            "Configuration Summary" in c14 and
            "Table 1-1." in c14 and
            re.search(r"DS60001513G\s*-\s*page\s*14", c14),
            "official revision / configuration page 14 mismatch")
    present = sorted({name for name in BASES
                      if re.search(r"\b" + name + r"\b", c14)})
    require(tuple(present) == BASES,
            "all twelve exact device-family feature rows not replayed")
    mandatory = ("SAM L10/L11 Family", "Ordering Information",
                 "Product Series", "Pin Count", "Memory Density",
                 "Device Variant", "Package Type", "Package Grade",
                 "Package Carrier", "ATSAML")
    missing = [token for token in mandatory if token not in c16]
    has_footer = bool(re.search(r"DS60001513G\s*-\s*page\s*16", c16))
    require(not missing and has_footer,
            f"official revision / ordering page 16 mismatch: "
            f"missing={missing}, footer={has_footer}")
    require(all(token in c16 for token in
                ("TQFP", "VQFN", "SSOP", "WLCSP", "KPH")),
            "manufacturer package or ordering caveats missing")
    return {
        "datasheet_page_14": "Table 1-1 device-specific family features",
        "datasheet_page_16": "Section 2 ordering information conventions",
        "family_base_names_observed_on_page_14": present,
        "package_and_ordering_conventions_observed": True,
        "individual_commercial_icpns_verified": 0,
    }


def extract(path, reader=pdftotext_pages):
    page14, page16 = reader(path, 14), reader(path, 16)
    return (
        page_evidence(page14, page16),
        {str(n): hashlib.sha256(s.encode("utf-8")).hexdigest()
         for n, s in ((14, page14), (16, page16))}
    )


def receipt_template():
    return {
        "schema_version": 1,
        "manufacturer": "Microchip",
        "scope": "saml10l11_official_pdf_document_custody_not_exact_icpn",
        "document_revision": REVISION,
        "original_url": URL,
        "retrieved_at_utc": datetime.now(timezone.utc).isoformat(),
        "status": "SOURCE_NOT_AVAILABLE",
        "original_pdf_file": None,
        "original_pdf_sha256": None,
        "original_pdf_bytes": None,
        "pdf_extract_text_sha256_by_page": None,
        "observations": None,
        "error": None,
        "manufacturer_exact_icpn_count_from_pdf": 0,
        "new_phase1_exact_variant_verified_fields": 0,
        "pdf_ordering_conventions_are_exact_icpn_rows": False,
        "software_supported_claimed": False,
        "production_write_authorized": False,
        "catalog_publication_authorized": False,
    }


def capture(root, getter=download_original, reader=pdftotext_pages):
    root = Path(root)
    require("production" not in {p.casefold() for p in root.resolve().parts},
            "cannot write manufacturer research PDF in Production")
    require(not root.exists(), "source capture directory must be new")
    root.mkdir(parents=True)
    receipt = receipt_template()
    try:
        raw = getter()
        validate_pdf_bytes(raw)
        path = root / FILENAME
        path.write_bytes(raw)
        receipt.update(
            status="SOURCE_BYTES_CAPTURED_SEMANTICS_NOT_REPLAYABLE",
            original_pdf_file=FILENAME,
            original_pdf_sha256=hashlib.sha256(raw).hexdigest(),
            original_pdf_bytes=len(raw),
        )
        observations, text_hashes = extract(path, reader)
        receipt.update(
            status="SOURCE_BYTES_CAPTURED_AND_SEMANTICALLY_REPLAYED",
            observations=observations,
            pdf_extract_text_sha256_by_page=text_hashes,
        )
    except (OSError, ValueError, subprocess.SubprocessError,
            TimeoutError) as exc:
        receipt["error"] = f"{type(exc).__name__}: {str(exc)[:280]}"
    (root / "manifest.json").write_text(
        json.dumps(receipt, sort_keys=True, indent=2) + "\n",
        encoding="utf-8")
    audit(root, reader)
    return receipt


def audit(root, reader=pdftotext_pages):
    root = Path(root)
    receipt = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    require(receipt.get("schema_version") == 1 and
            receipt.get("manufacturer") == "Microchip" and
            receipt.get("scope") ==
            "saml10l11_official_pdf_document_custody_not_exact_icpn" and
            receipt.get("document_revision") == REVISION and
            receipt.get("original_url") == URL and
            receipt.get("status") in VALID_STATUS and
            receipt.get("manufacturer_exact_icpn_count_from_pdf") == 0 and
            receipt.get("new_phase1_exact_variant_verified_fields") == 0 and
            receipt.get("pdf_ordering_conventions_are_exact_icpn_rows") is False and
            receipt.get("software_supported_claimed") is False and
            receipt.get("production_write_authorized") is False and
            receipt.get("catalog_publication_authorized") is False,
            "untrusted source receipt or prohibited qualification claim")
    state = receipt["status"]
    if state == "SOURCE_NOT_AVAILABLE":
        require(all(receipt.get(key) is None for key in (
            "original_pdf_file", "original_pdf_sha256",
            "original_pdf_bytes", "pdf_extract_text_sha256_by_page",
            "observations")), "missing PDF cannot claim manufacturer evidence")
        require(not (root / FILENAME).exists(),
                "unrecorded PDF original present")
        return receipt
    path = root / FILENAME
    require(receipt.get("original_pdf_file") == FILENAME and
            path.is_file() and not path.is_symlink(), "missing original PDF")
    raw = path.read_bytes()
    validate_pdf_bytes(raw)
    require(receipt.get("original_pdf_sha256") ==
            hashlib.sha256(raw).hexdigest() and
            receipt.get("original_pdf_bytes") == len(raw),
            "original PDF SHA-256/byte-length mismatch")
    if state == "SOURCE_BYTES_CAPTURED_SEMANTICS_NOT_REPLAYABLE":
        require(receipt.get("pdf_extract_text_sha256_by_page") is None
                and receipt.get("observations") is None,
                "unreplayable PDF cannot claim page evidence")
        return receipt
    observations, text_hashes = extract(path, reader)
    require(observations == receipt.get("observations") and
            text_hashes == receipt.get("pdf_extract_text_sha256_by_page"),
            "original PDF page replay or extracted-text SHA mismatch")
    return receipt


def main():
    cli = argparse.ArgumentParser(description=__doc__)
    mode = cli.add_mutually_exclusive_group(required=True)
    mode.add_argument("--capture", type=Path)
    mode.add_argument("--replay", type=Path)
    args = cli.parse_args()
    report = capture(args.capture) if args.capture else audit(args.replay)
    print(json.dumps(report, indent=2, sort_keys=True))
    require(report["status"] ==
            "SOURCE_BYTES_CAPTURED_AND_SEMANTICALLY_REPLAYED",
            "official PDF source not yet semantically replayed; "
            "archived diagnostics must not promote ICPN fields")


if __name__ == "__main__":
    main()

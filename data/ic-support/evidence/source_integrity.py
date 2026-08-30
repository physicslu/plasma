#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

HERE = Path(__file__).resolve().parent
SOURCE_FILE = HERE / "sources.json"


class SourceIntegrityError(RuntimeError):
    pass


def load_sources() -> list[dict[str, object]]:
    payload = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    sources = payload.get("sources")
    if not isinstance(sources, list):
        raise SourceIntegrityError("sources.json must contain a sources array")
    return [source for source in sources if isinstance(source, dict)]


def fetch_bytes(url: str) -> tuple[bytes, str]:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 Plasma-IC-Support-Evidence/1.0",
            "Accept": "application/pdf,*/*;q=0.8",
        },
    )
    with urlopen(request, timeout=60) as response:
        payload = response.read()
        final_url = response.geturl()
    if not payload.startswith(b"%PDF"):
        raise SourceIntegrityError(f"download is not a PDF: {url}")
    return payload, final_url


def inspect_source(source: dict[str, object]) -> dict[str, object]:
    source_id = source.get("source_id")
    url = source.get("url")
    if not isinstance(source_id, str) or not isinstance(url, str):
        raise SourceIntegrityError("manufacturer source requires source_id and url")
    payload, final_url = fetch_bytes(url)
    return {
        "source_id": source_id,
        "document_number": source.get("document_number"),
        "revision": source.get("revision"),
        "sha256": hashlib.sha256(payload).hexdigest(),
        "byte_length": len(payload),
        "requested_url": url,
        "final_url": final_url,
    }


def discover() -> int:
    rows: list[dict[str, object]] = []
    for source in load_sources():
        if source.get("authority") != "manufacturer_official":
            continue
        row = inspect_source(source)
        rows.append(row)
        print("SOURCE_LOCK " + json.dumps(row, sort_keys=True))
    if not rows:
        raise SourceIntegrityError("no manufacturer_official sources found")
    return 0


def verify() -> int:
    checked = 0
    for source in load_sources():
        if source.get("authority") != "manufacturer_official":
            continue
        integrity = source.get("integrity")
        if not isinstance(integrity, dict) or integrity.get("status") != "sha256_pinned":
            raise SourceIntegrityError(f"{source.get('source_id')}: source is not sha256_pinned")
        expected_sha = integrity.get("sha256")
        expected_size = integrity.get("byte_length")
        if not isinstance(expected_sha, str) or len(expected_sha) != 64:
            raise SourceIntegrityError(f"{source.get('source_id')}: invalid sha256 pin")
        if not isinstance(expected_size, int) or expected_size <= 0:
            raise SourceIntegrityError(f"{source.get('source_id')}: invalid byte_length pin")
        observed = inspect_source(source)
        if observed["sha256"] != expected_sha:
            raise SourceIntegrityError(
                f"{source.get('source_id')}: sha256 drift: {observed['sha256']} != {expected_sha}"
            )
        if observed["byte_length"] != expected_size:
            raise SourceIntegrityError(
                f"{source.get('source_id')}: byte-length drift: {observed['byte_length']} != {expected_size}"
            )
        checked += 1
        print(f"SOURCE_VERIFY PASS {source.get('source_id')} {expected_sha}")
    if checked == 0:
        raise SourceIntegrityError("no manufacturer sources verified")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Discover or verify official IC Support source hashes")
    parser.add_argument("mode", choices=["discover", "verify"])
    args = parser.parse_args()
    try:
        return discover() if args.mode == "discover" else verify()
    except (OSError, SourceIntegrityError) as exc:
        print(f"source-integrity: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

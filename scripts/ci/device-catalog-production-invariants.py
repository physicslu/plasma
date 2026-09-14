#!/usr/bin/env python3
"""Validate the current canonical Device Catalog Production manifest.

This is the small, current-state integrity gate.  It deliberately does not
replay historical research phases.  Historical/family workflows own their
frozen evidence; this validator owns only the canonical Production graph.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
MANIFEST = ROOT / "data/device-catalog/production/icpn-v1-manifest.json"
REQUIRED_COLUMNS = {"manufacturer", "icpn", "family", "base_device"}


def fail(message: str) -> None:
    raise SystemExit(message)


def git_blob_sha(data: bytes) -> str:
    header = f"blob {len(data)}\0".encode("ascii")
    return hashlib.sha1(header + data).hexdigest()


def main() -> int:
    payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1:
        fail("Production manifest schema_version must be 1")
    if payload.get("status") != "production":
        fail("Production manifest status must be production")
    if payload.get("selection_policy") != "admitted_exact_manufacturer_part_number_only":
        fail("Production manifest selection_policy drifted")

    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        fail("Production manifest requires a non-empty sources list")

    source_keys: set[tuple[str, str]] = set()
    exact_keys: set[tuple[str, str]] = set()
    base_keys: set[tuple[str, str, str]] = set()
    family_counts: dict[str, int] = {}
    exact_count = 0

    production_dir = MANIFEST.parent.resolve()
    repo_root = ROOT.resolve()

    for index, source in enumerate(sources):
        if not isinstance(source, dict):
            fail(f"sources[{index}] must be an object")
        manufacturer = source.get("manufacturer")
        family = source.get("family")
        relative_path = source.get("path")
        if not all(isinstance(value, str) and value for value in (manufacturer, family, relative_path)):
            fail(f"sources[{index}] requires manufacturer/family/path")

        source_key = (manufacturer, family)
        if source_key in source_keys:
            fail(f"duplicate Production source: {manufacturer}/{family}")
        source_keys.add(source_key)

        source_path = (production_dir / relative_path).resolve()
        try:
            source_path.relative_to(repo_root)
        except ValueError:
            fail(f"{manufacturer}/{family}: source path escapes repository")
        if not source_path.is_file():
            fail(f"{manufacturer}/{family}: source file missing: {relative_path}")

        data = source_path.read_bytes()
        expected_sha256 = source.get("sha256")
        actual_sha256 = hashlib.sha256(data).hexdigest()
        if actual_sha256 != expected_sha256:
            fail(f"{manufacturer}/{family}: SHA-256 mismatch")

        expected_blob = source.get("git_blob_sha")
        actual_blob = git_blob_sha(data)
        if actual_blob != expected_blob:
            fail(f"{manufacturer}/{family}: Git blob SHA mismatch")

        text = data.decode("utf-8")
        reader = csv.DictReader(io.StringIO(text, newline=""))
        fieldnames = set(reader.fieldnames or [])
        missing = REQUIRED_COLUMNS - fieldnames
        if missing:
            fail(f"{manufacturer}/{family}: missing CSV columns: {sorted(missing)}")
        rows = list(reader)

        expected_rows = source.get("row_count")
        if not isinstance(expected_rows, int) or expected_rows < 1:
            fail(f"{manufacturer}/{family}: invalid row_count")
        if len(rows) != expected_rows:
            fail(
                f"{manufacturer}/{family}: row_count mismatch: "
                f"manifest={expected_rows} actual={len(rows)}"
            )

        for row_number, row in enumerate(rows, start=2):
            if row.get("manufacturer") != manufacturer:
                fail(f"{manufacturer}/{family}:{row_number}: manufacturer mismatch")
            if row.get("family") != family:
                fail(f"{manufacturer}/{family}:{row_number}: family mismatch")
            icpn = (row.get("icpn") or "").strip()
            base_device = (row.get("base_device") or "").strip()
            if not icpn or not base_device:
                fail(f"{manufacturer}/{family}:{row_number}: blank icpn/base_device")
            exact_key = (manufacturer, icpn)
            if exact_key in exact_keys:
                fail(f"duplicate exact ICPN: {manufacturer}/{icpn}")
            exact_keys.add(exact_key)
            base_keys.add((manufacturer, family, base_device))

        exact_count += len(rows)
        family_counts[family] = len(rows)

    summary = {
        "production_sources": len(sources),
        "exact_icpns": exact_count,
        "base_devices": len(base_keys),
        "family_exact_icpn_counts": dict(sorted(family_counts.items())),
    }
    print(json.dumps(summary, indent=2, sort_keys=True))
    print("Device Catalog Production invariants: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

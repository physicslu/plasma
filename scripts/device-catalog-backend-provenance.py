#!/usr/bin/env python3
"""Export/query per-exact-ICPN source evidence without changing Catalog or Runtime."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "software/python"))

from plasma_web.backend_provenance import audit_snapshot, load_source_authorities  # noqa: E402
from plasma_web.device_catalog import DeviceCatalog, DeviceCatalogIntegrityError, default_catalog_manifest_path  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Audit pinned OpenOCD provider provenance per Production exact ICPN")
    parser.add_argument("--icpn", help="Print one exact Production ICPN provenance record")
    parser.add_argument("--out-dir", type=Path, help="Write deterministic JSONL and JSON summary evidence")
    args = parser.parse_args(argv)
    try:
        catalog = DeviceCatalog.from_manifest(default_catalog_manifest_path())
        upstream, gap = load_source_authorities(ROOT)
        records, summary, blob = audit_snapshot(catalog, upstream, gap)
    except DeviceCatalogIntegrityError as exc:
        parser.error(str(exc))
        return 2
    if args.icpn:
        matches = [record for record in records if record["icpn"].casefold() == args.icpn.strip().casefold()]
        if len(matches) != 1:
            parser.error("ICPN not found in Production Catalog (never resolve a research-only identifier)")
        print(json.dumps(matches[0], indent=2, ensure_ascii=False, sort_keys=True))
    elif not args.out_dir:
        print(json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True))

    if args.out_dir:
        args.out_dir.mkdir(parents=True, exist_ok=True)
        (args.out_dir / "icpn-backend-provenance-v1.jsonl").write_bytes(blob)
        (args.out_dir / "icpn-backend-provenance-v1-summary.json").write_text(
            json.dumps(summary, indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"Backend provenance audit PASS: {len(records)} exact ICPNs, SHA256={summary['records_jsonl_sha256']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

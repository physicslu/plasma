#!/usr/bin/env python3
"""Build a deterministic, DATA-ONLY-ADMITTED Bundle v3 smoke ZIP.

This is an example artifact producer, NOT a device installer or authorization.
The Python smoke payload is executable only via an explicit host test harness.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "examples" / "ppu-bundle-v3-smoke"
TARGET = {
    "platform": "linux-armv7",
    "board": "pynq-z2",
    "fpga_part": "xc7z020clg400-1",
}
# Intentionally reverse declared order: only the dependency DAG controls staging.
PACKAGES = (
    ("python-smoke", "python", ("programming-profile",), "python/smoke.py"),
    ("programming-profile", "programming-profile", ("ic-catalog",), "data/geometry.json"),
    ("ic-catalog", "ic-catalog", (), "data/device.json"),
)


def make_bundle(output: Path, source_commit: str | None = None) -> str:
    if source_commit is not None and not re.fullmatch(r"[0-9a-f]{40}", source_commit):
        raise ValueError("SOURCE_COMMIT_MUST_BE_EXACT_LOWERCASE_SHA40")
    members = {}
    packages = []
    for package_id, kind, requires, suffix in PACKAGES:
        raw = (FIXTURE / package_id / suffix).read_bytes()
        filename = f"payload/packages/{package_id}/{suffix}"
        members[filename] = raw
        packages.append({
            "id": package_id, "kind": kind, "version": "0.1.0",
            "requires": list(requires),
            "files": [{
                "path": filename,
                "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw),
                # Canonical Python package files are intentionally non-executable
                # metadata; explicit 'python smoke.py' is the test execution.
                "executable": False,
            }],
        })
    manifest = {
        "schema": "plasma.ppu.bundle.v3",
        "name": "ppu-b3-smoke",
        "version": "0.1.0",
        "purpose": "programming",
        "target": TARGET,
        "actions": ["install", "verify"],
        "packages": packages,
    }
    if source_commit is not None:
        manifest["source_commit"] = source_commit
    contents = {"manifest.json": (json.dumps(
        manifest, sort_keys=True, separators=(",", ":")
    ) + "\n").encode("utf-8"), **members}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w") as archive:
        for filename, raw in sorted(contents.items()):
            info = zipfile.ZipInfo(filename, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            archive.writestr(info, raw)
    return hashlib.sha256(output.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--source-commit", help="optional untrusted provenance; never authorization")
    args = parser.parse_args()
    digest = make_bundle(args.output, args.source_commit)
    print(json.dumps({
        "schema": "plasma.ppu.bundle.v3",
        "artifact_sha256": digest,
        "source_commit": args.source_commit,
        "output": str(args.output),
        "install_qualified": False,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

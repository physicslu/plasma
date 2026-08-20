#!/usr/bin/env python3
"""Guard canonical Plasma production code against retired vocabulary.

Canonical product/domain vocabulary is Facility -> PPU -> Site. Canonical
programming-data vocabulary is Programming Asset at the REST/input boundary and
Normalized Image at the execution/wire boundary. Plasma is still in development,
so there is no legacy compatibility exception in canonical production code.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN = re.compile(
    r"(?:\b(?:Programmer(?:Config|State|Manager|Worker)?|Channel(?:Config|State|Manager|Worker)?|"
    r"programmer|programmer_id|channel_id|channel_count|enabled_channel_count|"
    r"max_supported_channels|channels)\b|\bfirmware(?:\b|_))",
    re.IGNORECASE,
)

EXCLUDED_PREFIXES = (
    "software/python/tests/",
    "software/web/e2e/",
)

PRODUCTION_PREFIXES = (
    "software/python/",
    "software/web/",
)

CODE_SUFFIXES = {".py", ".js", ".jsx", ".ts", ".tsx"}


def checked_path(path: str) -> bool:
    if path.startswith(EXCLUDED_PREFIXES):
        return False
    if Path(path).suffix not in CODE_SUFFIXES:
        return False
    return path.startswith(PRODUCTION_PREFIXES)


def current_tree_findings() -> list[tuple[str, int, str]]:
    findings: list[tuple[str, int, str]] = []
    for prefix in PRODUCTION_PREFIXES:
        root = ROOT / prefix
        if not root.exists():
            continue
        for path in sorted(item for item in root.rglob("*") if item.is_file()):
            relative = path.relative_to(ROOT).as_posix()
            if not checked_path(relative):
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeDecodeError:
                continue
            for line_no, text in enumerate(lines, start=1):
                if FORBIDDEN.search(text):
                    findings.append((relative, line_no, text))
    return findings


def self_test() -> None:
    assert checked_path("software/web/app/engineering/new-feature.ts")
    assert checked_path("software/python/plasma_server/site_worker.py")
    assert not checked_path("software/web/package-lock.json")
    assert not checked_path("software/python/tests/test_protocol.py")
    assert not checked_path("software/web/e2e/tests/engineering-programming.spec.ts")
    assert FORBIDDEN.search("programmer")
    assert FORBIDDEN.search("channel_id")
    assert FORBIDDEN.search("ChannelManager")
    assert FORBIDDEN.search("channels")
    assert FORBIDDEN.search("Firmware")
    assert FORBIDDEN.search("firmware_sha256")
    assert FORBIDDEN.search("FIRMWARE_CACHE")
    assert not FORBIDDEN.search("site_id")
    assert not FORBIDDEN.search("SiteManager")
    assert not FORBIDDEN.search("ProgrammingAsset")
    assert not FORBIDDEN.search("NormalizedImage")
    print("Canonical terminology guard self-test: PASS")


def main() -> int:
    if "--self-test" in sys.argv:
        self_test()
        return 0

    findings = current_tree_findings()
    if not findings:
        print("Canonical terminology guard: PASS")
        return 0

    print("Canonical terminology guard: FAIL", file=sys.stderr)
    print(
        "Canonical production code contains retired vocabulary. "
        "Use Facility/PPU/Site, Programming Asset, and Normalized Image terminology.",
        file=sys.stderr,
    )
    for path, line_no, text in findings:
        print(f"  {path}:{line_no}: {text}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

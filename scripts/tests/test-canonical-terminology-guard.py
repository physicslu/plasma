#!/usr/bin/env python3
"""Guard canonical Plasma production code against retired domain vocabulary.

The canonical product/domain hierarchy is Facility -> PPU -> Site. Protocol/API
v3.1 compatibility remains an explicit adapter and is intentionally excluded from
this guard; removing that adapter is a separate migration decision.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

FORBIDDEN = re.compile(
    r"\b(?:Programmer(?:Config|State|Manager|Worker)?|Channel(?:Config|State|Manager|Worker)?|"
    r"programmer_id|channel_id|channel_count|enabled_channel_count|max_supported_channels|channels)\b"
)

# Explicit compatibility boundaries. These files may translate legacy v3.1
# Programmer/Channel identities into the canonical PPU/Site model.
COMPATIBILITY_PATHS = {
    "software/web/app/plasma-api.ts",
    "software/python/plasma_core/config.py",
    "software/python/plasma_server/channel_manager.py",
    "software/python/plasma_server/channel_worker.py",
}

EXCLUDED_PREFIXES = (
    "software/python/tests/",
    "software/web/e2e/",
)

PRODUCTION_PREFIXES = (
    "software/python/",
    "software/web/",
)


def git(*args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def resolve_base() -> str:
    explicit = os.environ.get("PLASMA_TERMINOLOGY_BASE", "").strip()
    if explicit and set(explicit) != {"0"}:
        return explicit

    github_base = os.environ.get("GITHUB_BASE_REF", "").strip()
    if github_base:
        candidate = f"origin/{github_base}"
        try:
            git("rev-parse", "--verify", candidate)
            return git("merge-base", candidate, "HEAD")
        except subprocess.CalledProcessError:
            pass

    try:
        return git("rev-parse", "HEAD^")
    except subprocess.CalledProcessError as exc:
        raise SystemExit(
            "Unable to resolve terminology comparison base; set PLASMA_TERMINOLOGY_BASE"
        ) from exc


def checked_path(path: str) -> bool:
    if path in COMPATIBILITY_PATHS:
        return False
    if path.startswith(EXCLUDED_PREFIXES):
        return False
    return path.startswith(PRODUCTION_PREFIXES)


def added_lines(base: str) -> list[tuple[str, int, str]]:
    diff = git("diff", "--unified=0", "--no-color", f"{base}...HEAD", "--", *PRODUCTION_PREFIXES)
    findings: list[tuple[str, int, str]] = []
    current_path: str | None = None
    new_line = 0

    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current_path = line[6:]
            continue
        if line.startswith("@@"):
            match = re.search(r"\+(\d+)(?:,(\d+))?", line)
            if match:
                new_line = int(match.group(1))
            continue
        if current_path is None:
            continue
        if line.startswith("+") and not line.startswith("+++"):
            if checked_path(current_path):
                text = line[1:]
                if FORBIDDEN.search(text):
                    findings.append((current_path, new_line, text))
            new_line += 1
        elif not line.startswith("-"):
            new_line += 1

    return findings


def self_test() -> None:
    assert checked_path("software/web/app/engineering/new-feature.ts")
    assert checked_path("software/python/plasma_server/site_worker.py")
    assert not checked_path("software/web/app/plasma-api.ts")
    assert not checked_path("software/python/tests/test_protocol_v31.py")
    assert FORBIDDEN.search("channel_id")
    assert FORBIDDEN.search("ChannelManager")
    assert FORBIDDEN.search("channels")
    assert not FORBIDDEN.search("site_id")
    assert not FORBIDDEN.search("SiteManager")
    print("Canonical terminology guard self-test: PASS")


def main() -> int:
    if "--self-test" in sys.argv:
        self_test()
        return 0

    base = resolve_base()
    findings = added_lines(base)
    if not findings:
        print("Canonical terminology guard: PASS")
        return 0

    print("Canonical terminology guard: FAIL", file=sys.stderr)
    print(
        "New production-code lines introduced retired Programmer/Channel vocabulary. "
        "Use Facility/PPU/Site, or place intentional v3.1 translation inside an explicit compatibility boundary.",
        file=sys.stderr,
    )
    for path, line_no, text in findings:
        print(f"  {path}:{line_no}: {text}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

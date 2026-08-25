#!/usr/bin/env python3
"""Validate Plasma documentation structure and executable contract facts."""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DOC_INDEX = ROOT / "docs" / "README.md"
LINK = re.compile(r"(?<!!)\[[^\]]+\]\(([^)]+)\)")


def repository_markdown() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "--", "*.md"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    paths: list[Path] = []
    for raw in result.stdout.splitlines():
        relative = Path(raw)
        if relative.parts and relative.parts[0] == "artifacts":
            continue
        path = ROOT / relative
        if path.is_file():
            paths.append(path)
    return sorted(paths)


def link_destination(raw: str) -> str:
    value = raw.strip()
    if value.startswith("<") and ">" in value:
        return value[1 : value.index(">")]
    return value.split(maxsplit=1)[0]


def validate_headings_and_links(markdown: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in markdown:
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if not re.search(r"(?m)^#\s+\S", text):
            errors.append(f"{relative}: missing level-one heading")
        for match in LINK.finditer(text):
            destination = link_destination(match.group(1))
            if not destination or destination.startswith(("#", "http://", "https://", "mailto:")):
                continue
            local = destination.split("#", 1)[0].split("?", 1)[0]
            if not local:
                continue
            resolved = (path.parent / local).resolve()
            try:
                resolved.relative_to(ROOT.resolve())
            except ValueError:
                errors.append(f"{relative}: local link escapes repository: {destination}")
                continue
            if not resolved.exists():
                errors.append(f"{relative}: broken local link: {destination}")
    return errors


def validate_index_coverage() -> list[str]:
    index = DOC_INDEX.read_text(encoding="utf-8")
    linked = {
        link_destination(match.group(1)).split("#", 1)[0]
        for match in LINK.finditer(index)
    }
    errors: list[str] = []
    for path in sorted((ROOT / "docs").rglob("*.md")):
        if path == DOC_INDEX:
            continue
        relative = path.relative_to(ROOT / "docs").as_posix()
        if relative not in linked:
            errors.append(f"docs/README.md: missing index entry for {relative}")
    return errors


def source_integer(path: Path, name: str, pattern: str) -> int:
    match = re.search(pattern, path.read_text(encoding="utf-8"), re.MULTILINE)
    if match is None:
        raise ValueError(f"cannot resolve {name} from {path.relative_to(ROOT)}")
    return int(match.group(1))


def validate_contract_facts(markdown: list[Path]) -> list[str]:
    errors: list[str] = []
    config_doc = (ROOT / "docs/architecture/configuration-architecture.md").read_text(encoding="utf-8")
    gateway_doc = (ROOT / "docs/architecture/gateway-communication-recovery.md").read_text(encoding="utf-8")

    config_version = source_integer(
        ROOT / "scripts/plasmactl",
        "deployment config version",
        r"^current_config_version=(\d+)$",
    )
    if f"PLASMA_CONFIG_VERSION={config_version}" not in config_doc:
        errors.append("configuration architecture does not match plasmactl schema version")

    settings_source = ROOT / "software/python/plasma_web/gateway_settings.py"
    timeout = source_integer(
        settings_source,
        "Gateway timeout default",
        r"^DEFAULT_PPU_REQUEST_TIMEOUT_MS\s*=\s*([\d_]+)$",
    )
    retries = source_integer(
        settings_source,
        "Gateway retry default",
        r"^DEFAULT_PPU_RETRY_COUNT\s*=\s*([\d_]+)$",
    )
    minimum = source_integer(
        settings_source,
        "Gateway timeout minimum",
        r"^MIN_PPU_REQUEST_TIMEOUT_MS\s*=\s*([\d_]+)$",
    )
    maximum = source_integer(
        settings_source,
        "Gateway timeout maximum",
        r"^MAX_PPU_REQUEST_TIMEOUT_MS\s*=\s*([\d_]+)$",
    )
    max_retries = source_integer(
        settings_source,
        "Gateway retry maximum",
        r"^MAX_PPU_RETRY_COUNT\s*=\s*([\d_]+)$",
    )
    required_gateway_facts = (
        str(timeout),
        str(retries),
        f"{minimum}–{maximum}",
        f"0–{max_retries}",
        "GET  /api/settings/gateway",
        "POST /api/settings/gateway",
    )
    for fact in required_gateway_facts:
        if fact not in gateway_doc:
            errors.append(f"Gateway communication document is missing executable fact: {fact}")

    errors_source = (ROOT / "software/python/plasma_core/errors.py").read_text(encoding="utf-8")
    errors_doc = (ROOT / "software/python/docs/errors.md").read_text(encoding="utf-8")
    declared_errors = re.findall(r'^\s{4}([A-Z][A-Z0-9_]+)\s*=\s*"(E\d{4})"$', errors_source, re.MULTILINE)
    for error_name, error_code in declared_errors:
        if f"| {error_code} | {error_name} |" not in errors_doc:
            errors.append(f"error documentation is missing {error_code} {error_name}")

    current_documents = [
        path for path in markdown
        if path.relative_to(ROOT).as_posix() != "docs/architecture/multi-programmer-sites.md"
        and path.name != "CHANGELOG.md"
    ]
    for path in current_documents:
        relative = path.relative_to(ROOT).as_posix()
        text = path.read_text(encoding="utf-8")
        if relative.startswith("software/python/tests/"):
            continue
        if "PLASMA32" in text:
            errors.append(f"{relative}: retired PLASMA32 marker in current documentation")
        if re.search(r"Protocol v3\.2|protocol v3\.2", text):
            errors.append(f"{relative}: retired Protocol v3.2 presented as current guidance")

    retired_names = (
        "engineering-programming-ui-v2.md",
        "production-server-batch-ui.md",
        "engineering-firmware-observability-test-plan.md",
        "engineering-firmware-cache-runtime.spec.ts",
    )
    for path in markdown:
        text = path.read_text(encoding="utf-8")
        relative = path.relative_to(ROOT).as_posix()
        for retired in retired_names:
            if retired in text:
                errors.append(f"{relative}: references retired file {retired}")

    gateway_sources = list((ROOT / "software/python").rglob("*.py"))
    for path in gateway_sources:
        text = path.read_text(encoding="utf-8")
        if "gateway_legacy" in text:
            errors.append(f"{path.relative_to(ROOT)}: references retired Gateway base module")
    return errors


def main() -> int:
    markdown = repository_markdown()
    errors = [
        *validate_headings_and_links(markdown),
        *validate_index_coverage(),
        *validate_contract_facts(markdown),
    ]
    if errors:
        print("Documentation integrity: FAIL", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Documentation integrity: PASS ({len(markdown)} Markdown files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

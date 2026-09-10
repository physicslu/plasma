#!/usr/bin/env python3
"""Validate the Production catalog documentation single-source-of-truth contract.

The production manifest is authoritative. README.md may describe the contract and
show how to inspect current state, but it must not duplicate mutable Production
inventory as a second source of truth.
"""

from __future__ import annotations

import json
import re
from pathlib import Path


HERE = Path(__file__).resolve().parent
README = HERE / "README.md"
MANIFEST = HERE / "icpn-v1-manifest.json"

REQUIRED_README_TOKENS = (
    "`icpn-v1-manifest.json` is the **single authoritative source of truth**",
    "intentionally does **not** duplicate mutable Production state",
    "PYTHONPATH=software/python python -m plasma_web.device_catalog --json",
    "Do not copy those mutable values back into this README as a second source of truth.",
)

FORBIDDEN_README_PATTERNS = (
    re.compile(r"(?im)^\s*Current v1 admitted scope:\s*$"),
    re.compile(r"(?im)^\s*\|\s*Manufacturer\s*\|\s*Family\s*\|\s*Exact ICPNs\s*\|"),
    re.compile(r"(?i)current\s+v1\s+aggregate\s+is\s+\d+"),
)


class DocumentationContractError(RuntimeError):
    pass


def validate_manifest_shape(payload: object) -> None:
    if not isinstance(payload, dict):
        raise DocumentationContractError("Production manifest must be a JSON object")
    if payload.get("status") != "production":
        raise DocumentationContractError("Production manifest status must be production")
    sources = payload.get("sources")
    if not isinstance(sources, list) or not sources:
        raise DocumentationContractError("Production manifest must contain a non-empty sources array")
    for index, source in enumerate(sources, start=1):
        if not isinstance(source, dict):
            raise DocumentationContractError(f"Production manifest source {index} must be an object")
        for field in ("manufacturer", "family", "path", "row_count"):
            if field not in source:
                raise DocumentationContractError(
                    f"Production manifest source {index} is missing {field}"
                )


def validate_readme_text(text: str) -> None:
    for token in REQUIRED_README_TOKENS:
        if token not in text:
            raise DocumentationContractError(
                f"Production README is missing single-source contract token: {token}"
            )
    for pattern in FORBIDDEN_README_PATTERNS:
        if pattern.search(text):
            raise DocumentationContractError(
                "Production README duplicates mutable current catalog state: "
                f"pattern={pattern.pattern}"
            )


def validate() -> None:
    try:
        manifest_payload = json.loads(MANIFEST.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise DocumentationContractError(
            f"Cannot read authoritative Production manifest: {MANIFEST}"
        ) from exc

    try:
        readme_text = README.read_text(encoding="utf-8")
    except OSError as exc:
        raise DocumentationContractError(f"Cannot read Production README: {README}") from exc

    validate_manifest_shape(manifest_payload)
    validate_readme_text(readme_text)


def main() -> int:
    try:
        validate()
    except DocumentationContractError as exc:
        print(f"Production documentation contract FAIL: {exc}")
        return 1
    print("Production documentation contract PASS: manifest remains the sole mutable source of truth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

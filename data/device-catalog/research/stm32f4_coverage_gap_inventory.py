#!/usr/bin/env python3
"""Inventory STM32F4 OpenOCD ordering-pattern coverage gaps against production ICPNs.

This is a research/read-only tool. It does not treat an OpenOCD target mapping as
proof of programming-algorithm equivalence and it never writes canonical data.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import CandidateManualReview, CandidateReject
from stm32f4_admission_policy import (
    BASE_RE,
    FAMILY,
    FLASH_BY_CODE,
    MANUFACTURER,
    TARGET_CONFIG,
    _package_and_pins,
)

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_CANONICAL = HERE / "stm32f4-commercial-icpn.csv"
SCHEMA_VERSION = 1


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _base_from_pattern(pattern: str) -> str | None:
    # STM32F4 commercial base identities are exactly 11 characters, e.g.
    # STM32F407VG; ordering patterns then add package + temperature wildcard.
    if len(pattern) < 13:
        return None
    base = pattern[:11]
    return base if BASE_RE.fullmatch(base) is not None else None


def _package_code_from_pattern(base: str, pattern: str) -> str | None:
    suffix = pattern[len(base) :]
    if len(suffix) < 2:
        return None
    return suffix[0]


def _policy_readiness(base: str, patterns: list[str]) -> tuple[bool, list[str], list[str]]:
    match = BASE_RE.fullmatch(base)
    if match is None:
        return False, [], ["unsupported base-device identity"]
    pin_code, flash_code = match.groups()
    blockers: list[str] = []
    package_codes: set[str] = set()
    if flash_code not in FLASH_BY_CODE:
        blockers.append(f"unsupported flash-size code {flash_code}")

    for pattern in patterns:
        package_code = _package_code_from_pattern(base, pattern)
        if package_code is None:
            blockers.append(f"cannot decode package code from {pattern}")
            continue
        package_codes.add(package_code)
        try:
            _package_and_pins(pin_code, package_code)
        except (CandidateManualReview, CandidateReject) as exc:
            blockers.append(str(exc))

    return not blockers, sorted(package_codes), sorted(set(blockers))


def build_inventory(*, catalog_path: Path, canonical_path: Path) -> dict[str, Any]:
    catalog_rows = _read_csv(catalog_path)
    canonical_rows = _read_csv(canonical_path)
    production_bases = sorted({row["base_device"] for row in canonical_rows})
    production_base_set = set(production_bases)

    patterns_by_base: dict[str, set[str]] = defaultdict(set)
    ignored_patterns: list[str] = []
    for row in catalog_rows:
        if (
            row.get("vendor") != MANUFACTURER
            or row.get("plasma_series") != FAMILY
            or row.get("identifier_kind") != "ordering_pattern"
            or row.get("target_config") != TARGET_CONFIG
        ):
            continue
        pattern = row.get("part_number", "")
        base = _base_from_pattern(pattern)
        if base is None:
            ignored_patterns.append(pattern)
            continue
        patterns_by_base[base].add(pattern)

    candidates: list[dict[str, Any]] = []
    for base in sorted(set(patterns_by_base) - production_base_set):
        patterns = sorted(patterns_by_base[base])
        policy_ready, package_codes, blockers = _policy_readiness(base, patterns)
        candidates.append(
            {
                "base_device": base,
                "series": base[:9],
                "ordering_patterns": patterns,
                "ordering_pattern_count": len(patterns),
                "package_codes": package_codes,
                "admission_policy_ready": policy_ready,
                "policy_blockers": blockers,
            }
        )

    policy_ready_candidates = [item for item in candidates if item["admission_policy_ready"]]
    blocked_candidates = [item for item in candidates if not item["admission_policy_ready"]]
    return {
        "schema_version": SCHEMA_VERSION,
        "scope": "STM32F4 device-catalog coverage gap only",
        "openocd_target_config": TARGET_CONFIG,
        "algorithm_equivalence_claimed": False,
        "inputs": {
            "openocd_catalog": catalog_path.name,
            "openocd_catalog_sha256": _sha256(catalog_path),
            "production_canonical": canonical_path.name,
            "production_canonical_sha256": _sha256(canonical_path),
        },
        "production": {
            "exact_icpn_rows": len(canonical_rows),
            "base_device_count": len(production_bases),
            "base_devices": production_bases,
        },
        "openocd_ordering_pattern_base_device_count": len(patterns_by_base),
        "gap": {
            "base_device_count": len(candidates),
            "policy_ready_count": len(policy_ready_candidates),
            "policy_blocked_count": len(blocked_candidates),
            "policy_ready": policy_ready_candidates,
            "policy_blocked": blocked_candidates,
        },
        "ignored_ordering_patterns": sorted(set(ignored_patterns)),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(argv)
    inventory = build_inventory(catalog_path=args.catalog, canonical_path=args.canonical)
    rendered = json.dumps(inventory, indent=None if args.compact else 2, sort_keys=True) + "\n"
    if args.output is None:
        print(rendered, end="")
    else:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

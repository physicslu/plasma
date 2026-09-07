#!/usr/bin/env python3
"""Run the second bounded, fail-closed official-ST STM32F2 discovery."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any
from device_catalog_admission_framework import canonical_csv_sha256, read_csv

from st_browser_acquisition import BROWSER_TRANSPORT, STBrowserAcquirer
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32f2_phase4_3b_discovery import (
    BASE_RE,
    EXPECTED_SUBFAMILIES,
    MAX_TARGETS,
    PATTERN_RE,
    RateLimitedFetcher,
    DiscoveryTarget,
    _f2_rows,
    discovery_is_clean as base_discovery_is_clean,
    read_catalog,
    run_discovery as run_base_discovery,
)

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_CANONICAL = HERE / "stm32f2-commercial-icpn.csv"
DEFAULT_MANIFEST = HERE / "stm32f2-phase4.3e-discovery-manifest.json"
PHASE = "4.3E"
EXPECTED_PRODUCTION_BASES = frozenset(
    {"STM32F205RB", "STM32F207IC", "STM32F215RE", "STM32F217IE"}
)


def read_production_bases(path: Path) -> set[str]:
    fields, rows = read_csv(path)
    historical = [row for row in rows if row.get("base_device") in EXPECTED_PRODUCTION_BASES]
    identities = [row.get("icpn") for row in rows]
    if len(set(identities)) != len(identities):
        raise AcquisitionError("duplicate Production identity")
    if canonical_csv_sha256(fields, historical) != "dab17b2892497a32e555e57c5349da4ebe6f37136d90c0cab87a4df08a8fe0c9":
        raise AcquisitionError("Phase 4.3E historical Phase 4.3D Production boundary is unavailable")
    return set(EXPECTED_PRODUCTION_BASES)


def deterministic_targets(
    catalog_rows: list[dict[str, str]], production_bases: set[str]
) -> list[tuple[str, str]]:
    by_subfamily: dict[str, set[str]] = defaultdict(set)
    for row in _f2_rows(catalog_rows):
        match = PATTERN_RE.fullmatch(row["part_number"])
        assert match is not None
        base = match.group(1)
        if base not in production_bases:
            by_subfamily[row["subfamily"]].add(base)
    if tuple(sorted(by_subfamily)) != EXPECTED_SUBFAMILIES:
        raise AcquisitionError("Phase 4.3E unadmitted STM32F2 subfamily set drifted")
    return [(subfamily, sorted(by_subfamily[subfamily])[0]) for subfamily in EXPECTED_SUBFAMILIES]


def read_manifest(
    path: Path,
    catalog_rows: list[dict[str, str]],
    production_bases: set[str],
) -> tuple[str, list[DiscoveryTarget]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != 1 or payload.get("phase") != PHASE:
        raise AcquisitionError("unsupported STM32F2 Phase 4.3E discovery manifest")
    pilot_id = payload.get("pilot_id")
    raw_targets = payload.get("targets")
    if not isinstance(pilot_id, str) or not pilot_id.strip():
        raise AcquisitionError("Phase 4.3E discovery manifest requires pilot_id")
    if not isinstance(raw_targets, list) or len(raw_targets) != MAX_TARGETS:
        raise AcquisitionError(f"Phase 4.3E discovery requires exactly {MAX_TARGETS} targets")

    targets: list[DiscoveryTarget] = []
    for raw in raw_targets:
        if not isinstance(raw, dict):
            raise AcquisitionError("Phase 4.3E target must be an object")
        subfamily = raw.get("subfamily")
        base = raw.get("base_device")
        source = raw.get("source_url")
        reason = raw.get("selection_reason")
        if not isinstance(subfamily, str) or subfamily not in EXPECTED_SUBFAMILIES:
            raise AcquisitionError(f"invalid STM32F2 subfamily: {subfamily!r}")
        if not isinstance(base, str) or BASE_RE.fullmatch(base) is None:
            raise AcquisitionError(f"invalid STM32F2 base device: {base!r}")
        if not isinstance(source, str):
            raise AcquisitionError(f"{base}: source_url is required")
        validate_source_url(source)
        if not source.endswith(f"/{base.lower()}.html"):
            raise AcquisitionError(f"{base}: source URL slug mismatch")
        if not isinstance(reason, str) or not reason.strip():
            raise AcquisitionError(f"{base}: selection_reason is required")
        targets.append(DiscoveryTarget(subfamily, base, source, reason.strip()))

    observed = [(target.subfamily, target.base_device) for target in targets]
    expected = deterministic_targets(catalog_rows, production_bases)
    if observed != expected:
        raise AcquisitionError(f"Phase 4.3E target selection drifted: expected={expected} observed={observed}")
    return pilot_id, targets


def run_discovery(**kwargs: Any) -> dict[str, object]:
    summary = run_base_discovery(**kwargs)
    summary["phase"] = PHASE
    summary["scope"] = "second bounded read-only official-ST STM32F2 discovery"
    return summary


def discovery_is_clean(summary: dict[str, object]) -> bool:
    return summary.get("phase") == PHASE and base_discovery_is_clean(summary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=75.0)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        catalog_rows = read_catalog(args.catalog)
        production_bases = read_production_bases(args.canonical)
        pilot_id, targets = read_manifest(args.manifest, catalog_rows, production_bases)
        with STBrowserAcquirer(headless=args.headless) as acquirer:
            fetcher = RateLimitedFetcher(delay_seconds=args.delay, fetcher=acquirer.fetch)
            summary = run_discovery(
                pilot_id=pilot_id,
                targets=targets,
                catalog_rows=catalog_rows,
                fetcher=fetcher,
                timeout_seconds=args.timeout,
            )
            browser_version = acquirer.browser_version
        summary["acquisition_transport"] = BROWSER_TRANSPORT
        summary["browser_runtime"] = {
            "engine": "chromium",
            "browser_version": browser_version,
            "playwright_requirement": "1.62.0",
            "headless": args.headless,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if discovery_is_clean(summary) else 1
    except (AcquisitionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

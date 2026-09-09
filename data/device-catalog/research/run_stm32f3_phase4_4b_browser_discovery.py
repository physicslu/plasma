#!/usr/bin/env python3
"""Run STM32F3 Phase 4.4B with the family-specific dual-surface browser adapter."""

from __future__ import annotations

import argparse
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from stm32f3_browser_acquisition import STM32F3BrowserAcquirer
from stm32f3_dual_surface_evidence import build_dual_surface_browser_evidence_record
from stm32f3_foundation import DEFAULT_CATALOG, read_catalog
from stm32f3_phase4_4b_discovery import (
    DEFAULT_MANIFEST,
    DEFAULT_OUTPUT,
    RateLimitedFetcher,
    discovery_is_clean,
    read_manifest,
    run_discovery,
    write_evidence_files,
)


def _playwright_version() -> str:
    try:
        return version("playwright")
    except PackageNotFoundError:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)

    catalog_rows = read_catalog(DEFAULT_CATALOG)
    pilot_id, targets = read_manifest(args.manifest, catalog_rows)
    base_by_url = {target.source_url: target.base_device for target in targets}

    with STM32F3BrowserAcquirer(
        base_by_url=base_by_url,
        headless=args.headless,
    ) as acquirer:
        fetcher = RateLimitedFetcher(
            delay_seconds=args.delay,
            fetcher=acquirer.fetch,
        )
        summary = run_discovery(
            pilot_id=pilot_id,
            targets=targets,
            catalog_rows=catalog_rows,
            fetcher=fetcher,
            evidence_builder=build_dual_surface_browser_evidence_record,
            timeout_seconds=args.timeout,
        )
        summary["browser"] = {
            "headless": args.headless,
            "browser_version": acquirer.browser_version,
            "playwright_version": _playwright_version(),
            "evidence_profile": "stm32f3_dual_surface_v1",
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    if args.evidence_dir is not None:
        write_evidence_files(summary, args.evidence_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if discovery_is_clean(summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())

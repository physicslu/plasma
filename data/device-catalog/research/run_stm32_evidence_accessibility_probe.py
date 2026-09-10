#!/usr/bin/env python3
"""Run the bounded STM32U0/C0/L1 official-ST evidence accessibility probe."""
from __future__ import annotations

import argparse
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from st_dual_surface_browser_acquisition import STDualSurfaceBrowserAcquirer
from stm32_evidence_accessibility_probe import (
    DEFAULT_CATALOG,
    DEFAULT_MANIFEST,
    DEFAULT_OUTPUT,
    PARSER_PROFILE,
    RateLimitedFetcher,
    build_probe_evidence_record,
    probe_is_clean,
    read_catalog,
    read_manifest,
    run_probe,
    write_evidence_files,
)


def _playwright_version() -> str:
    try:
        return version("playwright")
    except PackageNotFoundError:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)

    rows = read_catalog(DEFAULT_CATALOG)
    pilot_id, targets = read_manifest(args.manifest, rows)
    base_by_url = {target.source_url: target.base_device for target in targets}
    with STDualSurfaceBrowserAcquirer(
        base_by_url=base_by_url,
        family_label="STM32 U0/C0/L1 accessibility probe",
        headless=args.headless,
    ) as acquirer:
        fetcher = RateLimitedFetcher(delay_seconds=args.delay, fetcher=acquirer.fetch)
        summary = run_probe(
            pilot_id=pilot_id,
            targets=targets,
            fetcher=fetcher,
            evidence_builder=build_probe_evidence_record,
            timeout_seconds=args.timeout,
        )
        summary["browser"] = {
            "headless": args.headless,
            "browser_version": acquirer.browser_version,
            "playwright_version": _playwright_version(),
            "evidence_profile": PARSER_PROFILE,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.evidence_dir is not None:
        write_evidence_files(summary, args.evidence_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if probe_is_clean(summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())

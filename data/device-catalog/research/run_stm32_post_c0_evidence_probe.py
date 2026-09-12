#!/usr/bin/env python3
"""Run the authoritative post-C0 STM32L1/L0/L4 official-ST evidence probe."""
from __future__ import annotations

import argparse
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from st_dual_surface_browser_acquisition import STDualSurfaceBrowserAcquirer
from stm32_post_c0_evidence_probe import (
    DEFAULT_CATALOG,
    DEFAULT_OUTPUT,
    PARSER_PROFILE,
    RateLimitedFetcher,
    build_probe_evidence_record,
    deterministic_targets,
    read_catalog,
    run_probe,
    target_manifest,
    write_evidence_files,
)


def _playwright_version() -> str:
    try:
        return version("playwright")
    except PackageNotFoundError:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--targets-output", type=Path)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)

    rows = read_catalog(DEFAULT_CATALOG)
    targets = deterministic_targets(rows)
    base_by_url = {target.source_url: target.base_device for target in targets}
    with STDualSurfaceBrowserAcquirer(
        base_by_url=base_by_url,
        family_label="STM32 L1/L0/L4 post-C0 evidence probe",
        headless=args.headless,
    ) as acquirer:
        fetcher = RateLimitedFetcher(delay_seconds=args.delay, fetcher=acquirer.fetch)
        summary = run_probe(
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
        summary["commercial_identity_authority"] = (
            "official_st_quality_and_reliability_exact_identity_plus_"
            "sample_and_buy_marketing_status_exact_set_join"
        )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.targets_output is not None:
        args.targets_output.parent.mkdir(parents=True, exist_ok=True)
        args.targets_output.write_text(
            json.dumps(target_manifest(targets), indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
    if args.evidence_dir is not None:
        write_evidence_files(summary, args.evidence_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("bounded_probe_complete") is True else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the post-U0 Q&R-only method diagnostic.

This diagnostic is not the C0.0 selection authority. It measures whether each ST
product page co-locates exact Part Number and Marketing Status inside Quality &
Reliability. C0 currently does not, which is a page-schema/method limitation rather
than a lifecycle or family-quality failure.
"""
from __future__ import annotations

import argparse
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from st_browser_acquisition import STBrowserAcquirer
from stm32_post_u0_evidence_probe import (
    DEFAULT_CATALOG,
    RateLimitedFetcher,
    deterministic_targets,
    read_catalog,
    run_probe,
    target_manifest,
    write_evidence_files,
)
from stm32_post_u0_qr_evidence import (
    EVIDENCE_AUTHORITY,
    PARSER_PROFILE,
    SAMPLE_BUY_IS_IDENTITY_GATE,
    build_qr_evidence_record,
)

DEFAULT_OUTPUT = Path("/tmp/stm32-post-u0-qr-method-diagnostic.json")


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
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)

    rows = read_catalog(DEFAULT_CATALOG)
    targets = deterministic_targets(rows)
    with STBrowserAcquirer(headless=args.headless) as acquirer:
        fetcher = RateLimitedFetcher(delay_seconds=args.delay, fetcher=acquirer.fetch)
        summary = run_probe(
            targets=targets,
            fetcher=fetcher,
            evidence_builder=build_qr_evidence_record,
            timeout_seconds=args.timeout,
        )
        summary["browser"] = {
            "headless": args.headless,
            "browser_version": acquirer.browser_version,
            "playwright_version": _playwright_version(),
            "evidence_profile": PARSER_PROFILE,
        }
        summary["commercial_identity_authority"] = EVIDENCE_AUTHORITY
        summary["sample_buy_is_identity_gate"] = SAMPLE_BUY_IS_IDENTITY_GATE
        summary["method_diagnostic_only"] = True

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
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

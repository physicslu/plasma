#!/usr/bin/env python3
"""Run bounded STM32F4 acquisition through real Chromium without canonical writes."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable

from st_browser_acquisition import (
    BROWSER_TRANSPORT,
    STBrowserAcquirer,
    build_browser_evidence_record,
)
from st_product_page_acquisition import AcquisitionError
from stm32f4_acquisition_pilot import (
    DEFAULT_CATALOG,
    DEFAULT_MANIFEST,
    FetchResult,
    PilotTarget,
    pilot_is_clean,
    read_catalog,
    read_manifest,
    run_pilot,
)

CONTROL_BASE_DEVICE = "STM32F401CC"
PLAYWRIGHT_REQUIREMENT = "1.62.0"
DEFAULT_INTER_REQUEST_DELAY_SECONDS = 2.0
MIN_INTER_REQUEST_DELAY_SECONDS = 1.0


class RateLimitedFetcher:
    def __init__(
        self,
        *,
        delay_seconds: float,
        fetcher: Callable[[str, float], FetchResult],
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if delay_seconds < MIN_INTER_REQUEST_DELAY_SECONDS:
            raise AcquisitionError(
                f"live pilot delay must be at least {MIN_INTER_REQUEST_DELAY_SECONDS:.1f} seconds"
            )
        self.delay_seconds = delay_seconds
        self.fetcher = fetcher
        self.sleeper = sleeper
        self._first = True

    def __call__(self, source_url: str, timeout_seconds: float) -> FetchResult:
        if self._first:
            self._first = False
        else:
            self.sleeper(self.delay_seconds)
        return self.fetcher(source_url, timeout_seconds)


def select_targets(scope: str, targets: list[PilotTarget]) -> list[PilotTarget]:
    if scope == "pilot":
        return targets
    control = [target for target in targets if target.base_device == CONTROL_BASE_DEVICE]
    if len(control) != 1:
        raise AcquisitionError(f"STM32F4 browser pilot requires control {CONTROL_BASE_DEVICE}")
    return control


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--scope", choices=("control", "pilot"), default="control")
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--delay", type=float, default=DEFAULT_INTER_REQUEST_DELAY_SECONDS)
    browser_mode = parser.add_mutually_exclusive_group()
    browser_mode.add_argument("--headless", action="store_true")
    browser_mode.add_argument("--headed", dest="headless", action="store_false")
    parser.set_defaults(headless=False)
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)

    try:
        pilot_id, manifest_targets = read_manifest(args.manifest)
        targets = select_targets(args.scope, manifest_targets)
        catalog_rows = read_catalog(args.catalog)
        with STBrowserAcquirer(headless=args.headless) as acquirer:
            fetcher = RateLimitedFetcher(delay_seconds=args.delay, fetcher=acquirer.fetch)
            summary = run_pilot(
                pilot_id=pilot_id,
                targets=targets,
                catalog_rows=catalog_rows,
                fetcher=fetcher,
                evidence_builder=build_browser_evidence_record,
                timeout_seconds=args.timeout,
            )
            browser_version = acquirer.browser_version
        summary["acquisition_transport"] = BROWSER_TRANSPORT
        summary["browser_scope"] = args.scope
        summary["browser_runtime"] = {
            "engine": "chromium",
            "browser_version": browser_version,
            "playwright_requirement": PLAYWRIGHT_REQUIREMENT,
            "headless": args.headless,
        }
        summary["canonical_dataset_admission"] = False
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if pilot_is_clean(summary) else 1
    except (AcquisitionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the bounded STM32F1 acquisition pilot with conservative live-request pacing."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Callable

from st_product_page_acquisition import AcquisitionError, fetch_html
from stm32f1_acquisition_pilot import (
    DEFAULT_CATALOG,
    DEFAULT_MANIFEST,
    FetchResult,
    pilot_is_clean,
    read_catalog,
    read_manifest,
    run_pilot,
)

DEFAULT_INTER_REQUEST_DELAY_SECONDS = 2.0
MIN_INTER_REQUEST_DELAY_SECONDS = 1.0


class RateLimitedFetcher:
    def __init__(
        self,
        *,
        delay_seconds: float,
        fetcher: Callable[[str, float], FetchResult] = fetch_html,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if delay_seconds < MIN_INTER_REQUEST_DELAY_SECONDS:
            raise AcquisitionError(
                f"live pilot delay must be at least {MIN_INTER_REQUEST_DELAY_SECONDS:.1f} seconds"
            )
        self.delay_seconds = delay_seconds
        self.fetcher = fetcher
        self.sleeper = sleeper
        self._first_request = True

    def __call__(self, source_url: str, timeout_seconds: float) -> FetchResult:
        if self._first_request:
            self._first_request = False
        else:
            self.sleeper(self.delay_seconds)
        return self.fetcher(source_url, timeout_seconds)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=30.0)
    parser.add_argument("--delay", type=float, default=DEFAULT_INTER_REQUEST_DELAY_SECONDS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    try:
        pilot_id, targets = read_manifest(args.manifest)
        catalog_rows = read_catalog(args.catalog)
        summary = run_pilot(
            pilot_id=pilot_id,
            targets=targets,
            catalog_rows=catalog_rows,
            fetcher=RateLimitedFetcher(delay_seconds=args.delay),
            timeout_seconds=args.timeout,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return 0 if pilot_is_clean(summary) else 1
    except (AcquisitionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

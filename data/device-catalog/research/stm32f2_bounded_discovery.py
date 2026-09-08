#!/usr/bin/env python3
"""Reusable bounded-discovery adapter for STM32F2.

Future bounded STM32F2 discovery batches should add immutable registry/manifest
state and invoke this adapter rather than cloning another phase-specific Python
implementation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from device_catalog_admission_framework import canonical_csv_sha256, read_csv
from device_catalog_bounded_discovery import (
    BoundedBatchSpec,
    decorate_discovery_summary,
    deterministic_first_unadmitted_targets,
    discovery_is_clean as generic_discovery_is_clean,
    load_batch_spec,
    read_guarded_manifest,
    read_guarded_production_bases,
)
from st_browser_acquisition import BROWSER_TRANSPORT, STBrowserAcquirer
from st_product_page_acquisition import AcquisitionError, validate_source_url
from stm32f2_phase4_3b_discovery import (
    BASE_RE,
    EXPECTED_SUBFAMILIES,
    PATTERN_RE,
    DiscoveryTarget,
    RateLimitedFetcher,
    _f2_rows,
    discovery_is_clean as base_discovery_is_clean,
    read_catalog,
    run_discovery as run_base_discovery,
)

HERE = Path(__file__).resolve().parent
FAMILY = "STM32F2"
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_CANONICAL = HERE / "stm32f2-commercial-icpn.csv"
DEFAULT_REGISTRY = HERE / "stm32f2-bounded-discovery-batches.json"


def load_spec(phase: str, *, registry_path: Path = DEFAULT_REGISTRY) -> BoundedBatchSpec:
    return load_batch_spec(
        registry_path=registry_path,
        family=FAMILY,
        phase=phase,
        root=HERE,
    )


def read_production_bases(path: Path, *, spec: BoundedBatchSpec) -> set[str]:
    return read_guarded_production_bases(
        path,
        spec=spec,
        read_csv=read_csv,
        canonical_csv_sha256=canonical_csv_sha256,
        error_type=AcquisitionError,
    )


def _base_from_row(row: dict[str, str]) -> str:
    match = PATTERN_RE.fullmatch(row["part_number"])
    assert match is not None
    return match.group(1)


def deterministic_targets(
    catalog_rows: list[dict[str, str]],
    production_bases: set[str],
    *,
    spec: BoundedBatchSpec,
) -> list[tuple[str, str]]:
    return deterministic_first_unadmitted_targets(
        family_rows=_f2_rows(catalog_rows),
        production_bases=production_bases,
        expected_subfamilies=EXPECTED_SUBFAMILIES,
        base_from_row=_base_from_row,
        subfamily_from_row=lambda row: row["subfamily"],
        phase=spec.phase,
        error_type=AcquisitionError,
    )


def _source_url_for_base(base: str) -> str:
    return f"https://www.st.com/en/microcontrollers-microprocessors/{base.lower()}.html"


def read_manifest(
    path: Path,
    catalog_rows: list[dict[str, str]],
    production_bases: set[str],
    *,
    spec: BoundedBatchSpec,
) -> tuple[str, list[DiscoveryTarget]]:
    expected = deterministic_targets(catalog_rows, production_bases, spec=spec)
    return read_guarded_manifest(
        path,
        spec=spec,
        expected_targets=expected,
        expected_subfamilies=EXPECTED_SUBFAMILIES,
        base_is_valid=lambda base: BASE_RE.fullmatch(base) is not None,
        validate_source_url=validate_source_url,
        source_url_for_base=_source_url_for_base,
        target_factory=DiscoveryTarget,
        error_type=AcquisitionError,
    )


def run_discovery(*, spec: BoundedBatchSpec, **kwargs: Any) -> dict[str, object]:
    summary = run_base_discovery(**kwargs)
    return decorate_discovery_summary(summary, spec=spec)


def discovery_is_clean(summary: dict[str, object], *, spec: BoundedBatchSpec) -> bool:
    return generic_discovery_is_clean(
        summary,
        spec=spec,
        base_clean=base_discovery_is_clean,
    )


def main_for_phase(phase: str, argv: list[str] | None = None) -> int:
    spec = load_spec(phase)
    parser = argparse.ArgumentParser(description=f"Run {spec.scope}.")
    parser.add_argument("--manifest", type=Path, default=spec.manifest_path)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=75.0)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        catalog_rows = read_catalog(args.catalog)
        production_bases = read_production_bases(args.canonical, spec=spec)
        pilot_id, targets = read_manifest(
            args.manifest,
            catalog_rows,
            production_bases,
            spec=spec,
        )
        with STBrowserAcquirer(headless=args.headless) as acquirer:
            fetcher = RateLimitedFetcher(delay_seconds=args.delay, fetcher=acquirer.fetch)
            summary = run_discovery(
                spec=spec,
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
        args.output.write_text(
            json.dumps(summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        return 0 if discovery_is_clean(summary, spec=spec) else 1
    except (AcquisitionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run one registered bounded STM32F2 discovery batch."
    )
    parser.add_argument("--phase", required=True)
    args, remainder = parser.parse_known_args(sys.argv[1:] if argv is None else argv)
    return main_for_phase(args.phase, remainder)


if __name__ == "__main__":
    raise SystemExit(main())

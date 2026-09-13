#!/usr/bin/env python3
"""Run one deterministic STM32L1 L1.2 commercial-discovery shard."""
from __future__ import annotations

import argparse
import json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from st_dual_surface_browser_acquisition import STDualSurfaceBrowserAcquirer
import stm32l1_phase_l1_2_discovery as core
from stm32l1_phase_l1_2_sharded import run_discovery_slice, select_shard, slice_is_clean


def _playwright_version() -> str:
    try:
        return version("playwright")
    except PackageNotFoundError:
        return "unknown"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--shard-index", type=int, required=True)
    parser.add_argument("--shard-count", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=90.0)
    parser.add_argument("--delay", type=float, default=1.0)
    parser.add_argument("--headless", action="store_true")
    args = parser.parse_args(argv)

    rows = core.read_catalog(core.DEFAULT_CATALOG)
    full_targets = core.deterministic_targets(rows)
    targets = select_shard(
        full_targets,
        shard_index=args.shard_index,
        shard_count=args.shard_count,
    )
    base_by_url = {
        surface.source_url: target.base_device
        for target in targets
        for surface in target.surfaces
    }
    with STDualSurfaceBrowserAcquirer(
        base_by_url=base_by_url,
        family_label=(
            f"STM32L1 L1.2 commercial discovery shard "
            f"{args.shard_index}/{args.shard_count}"
        ),
        headless=args.headless,
        reuse_browser=True,
        global_deadline=True,
    ) as acquirer:
        summary = run_discovery_slice(
            full_targets=full_targets,
            targets=targets,
            shard_index=args.shard_index,
            shard_count=args.shard_count,
            catalog_rows=rows,
            fetcher=core.RateLimitedFetcher(delay_seconds=args.delay, fetcher=acquirer.fetch),
            evidence_builder=core.build_discovery_evidence_record,
            timeout_seconds=args.timeout,
        )
        summary["browser"] = {
            "shard_index": args.shard_index,
            "headless": args.headless,
            "browser_version": acquirer.browser_version,
            "playwright_version": _playwright_version(),
            "evidence_profile": core.PARSER_PROFILE,
            "reuse_browser": acquirer.reuse_browser,
            "per_device_global_deadline": acquirer.global_deadline,
            "per_surface_timeout_seconds": args.timeout,
        }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    if args.evidence_dir is not None:
        core.write_evidence_files(summary, args.evidence_dir)
    print(
        json.dumps(
            {
                "shard_index": args.shard_index,
                "shard_count": args.shard_count,
                "base_device_count": summary["base_device_count"],
                "evidence_surface_count": summary["evidence_surface_count"],
                "active_exact_icpn_candidates": summary["active_exact_icpn_candidates"],
                "slice_clean": summary["slice_clean"],
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0 if slice_is_clean(summary) else 1


if __name__ == "__main__":
    raise SystemExit(main())

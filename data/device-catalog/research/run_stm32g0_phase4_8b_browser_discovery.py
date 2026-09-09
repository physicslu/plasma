#!/usr/bin/env python3
"""Run STM32G0 Phase 4.8B with the family-owned dual-surface browser profile."""
from __future__ import annotations
import argparse, json
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path
from stm32g0_browser_acquisition import STM32G0BrowserAcquirer
from stm32g0_dual_surface_evidence import PARSER_PROFILE, build_dual_surface_browser_evidence_record
from stm32g0_foundation import DEFAULT_CATALOG, read_catalog
from stm32g0_phase4_8b_discovery import (
    DEFAULT_MANIFEST, DEFAULT_OUTPUT, RateLimitedFetcher, discovery_is_clean,
    read_manifest, run_discovery, write_evidence_files,
)

def _playwright_version() -> str:
    try: return version("playwright")
    except PackageNotFoundError: return "unknown"

def main(argv: list[str] | None = None) -> int:
    p=argparse.ArgumentParser()
    p.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    p.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    p.add_argument("--evidence-dir", type=Path)
    p.add_argument("--timeout", type=float, default=90.0)
    p.add_argument("--delay", type=float, default=2.0)
    p.add_argument("--headless", action="store_true")
    a=p.parse_args(argv)
    rows=read_catalog(DEFAULT_CATALOG)
    pilot_id, targets=read_manifest(a.manifest, rows)
    base_by_url={t.source_url:t.base_device for t in targets}
    with STM32G0BrowserAcquirer(base_by_url=base_by_url, headless=a.headless) as acq:
        fetcher=RateLimitedFetcher(delay_seconds=a.delay, fetcher=acq.fetch)
        summary=run_discovery(pilot_id=pilot_id, targets=targets, catalog_rows=rows,
            fetcher=fetcher, evidence_builder=build_dual_surface_browser_evidence_record,
            timeout_seconds=a.timeout)
        summary["browser"]={"headless":a.headless,"browser_version":acq.browser_version,
            "playwright_version":_playwright_version(),"evidence_profile":PARSER_PROFILE}
    a.output.parent.mkdir(parents=True, exist_ok=True)
    a.output.write_text(json.dumps(summary, indent=2, sort_keys=True)+"\n", encoding="utf-8")
    if a.evidence_dir is not None: write_evidence_files(summary, a.evidence_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if discovery_is_clean(summary) else 1

if __name__ == "__main__": raise SystemExit(main())

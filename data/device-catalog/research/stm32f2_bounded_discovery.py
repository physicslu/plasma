#!/usr/bin/env python3
"""Reusable bounded-discovery adapter for STM32F2.

Future bounded STM32F2 discovery batches should use ``plan`` + ``materialize``
to create immutable registry/manifest state, then invoke the registered batch
instead of cloning another phase-specific Python implementation.
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
from device_catalog_bounded_planning import (
    PLAN_SCHEMA_VERSION,
    BoundedPlanningError,
    materialize_plan,
    read_registry_payload,
    require_phase_available,
    validate_acquisition_date,
    validate_phase,
    write_json_atomic,
)
from device_catalog_evidence_framework import sha256
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
DEFAULT_SCOPE = "bounded read-only official-ST STM32F2 discovery"
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


def _deterministic_targets_for_phase(
    catalog_rows: list[dict[str, str]],
    production_bases: set[str],
    *,
    phase: str,
    error_type: type[Exception],
) -> list[tuple[str, str]]:
    return deterministic_first_unadmitted_targets(
        family_rows=_f2_rows(catalog_rows),
        production_bases=production_bases,
        expected_subfamilies=EXPECTED_SUBFAMILIES,
        base_from_row=_base_from_row,
        subfamily_from_row=lambda row: row["subfamily"],
        phase=phase,
        error_type=error_type,
    )


def deterministic_targets(
    catalog_rows: list[dict[str, str]],
    production_bases: set[str],
    *,
    spec: BoundedBatchSpec,
) -> list[tuple[str, str]]:
    return _deterministic_targets_for_phase(
        catalog_rows,
        production_bases,
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


def _current_production_boundary(
    canonical_path: Path,
) -> tuple[list[str], list[dict[str, str]], set[str], str]:
    fields, rows = read_csv(canonical_path)
    if not fields or not rows:
        raise BoundedPlanningError("STM32F2 canonical Production is empty")
    identities = [row.get("icpn") for row in rows]
    if any(not isinstance(icpn, str) or not icpn for icpn in identities):
        raise BoundedPlanningError("STM32F2 canonical Production contains an invalid ICPN")
    if len(set(identities)) != len(identities):
        raise BoundedPlanningError("duplicate Production identity")
    if any(row.get("family") != FAMILY for row in rows):
        raise BoundedPlanningError("STM32F2 canonical Production contains another family")
    bases = {row.get("base_device", "") for row in rows}
    if "" in bases or any(BASE_RE.fullmatch(base) is None for base in bases):
        raise BoundedPlanningError("STM32F2 canonical Production contains an invalid Base Device")
    return fields, rows, bases, canonical_csv_sha256(fields, rows)


def _phase_file_token(phase: str) -> str:
    return f"phase{phase.lower()}"


def build_next_batch_plan(
    *,
    phase: str,
    acquisition_date: str,
    scope: str = DEFAULT_SCOPE,
    registry_path: Path = DEFAULT_REGISTRY,
    catalog_path: Path = DEFAULT_CATALOG,
    canonical_path: Path = DEFAULT_CANONICAL,
) -> dict[str, Any]:
    """Build a deterministic next-batch transaction without writing repo state."""

    phase = validate_phase(phase)
    acquisition_date = validate_acquisition_date(acquisition_date)
    if not isinstance(scope, str) or not scope.strip():
        raise BoundedPlanningError("bounded-discovery scope is required")
    scope = scope.strip()

    registry = read_registry_payload(registry_path, family=FAMILY)
    require_phase_available(registry, phase=phase)

    fields, rows, production_bases, production_sha = _current_production_boundary(
        canonical_path
    )
    catalog_rows = read_catalog(catalog_path)
    targets = _deterministic_targets_for_phase(
        catalog_rows,
        production_bases,
        phase=phase,
        error_type=BoundedPlanningError,
    )

    token = _phase_file_token(phase)
    family_lower = FAMILY.lower()
    manifest_name = f"{family_lower}-{token}-discovery-manifest.json"
    baseline_name = f"{family_lower}-{token}-discovery-baseline.json"
    evidence_dir = (
        f"evidence/{family_lower}-{token}-official-st-discovery-live-{acquisition_date}"
    )
    pilot_id = (
        f"{family_lower}-{token}-official-st-discovery-{acquisition_date}"
    )

    registry_entry = {
        "scope": scope,
        "manifest": manifest_name,
        "baseline": baseline_name,
        "evidence_dir": evidence_dir,
        "expected_production_bases": sorted(production_bases),
        "expected_production_sha256": production_sha,
    }
    manifest_targets = [
        {
            "subfamily": subfamily,
            "base_device": base,
            "source_url": _source_url_for_base(base),
            "selection_reason": (
                "lexicographically first unadmitted Base Device at the guarded "
                f"{FAMILY} Production boundary in the guarded {subfamily} OpenOCD surface"
            ),
        }
        for subfamily, base in targets
    ]
    manifest = {
        "schema_version": 1,
        "phase": phase,
        "pilot_id": pilot_id,
        "targets": manifest_targets,
    }
    return {
        "schema_version": PLAN_SCHEMA_VERSION,
        "family": FAMILY,
        "phase": phase,
        "acquisition_date": acquisition_date,
        "scope": scope,
        "inputs": {
            "registry_sha256": sha256(registry_path),
            "openocd_catalog_sha256": sha256(catalog_path),
            "canonical_file_sha256": sha256(canonical_path),
            "canonical_state_sha256": canonical_csv_sha256(fields, rows),
            "production_exact_icpn_count": len(rows),
            "production_base_device_count": len(production_bases),
        },
        "registry_entry": registry_entry,
        "manifest": manifest,
    }


def materialize_next_batch_plan(
    *,
    plan_path: Path,
    registry_path: Path = DEFAULT_REGISTRY,
    catalog_path: Path = DEFAULT_CATALOG,
    canonical_path: Path = DEFAULT_CANONICAL,
    root: Path = HERE,
) -> dict[str, Any]:
    return materialize_plan(
        plan_path=plan_path,
        registry_path=registry_path,
        root=root,
        family=FAMILY,
        rebuild_plan=lambda **kwargs: build_next_batch_plan(
            catalog_path=catalog_path,
            canonical_path=canonical_path,
            **kwargs,
        ),
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


def _plan_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Build a deterministic, read-only next STM32F2 bounded-discovery plan."
    )
    parser.add_argument("--phase", required=True)
    parser.add_argument("--date", required=True, dest="acquisition_date")
    parser.add_argument("--scope", default=DEFAULT_SCOPE)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        plan = build_next_batch_plan(
            phase=args.phase,
            acquisition_date=args.acquisition_date,
            scope=args.scope,
            registry_path=args.registry,
            catalog_path=args.catalog,
            canonical_path=args.canonical,
        )
        write_json_atomic(args.output, plan)
        print(json.dumps(plan, indent=2, sort_keys=False))
        return 0
    except (BoundedPlanningError, AcquisitionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def _materialize_main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Materialize a replay-validated STM32F2 bounded-discovery plan."
    )
    parser.add_argument("--plan", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--root", type=Path, default=HERE)
    args = parser.parse_args(argv)
    try:
        report = materialize_next_batch_plan(
            plan_path=args.plan,
            registry_path=args.registry,
            catalog_path=args.catalog,
            canonical_path=args.canonical,
            root=args.root,
        )
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    except (BoundedPlanningError, AcquisitionError, OSError, json.JSONDecodeError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


def main(argv: list[str] | None = None) -> int:
    raw = list(sys.argv[1:] if argv is None else argv)
    if raw and raw[0] == "plan":
        return _plan_main(raw[1:])
    if raw and raw[0] == "materialize":
        return _materialize_main(raw[1:])

    parser = argparse.ArgumentParser(
        description="Run one registered bounded STM32F2 discovery batch."
    )
    parser.add_argument("--phase", required=True)
    args, remainder = parser.parse_known_args(raw)
    return main_for_phase(args.phase, remainder)


if __name__ == "__main__":
    raise SystemExit(main())

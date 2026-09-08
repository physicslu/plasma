#!/usr/bin/env python3
"""Historical 4.3H STM32F2 discovery entry point backed by the generic batch engine."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from stm32f2_bounded_discovery import (
    DEFAULT_CANONICAL,
    DEFAULT_CATALOG,
    deterministic_targets as _deterministic_targets,
    discovery_is_clean as _discovery_is_clean,
    load_spec,
    main_for_phase,
    read_catalog,
    read_manifest as _read_manifest,
    read_production_bases as _read_production_bases,
    run_discovery as _run_discovery,
)

SPEC = load_spec("4.3H")
PHASE = SPEC.phase
DEFAULT_MANIFEST = SPEC.manifest_path
EXPECTED_PRODUCTION_BASES = SPEC.expected_production_bases
EXPECTED_PRODUCTION_SHA256 = SPEC.expected_production_sha256


def read_production_bases(path: Path) -> set[str]:
    return _read_production_bases(path, spec=SPEC)


def deterministic_targets(
    catalog_rows: list[dict[str, str]],
    production_bases: set[str],
) -> list[tuple[str, str]]:
    return _deterministic_targets(catalog_rows, production_bases, spec=SPEC)


def read_manifest(
    path: Path,
    catalog_rows: list[dict[str, str]],
    production_bases: set[str],
):
    return _read_manifest(path, catalog_rows, production_bases, spec=SPEC)


def run_discovery(**kwargs: Any) -> dict[str, object]:
    return _run_discovery(spec=SPEC, **kwargs)


def discovery_is_clean(summary: dict[str, object]) -> bool:
    return _discovery_is_clean(summary, spec=SPEC)


def main(argv: list[str] | None = None) -> int:
    return main_for_phase(PHASE, argv)


if __name__ == "__main__":
    raise SystemExit(main())

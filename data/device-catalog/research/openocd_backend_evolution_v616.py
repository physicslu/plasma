#!/usr/bin/env python3
"""Compatibility helpers for the exact v6.16 backend-only Production evolution.

Historical Layer-1 publications own exact commercial identity and metadata.
The v6.16 OpenOCD backend routing state is validated against an immutable,
human-readable 364-row binding ledger materialized from the frozen v6.14
workflow artifact.
"""
from __future__ import annotations

import csv
import hashlib
from collections.abc import Iterable, Mapping
from pathlib import Path

HERE = Path(__file__).resolve().parent
LEDGER = HERE / "openocd-production-backend-bindings-v6.16.csv"

BACKEND_FIELDS = (
    "cmsis_device_name",
    "existing_identifier",
    "existing_identifier_kind",
    "mapping_status",
    "openocd_target_config",
)

EXPECTED_EXACT_COUNT = 364
EXPECTED_LEDGER_SHA256 = "3b5bc6078aba3d18d9f96969a6147df2304e2390c7c93ff4f78409e584ce8501"
EXPECTED_FAMILY_COUNTS = {
    "STM32C0": 12,
    "STM32F2": 72,
    "STM32F3": 168,
    "STM32F4": 3,
    "STM32F7": 62,
    "STM32G0": 30,
    "STM32H7": 14,
    "STM32L1": 1,
    "STM32L4": 1,
    "STM32U3": 1,
}


class BackendEvolutionError(RuntimeError):
    pass


def _ledger_rows() -> list[dict[str, str]]:
    raw = LEDGER.read_bytes()
    if hashlib.sha256(raw).hexdigest() != EXPECTED_LEDGER_SHA256:
        raise BackendEvolutionError("v6.16 binding ledger digest drift")
    with LEDGER.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))
    if len(rows) != EXPECTED_EXACT_COUNT or len({r["icpn"] for r in rows}) != EXPECTED_EXACT_COUNT:
        raise BackendEvolutionError("v6.16 binding ledger cardinality drift")
    counts: dict[str, int] = {}
    for row in rows:
        counts[row["family"]] = counts.get(row["family"], 0) + 1
    if dict(sorted(counts.items())) != EXPECTED_FAMILY_COUNTS:
        raise BackendEvolutionError(f"v6.16 family partition drift: {counts}")
    return rows


def bindings() -> dict[str, dict[str, str]]:
    return {
        row["icpn"]: {
            "authority": row["authority"],
            "family": row["family"],
            "existing_identifier": row["existing_identifier"],
            "existing_identifier_kind": row["existing_identifier_kind"],
            "cmsis_device_name": row["cmsis_device_name"],
            "openocd_target_config": row["openocd_target_config"],
            "mapping_status": row["mapping_status"],
        }
        for row in _ledger_rows()
    }


def promoted_exact_set(family: str | None = None) -> set[str]:
    b = bindings()
    return {
        icpn for icpn, item in b.items()
        if family is None or item["family"] == family
    }


def validate_current_binding(row: Mapping[str, str], binding: Mapping[str, str]) -> None:
    icpn = row.get("icpn", "")
    if row.get("family") != binding["family"]:
        raise BackendEvolutionError(f"{icpn}: family drift")
    for field in BACKEND_FIELDS:
        expected = binding[field]
        if row.get(field, "") != expected:
            raise BackendEvolutionError(
                f"{icpn}: {field} drift: {row.get(field)!r} != {expected!r}"
            )


def validate_family_current_bindings(
    rows: Iterable[Mapping[str, str]], family: str
) -> set[str]:
    family_bindings = {
        icpn: item for icpn, item in bindings().items()
        if item["family"] == family
    }
    by_icpn = {row.get("icpn", ""): row for row in rows}
    missing = set(family_bindings) - set(by_icpn)
    if missing:
        raise BackendEvolutionError(
            f"{family}: promoted ICPNs missing from current Production: {sorted(missing)}"
        )
    for icpn, item in family_bindings.items():
        validate_current_binding(by_icpn[icpn], item)
    return set(family_bindings)


def rewind_v616_backend(
    rows: Iterable[Mapping[str, str]], family: str
) -> list[dict[str, str]]:
    """Validate current bindings, then return the pre-v6.16 backend view."""
    current = [dict(row) for row in rows]
    promoted = validate_family_current_bindings(current, family)
    out: list[dict[str, str]] = []
    for row in current:
        historical = dict(row)
        if historical.get("icpn") in promoted:
            historical["cmsis_device_name"] = ""
            historical["existing_identifier"] = ""
            historical["existing_identifier_kind"] = ""
            historical["mapping_status"] = "no_mapping"
            historical["openocd_target_config"] = ""
        out.append(historical)
    return out

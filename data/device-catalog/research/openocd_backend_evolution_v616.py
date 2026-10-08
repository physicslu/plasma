#!/usr/bin/env python3
"""Compatibility helpers for v6.16 backend-only Production evolution.

Historical Layer-1 publications own exact commercial identity and metadata.
OpenOCD backend routing is allowed to evolve only for the exact 364-ICPN set
frozen by v6.14/v6.15 and explicitly written by v6.16.
"""
from __future__ import annotations

from collections.abc import Iterable, Mapping

import propose_openocd_consolidated_backend_promotion_v614 as v614

BACKEND_FIELDS = (
    "cmsis_device_name",
    "existing_identifier",
    "existing_identifier_kind",
    "mapping_status",
    "openocd_target_config",
)

EXPECTED_EXACT_COUNT = 364
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


def bindings() -> dict[str, dict[str, str]]:
    out = v614.build_bindings()
    if len(out) != EXPECTED_EXACT_COUNT:
        raise BackendEvolutionError(f"v6.16 binding cardinality drift: {len(out)}")
    counts: dict[str, int] = {}
    for item in out.values():
        family = item["family"]
        counts[family] = counts.get(family, 0) + 1
    if dict(sorted(counts.items())) != EXPECTED_FAMILY_COUNTS:
        raise BackendEvolutionError(f"v6.16 family partition drift: {counts}")
    return out


def promoted_exact_set(family: str | None = None) -> set[str]:
    b = bindings()
    return {
        icpn for icpn, item in b.items()
        if family is None or item["family"] == family
    }


def _expected_mapping_status(kind: str) -> str:
    if kind == "cmsis_device_name":
        return "deterministic_cmsis_device_name"
    if kind == "ordering_pattern":
        return "deterministic_ordering_pattern"
    raise BackendEvolutionError(f"unsupported v6.16 identifier kind: {kind}")


def validate_current_binding(row: Mapping[str, str], binding: Mapping[str, str]) -> None:
    icpn = row.get("icpn", "")
    kind = binding["existing_identifier_kind"]
    identifier = binding["existing_identifier"]
    expected_cmsis = identifier if kind == "cmsis_device_name" else ""
    expected = {
        "cmsis_device_name": expected_cmsis,
        "existing_identifier": identifier,
        "existing_identifier_kind": kind,
        "mapping_status": _expected_mapping_status(kind),
        "openocd_target_config": binding["openocd_target_config"],
    }
    if row.get("family") != binding["family"]:
        raise BackendEvolutionError(f"{icpn}: family drift")
    for field, value in expected.items():
        if row.get(field, "") != value:
            raise BackendEvolutionError(
                f"{icpn}: {field} drift: {row.get(field)!r} != {value!r}"
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
    """Return the pre-v6.16 backend view after validating current v6.16 bindings.

    Only the five backend-routing fields for the exact authorized family subset
    are rewound. Identity, metadata, source provenance, and row order are kept
    byte-for-byte at the field-value level.
    """
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

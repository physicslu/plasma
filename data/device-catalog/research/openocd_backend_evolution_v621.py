#!/usr/bin/env python3
"""Compatibility helpers for the exact v6.21 backend-only Production evolution.

The v6.21 write changes backend-routing fields only for the exact 17-row
bounded bridge frozen by v6.19/v6.20. Historical Layer-1 publication
validators may rewind those fields after first validating the current binding.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY = HERE / "openocd-bounded-identifier-bridge-v6.19.json"

BACKEND_FIELDS = (
    "cmsis_device_name",
    "existing_identifier",
    "existing_identifier_kind",
    "mapping_status",
    "openocd_target_config",
)

EXPECTED_EXACT_COUNT = 17
EXPECTED_FAMILY_COUNTS = {
    "STM32F3": 4,
    "STM32G0": 12,
    "STM32L1": 1,
}
EXPECTED_EXACT_SET_SHA256 = "20b3910840a802a8855ad9022aa6bc67a35e8b169bd71726189eb803ded8636f"
EXPECTED_BINDING_SHA256 = "c986e9dbd6e365b3ed6a7054f62e01ae2cd0e18e15cb3841321d43d20fc94892"


class BackendEvolutionError(RuntimeError):
    pass


def _policy() -> dict:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    if policy["scope"]["exact_icpn_count"] != EXPECTED_EXACT_COUNT:
        raise BackendEvolutionError("v6.21 policy cardinality drift")
    if policy["scope"]["family_counts"] != EXPECTED_FAMILY_COUNTS:
        raise BackendEvolutionError("v6.21 policy family partition drift")
    if policy["evidence"]["source_review_exact_set_sha256"] != EXPECTED_EXACT_SET_SHA256:
        raise BackendEvolutionError("v6.21 exact-set evidence digest drift")
    if policy["evidence"]["source_bridge_binding_sha256"] != EXPECTED_BINDING_SHA256:
        raise BackendEvolutionError("v6.21 binding evidence digest drift")
    return policy


def bindings() -> dict[str, dict[str, str]]:
    policy = _policy()
    out = {}
    for icpn, bridge in policy["bridges"].items():
        family = next(
            family for family in EXPECTED_FAMILY_COUNTS
            if icpn.startswith(family)
        )
        out[icpn] = {
            "family": family,
            "cmsis_device_name": "",
            "existing_identifier": bridge["existing_identifier"],
            "existing_identifier_kind": bridge["existing_identifier_kind"],
            "mapping_status": "deterministic_ordering_pattern",
            "openocd_target_config": bridge["openocd_target_config"],
        }
    if len(out) != EXPECTED_EXACT_COUNT:
        raise BackendEvolutionError("v6.21 binding cardinality drift")
    return out


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
    if not family_bindings:
        return set()
    by_icpn = {row.get("icpn", ""): row for row in rows}
    missing = set(family_bindings) - set(by_icpn)
    if missing:
        raise BackendEvolutionError(
            f"{family}: v6.21 promoted ICPNs missing from current Production: {sorted(missing)}"
        )
    for icpn, item in family_bindings.items():
        validate_current_binding(by_icpn[icpn], item)
    return set(family_bindings)


def rewind_v621_backend(
    rows: Iterable[Mapping[str, str]], family: str
) -> list[dict[str, str]]:
    """Validate current v6.21 bindings, then return the pre-v6.21 backend view."""
    current = [dict(row) for row in rows]
    promoted = validate_family_current_bindings(current, family)
    out = []
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

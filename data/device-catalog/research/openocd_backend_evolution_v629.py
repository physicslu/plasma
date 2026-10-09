#!/usr/bin/env python3
"""Compatibility helpers for the exact v6.29 STM32C0 backend-only evolution.

v6.29 is allowed to change only backend-routing fields for five exact STM32C0
Production rows frozen by v6.28. Historical validators may call
rewind_v629_backend() so completed publication transactions continue to replay
against their original backend prestate.

The helper is deliberately dual-state before merge: it accepts either the
complete pre-v6.29 state or the complete frozen v6.29 poststate. Mixed or
partial application fails closed.
"""
from __future__ import annotations

import json
from collections.abc import Iterable, Mapping
from pathlib import Path

HERE = Path(__file__).resolve().parent
POLICY = HERE / "openocd-c0-production-backend-dry-run-v6.28.json"

BACKEND_FIELDS = (
    "cmsis_device_name",
    "existing_identifier",
    "existing_identifier_kind",
    "mapping_status",
    "openocd_target_config",
)

EXPECTED_EXACT_COUNT = 5
EXPECTED_EXACT_SET_SHA256 = "c4bbc25d50dfbb77101d8247a00e4730f8ac22e4ee05729245412808ece1a716"
EXPECTED_BINDING_SHA256 = "dffa61c93a357b6ce65ca83f3789eec162d0937e56fc0f798b81fb38f1ada90e"


class BackendEvolutionError(RuntimeError):
    pass


def _policy() -> dict:
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    scope = policy["scope"]
    if scope["family"] != "STM32C0" or scope["exact_icpn_count"] != EXPECTED_EXACT_COUNT:
        raise BackendEvolutionError("v6.29 policy cardinality/family drift")
    if scope["exact_set_sha256"] != EXPECTED_EXACT_SET_SHA256:
        raise BackendEvolutionError("v6.29 exact-set digest drift")
    if scope["binding_sha256"] != EXPECTED_BINDING_SHA256:
        raise BackendEvolutionError("v6.29 binding digest drift")
    if policy["frozen_postimages"]["lock_state"] != "FROZEN":
        raise BackendEvolutionError("v6.29 source dry-run postimages are not frozen")
    return policy


def bindings() -> dict[str, dict[str, str]]:
    policy = _policy()
    out = {}
    for icpn, bridge in policy["bindings"].items():
        out[icpn] = {
            "family": "STM32C0",
            "cmsis_device_name": "",
            "existing_identifier": bridge["existing_identifier"],
            "existing_identifier_kind": bridge["existing_identifier_kind"],
            "mapping_status": "deterministic_ordering_pattern",
            "openocd_target_config": bridge["openocd_target_config"],
        }
    if len(out) != EXPECTED_EXACT_COUNT:
        raise BackendEvolutionError("v6.29 binding cardinality drift")
    return out


def _is_pre(row: Mapping[str, str]) -> bool:
    return (
        row.get("cmsis_device_name", "") == ""
        and row.get("existing_identifier", "") == ""
        and row.get("existing_identifier_kind", "") == ""
        and row.get("mapping_status", "") == "no_mapping"
        and row.get("openocd_target_config", "") == ""
    )


def _is_post(row: Mapping[str, str], binding: Mapping[str, str]) -> bool:
    if row.get("family") != binding["family"]:
        return False
    return all(row.get(field, "") == binding[field] for field in BACKEND_FIELDS)


def backend_state(rows: Iterable[Mapping[str, str]], family: str) -> str:
    if family != "STM32C0":
        return "not_applicable"

    current = [dict(row) for row in rows]
    by_icpn = {row.get("icpn", ""): row for row in current}
    expected = bindings()
    missing = set(expected) - set(by_icpn)
    if missing:
        raise BackendEvolutionError(
            f"STM32C0: v6.29 scoped ICPNs missing from current Production: {sorted(missing)}"
        )

    states = set()
    for icpn, binding in expected.items():
        row = by_icpn[icpn]
        if row.get("family") != "STM32C0":
            raise BackendEvolutionError(f"{icpn}: family drift")
        if _is_pre(row):
            states.add("pre")
        elif _is_post(row, binding):
            states.add("post")
        else:
            raise BackendEvolutionError(f"{icpn}: neither valid pre-v6.29 nor frozen post-v6.29 backend state")

    if len(states) != 1:
        raise BackendEvolutionError(f"v6.29 partial/mixed backend application detected: {sorted(states)}")
    return states.pop()


def rewind_v629_backend(
    rows: Iterable[Mapping[str, str]], family: str
) -> list[dict[str, str]]:
    current = [dict(row) for row in rows]
    state = backend_state(current, family)
    if state in ("not_applicable", "pre"):
        return current

    scoped = set(bindings())
    out = []
    for row in current:
        historical = dict(row)
        if historical.get("icpn") in scoped:
            historical["cmsis_device_name"] = ""
            historical["existing_identifier"] = ""
            historical["existing_identifier_kind"] = ""
            historical["mapping_status"] = "no_mapping"
            historical["openocd_target_config"] = ""
        out.append(historical)
    return out

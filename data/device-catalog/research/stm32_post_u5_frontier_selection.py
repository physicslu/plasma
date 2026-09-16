#!/usr/bin/env python3
"""Select the next bounded STM32 research frontier after STM32U5 publication.

This transaction is research-only. It replays the retained cross-family
prioritization inventory against an immutable post-U5 Production prestate.
It does not admit ICPNs, modify Production, define programming behavior, or
authorize target execution.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
PRIORITIZATION_BASELINE = HERE / "stm32-cross-family-prioritization-baseline.json"
FROZEN_PRESTATE = HERE / "stm32-post-u5-production-prestate.json"
EXPECTED_SOURCE_MANIFEST_SHA256 = "3fbab3198e813580e29c3388a9027d1993a44a6d66ec73349ad20da708cc66af"
EXPECTED_PRODUCTION_EXACT = 2282
EXPECTED_PRODUCTION_FAMILIES = 16
EXPECTED_H7 = {
    "plasma_series": "STM32H7",
    "row_count": 200,
    "ordering_pattern_rows": 168,
    "cmsis_device_name_rows": 32,
    "subfamily_count": 20,
    "target_configs": ["tcl/target/stm32h7rsx.cfg", "tcl/target/stm32h7x.cfg"],
    "cohort": "high_complexity_requires_partitioned_scope",
    "structural_gate_pass": False,
    "shortlist_eligible": False,
}
NEXT_GATE = "stm32h7-partitioned-scope-selection-gate"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise RuntimeError(f"{path.name}: expected object")
    return value


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def _production_boundary() -> tuple[list[str], int]:
    manifest = _read_json(FROZEN_PRESTATE)
    _require(manifest.get("status") == "production", "frozen Production status drifted")
    _require(manifest.get("selection_policy") == "admitted_exact_manufacturer_part_number_only", "frozen Production selection policy drifted")
    sources = manifest.get("sources")
    _require(isinstance(sources, list), "frozen Production sources missing")
    families: list[str] = []
    exact = 0
    for source in sources:
        _require(isinstance(source, dict), "frozen Production source must be object")
        _require(source.get("manufacturer") == "STMicroelectronics", "frozen Production manufacturer drifted")
        family = source.get("family")
        rows = source.get("row_count")
        _require(isinstance(family, str) and isinstance(rows, int), "frozen Production source identity/count invalid")
        _require(family not in families, f"duplicate frozen Production family: {family}")
        families.append(family)
        exact += rows
    return sorted(families), exact


def build_selection() -> dict[str, Any]:
    baseline = _read_json(PRIORITIZATION_BASELINE)
    _require(baseline.get("policy_id") == "stm32-cross-family-prioritization-v1", "prioritization policy drifted")
    candidates = baseline.get("candidates")
    _require(isinstance(candidates, list), "prioritization candidates missing")

    production_series, exact = _production_boundary()
    _require(exact == EXPECTED_PRODUCTION_EXACT, "frozen Production exact ICPN count drifted")
    _require(len(production_series) == EXPECTED_PRODUCTION_FAMILIES, "frozen Production family count drifted")
    _require("STM32U5" in production_series, "STM32U5 missing from frozen Production")

    remaining = [item for item in candidates if isinstance(item, dict) and item.get("plasma_series") not in set(production_series)]
    standard_shortlist = [item for item in remaining if item.get("shortlist_eligible") is True]
    _require(standard_shortlist == [], "standard non-wireless shortlist is not exhausted")

    nonwireless = [item for item in remaining if not str(item.get("plasma_series", "")).startswith("STM32W")]
    _require([item.get("plasma_series") for item in nonwireless] == ["STM32H7"], "remaining non-wireless frontier drifted")
    h7 = nonwireless[0]
    for key, expected in EXPECTED_H7.items():
        _require(h7.get(key) == expected, f"STM32H7 frontier drifted: {key}")

    wireless = sorted(
        (
            {
                "plasma_series": item["plasma_series"],
                "row_count": item["row_count"],
                "ordering_pattern_rows": item["ordering_pattern_rows"],
                "cmsis_device_name_rows": item["cmsis_device_name_rows"],
                "subfamily_count": item["subfamily_count"],
                "target_configs": item["target_configs"],
                "cohort": item["cohort"],
                "structural_gate_pass": item["structural_gate_pass"],
            }
            for item in remaining
            if str(item.get("plasma_series", "")).startswith("STM32W")
        ),
        key=lambda item: item["plasma_series"],
    )
    _require(wireless, "wireless frontier inventory unexpectedly empty")
    _require(all(item["cohort"] == "wireless_requires_dedicated_scope" for item in wireless), "wireless cohort classification drifted")

    return {
        "schema_version": 1,
        "selection_id": "stm32-post-u5-frontier-selection-v1",
        "scope": "next_frontier_research_only",
        "status": "selected_for_partitioning_only",
        "production_boundary": {
            "source_production_manifest_sha256": EXPECTED_SOURCE_MANIFEST_SHA256,
            "frozen_prestate_sha256": _sha256(FROZEN_PRESTATE),
            "exact_icpns": EXPECTED_PRODUCTION_EXACT,
            "families": EXPECTED_PRODUCTION_FAMILIES,
            "production_series": production_series,
            "stm32u5_published": True,
        },
        "upstream_policy": {
            "policy_id": baseline.get("policy_id"),
            "prioritization_baseline_sha256": _sha256(PRIORITIZATION_BASELINE),
            "openocd_catalog_sha256": (baseline.get("inputs") or {}).get("openocd_catalog_sha256"),
            "standard_nonwireless_shortlist_exhausted": True,
        },
        "selected_next_research_frontier": "STM32H7",
        "selection_basis": [
            "all retained standard_nonwireless_research shortlist candidates are already in Production",
            "STM32H7 is the only remaining non-wireless candidate in the retained cross-family inventory",
            "STM32H7 has two target configs and therefore requires partitioning before bounded manufacturer-evidence discovery",
            "wireless STM32 cohorts remain separate because they require dedicated wireless/security scope",
        ],
        "stm32h7_frontier": {
            "row_count": h7["row_count"],
            "ordering_pattern_rows": h7["ordering_pattern_rows"],
            "cmsis_device_name_rows": h7["cmsis_device_name_rows"],
            "subfamily_count": h7["subfamily_count"],
            "subfamilies": h7["subfamilies"],
            "target_configs": h7["target_configs"],
            "cohort": h7["cohort"],
            "structural_gate_pass": h7["structural_gate_pass"],
            "shortlist_eligible": h7["shortlist_eligible"],
        },
        "wireless_frontier_backlog": wireless,
        "next_gate": NEXT_GATE,
        "claims": {
            "production_write_authorized": False,
            "icpn_admission_authorized": False,
            "exact_icpn_claimed_from_openocd": False,
            "programming_algorithm_equivalence_claimed": False,
            "runtime_programming_support_claimed": False,
            "physical_validation_claimed": False,
            "hil_required_for_catalog_admission": False,
            "wireless_family_rejected": False,
            "stm32h7_admission_ready": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    value = build_selection()
    payload = json.dumps(value, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.write_text(payload, encoding="utf-8")
    else:
        print(payload, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

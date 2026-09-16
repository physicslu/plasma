#!/usr/bin/env python3
"""Select the next bounded STM32 research frontier after STM32U5 publication.

This transaction is research-only. It does not admit ICPNs, modify Production,
define programming behavior, or authorize target execution. The current
standard non-wireless shortlist is expected to be exhausted after STM32U5
publication. The remaining non-wireless frontier may be selected only for a
bounded partitioning gate; wireless cohorts remain a separate dedicated-scope
backlog.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from stm32_cross_family_prioritization import (
    DEFAULT_CATALOG,
    DEFAULT_MANIFEST,
    build_prioritization,
)

HERE = Path(__file__).resolve().parent
EXPECTED_MANIFEST_SHA256 = "3fbab3198e813580e29c3388a9027d1993a44a6d66ec73349ad20da708cc66af"
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


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def build_selection() -> dict[str, Any]:
    report = build_prioritization(catalog_path=DEFAULT_CATALOG, manifest_path=DEFAULT_MANIFEST)
    production = report.get("production_invariants") or {}
    _require(production.get("exact_icpn_count") == EXPECTED_PRODUCTION_EXACT, "Production exact ICPN count drifted")
    production_series = production.get("production_series") or []
    _require(len(production_series) == EXPECTED_PRODUCTION_FAMILIES, "Production family count drifted")
    _require("STM32U5" in production_series, "STM32U5 is not in Production")
    _require(_sha256(DEFAULT_MANIFEST) == EXPECTED_MANIFEST_SHA256, "post-U5 Production manifest drifted")
    _require(report.get("research_shortlist") == [], "standard non-wireless shortlist is not exhausted")

    candidates = report.get("candidates") or []
    nonwireless = [item for item in candidates if not str(item.get("plasma_series", "")).startswith("STM32W")]
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
            for item in candidates
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
            "manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "exact_icpns": EXPECTED_PRODUCTION_EXACT,
            "families": EXPECTED_PRODUCTION_FAMILIES,
            "stm32u5_published": True,
        },
        "upstream_policy": {
            "policy_id": report.get("policy_id"),
            "openocd_catalog_sha256": (report.get("inputs") or {}).get("openocd_catalog_sha256"),
            "standard_nonwireless_shortlist_exhausted": True,
        },
        "selected_next_research_frontier": "STM32H7",
        "selection_basis": [
            "all standard_nonwireless_research shortlist candidates are already in Production",
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

#!/usr/bin/env python3
"""Deterministically qualify the STM32 TrustZone research cohort.

This transaction is research-only. It selects the smallest bounded research
surface from the already-frozen cross-family inventory. It does not admit any
ICPN to Production and does not claim security, programming, geometry, option-
byte, HIL, or runtime support.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "stm32-cross-family-prioritization-baseline.json"
COHORT = "trustzone_requires_security_scope"
EXPECTED = ("STM32L5", "STM32U3", "STM32U5")


def build_qualification() -> dict:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    by_series = {item["plasma_series"]: item for item in payload["candidates"]}

    candidates = []
    for series in EXPECTED:
        item = by_series[series]
        if item["cohort"] != COHORT:
            raise ValueError(f"{series}: TrustZone cohort classification drifted")
        if not item["structural_gate_pass"]:
            raise ValueError(f"{series}: structural gate no longer passes")
        if not item["complete_mapping_metadata"]:
            raise ValueError(f"{series}: mapping metadata incomplete")
        if len(item["target_configs"]) != 1:
            raise ValueError(f"{series}: target config surface is not singular")
        if item["ordering_pattern_rows"] <= 0:
            raise ValueError(f"{series}: no ordering-pattern research surface")

        candidates.append(
            {
                "plasma_series": series,
                "subfamily_count": item["subfamily_count"],
                "row_count": item["row_count"],
                "ordering_pattern_rows": item["ordering_pattern_rows"],
                "ordering_pattern_fraction": item["ordering_pattern_fraction"],
                "target_config": item["target_configs"][0],
                "legacy_standard_shortlist_eligible": item["shortlist_eligible"],
            }
        )

    # Avoid pseudo-precision from arbitrary weighted scores. Security evidence is
    # expected to scale first with distinct subfamilies, then inventory breadth.
    candidates.sort(
        key=lambda item: (
            item["subfamily_count"],
            item["row_count"],
            item["ordering_pattern_rows"],
            item["plasma_series"],
        )
    )
    for rank, item in enumerate(candidates, start=1):
        item["rank"] = rank

    return {
        "schema_version": 1,
        "transaction": "stm32-trustzone-cohort-gate1",
        "authority": "research_only",
        "source_inventory": SOURCE.name,
        "cohort": COHORT,
        "ranking_policy": {
            "eligibility": [
                "trustzone cohort classification",
                "structural gate pass",
                "complete mapping metadata",
                "exactly one target config",
                "ordering-pattern rows greater than zero",
            ],
            "complexity_key": [
                "subfamily_count ascending",
                "row_count ascending",
                "ordering_pattern_rows ascending",
                "plasma_series ascending",
            ],
            "weighted_score": False,
        },
        "candidates": candidates,
        "selected_for_next_research": candidates[0]["plasma_series"],
        "claims": {
            "production_admission": False,
            "programming_algorithm_equivalence": False,
            "flash_geometry_validated": False,
            "trustzone_security_semantics_supported": False,
            "option_byte_semantics_supported": False,
            "hil_validated": False,
            "runtime_programming_supported": False,
        },
    }


if __name__ == "__main__":
    print(json.dumps(build_qualification(), indent=2, sort_keys=True))

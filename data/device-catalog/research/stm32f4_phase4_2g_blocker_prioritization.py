#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from stm32f4_coverage_gap_inventory import build_inventory

HERE = Path(__file__).resolve().parent
DEFAULT_CATALOG = HERE / "openocd-parts-canonical.csv"
DEFAULT_CANONICAL = HERE / "stm32f4-commercial-icpn.csv"


def build_portfolio(*, catalog_path: Path, canonical_path: Path) -> dict:
    inventory = build_inventory(catalog_path=catalog_path, canonical_path=canonical_path)
    blocked = inventory["gap"]["policy_blocked"]
    by_blocker: dict[str, list[dict]] = defaultdict(list)
    for item in blocked:
        for blocker in item["policy_blockers"]:
            by_blocker[blocker].append(item)

    surfaces = []
    for blocker, items in sorted(by_blocker.items()):
        affected = sorted(item["base_device"] for item in items)
        immediately_unblocked = sorted(
            item["base_device"]
            for item in items
            if item["policy_blockers"] == [blocker]
        )
        residual = {
            item["base_device"]: [b for b in item["policy_blockers"] if b != blocker]
            for item in items
            if len(item["policy_blockers"]) > 1
        }
        surfaces.append(
            {
                "surface": blocker,
                "affected_base_device_count": len(affected),
                "affected_base_devices": affected,
                "immediately_unblocked_count": len(immediately_unblocked),
                "immediately_unblocked_if_only_surface_resolved": immediately_unblocked,
                "residual_blockers": residual,
            }
        )

    surfaces.sort(
        key=lambda x: (
            -x["immediately_unblocked_count"],
            x["affected_base_device_count"],
            x["surface"],
        )
    )
    return {
        "schema_version": 1,
        "phase": "4.2G",
        "scope": "read-only current-main STM32F4 policy-blocker prioritization",
        "current_state": {
            "production_exact_icpn_rows": inventory["production"]["exact_icpn_rows"],
            "production_base_device_count": inventory["production"]["base_device_count"],
            "openocd_ordering_pattern_base_device_count": inventory["openocd_ordering_pattern_base_device_count"],
            "gap_base_device_count": inventory["gap"]["base_device_count"],
            "policy_ready_count": inventory["gap"]["policy_ready_count"],
            "policy_blocked_count": inventory["gap"]["policy_blocked_count"],
        },
        "surfaces_ranked_by_immediate_unlock": surfaces,
        "policy_change_applied": False,
        "production_write_applied": False,
        "algorithm_equivalence_claimed": False,
        "physical_ppu_validation_claimed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--catalog", type=Path, default=DEFAULT_CATALOG)
    parser.add_argument("--canonical", type=Path, default=DEFAULT_CANONICAL)
    parser.add_argument("--inventory-output", type=Path, required=True)
    parser.add_argument("--portfolio-output", type=Path, required=True)
    args = parser.parse_args()

    inventory = build_inventory(catalog_path=args.catalog, canonical_path=args.canonical)
    portfolio = build_portfolio(catalog_path=args.catalog, canonical_path=args.canonical)
    args.inventory_output.parent.mkdir(parents=True, exist_ok=True)
    args.inventory_output.write_text(json.dumps(inventory, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    args.portfolio_output.write_text(json.dumps(portfolio, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    state = portfolio["current_state"]
    assert state == {
        "production_exact_icpn_rows": 208,
        "production_base_device_count": 70,
        "openocd_ordering_pattern_base_device_count": 149,
        "gap_base_device_count": 79,
        "policy_ready_count": 0,
        "policy_blocked_count": 79,
    }, state
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

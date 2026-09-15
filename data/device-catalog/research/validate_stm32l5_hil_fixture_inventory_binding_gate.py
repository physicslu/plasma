#!/usr/bin/env python3
from __future__ import annotations

import json

from device_catalog_admission_framework import AdmissionError
from stm32l5_hil_fixture_inventory_binding import (
    INVENTORY,
    _read_json,
    build_gate_result,
    negative_controls,
    validate_inventory,
)


def main() -> int:
    result = build_gate_result()
    if result["stm32l5_commercial_icpn_count"] != 49:
        raise SystemExit("FAIL: expected 49 retained STM32L5 commercial ICPNs")
    if result["verified_fixture_count"] != 0 or result["hil_test_cells_bound"] != 0:
        raise SystemExit("FAIL: unevidenced physical fixtures were bound")
    if result["fixture_inventory_bound"] or result["hil_execution_ready"] or result["hil_executed"]:
        raise SystemExit("FAIL: fixture binding gate made premature HIL claim")
    if result["production_manifest_admission_authorized"] or result["runtime_programming_authorized"]:
        raise SystemExit("FAIL: fixture binding gate opened unsafe capability")
    if result["exact_icpn_count"] != 1862:
        raise SystemExit("FAIL: Production exact ICPN count drifted")
    if result["blocker"] != "external_physical_asset_dependency":
        raise SystemExit("FAIL: physical asset blocker missing")

    inventory = _read_json(INVENTORY)
    rejected = 0
    controls = negative_controls(inventory)
    for name, mutated in controls:
        try:
            validate_inventory(mutated)
        except AdmissionError:
            rejected += 1
        else:
            raise SystemExit(f"FAIL: negative control admitted: {name}")
    if rejected != len(controls):
        raise SystemExit(f"FAIL: expected {len(controls)} rejected negative controls, got {rejected}")

    print(json.dumps({
        **result,
        "negative_controls_rejected": rejected,
        "validation": "PASS",
    }, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

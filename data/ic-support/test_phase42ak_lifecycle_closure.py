#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "coverage_inventory.py"
LIFECYCLE_ONLY_ICPNS = {
    "STM32F429BET6",
    "STM32F429BGT6",
    "STM32F429BIT6",
    "STM32F429BIT7",
    "STM32F439BGT6",
    "STM32F439BIT6",
    "STM32F439BIT7",
    "STM32F469BET6",
    "STM32F469BGT6",
    "STM32F469BIT6",
    "STM32F469BIT7",
    "STM32F479BGT6",
    "STM32F479BIT6",
}


def load_module():
    spec = importlib.util.spec_from_file_location("ic_support_phase42ak_coverage", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load coverage_inventory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    inventory = load_module().build_inventory()
    metrics = inventory["metrics"]
    assert metrics["exact_icpns"] == 459
    assert metrics["families"] == 2
    assert metrics["family_exact_icpns"] == {"STM32F1": 75, "STM32F4": 384}
    assert metrics["base_devices"] == 157
    assert metrics["deterministic_openocd_exact_icpns"] == 459
    assert metrics["ic_support_bound_exact_icpns"] == 2
    assert metrics["unresolved_programming_profile_exact_icpns"] == 457
    assert metrics["evidence_backed_programming_profiles"] == 1
    assert metrics["native_ppu_runtime_ready_exact_icpns"] == 0
    observed = {row["icpn"] for row in inventory["exact_icpns"]}
    assert LIFECYCLE_ONLY_ICPNS.isdisjoint(observed)
    print("Phase 4.2AK IC Support closure PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

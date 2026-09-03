#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
from pathlib import Path

HERE = Path(__file__).resolve().parent
MODULE_PATH = HERE / "coverage_inventory.py"


def load_module():
    spec = importlib.util.spec_from_file_location("ic_support_coverage", MODULE_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load coverage_inventory.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def find_exact(inventory: dict, icpn: str) -> dict:
    for row in inventory["exact_icpns"]:
        if row["icpn"] == icpn:
            return row
    raise AssertionError(f"missing exact ICPN {icpn}")


def find_base(inventory: dict, base_device: str) -> dict:
    for row in inventory["base_devices"]:
        if row["base_device"] == base_device:
            return row
    raise AssertionError(f"missing base device {base_device}")


def test_current_production_metrics() -> None:
    module = load_module()
    inventory = module.build_inventory()
    metrics = inventory["metrics"]

    assert metrics["exact_icpns"] == 301
    assert metrics["families"] == 2
    assert metrics["family_exact_icpns"] == {"STM32F1": 75, "STM32F4": 226}
    assert metrics["base_devices"] == 95
    assert metrics["deterministic_openocd_exact_icpns"] == 301
    assert metrics["ic_support_bound_exact_icpns"] == 2
    assert metrics["unresolved_programming_profile_exact_icpns"] == 299
    assert metrics["evidence_backed_programming_profiles"] == 1
    assert metrics["native_ppu_runtime_ready_exact_icpns"] == 0
    assert inventory["programming_profile_ids"] == ["stm32f1-medium-density-flash-v0"]


def test_exact_icpn_to_base_device_to_profile_projection() -> None:
    module = load_module()
    inventory = module.build_inventory()

    f407 = find_exact(inventory, "STM32F407VGT6")
    f407_tr = find_exact(inventory, "STM32F407VGT6TR")
    assert f407["base_device"] == f407_tr["base_device"] == "STM32F407VG"
    assert f407["flash_size"] == f407_tr["flash_size"] == "1024 KiB"
    assert f407["package"] == f407_tr["package"] == "LQFP"
    assert f407["pin_count"] == f407_tr["pin_count"] == 100
    assert f407["openocd"]["target_config"] == f407_tr["openocd"]["target_config"] == "tcl/target/stm32f4x.cfg"
    assert f407["programming_profile"]["state"] == "unresolved"
    assert f407_tr["programming_profile"]["state"] == "unresolved"
    assert f407["native_ppu"]["runtime_ready"] is False
    assert f407_tr["native_ppu"]["runtime_ready"] is False

    f103 = find_exact(inventory, "STM32F103C8T6")
    assert f103["base_device"] == "STM32F103C8"
    assert f103["programming_profile"] == {
        "state": "evidence_backed_pilot",
        "profile_id": "stm32f1-medium-density-flash-v0",
        "status": "pilot",
    }
    assert f103["native_ppu"] == {
        "state": "profile_available_research_only",
        "runtime_resolver": "not_implemented",
        "runtime_ready": False,
    }


def test_base_device_grouping_is_not_exact_icpn_counting() -> None:
    module = load_module()
    inventory = module.build_inventory()
    base = find_base(inventory, "STM32F407VG")
    assert base["exact_icpn_count"] == 4
    assert base["flash_size"] == "1024 KiB"
    assert base["openocd_target_config"] == "tcl/target/stm32f4x.cfg"
    assert base["programming_profile_state"] == "unresolved"
    assert base["programming_profile_id"] is None


def test_conflicting_base_device_flash_or_openocd_mapping_fails_closed() -> None:
    module = load_module()
    _manifest, rows = module.load_production_catalog()
    profiles = module.load_profiles()
    bindings = module.load_programming_bindings({row["icpn"] for row in rows}, profiles)

    members = [copy.deepcopy(row) for row in rows if row["base_device"] == "STM32F407VG"]
    assert len(members) >= 2

    mutated_flash = copy.deepcopy(members)
    mutated_flash[1]["flash_size"] = "2048 KiB"
    try:
        module.summarize_base_device("STMicroelectronics", "STM32F407VG", mutated_flash, bindings)
    except module.CoverageError as exc:
        assert "conflicting Flash sizes" in str(exc)
    else:
        raise AssertionError("conflicting Flash size must fail closed")

    mutated_target = copy.deepcopy(members)
    mutated_target[1]["openocd_target_config"] = "tcl/target/not-the-same.cfg"
    try:
        module.summarize_base_device("STMicroelectronics", "STM32F407VG", mutated_target, bindings)
    except module.CoverageError as exc:
        assert "conflicting OpenOCD targets" in str(exc)
    else:
        raise AssertionError("conflicting OpenOCD target must fail closed")


def test_conflicting_bound_programming_profiles_fail_closed() -> None:
    module = load_module()
    _manifest, rows = module.load_production_catalog()
    profiles = module.load_profiles()
    bindings = module.load_programming_bindings({row["icpn"] for row in rows}, profiles)

    members = [copy.deepcopy(row) for row in rows if row["base_device"] == "STM32F103C8"]
    synthetic_bindings = copy.deepcopy(bindings)
    synthetic_bindings["STM32F103C8T6TR"] = {
        "binding_set_id": "synthetic-negative-test",
        "programming_profile_id": "different-profile",
        "programming_profile_status": "pilot",
    }
    try:
        module.summarize_base_device("STMicroelectronics", "STM32F103C8", members, synthetic_bindings)
    except module.CoverageError as exc:
        assert "disagree on programming profile" in str(exc)
    else:
        raise AssertionError("conflicting programming profiles must fail closed")


def main() -> int:
    test_current_production_metrics()
    test_exact_icpn_to_base_device_to_profile_projection()
    test_base_device_grouping_is_not_exact_icpn_counting()
    test_conflicting_base_device_flash_or_openocd_mapping_fails_closed()
    test_conflicting_bound_programming_profiles_fail_closed()
    print("IC Support coverage inventory tests PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

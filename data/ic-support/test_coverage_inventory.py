#!/usr/bin/env python3
from __future__ import annotations

import copy
import importlib.util
from collections import Counter
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
    manifest, rows = module.load_production_catalog()
    inventory = module.build_inventory()
    metrics = inventory["metrics"]

    expected_family_counts = dict(sorted(Counter(row["family"] for row in rows).items()))
    expected_base_devices = {
        (row["manufacturer"], row["base_device"])
        for row in rows
    }
    expected_exact_icpns = len(rows)

    assert manifest["status"] == "production"
    assert expected_exact_icpns == sum(source["row_count"] for source in manifest["sources"])
    assert metrics["exact_icpns"] == expected_exact_icpns
    assert metrics["families"] == len(expected_family_counts)
    assert metrics["family_exact_icpns"] == expected_family_counts
    assert metrics["base_devices"] == len(expected_base_devices)
    assert metrics["deterministic_openocd_exact_icpns"] == 4176
    assert metrics["openocd_unmapped_exact_icpns"] == 677
    assert (
        metrics["deterministic_openocd_exact_icpns"]
        + metrics["openocd_unmapped_exact_icpns"]
        == expected_exact_icpns
    )
    # Twelve manufacturer-reviewed KL25 exact SKUs enter Catalog Layer 1
    # with a deterministic OpenOCD mapping, but no programming profile, HIL,
    # software executor admission, or manufacturer enrichment M1 grant.
    kl25 = [row for row in inventory["exact_icpns"]
            if row["manufacturer"] == "NXP" and row["family"] == "KL25"]
    assert len(kl25) == 12
    new_nxp = [row for row in inventory["exact_icpns"] if
               row["manufacturer"] == "NXP" and
               row["family"] in {"MCX","K32L2"}]
    assert len(new_nxp)==212
    assert Counter(row["family"] for row in new_nxp)=={"MCX":196,"K32L2":16}
    assert all(row["openocd"]["mapping_status"]=="no_mapping" and
               row["programming_profile"]["state"]=="unresolved" and
               row["native_ppu"]["runtime_ready"] is False and
               row["manufacturer_enrichment"]["highest_level"]=="M0"
               for row in new_nxp)
    assert sum(row["manufacturer"] == "STMicroelectronics"
               for row in inventory["exact_icpns"]) == 4629
    assert all(row["programming_profile"]["state"] == "unresolved"
               and row["native_ppu"]["runtime_ready"] is False
               and row["manufacturer_enrichment"]["highest_level"] == "M0"
               for row in kl25)
    assert metrics["ic_support_bound_exact_icpns"] == 2
    assert metrics["unresolved_programming_profile_exact_icpns"] == (
        expected_exact_icpns - metrics["ic_support_bound_exact_icpns"]
    )
    assert metrics["evidence_backed_programming_profiles"] == 1
    assert metrics["native_ppu_runtime_ready_exact_icpns"] == 0
    assert metrics["manufacturer_enrichment_m1_or_higher_exact_icpns"] == 1185
    assert metrics["manufacturer_enrichment_m4_or_higher_exact_icpns"] == 1
    assert metrics["manufacturer_enrichment_m5_exact_icpns"] == 0
    assert inventory["programming_profile_ids"] == ["stm32f1-medium-density-flash-v0"]

    enrichment = inventory["manufacturer_enrichment"]
    assert enrichment["highest_level_counts"] == {
        "M0": expected_exact_icpns - 1185,
        "M1": 1184,
        "M2": 0,
        "M3": 0,
        "M4": 1,
        "M5": 0,
    }
    assert enrichment["at_least_level_counts"] == {
        "M0": expected_exact_icpns,
        "M1": 1185,
        "M2": 1,
        "M3": 1,
        "M4": 1,
        "M5": 0,
    }
    assert enrichment["by_family_highest_level"]["STM32F1"]["M4"] == 1
    assert enrichment["by_family_highest_level"]["STM32F1"]["M1"] == 279
    assert enrichment["by_family_highest_level"]["STM32F1"]["M0"] == 0
    assert enrichment["by_family_highest_level"]["STM32C0"]["M1"] == 226
    assert enrichment["by_family_highest_level"]["STM32C0"]["M0"] == 0
    assert enrichment["by_family_highest_level"]["STM32G0"]["M1"] == 406
    assert enrichment["by_family_highest_level"]["STM32G0"]["M0"] == 0
    assert enrichment["by_family_highest_level"]["STM32G4"]["M1"] == 273
    assert enrichment["by_family_highest_level"]["STM32G4"]["M0"] == 0


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

    f103_new = find_exact(inventory, "STM32F103R8T6")
    assert f103_new["base_device"] == "STM32F103R8"
    assert f103_new["openocd"]["target_config"] == "tcl/target/stm32f1x.cfg"
    assert f103_new["programming_profile"] == {
        "state": "unresolved",
        "profile_id": None,
        "status": None,
    }
    assert f103_new["native_ppu"]["runtime_ready"] is False

    f100_new = find_exact(inventory, "STM32F100C4T6B")
    assert f100_new["base_device"] == "STM32F100C4"
    assert f100_new["programming_profile"]["state"] == "unresolved"
    assert f100_new["openocd"]["target_config"] == "tcl/target/stm32f1x.cfg"


def test_manufacturer_enrichment_golden_reference_and_missing_layers() -> None:
    module = load_module()
    inventory = module.build_inventory()

    c8 = find_exact(inventory, "STM32F103C8T6")
    enrichment = c8["manufacturer_enrichment"]
    assert enrichment["highest_level"] == "M4"
    assert enrichment["dimensions"] == {
        "catalog_identity": True,
        "manufacturer_device_basic_profile": True,
        "ram": True,
        "operating_vdd": True,
        "io_supply": False,
        "vdda": False,
        "operating_temperature": True,
        "manufacturer_device_profile": True,
        "operating_electrical": True,
        "memory_map": True,
        "manufacturer_programming_profile": True,
        "programming_electrical": True,
        "programming_interfaces": True,
        "flash_geometry": True,
        "execution_ir": True,
        "generated_programmer": True,
        "independent_software_differential": True,
        "physical_hil": False,
    }
    assert enrichment["missing_dimensions"] == ["io_supply", "vdda", "physical_hil"]
    assert enrichment["evidence"]["manufacturer_baseline"].endswith(
        "stm32f103c8t6-manufacturer-only-v1.json"
    )
    assert enrichment["evidence"]["openocd_comparison"].endswith(
        "stm32f103c8t6-openocd-v0.12.0-v1.json"
    )
    assert enrichment["evidence"]["physical_hil"] is None

    same_family_basic = find_exact(inventory, "STM32F103R8T6")
    basic = same_family_basic["manufacturer_enrichment"]
    assert basic["highest_level"] == "M1"
    assert basic["dimensions"]["catalog_identity"] is True
    assert basic["dimensions"]["manufacturer_device_basic_profile"] is True
    assert basic["dimensions"]["ram"] is True
    assert basic["dimensions"]["operating_vdd"] is True
    assert basic["dimensions"]["io_supply"] is False
    assert basic["dimensions"]["vdda"] is False
    assert basic["dimensions"]["operating_temperature"] is True
    assert basic["dimensions"]["manufacturer_device_profile"] is False
    assert basic["dimensions"]["memory_map"] is False
    assert basic["dimensions"]["manufacturer_programming_profile"] is False
    assert basic["dimensions"]["execution_ir"] is False
    assert basic["dimensions"]["physical_hil"] is False

    c0 = find_exact(inventory, "STM32C011F4P6")
    c0_basic = c0["manufacturer_enrichment"]
    assert c0_basic["highest_level"] == "M1"
    assert c0_basic["dimensions"]["manufacturer_device_basic_profile"] is True
    assert c0_basic["dimensions"]["ram"] is True
    assert c0_basic["dimensions"]["operating_vdd"] is True
    assert c0_basic["dimensions"]["io_supply"] is False
    assert c0_basic["dimensions"]["vdda"] is False
    assert c0_basic["evidence"]["device_basic_profile"].endswith(
        "stm32c0-device-basic-v1.json"
    )

    g0 = find_exact(inventory, "STM32G031K8T3")
    g0_basic = g0["manufacturer_enrichment"]
    assert g0_basic["highest_level"] == "M1"
    assert g0_basic["dimensions"]["manufacturer_device_basic_profile"] is True
    assert g0_basic["dimensions"]["ram"] is True
    assert g0_basic["dimensions"]["operating_vdd"] is True
    assert g0_basic["dimensions"]["io_supply"] is False
    assert g0_basic["dimensions"]["vdda"] is False
    assert g0_basic["evidence"]["device_basic_profile"].endswith(
        "stm32g0-device-basic-v1.json"
    )

    g4 = find_exact(inventory, "STM32G474VCH3TR")
    g4_basic = g4["manufacturer_enrichment"]
    assert g4_basic["highest_level"] == "M1"
    assert g4_basic["dimensions"]["manufacturer_device_basic_profile"] is True
    assert g4_basic["dimensions"]["ram"] is True
    assert g4_basic["dimensions"]["operating_vdd"] is True
    assert g4_basic["dimensions"]["io_supply"] is False
    assert g4_basic["dimensions"]["vdda"] is True
    assert "vdda" not in g4_basic["missing_dimensions"]
    assert "io_supply" in g4_basic["missing_dimensions"]
    assert g4_basic["evidence"]["device_basic_profile"].endswith(
        "stm32g4-device-basic-v1.json"
    )

    outside_family = find_exact(inventory, "STM32F407VGT6")
    missing = outside_family["manufacturer_enrichment"]
    assert missing["highest_level"] == "M0"
    assert missing["dimensions"]["manufacturer_device_basic_profile"] is False
    assert "ram" in missing["missing_dimensions"]
    assert "operating_vdd" in missing["missing_dimensions"]


def test_manufacturer_enrichment_registry_is_research_only() -> None:
    module = load_module()
    _manifest, rows = module.load_production_catalog()
    evidence = module.load_manufacturer_enrichment_evidence({row["icpn"] for row in rows})
    assert set(evidence) == {"STM32F103C8T6"}
    assert evidence["STM32F103C8T6"]["highest_level"] == "M4"
    assert evidence["STM32F103C8T6"]["dimensions"]["physical_hil"] is False


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



def test_stm32h5_package_dependent_pin_count_resolution() -> None:
    module = load_module()
    assert module.parse_pin_count("64/68", "LQFP") == 64
    assert module.parse_pin_count("64/68", "VFQFPN") == 68
    assert module.parse_pin_count("176/176+25", "LQFP") == 176
    assert module.parse_pin_count("176/176+25", "UFBGA 10x10 0.65") == 201
    assert module.parse_pin_count("100/105", "LQFP") == 100
    assert module.parse_pin_count("144/144", "UFBGA 10x10 0.80") == 144
    assert module.parse_pin_count("240+25", "TFBGA") == 265

    try:
        module.parse_pin_count("64/68", "UFBGA")
    except module.CoverageError as exc:
        assert "cannot resolve pin_count" in str(exc)
    else:
        raise AssertionError("unknown package-dependent pin count must fail closed")


def main() -> int:
    test_current_production_metrics()
    test_stm32h5_package_dependent_pin_count_resolution()
    test_exact_icpn_to_base_device_to_profile_projection()
    test_manufacturer_enrichment_golden_reference_and_missing_layers()
    test_manufacturer_enrichment_registry_is_research_only()
    test_base_device_grouping_is_not_exact_icpn_counting()
    test_conflicting_base_device_flash_or_openocd_mapping_fails_closed()
    test_conflicting_bound_programming_profiles_fail_closed()
    print("IC Support coverage inventory tests PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

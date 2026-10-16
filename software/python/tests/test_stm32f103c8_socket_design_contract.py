from __future__ import annotations

import json
from pathlib import Path

from plasma_core.ic_support import ICSupportResolver


REPO_ROOT = Path(__file__).resolve().parents[3]
IC_SUPPORT_ROOT = REPO_ROOT / "data" / "ic-support"
CONTRACT = IC_SUPPORT_ROOT / "socket-design" / "stm32f103c8t6-lqfp48-swd-v1.json"


def test_stm32f103c8_socket_contract_matches_resolved_ic_support() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    resolver = ICSupportResolver.from_root(IC_SUPPORT_ROOT)
    resolved = resolver.require_exact("STM32F103C8T6")

    assert contract["target"] == {
        "manufacturer": "STMicroelectronics",
        "icpn": "STM32F103C8T6",
        "base_device": "STM32F103C8",
        "package": "LQFP48",
        "pin_count": 48,
        "catalog_level": 2,
    }

    refs = contract["canonical_profiles"]
    assert refs["programming"] == resolved.programming_profile.profile_id
    assert refs["memory_geometry"] == resolved.memory_geometry_profile.profile_id
    assert resolved.socket_programming_hardware_profile is not None
    assert refs["package_hardware"] == resolved.socket_programming_hardware_profile.profile_id
    assert refs["option"] == resolved.profile("option").profile_id
    assert refs["security"] == resolved.profile("security").profile_id

    assert resolved.socket_programming_hardware_profile is not None
    hardware = resolved.socket_programming_hardware_profile.data
    mandatory_from_profile = [
        {"pin": item["package_pin"], "signal": item["signal"]}
        for item in hardware["minimum_swd_programming_contacts"]
    ]
    assert contract["socket_interface"]["mandatory_contacts"] == mandatory_from_profile

    geometry = resolved.memory_geometry_profile.data
    software = contract["software_design_input"]
    assert software["flash_start"] == geometry["main_flash_start"]
    assert software["flash_size_bytes"] == geometry["main_flash_size_bytes"]
    assert software["page_size_bytes"] == geometry["page_size_bytes"]
    assert software["page_count"] == geometry["page_count"]
    assert software["program_unit_bytes"] == geometry["program_granularity_bytes"]

    route = contract["provider_route"]
    assert route["target_config"] == resolved.openocd_target_config
    assert route["operations"] == ["probe", "erase", "program", "read", "verify"]

    boundary = contract["qualification_boundary"]
    assert boundary["sufficient_for_socket_schematic_and_layout_design"] is True
    assert boundary["sufficient_for_openocd_programmer_software_development"] is True
    assert boundary["sufficient_for_native_swd_transport_implementation"] is False
    assert boundary["hardware_runtime_ready"] is False
    assert boundary["physical_programming_qualified"] is False
    assert boundary["hil_verified"] is False
    assert boundary["execution_authorized"] is False


def test_stm32f103c8_socket_contract_keeps_boot0_out_of_minimum_swd_set() -> None:
    contract = json.loads(CONTRACT.read_text(encoding="utf-8"))
    mandatory = {
        (entry["pin"], entry["signal"])
        for entry in contract["socket_interface"]["mandatory_contacts"]
    }
    optional = {
        (entry["pin"], entry["signal"])
        for entry in contract["socket_interface"]["recommended_optional_contacts"]
    }

    assert (44, "BOOT0") not in mandatory
    assert (44, "BOOT0") in optional
    assert (1, "VBAT") not in mandatory
    assert (1, "VBAT") in optional

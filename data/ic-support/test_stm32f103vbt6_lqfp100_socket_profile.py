#!/usr/bin/env python3
"""Exact STM32F103VBT6 Socket contract: shared LQFP100 pins, independent 128-KiB Flash."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import test_stm32f103v8t6_lqfp100_socket_profile as original

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HARDWARE = HERE / "profiles/package-hardware/stm32f103-lqfp100-programming-hardware-v1.json"
NEW_SOCKET = HERE / "socket-profiles/stm32f103vbt6-lqfp100-swd-v1.json"
V8_SOCKET = HERE / "socket-profiles/stm32f103v8t6-lqfp100-swd-v1.json"
QUALIFICATION = REPO / "release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json"
APPLICABILITY = REPO / "release/openocd-qualification/stm32f103-medium-density-lqfp-t6-t7-applicability-v2.json"
VB_GEOMETRY = HERE / "profiles/memory-geometry/stm32f103vb-128k-v0.json"
V8_GEOMETRY = HERE / "profiles/memory-geometry/stm32f103v8-64k-v0.json"

REQUIRED = original.REQUIRED
OPTIONAL = original.OPTIONAL


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify(hw: dict, sock: dict, qual: dict, applicability: dict, vb: dict, v8: dict) -> None:
    assert hw["profile_id"] == "stm32f103-lqfp100-programming-hardware-v1"
    assert hw["kind"] == "package_hardware" and hw["status"] == "pilot_reviewed"
    assert hw["scope"]["manufacturer"] == "STMicroelectronics"
    assert hw["scope"]["series"] == "STM32F103"
    assert hw["scope"]["package"] == "LQFP"
    assert hw["scope"]["pin_count"] == 100
    assert hw["scope"]["applicable_base_devices"] == ["STM32F103V8", "STM32F103VB"]
    assert set(hw["scope"]["applicability_basis"]) == {"STM32F103V8", "STM32F103VB"}
    assert all("DS5319 Rev 20" in evidence and "Figure 4" in evidence
               for evidence in hw["scope"]["applicability_basis"].values())
    assert {e["source_id"] for e in hw["evidence"]} == {"st_ds5319_rev20"}
    d = hw["data"]
    assert d["package"] == "LQFP" and d["pin_count"] == 100
    assert len(original.PIN_NAMES) == 100
    assert d["physical_pin_map"] == [
        {"pin": i, "name": name} for i, name in enumerate(original.PIN_NAMES, 1)
    ]
    assert d["mechanical"]["body_mm"] == {"x": 14, "y": 14}
    assert d["mechanical"]["lead_span_mm"] == {"x": 16, "y": 16}
    assert d["mechanical"]["pitch_mm"] == 0.5
    assert d["mechanical"]["pin1_identifier_required_for_fixture_orientation"] is True
    assert d["programming_route"]["primary_interface"] == "SWD"
    for name, pin in (("SWDIO", 72), ("SWCLK", 76), ("NRST", 14), ("BOOT0", 94)):
        assert d["programming_route"]["signals"][name]["pin"] == pin
    assert d["programming_route"]["signals"]["SWDIO"]["gpio"] == "PA13"
    assert d["programming_route"]["signals"]["SWCLK"]["gpio"] == "PA14"
    assert {x["purpose"]: x["pin"] for x in d["socket_contacts"]["mandatory"]} == REQUIRED
    assert {x["purpose"]: x["pin"] for x in d["socket_contacts"]["optional"]} == OPTIONAL
    assert d["socket_contacts"]["not_connected"] == [
        {"purpose": "NC", "pin": 73, "policy": "do_not_connect"}
    ]

    power = d["power"]
    assert power["programming_vdd_v"] == {"min": 2, "max": 3.6}
    assert power["external_vpp_required"] is False
    assert power["all_main_power_and_ground_pins_must_be_connected"] is True
    assert {x["name"]: x["pin"] for x in power["mandatory_positive_contacts"]} == {
        name: pin for name, pin in REQUIRED.items() if name.startswith("VDD") or name == "VDDA"
    }
    assert {x["name"]: x["pin"] for x in power["mandatory_ground_contacts"]} == {
        name: pin for name, pin in REQUIRED.items() if name.startswith("VSS") or name == "VSSA"
    }
    analog = power["analog_reference"]
    assert "Figures 39-40" in analog["manufacturer_reference"]
    assert "figure_40" in analog["fixture_provisioning_policy"]
    assert {x["name"]: (x["pin"], x["tie_to"], x["mandatory_for_this_fixture_profile"])
            for x in analog["contacts"]} == {
        "VREF+": (21, "VDDA", True), "VREF-": (20, "VSSA", True)
    }
    assert power["vbat"]["pin"] == 6
    assert "VBAT" in power["vbat"]["socket_policy"]
    for key in ("physical_socket_qualified", "hardware_runtime_ready", "execution_authorized"):
        assert d["hardware_readiness_boundary"][key] is False

    assert sock["socket_profile_id"] == "stm32f103vbt6-lqfp100-swd-socket-v1"
    assert sock["schema_version"] == "1.0.0" and sock["status"] == "design_input_ready"
    assert sock["target"] == {
        "manufacturer": "STMicroelectronics",
        "icpn": "STM32F103VBT6",
        "base_device": "STM32F103VB",
        "package": "LQFP100",
    }
    assert {e["source_id"] for e in sock["evidence"]} == {"st_ds5319_rev20"}
    assert sock["programming_hardware_profile_id"] == hw["profile_id"]
    route = sock["route"]
    assert route["provider_qualification_level"] == "L2"
    assert route["interface"] == "SWD"
    assert route["target_config"] == "tcl/target/stm32f1x.cfg"
    assert len(route["required_contacts"]) == 17
    assert set(route["required_contacts"]) == set(REQUIRED)
    assert len(route["optional_contacts"]) == 2
    assert set(route["optional_contacts"]) == set(OPTIONAL)
    fixture = sock["fixture_contract"]
    assert fixture["orientation"]["pin1_must_be_keyed"] is True
    assert fixture["power"]["all_main_supply_and_ground_contacts_required"] is True
    assert fixture["power"]["vbat_bias_documented_before_fixture_release"] is True
    assert fixture["power"]["vref_plus_minus_must_follow_manufacturer_decoupling"] is True
    assert fixture["no_connect_pins"] == [73]
    assert fixture["reset"]["connect_under_reset_capable"] is True
    assert sock["readiness"]["sufficient_for_socket_schematic_and_pin_assignment_development"] is True
    for key in ("sufficient_for_socket_vendor_selection", "sufficient_for_production_release",
                "physical_programming_qualified", "hil_verified", "execution_authorized"):
        assert sock["readiness"][key] is False

    binding = sock["qualification_binding"]
    assert binding == {
        "software_registry": "release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json",
        "software_state": "SUPPORTED",
        "programming_profile_id": "stm32f1-medium-density-flash-v0",
        "memory_geometry_profile_id": "stm32f103vb-128k-v0",
        "main_flash_size_bytes": 131072,
        "erase_page_count": 128,
        "identity_applicability": "release/openocd-qualification/stm32f103-medium-density-lqfp-t6-t7-applicability-v2.json",
        "hardware_profile_applicable_base_device": "STM32F103VB",
    }
    records = [r for r in qual["records"] if r["icpn"] == sock["target"]["icpn"]]
    assert len(records) == 1
    record = records[0]
    assert record["manufacturer"] == sock["target"]["manufacturer"]
    assert record["base_device"] == sock["target"]["base_device"]
    assert record["software_state"] == binding["software_state"]
    assert record["programming_profile_id"] == binding["programming_profile_id"]
    assert record["memory_geometry_profile_id"] == binding["memory_geometry_profile_id"]
    assert record["main_flash_size_bytes"] == binding["main_flash_size_bytes"]
    assert record["page_count"] == binding["erase_page_count"]
    assert set(record["operations"]) == {"probe", "erase", "program", "read", "verify"}
    targets = [r for r in applicability["targets"] if r["icpn"] == sock["target"]["icpn"]]
    assert len(targets) == 1
    target = targets[0]
    assert target["base_device"] == record["base_device"]
    assert target["package"] == "LQFP" and target["pin_count"] == "100"
    assert target["memory_geometry_profile_id"] == binding["memory_geometry_profile_id"]
    assert target["main_flash_size_bytes"] == binding["main_flash_size_bytes"]
    assert target["page_count"] == binding["erase_page_count"]
    assert target["target_config"] == route["target_config"]
    assert vb["profile_id"] == "stm32f103vb-128k-v0"
    assert vb["scope"]["base_device"] == "STM32F103VB"
    assert vb["data"]["main_flash_size_bytes"] == binding["main_flash_size_bytes"]
    assert vb["data"]["page_count"] == binding["erase_page_count"]
    assert vb["data"]["page_size_bytes"] == 1024
    assert vb["data"]["program_granularity_bytes"] == 2
    assert vb["data"]["main_flash_end"] == "0x0801FFFF"
    assert v8["profile_id"] == "stm32f103v8-64k-v0"
    assert v8["scope"]["base_device"] == "STM32F103V8"
    assert v8["data"]["main_flash_size_bytes"] == 65536
    assert v8["data"]["page_count"] == 64
    assert vb["profile_id"] != v8["profile_id"]


def reject(hw: dict, sock: dict, qual: dict, app: dict, vb: dict, v8: dict) -> None:
    try:
        verify(hw, sock, qual, app, vb, v8)
    except (AssertionError, KeyError):
        return
    raise AssertionError("unsafe VBT6 LQFP100 mutation admitted")


def main() -> int:
    hw, sock, qual, app, vb, v8 = (load(p) for p in (
        HARDWARE, NEW_SOCKET, QUALIFICATION, APPLICABILITY, VB_GEOMETRY, V8_GEOMETRY
    ))
    # A new exact VB variant must not invalidate the previously approved V8 variant.
    original.verify(hw, load(V8_SOCKET), qual)
    verify(hw, sock, qual, app, vb, v8)
    negatives = 0

    for key, value in (
        ("icpn", "STM32F103V8T6"),
        ("icpn", "STM32F103VBT6TR"),
        ("icpn", "STM32F103VBT7"),
        ("icpn", "STM32F103RBT6"),
        ("base_device", "STM32F103V8"),
        ("package", "LQFP64"),
    ):
        bad = deepcopy(sock)
        bad["target"][key] = value
        reject(hw, bad, qual, app, vb, v8)
        negatives += 1

    for key, value in (
        ("memory_geometry_profile_id", "stm32f103v8-64k-v0"),
        ("main_flash_size_bytes", 65536),
        ("erase_page_count", 64),
        ("hardware_profile_applicable_base_device", "STM32F103V8"),
    ):
        bad = deepcopy(sock)
        bad["qualification_binding"][key] = value
        reject(hw, bad, qual, app, vb, v8)
        negatives += 1

    for contact in ("SWDIO", "VDD_5", "VSS_5", "VREF+", "VREF-", "NRST"):
        bad = deepcopy(sock)
        bad["route"]["required_contacts"].remove(contact)
        reject(hw, bad, qual, app, vb, v8)
        negatives += 1

    for modify in (
        lambda s: s["fixture_contract"]["no_connect_pins"].clear(),
        lambda s: s["fixture_contract"]["power"].update(vref_plus_minus_must_follow_manufacturer_decoupling=False),
        lambda s: s["fixture_contract"]["power"].update(vbat_bias_documented_before_fixture_release=False),
        lambda s: s["readiness"].update(hil_verified=True),
        lambda s: s["readiness"].update(execution_authorized=True),
        lambda s: s["readiness"].update(physical_programming_qualified=True),
    ):
        bad = deepcopy(sock)
        modify(bad)
        reject(hw, bad, qual, app, vb, v8)
        negatives += 1

    for modify in (
        lambda h: h["scope"]["applicable_base_devices"].append("STM32F103VC"),
        lambda h: h["data"]["physical_pin_map"][71].update(name="PA14"),
        lambda h: h["data"]["socket_contacts"]["not_connected"].clear(),
        lambda h: h["data"]["power"]["analog_reference"]["contacts"][0].update(tie_to="VSS"),
    ):
        bad = deepcopy(hw)
        modify(bad)
        reject(bad, sock, qual, app, vb, v8)
        negatives += 1

    bad = deepcopy(vb)
    bad["data"]["page_size_bytes"] = 2048
    reject(hw, sock, qual, app, bad, v8)
    negatives += 1
    assert negatives == 27
    print(f"STM32F103VBT6 LQFP100 Socket PASS ({negatives} negative cases; V8 retained)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Manufacturer-backed LQFP64-only socket contract; Host-only, fail-closed."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
HARDWARE = ROOT / "profiles/package-hardware/stm32f103-lqfp64-programming-hardware-v1.json"
SOCKET = ROOT / "socket-profiles/stm32f103r8t6-lqfp64-swd-v1.json"
QUALIFICATION = REPO / "release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json"

# ST DS5319 Rev 20, Figure 6 and Table 5. Do NOT generate by shifting LQFP48 pins.
PIN_NAMES = (
    "VBAT", "PC13-TAMPER-RTC", "PC14-OSC32_IN", "PC15-OSC32_OUT", "PD0-OSC_IN", "PD1-OSC_OUT",
    "NRST", "PC0", "PC1", "PC2", "PC3", "VSSA", "VDDA", "PA0-WKUP", "PA1", "PA2",
    "PA3", "VSS_4", "VDD_4", "PA4", "PA5", "PA6", "PA7", "PC4", "PC5", "PB0", "PB1",
    "PB2", "PB10", "PB11", "VSS_1", "VDD_1", "PB12", "PB13", "PB14", "PB15",
    "PC6", "PC7", "PC8", "PC9", "PA8", "PA9", "PA10", "PA11", "PA12", "PA13",
    "VSS_2", "VDD_2", "PA14", "PA15", "PC10", "PC11", "PC12", "PD2", "PB3", "PB4",
    "PB5", "PB6", "PB7", "BOOT0", "PB8", "PB9", "VSS_3", "VDD_3"
)
REQUIRED = {
    "SWDIO": 46, "SWCLK": 49, "NRST": 7,
    "VDD_1": 32, "VDD_2": 48, "VDD_3": 64, "VDD_4": 19,
    "VSS_1": 31, "VSS_2": 47, "VSS_3": 63, "VSS_4": 18,
    "VDDA": 13, "VSSA": 12,
}
OPTIONAL = {"BOOT0": 60, "VBAT": 1}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify(hw: dict, socket: dict, qualification: dict) -> None:
    assert len(PIN_NAMES) == 64
    assert hw["profile_id"] == "stm32f103-lqfp64-programming-hardware-v1"
    assert hw["kind"] == "package_hardware" and hw["status"] == "pilot_reviewed"
    assert hw["scope"]["applicable_base_devices"] == ["STM32F103R8"]
    assert hw["scope"]["pin_count"] == 64
    assert {e["source_id"] for e in hw["evidence"]} == {"st_ds5319_rev20"}
    data = hw["data"]
    assert data["package"] == "LQFP" and data["pin_count"] == 64
    rows = data["physical_pin_map"]
    assert len(rows) == 64
    assert rows == [{"pin": i, "name": name} for i, name in enumerate(PIN_NAMES, 1)]
    route = data["programming_route"]
    assert route["primary_interface"] == "SWD"
    assert {s: route["signals"][s]["pin"] for s in ("SWDIO", "SWCLK", "NRST")} == {
        s: REQUIRED[s] for s in ("SWDIO", "SWCLK", "NRST")
    }
    assert route["signals"]["SWDIO"]["gpio"] == "PA13"
    assert route["signals"]["SWCLK"]["gpio"] == "PA14"
    assert route["signals"]["BOOT0"]["pin"] == OPTIONAL["BOOT0"]
    assert data["mechanical"]["body_mm"] == {"x": 10, "y": 10}
    assert data["mechanical"]["lead_span_mm"] == {"x": 12, "y": 12}
    assert data["mechanical"]["pitch_mm"] == 0.5
    assert data["mechanical"]["max_height_mm"] == 1.6
    assert data["mechanical"]["pin1_identifier_required_for_fixture_orientation"] is True
    power = data["power"]
    assert power["programming_vdd_v"] == {"min": 2, "max": 3.6}
    assert power["external_vpp_required"] is False
    assert power["all_main_power_and_ground_pins_must_be_connected"] is True
    assert {x["name"]: x["pin"] for x in power["mandatory_positive_contacts"]} == {
        k: v for k, v in REQUIRED.items() if k.startswith("VDD") or k == "VDDA"
    }
    assert {x["name"]: x["pin"] for x in power["mandatory_ground_contacts"]} == {
        k: v for k, v in REQUIRED.items() if k.startswith("VSS") or k == "VSSA"
    }
    assert {x["purpose"]: x["pin"] for x in data["socket_contacts"]["mandatory"]} == REQUIRED
    assert {x["purpose"]: x["pin"] for x in data["socket_contacts"]["optional"]} == OPTIONAL
    assert "VBAT" in power["vbat"]["socket_policy"]

    assert socket["socket_profile_id"] == "stm32f103r8t6-lqfp64-swd-socket-v1"
    assert socket["status"] == "design_input_ready"
    assert socket["target"] == {
        "manufacturer": "STMicroelectronics", "icpn": "STM32F103R8T6",
        "base_device": "STM32F103R8", "package": "LQFP64",
    }
    assert socket["programming_hardware_profile_id"] == hw["profile_id"]
    assert socket["route"]["interface"] == "SWD"
    assert socket["route"]["provider_qualification_level"] == "L2"
    assert socket["route"]["target_config"] == "tcl/target/stm32f1x.cfg"
    assert set(socket["route"]["required_contacts"]) == set(REQUIRED)
    assert len(socket["route"]["required_contacts"]) == len(REQUIRED)
    assert set(socket["route"]["optional_contacts"]) == set(OPTIONAL)
    assert socket["fixture_contract"]["power"]["all_main_supply_and_ground_contacts_required"] is True
    assert socket["fixture_contract"]["power"]["vbat_bias_documented_before_fixture_release"] is True
    assert socket["fixture_contract"]["orientation"]["pin1_must_be_keyed"] is True
    for key in ("physical_socket_qualified", "hardware_runtime_ready", "execution_authorized"):
        assert data["hardware_readiness_boundary"][key] is False
    for key in ("sufficient_for_socket_vendor_selection", "sufficient_for_production_release",
                "physical_programming_qualified", "hil_verified", "execution_authorized"):
        assert socket["readiness"][key] is False
    records = [x for x in qualification["records"] if x["icpn"] == "STM32F103R8T6"]
    assert len(records) == 1
    r = records[0]
    assert r["software_state"] == "SUPPORTED"
    assert r["base_device"] == "STM32F103R8"
    assert r["programming_profile_id"] == "stm32f1-medium-density-flash-v0"
    assert r["memory_geometry_profile_id"] == "stm32f103r8-64k-v0"
    assert r["main_flash_size_bytes"] == 65536


def must_reject(bad_hw: dict, bad_socket: dict, qualification: dict) -> None:
    try:
        verify(bad_hw, bad_socket, qualification)
    except (AssertionError, KeyError):
        return
    raise AssertionError("unsafe fixture mutation accepted")


def main() -> int:
    hw, socket, qualification = load(HARDWARE), load(SOCKET), load(QUALIFICATION)
    verify(hw, socket, qualification)
    bad_hw = deepcopy(hw)
    bad_hw["data"]["physical_pin_map"][45]["name"] = "PA14"
    must_reject(bad_hw, socket, qualification)
    bad_hw = deepcopy(hw)
    bad_hw["data"]["socket_contacts"]["mandatory"].pop()
    must_reject(bad_hw, socket, qualification)
    bad_hw = deepcopy(hw)
    bad_hw["scope"]["applicable_base_devices"].append("STM32F103RB")
    must_reject(bad_hw, socket, qualification)
    bad_socket = deepcopy(socket)
    bad_socket["route"]["required_contacts"].remove("VDD_4")
    must_reject(hw, bad_socket, qualification)
    bad_socket = deepcopy(socket)
    bad_socket["target"]["icpn"] = "STM32F103RBT6"
    must_reject(hw, bad_socket, qualification)
    bad_socket = deepcopy(socket)
    bad_socket["readiness"]["hil_verified"] = True
    must_reject(hw, bad_socket, qualification)
    print("STM32F103R8T6 LQFP64 socket contract PASS (including 6 fail-closed cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

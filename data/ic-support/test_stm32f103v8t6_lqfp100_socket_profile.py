#!/usr/bin/env python3
"""Exact STM32F103V8T6/LQFP100 manufacturer-backed Socket input; Host-only."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
REPO = ROOT.parents[1]
HW_PATH = ROOT / "profiles/package-hardware/stm32f103-lqfp100-programming-hardware-v1.json"
SOCKET_PATH = ROOT / "socket-profiles/stm32f103v8t6-lqfp100-swd-v1.json"
L2_PATH = REPO / "release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json"

# Independently transcribed from official ST DS5319 Rev 20, Figure 4 and Table 5.
# Do not calculate LQFP100 pin locations from either LQFP48 or LQFP64.
PIN_NAMES = (
    "PE2","PE3","PE4","PE5","PE6","VBAT","PC13-TAMPER-RTC","PC14-OSC32_IN",
    "PC15-OSC32_OUT","VSS_5","VDD_5","OSC_IN","OSC_OUT","NRST","PC0","PC1","PC2",
    "PC3","VSSA","VREF-","VREF+","VDDA","PA0-WKUP","PA1","PA2","PA3","VSS_4",
    "VDD_4","PA4","PA5","PA6","PA7","PC4","PC5","PB0","PB1","PB2","PE7","PE8",
    "PE9","PE10","PE11","PE12","PE13","PE14","PE15","PB10","PB11","VSS_1",
    "VDD_1","PB12","PB13","PB14","PB15","PD8","PD9","PD10","PD11","PD12","PD13",
    "PD14","PD15","PC6","PC7","PC8","PC9","PA8","PA9","PA10","PA11","PA12",
    "PA13","NC","VSS_2","VDD_2","PA14","PA15","PC10","PC11","PC12","PD0",
    "PD1","PD2","PD3","PD4","PD5","PD6","PD7","PB3","PB4","PB5","PB6",
    "PB7","BOOT0","PB8","PB9","PE0","PE1","VSS_3","VDD_3",
)
REQUIRED = {
    "SWDIO":72,"SWCLK":76,"NRST":14,
    "VDD_1":50,"VDD_2":75,"VDD_3":100,"VDD_4":28,"VDD_5":11,
    "VSS_1":49,"VSS_2":74,"VSS_3":99,"VSS_4":27,"VSS_5":10,
    "VDDA":22,"VSSA":19,"VREF+":21,"VREF-":20,
}
OPTIONAL = {"BOOT0":94,"VBAT":6}


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def verify(hw: dict, socket: dict, l2: dict) -> None:
    assert len(PIN_NAMES) == 100
    assert hw["schema_version"] == "1.0.0"
    assert hw["profile_id"] == "stm32f103-lqfp100-programming-hardware-v1"
    assert hw["kind"] == "package_hardware" and hw["status"] == "pilot_reviewed"
    assert hw["scope"] == {
        "manufacturer":"STMicroelectronics", "series":"STM32F103",
        "package":"LQFP", "pin_count":100,
        "applicable_base_devices":["STM32F103V8"],
    }
    assert {e["source_id"] for e in hw["evidence"]} == {"st_ds5319_rev20"}
    d = hw["data"]
    assert d["pin_count"] == 100 and d["package"] == "LQFP"
    assert d["physical_pin_map"] == [
        {"pin":i,"name":s} for i,s in enumerate(PIN_NAMES, 1)
    ]
    assert d["mechanical"]["body_mm"] == {"x":14,"y":14}
    assert d["mechanical"]["lead_span_mm"] == {"x":16,"y":16}
    assert d["mechanical"]["pitch_mm"] == 0.5
    assert d["mechanical"]["max_height_mm"] == 1.6
    assert d["mechanical"]["pin1_identifier_required_for_fixture_orientation"] is True

    route = d["programming_route"]
    assert route["primary_interface"] == "SWD"
    for name, pin in {"SWDIO":72,"SWCLK":76,"NRST":14,"BOOT0":94}.items():
        assert route["signals"][name]["pin"] == pin
    assert route["signals"]["SWDIO"]["gpio"] == "PA13"
    assert route["signals"]["SWCLK"]["gpio"] == "PA14"

    power = d["power"]
    assert power["programming_vdd_v"] == {"min":2,"max":3.6}
    assert power["external_vpp_required"] is False
    assert power["all_main_power_and_ground_pins_must_be_connected"] is True
    assert {p["name"]:p["pin"] for p in power["mandatory_positive_contacts"]} == {
        name:pin for name,pin in REQUIRED.items()
        if name.startswith("VDD") or name == "VDDA"
    }
    assert {p["name"]:p["pin"] for p in power["mandatory_ground_contacts"]} == {
        name:pin for name,pin in REQUIRED.items()
        if name.startswith("VSS") or name == "VSSA"
    }
    assert next(x for x in power["mandatory_positive_contacts"] if x["name"] == "VDDA")["tie_to"] == "VDD"
    assert next(x for x in power["mandatory_ground_contacts"] if x["name"] == "VSSA")["tie_to"] == "VSS"
    analog = power["analog_reference"]
    assert "Figures 39-40" in analog["manufacturer_reference"]
    assert "figure_40" in analog["fixture_provisioning_policy"]
    assert {x["name"]:(x["pin"],x["tie_to"],x["mandatory_for_this_fixture_profile"]) for x in analog["contacts"]} == {
        "VREF+":(21,"VDDA",True), "VREF-":(20,"VSSA",True)
    }
    assert power["vbat"]["pin"] == 6
    assert "VBAT" in power["vbat"]["socket_policy"]

    contacts = d["socket_contacts"]
    assert {x["purpose"]:x["pin"] for x in contacts["mandatory"]} == REQUIRED
    assert {x["purpose"]:x["pin"] for x in contacts["optional"]} == OPTIONAL
    assert contacts["not_connected"] == [{"purpose":"NC","pin":73,"policy":"do_not_connect"}]
    for key in ("physical_socket_qualified","hardware_runtime_ready","execution_authorized"):
        assert d["hardware_readiness_boundary"][key] is False

    assert socket["socket_profile_id"] == "stm32f103v8t6-lqfp100-swd-socket-v1"
    assert socket["status"] == "design_input_ready"
    assert socket["target"] == {
        "manufacturer":"STMicroelectronics","icpn":"STM32F103V8T6",
        "base_device":"STM32F103V8","package":"LQFP100"
    }
    assert socket["programming_hardware_profile_id"] == hw["profile_id"]
    assert {e["source_id"] for e in socket["evidence"]} == {"st_ds5319_rev20"}
    sr = socket["route"]
    assert sr["provider_qualification_level"] == "L2"
    assert sr["interface"] == "SWD"
    assert sr["target_config"] == "tcl/target/stm32f1x.cfg"
    assert len(sr["required_contacts"]) == len(REQUIRED)
    assert set(sr["required_contacts"]) == set(REQUIRED)
    assert set(sr["optional_contacts"]) == set(OPTIONAL)
    fixture = socket["fixture_contract"]
    assert fixture["orientation"]["pin1_must_be_keyed"] is True
    assert fixture["power"]["all_main_supply_and_ground_contacts_required"] is True
    assert fixture["power"]["vbat_bias_documented_before_fixture_release"] is True
    assert fixture["power"]["vref_plus_minus_must_follow_manufacturer_decoupling"] is True
    assert fixture["no_connect_pins"] == [73]
    for key in ("sufficient_for_socket_vendor_selection","sufficient_for_production_release",
                "physical_programming_qualified","hil_verified","execution_authorized"):
        assert socket["readiness"][key] is False
    assert socket["readiness"]["sufficient_for_socket_schematic_and_pin_assignment_development"] is True

    cohort = [r for r in l2["records"] if r["icpn"] == "STM32F103V8T6"]
    assert len(cohort) == 1
    r = cohort[0]
    assert r["software_state"] == "SUPPORTED"
    assert r["base_device"] == "STM32F103V8"
    assert r["programming_profile_id"] == "stm32f1-medium-density-flash-v0"
    assert r["memory_geometry_profile_id"] == "stm32f103v8-64k-v0"
    assert r["main_flash_size_bytes"] == 65536
    assert r["page_count"] == 64


def reject(hw: dict, socket: dict, l2: dict) -> None:
    try:
        verify(hw, socket, l2)
    except (AssertionError, KeyError):
        return
    raise AssertionError("unsafe package-contract mutation admitted")


def main() -> int:
    hw, socket, l2 = load(HW_PATH), load(SOCKET_PATH), load(L2_PATH)
    verify(hw, socket, l2)

    for field, value in (
        ("physical_pin_map", [{"pin":1,"name":"VSS_5"}] + hw["data"]["physical_pin_map"][1:]),
        ("socket_contacts", {**hw["data"]["socket_contacts"],
                             "mandatory": hw["data"]["socket_contacts"]["mandatory"][:-1]}),
        ("mechanical", {**hw["data"]["mechanical"],"body_mm":{"x":10,"y":10}}),
    ):
        corrupted = deepcopy(hw)
        corrupted["data"][field] = value
        reject(corrupted, socket, l2)

    for mutate in (
        lambda h: h["data"]["power"]["analog_reference"]["contacts"][0].update(tie_to="VSS"),
        lambda h: h["data"]["socket_contacts"]["not_connected"].clear(),
        lambda h: h["scope"]["applicable_base_devices"].append("STM32F103VB"),
    ):
        corrupted = deepcopy(hw)
        mutate(corrupted)
        reject(corrupted, socket, l2)

    for mutate in (
        lambda s: s["route"]["required_contacts"].remove("VREF+"),
        lambda s: s["route"]["required_contacts"].remove("VDD_5"),
        lambda s: s["fixture_contract"]["no_connect_pins"].clear(),
        lambda s: s["target"].update(icpn="STM32F103VBT6"),
        lambda s: s["readiness"].update(hil_verified=True),
        lambda s: s["readiness"].update(execution_authorized=True),
    ):
        corrupted = deepcopy(socket)
        mutate(corrupted)
        reject(hw, corrupted, l2)

    print("STM32F103V8T6 LQFP100 socket contract PASS (12 fail-closed mutations)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

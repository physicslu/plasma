#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROFILE = ROOT / "profiles" / "package-hardware" / "stm32f103-lqfp48-programming-hardware-v1.json"
SOCKET = ROOT / "socket-profiles" / "stm32f103c8t6-lqfp48-swd-v1.json"


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def main() -> int:
    profile = load(PROFILE)
    socket = load(SOCKET)
    data = profile["data"]
    pin_map = {row["pin"]: row["name"] for row in data["physical_pin_map"]}

    assert profile["kind"] == "package_hardware"
    assert profile["status"] == "pilot_reviewed"
    assert len(pin_map) == 48
    assert set(pin_map) == set(range(1, 49))
    assert pin_map[7] == "NRST"
    assert pin_map[34] == "PA13"
    assert pin_map[37] == "PA14"
    assert pin_map[44] == "BOOT0"
    assert {pin_map[n] for n in (24, 36, 48)} == {"VDD_1", "VDD_2", "VDD_3"}
    assert {pin_map[n] for n in (23, 35, 47)} == {"VSS_1", "VSS_2", "VSS_3"}
    assert pin_map[9] == "VDDA"
    assert pin_map[8] == "VSSA"

    route = data["programming_route"]
    assert route["primary_interface"] == "SWD"
    assert route["signals"]["SWDIO"]["pin"] == 34
    assert route["signals"]["SWCLK"]["pin"] == 37
    assert route["signals"]["NRST"]["pin"] == 7

    power = data["power"]
    assert power["programming_vdd_v"] == {"min": 2.0, "max": 3.6}
    assert power["external_vpp_required"] is False
    assert power["all_main_power_and_ground_pins_must_be_connected"] is True

    boundary = data["hardware_readiness_boundary"]
    assert boundary["socket_design_input_complete"] is True
    assert boundary["physical_socket_qualified"] is False
    assert boundary["hardware_runtime_ready"] is False
    assert boundary["execution_authorized"] is False

    assert socket["target"]["icpn"] == "STM32F103C8T6"
    assert socket["programming_hardware_profile_id"] == profile["profile_id"]
    assert socket["route"]["provider_qualification_level"] == "L2"
    assert socket["route"]["interface"] == "SWD"
    assert socket["fixture_contract"]["reset"]["nrst_contact_required"] is True
    assert socket["fixture_contract"]["reset"]["connect_under_reset_capable"] is True
    ready = socket["readiness"]
    assert ready["sufficient_for_socket_schematic_and_pin_assignment_development"] is True
    assert ready["sufficient_for_socket_vendor_selection"] is False
    assert ready["sufficient_for_production_release"] is False
    assert ready["physical_programming_qualified"] is False
    assert ready["hil_verified"] is False
    assert ready["execution_authorized"] is False

    print("STM32F103C8T6 socket profile contract PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Exact STM32F103RBT6 Socket contract: reused LQFP64 pin map, distinct Flash geometry."""
from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import test_stm32f103r8t6_lqfp64_socket_profile as original

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
HW_PATH = HERE / "profiles/package-hardware/stm32f103-lqfp64-programming-hardware-v1.json"
NEW_SOCKET = HERE / "socket-profiles/stm32f103rbt6-lqfp64-swd-v1.json"
R8_SOCKET = HERE / "socket-profiles/stm32f103r8t6-lqfp64-swd-v1.json"
QUAL_PATH = REPO / "release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json"
APPLICABILITY = REPO / "release/openocd-qualification/stm32f103-medium-density-lqfp-t6-t7-applicability-v2.json"
RB_GEOMETRY = HERE / "profiles/memory-geometry/stm32f103rb-128k-v0.json"
R8_GEOMETRY = HERE / "profiles/memory-geometry/stm32f103r8-64k-v0.json"

REQUIRED = original.REQUIRED
OPTIONAL = original.OPTIONAL


def load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def check(hw: dict, sock: dict, qual: dict, applicability: dict, rb: dict, r8: dict) -> None:
    assert hw["profile_id"] == "stm32f103-lqfp64-programming-hardware-v1"
    assert hw["scope"]["manufacturer"] == "STMicroelectronics"
    assert hw["scope"]["series"] == "STM32F103"
    assert hw["scope"]["package"] == "LQFP"
    assert hw["scope"]["pin_count"] == 64
    assert hw["scope"]["applicable_base_devices"] == ["STM32F103R8", "STM32F103RB"]
    assert set(hw["scope"]["applicability_basis"]) == {"STM32F103R8", "STM32F103RB"}
    assert {x["source_id"] for x in hw["evidence"]} == {"st_ds5319_rev20"}

    # Independent full 64-pin map from the existing reviewed hardware authority.
    assert hw["data"]["physical_pin_map"] == [
        {"pin":pin,"name":name} for pin,name in enumerate(original.PIN_NAMES,1)
    ]
    assert {x["purpose"]:x["pin"] for x in hw["data"]["socket_contacts"]["mandatory"]} == REQUIRED
    assert {x["purpose"]:x["pin"] for x in hw["data"]["socket_contacts"]["optional"]} == OPTIONAL
    assert hw["data"]["mechanical"]["body_mm"] == {"x":10,"y":10}
    assert hw["data"]["mechanical"]["lead_span_mm"] == {"x":12,"y":12}
    assert hw["data"]["mechanical"]["pitch_mm"] == 0.5
    assert hw["data"]["power"]["programming_vdd_v"] == {"min":2,"max":3.6}
    assert hw["data"]["power"]["external_vpp_required"] is False
    for flag in ("physical_socket_qualified","hardware_runtime_ready","execution_authorized"):
        assert hw["data"]["hardware_readiness_boundary"][flag] is False

    assert sock["schema_version"] == "1.0.0"
    assert sock["socket_profile_id"] == "stm32f103rbt6-lqfp64-swd-socket-v1"
    assert sock["status"] == "design_input_ready"
    assert sock["target"] == {
        "manufacturer":"STMicroelectronics",
        "icpn":"STM32F103RBT6",
        "base_device":"STM32F103RB",
        "package":"LQFP64",
    }
    assert {x["source_id"] for x in sock["evidence"]} == {"st_ds5319_rev20"}
    assert sock["programming_hardware_profile_id"] == hw["profile_id"]
    route = sock["route"]
    assert route["provider_qualification_level"] == "L2"
    assert route["interface"] == "SWD"
    assert route["target_config"] == "tcl/target/stm32f1x.cfg"
    assert len(route["required_contacts"]) == 13
    assert set(route["required_contacts"]) == set(REQUIRED)
    assert len(route["optional_contacts"]) == 2
    assert set(route["optional_contacts"]) == set(OPTIONAL)
    fixture = sock["fixture_contract"]
    assert fixture["orientation"]["pin1_must_be_keyed"] is True
    assert fixture["power"]["all_main_supply_and_ground_contacts_required"] is True
    assert fixture["power"]["vbat_bias_documented_before_fixture_release"] is True
    assert fixture["reset"]["connect_under_reset_capable"] is True
    assert sock["readiness"]["sufficient_for_socket_schematic_and_pin_assignment_development"] is True
    for flag in ("sufficient_for_socket_vendor_selection","sufficient_for_production_release",
                 "physical_programming_qualified","hil_verified","execution_authorized"):
        assert sock["readiness"][flag] is False

    binding = sock["qualification_binding"]
    assert binding == {
        "software_registry":"release/openocd-qualification/openocd-0.12.0-stm32f103-medium-v4.json",
        "software_state":"SUPPORTED",
        "programming_profile_id":"stm32f1-medium-density-flash-v0",
        "memory_geometry_profile_id":"stm32f103rb-128k-v0",
        "main_flash_size_bytes":131072,
        "erase_page_count":128,
        "identity_applicability":"release/openocd-qualification/stm32f103-medium-density-lqfp-t6-t7-applicability-v2.json",
        "hardware_profile_applicable_base_device":"STM32F103RB",
    }
    records = [x for x in qual["records"] if x["icpn"] == sock["target"]["icpn"]]
    assert len(records) == 1
    record = records[0]
    assert record["software_state"] == binding["software_state"]
    assert record["base_device"] == sock["target"]["base_device"]
    assert record["programming_profile_id"] == binding["programming_profile_id"]
    assert record["memory_geometry_profile_id"] == binding["memory_geometry_profile_id"]
    assert record["main_flash_size_bytes"] == binding["main_flash_size_bytes"]
    assert record["page_count"] == binding["erase_page_count"]
    assert set(record["operations"]) == {"probe","erase","program","read","verify"}
    targets = [x for x in applicability["targets"] if x["icpn"] == sock["target"]["icpn"]]
    assert len(targets) == 1
    target = targets[0]
    assert target["base_device"] == record["base_device"]
    assert target["pin_count"] == "64"
    assert target["package"] == "LQFP"
    assert target["memory_geometry_profile_id"] == binding["memory_geometry_profile_id"]
    assert target["main_flash_size_bytes"] == binding["main_flash_size_bytes"]
    assert target["page_count"] == binding["erase_page_count"]
    assert rb["profile_id"] == "stm32f103rb-128k-v0"
    assert rb["scope"]["base_device"] == "STM32F103RB"
    assert rb["data"]["main_flash_size_bytes"] == binding["main_flash_size_bytes"]
    assert rb["data"]["page_count"] == binding["erase_page_count"]
    assert rb["data"]["page_size_bytes"] == 1024
    assert rb["data"]["program_granularity_bytes"] == 2
    assert r8["profile_id"] == "stm32f103r8-64k-v0"
    assert r8["data"]["main_flash_size_bytes"] == 65536
    assert r8["data"]["page_count"] == 64
    assert r8["profile_id"] != rb["profile_id"]


def reject(hw:dict, sock:dict, qual:dict, applicability:dict, rb:dict, r8:dict)->None:
    try:
        check(hw,sock,qual,applicability,rb,r8)
    except (AssertionError,KeyError):
        return
    raise AssertionError("dangerous profile mutation went undetected")


def main()->int:
    hw,sock,qual,app,rb,r8 = (load(p) for p in (
        HW_PATH,NEW_SOCKET,QUAL_PATH,APPLICABILITY,RB_GEOMETRY,R8_GEOMETRY))
    # Old R8 exact Socket Profile must remain intact after shared hardware scope expansion.
    original.verify(hw,load(R8_SOCKET),qual)
    check(hw,sock,qual,app,rb,r8)

    for field,value in (
        ("icpn","STM32F103R8T6"),("icpn","STM32F103RBT6TR"),
        ("icpn","STM32F103VBT6"),("base_device","STM32F103R8"),
        ("package","LQFP100"),
    ):
        broken=deepcopy(sock);broken["target"][field]=value
        reject(hw,broken,qual,app,rb,r8)
    for key,value in (
        ("memory_geometry_profile_id","stm32f103r8-64k-v0"),
        ("main_flash_size_bytes",65536),("erase_page_count",64),
        ("hardware_profile_applicable_base_device","STM32F103R8"),
    ):
        broken=deepcopy(sock);broken["qualification_binding"][key]=value
        reject(hw,broken,qual,app,rb,r8)
    for key in ("VDD_4","VSS_4","NRST"):
        broken=deepcopy(sock);broken["route"]["required_contacts"].remove(key)
        reject(hw,broken,qual,app,rb,r8)
    for key in ("hil_verified","physical_programming_qualified","execution_authorized"):
        broken=deepcopy(sock);broken["readiness"][key]=True
        reject(hw,broken,qual,app,rb,r8)
    broken=deepcopy(hw)
    broken["scope"]["applicable_base_devices"].append("STM32F103VB")
    reject(broken,sock,qual,app,rb,r8)
    broken=deepcopy(hw)
    broken["data"]["physical_pin_map"][45]["name"]="PA14"
    reject(broken,sock,qual,app,rb,r8)
    broken=deepcopy(rb);broken["data"]["page_size_bytes"]=2048
    reject(hw,sock,qual,app,broken,r8)
    print("STM32F103RBT6 shared-LQFP64 exact socket PASS (18 negative tests)")
    return 0


if __name__=="__main__":
    raise SystemExit(main())

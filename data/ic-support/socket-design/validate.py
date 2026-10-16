#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
IC_SUPPORT_ROOT = HERE.parent
LEGACY_SOURCES = IC_SUPPORT_ROOT / "evidence" / "sources.json"
LEGACY_BINDING = IC_SUPPORT_ROOT / "bindings" / "stm32f103c-pilot-v0.json"
SOURCES = HERE / "evidence" / "sources.json"
PROFILE = HERE / "profiles" / "stm32f103c8t6-lqfp48-programming-hardware-v1.json"
BINDING = HERE / "bindings" / "stm32f103c8t6-v1.json"
SCHEMA = HERE / "schema" / "socket-design-v1.schema.json"


class SocketDesignValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SocketDesignValidationError(message)


def load_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    require(isinstance(value, dict), f"{path}: top-level JSON must be an object")
    return value


def source_ids(payload: dict[str, Any]) -> set[str]:
    rows = payload.get("sources")
    require(isinstance(rows, list) and rows, "source registry must contain sources")
    out: set[str] = set()
    for index, source in enumerate(rows):
        require(isinstance(source, dict), f"source[{index}] must be an object")
        sid = source.get("source_id")
        require(isinstance(sid, str) and sid, f"source[{index}] requires source_id")
        require(sid not in out, f"duplicate source_id: {sid}")
        out.add(sid)
    return out


def validate_profile(profile: dict[str, Any], known_sources: set[str]) -> None:
    require(profile.get("schema_version") == "1.0.0", "Socket profile schema version drift")
    require(profile.get("profile_id") == "stm32f103c8t6-lqfp48-programming-hardware-v1", "Socket profile id drift")
    require(profile.get("kind") == "package_hardware", "Socket profile kind drift")
    require(profile.get("status") == "pilot_socket_design_input_ready", "Socket profile status drift")

    scope = profile.get("scope")
    require(isinstance(scope, dict), "Socket profile scope is required")
    require(scope.get("exact_icpn") == "STM32F103C8T6", "Socket profile must be exact-ICPN scoped")
    require(scope.get("base_device") == "STM32F103C8", "Socket profile base-device drift")
    require(scope.get("package") == "LQFP" and scope.get("pin_count") == 48, "Socket profile package identity drift")

    evidence = profile.get("evidence")
    require(isinstance(evidence, list) and evidence, "Socket profile evidence is required")
    observed_sources: set[str] = set()
    for index, item in enumerate(evidence):
        require(isinstance(item, dict), f"evidence[{index}] must be an object")
        sid = item.get("source_id")
        require(sid in known_sources, f"Socket profile references unknown source: {sid!r}")
        observed_sources.add(str(sid))
    require(
        {"st_ds5319_rev20", "st_pm0075_rev2", "st_an2586_rev8"}.issubset(observed_sources),
        "Socket profile must retain datasheet, programming, and hardware-design authorities",
    )

    data = profile.get("data")
    require(isinstance(data, dict), "Socket design data is required")
    require(data.get("design_readiness") == "socket_design_input_ready", "Socket design-readiness drift")

    package = data.get("package")
    require(isinstance(package, dict), "Socket package mechanics are required")
    require(package.get("type") == "LQFP48" and package.get("pin_count") == 48, "LQFP48 identity drift")
    require(package.get("body_size_mm") == {"x": 7, "y": 7}, "LQFP48 body-size drift")
    require(package.get("lead_span_mm") == {"x": 9, "y": 9}, "LQFP48 lead-span drift")
    require(package.get("lead_pitch_mm") == 0.5, "LQFP48 pitch drift")
    require(package.get("max_package_height_mm") == 1.6, "LQFP48 height drift")

    minimum = data.get("pin_level_minimum_programming_hardware")
    require(isinstance(minimum, dict), "minimum programming hardware is required")
    contacts = minimum.get("mandatory_contacts")
    require(isinstance(contacts, list), "mandatory Socket contacts are required")
    require(minimum.get("mandatory_contact_count") == len(contacts) == 13, "mandatory contact count drift")

    expected_contacts = {
        (1, "VBAT", "VBAT", "backup_domain_power_required"),
        (24, "VDD_1", None, "target_power"),
        (36, "VDD_2", None, "target_power"),
        (48, "VDD_3", None, "target_power"),
        (23, "VSS_1", None, "target_ground"),
        (35, "VSS_2", None, "target_ground"),
        (47, "VSS_3", None, "target_ground"),
        (9, "VDDA", None, "analog_power_required"),
        (8, "VSSA", None, "analog_ground_required"),
        (34, "PA13", "SWDIO", "debug_data_bidirectional"),
        (37, "PA14", "SWCLK", "debug_clock_input"),
        (7, "NRST", "NRST", "recovery_reset_active_low"),
        (44, "BOOT0", "BOOT0", "boot_mode_control"),
    }
    observed_contacts = {
        (row.get("package_pin"), row.get("pin_name"), row.get("signal"), row.get("role"))
        for row in contacts
        if isinstance(row, dict)
    }
    require(observed_contacts == expected_contacts, "mandatory Socket contact map drift")
    require(len({row[0] for row in observed_contacts}) == 13, "mandatory Socket pins must be unique")

    recovery = minimum.get("recovery_contacts")
    require(isinstance(recovery, list), "recovery contacts must be an array")
    require(recovery == [], "normal Socket design must not leave BOOT0 as an optional-only contact")

    power = data.get("power_and_reset")
    require(isinstance(power, dict), "power/reset design rules are required")
    require(power.get("target_vdd_v") == {"min": 2, "max": 3.6}, "target VDD range drift")
    require(power.get("all_main_power_and_ground_contacts_required") is True, "all supply contacts must remain mandatory")
    require(power.get("vdda", {}).get("connect_to") == "TARGET_VDD", "VDDA must connect to target VDD")
    require(power.get("vssa") == {"package_pin": 8, "connect_to": "TARGET_GND"}, "VSSA rule drift")
    require(
        power.get("vbat") == {
            "package_pin": 1,
            "normal_socket_policy": "connect_to_TARGET_VDD_when_no_external_battery",
            "decoupling_to_ground_nf": 100,
            "external_battery_range_v": {"min": 1.8, "max": 3.6},
        },
        "VBAT design policy drift",
    )
    require(
        power.get("decoupling", {}).get("main_vdd", {}).get("bulk", {}).get("min_capacitance_uF") == 4.7
        and power.get("decoupling", {}).get("main_vdd", {}).get("bulk", {}).get("typical_capacitance_uF") == 10,
        "main VDD bulk decoupling drift",
    )
    require(
        power.get("decoupling", {}).get("vdda", {}).get("capacitors_to_vssa")
        == [{"capacitance_nf": 100}, {"capacitance_uF": 1}],
        "VDDA decoupling drift",
    )
    require(power.get("nrst", {}).get("package_pin") == 7, "NRST physical pin drift")
    require(
        power.get("boot0") == {
            "package_pin": 44,
            "reset_latched": True,
            "normal_boot_value": 0,
            "normal_boot_target": "main_flash_memory",
            "pull_down_ohms": {"typical": 10000, "basis": "AN2586 Figure 10 typical example"},
            "programmer_control_recommended": True,
        },
        "BOOT0 Socket policy drift",
    )

    boundaries = data.get("design_boundaries")
    require(isinstance(boundaries, dict), "Socket design boundaries are required")
    require(boundaries.get("socket_design_input_complete") is True, "design input must remain complete")
    require(boundaries.get("socket_model_selected") is False, "actual Socket model must remain unselected")
    require(boundaries.get("site_electrical_compatibility") == "not_evaluated", "Site compatibility must remain open")
    require(boundaries.get("socket_compatibility") == "not_evaluated", "Socket compatibility must remain open")
    require(boundaries.get("hardware_runtime_ready") is False, "hardware runtime readiness must remain false")
    require(boundaries.get("physical_programming_qualified") is False, "physical programming qualification must remain false")
    require(boundaries.get("hil_required_before_l3") is True, "HIL must remain required before L3")


def main() -> int:
    schema = load_json(SCHEMA)
    require(schema.get("$schema") == "https://json-schema.org/draft/2020-12/schema", "unexpected Socket schema draft")
    require(schema.get("$defs", {}).get("profile", {}).get("properties", {}).get("schema_version", {}).get("const") == "1.0.0", "Socket schema/profile version mismatch")

    legacy_sources = source_ids(load_json(LEGACY_SOURCES))
    socket_sources_payload = load_json(SOURCES)
    require(socket_sources_payload.get("schema_version") == "1.0.0", "Socket source registry version drift")
    require(socket_sources_payload.get("status") == "engineering_design_input", "Socket source registry status drift")
    socket_sources = socket_sources_payload.get("sources")
    require(isinstance(socket_sources, list) and socket_sources, "Socket source registry must contain sources")
    for source in socket_sources:
        require(isinstance(source, dict), "Socket source must be an object")
        require(source.get("authority") == "manufacturer_official", "Socket evidence must be manufacturer-official")
        integrity = source.get("integrity")
        require(
            isinstance(integrity, dict)
            and integrity.get("status") == "not_content_pinned"
            and integrity.get("sha256") is None,
            "Socket source integrity must not fabricate a digest",
        )
    socket_ids = source_ids(socket_sources_payload)
    require(not (legacy_sources & socket_ids), "Socket source ids must not shadow frozen IC Support source ids")

    profile = load_json(PROFILE)
    validate_profile(profile, legacy_sources | socket_ids)

    frozen = load_json(LEGACY_BINDING)
    exact = {
        row.get("icpn"): row
        for row in frozen.get("bindings", [])
        if isinstance(row, dict)
    }
    require("STM32F103C8T6" in exact, "Socket overlay requires frozen exact C8T6 binding")
    require(
        exact["STM32F103C8T6"].get("profiles", {}).get("package_hardware")
        == "stm32f103-lqfp48-debug-v0",
        "Socket overlay must not rewrite manufacturer-near package facts",
    )

    binding = load_json(BINDING)
    require(binding.get("schema_version") == "1.0.0", "Socket binding version drift")
    require(binding.get("status") == "design_input_only", "Socket binding status drift")
    rows = binding.get("bindings")
    require(
        rows == [
            {
                "icpn": "STM32F103C8T6",
                "profile_id": "stm32f103c8t6-lqfp48-programming-hardware-v1",
            }
        ],
        "Socket binding scope drift",
    )

    print("Socket design validation PASS: STM32F103C8T6 / LQFP48 / 12 mandatory contacts")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SocketDesignValidationError as exc:
        print(f"Socket design validation FAIL: {exc}")
        raise SystemExit(1)

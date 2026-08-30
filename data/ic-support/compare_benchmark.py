#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
GROUND_TRUTH = HERE / "benchmarks" / "stm32f103c" / "ground-truth.json"
BINDINGS = HERE / "bindings" / "stm32f103c-pilot-v0.json"
PROFILE_ROOT = HERE / "profiles"


def load_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"{path}: top-level JSON must be an object")
    return value


def profile_index() -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for path in PROFILE_ROOT.glob("*/*.json"):
        profile = load_json(path)
        out[profile["profile_id"]] = profile
    return out


def build_projection() -> dict[str, Any]:
    bindings = load_json(BINDINGS)["bindings"]
    profiles = profile_index()
    by_icpn = {item["icpn"]: item for item in bindings}
    c8 = by_icpn["STM32F103C8T6"]
    cb = by_icpn["STM32F103CBT6"]

    def part_projection(binding: dict[str, Any]) -> dict[str, Any]:
        geometry = profiles[binding["profiles"]["memory_geometry"]]["data"]
        return {
            "base_device": binding["expected_catalog"]["base_device"],
            "flash_size_bytes": geometry["main_flash_size_bytes"],
            "page_size_bytes": geometry["page_size_bytes"],
            "page_count": geometry["page_count"],
            "profiles": binding["profiles"],
        }

    p = profiles[c8["profiles"]["programming"]]["data"]
    o = profiles[c8["profiles"]["option"]]["data"]
    s = profiles[c8["profiles"]["security"]]["data"]
    shared = [
        kind
        for kind in ["programming", "package_hardware", "option", "security"]
        if c8["profiles"][kind] == cb["profiles"][kind]
    ]
    different = [
        kind
        for kind in ["programming", "memory_geometry", "package_hardware", "option", "security"]
        if c8["profiles"][kind] != cb["profiles"][kind]
    ]
    return {
        "shared_profile_kinds": shared,
        "different_profile_kinds": different,
        "parts": {
            "STM32F103C8T6": part_projection(c8),
            "STM32F103CBT6": part_projection(cb),
        },
        "programming_contract": {
            "program_granularity_bytes": p["program_granularity_bytes"],
            "unlock_keys": p["unlock_keys"],
            "write_erase_requires_hsi": p["write_erase_requires_hsi"],
        },
        "option_contract": {
            "region_start": o["region_start"],
            "region_size_bytes": o["region_size_bytes"],
            "encoding": o["encoding"],
        },
        "security_contract": {
            "read_unprotect_is_destructive": s["read_protection"]["disable_transition"]["destructive"],
            "write_protection_granularity_bytes": s["write_protection"]["granularity_bytes"],
        },
        "revision_overrides": {
            "STM32F103C8T6": c8["revision_overrides"],
            "STM32F103CBT6": cb["revision_overrides"],
        },
    }


def diff(expected: Any, actual: Any, path: str = "$") -> list[str]:
    if type(expected) is not type(actual):
        return [f"{path}: type {type(actual).__name__} != expected {type(expected).__name__}"]
    if isinstance(expected, dict):
        errors: list[str] = []
        for key in sorted(set(expected) | set(actual)):
            child = f"{path}.{key}"
            if key not in expected:
                errors.append(f"{child}: unexpected")
            elif key not in actual:
                errors.append(f"{child}: missing")
            else:
                errors.extend(diff(expected[key], actual[key], child))
        return errors
    if isinstance(expected, list):
        if len(expected) != len(actual):
            return [f"{path}: length {len(actual)} != expected {len(expected)}"]
        errors: list[str] = []
        for index, (e, a) in enumerate(zip(expected, actual)):
            errors.extend(diff(e, a, f"{path}[{index}]"))
        return errors
    if expected != actual:
        return [f"{path}: {actual!r} != expected {expected!r}"]
    return []


def compare(expected: dict[str, Any], observed: dict[str, Any]) -> list[str]:
    return diff(expected, observed)


def main() -> int:
    parser = argparse.ArgumentParser(description="Compare STM32F103C IC Support candidate with ground truth")
    parser.add_argument("--candidate", type=Path, help="JSON file containing an 'observed' projection")
    args = parser.parse_args()

    expected = load_json(GROUND_TRUTH)["expected"]
    if args.candidate:
        payload = load_json(args.candidate)
        observed = payload.get("observed")
        if not isinstance(observed, dict):
            raise SystemExit("candidate must contain an object named 'observed'")
    else:
        observed = build_projection()

    errors = compare(expected, observed)
    if errors:
        print("IC Support benchmark FAIL")
        for error in errors:
            print(f"- {error}")
        return 1
    print("IC Support benchmark PASS: STM32F103C profile decomposition matches ground truth")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Manufacturer-only STM32F103 programming knowledge model.

This module performs no hardware I/O. It loads the frozen manufacturer-derived
baseline, validates the evidence/semantic boundary, and renders normalized
programming-operation traces for later independent backend comparison.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Iterable


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_BASELINE = ROOT / "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.json"
DEFAULT_LOCK = ROOT / "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.lock.json"

_BACKEND_DERIVATION_KEYS = {
    "target_config",
    "flash_driver",
    "adapter_speed",
    "adapter_khz",
    "runtime_id",
    "backend_command",
}


class ManufacturerBaselineError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ManufacturerBaselineError(f"cannot load {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ManufacturerBaselineError(f"{path}: top level must be an object")
    return payload


def _hex(value: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise ManufacturerBaselineError(f"expected hexadecimal string, got {value!r}")
    return int(value, 16)


def _walk_keys(value: Any) -> Iterable[str]:
    if isinstance(value, dict):
        for key, item in value.items():
            yield str(key)
            yield from _walk_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_keys(item)


def validate_baseline(
    baseline_path: Path = DEFAULT_BASELINE,
    lock_path: Path = DEFAULT_LOCK,
) -> dict[str, Any]:
    raw = baseline_path.read_bytes()
    baseline = _load_json(baseline_path)
    lock = _load_json(lock_path)

    digest = hashlib.sha256(raw).hexdigest()
    if lock.get("canonical_file_sha256") != digest:
        raise ManufacturerBaselineError(
            f"baseline digest drift: expected {lock.get('canonical_file_sha256')}, got {digest}"
        )
    if lock.get("baseline_id") != baseline.get("baseline_id"):
        raise ManufacturerBaselineError("baseline/lock identity mismatch")
    if baseline.get("status") != "frozen_manufacturer_only":
        raise ManufacturerBaselineError("baseline is not frozen manufacturer-only state")

    policy = baseline.get("source_policy")
    if not isinstance(policy, dict) or policy.get("derivation_authority") != "manufacturer_official_only":
        raise ManufacturerBaselineError("manufacturer-only derivation authority is required")

    locked_sources = policy.get("locked_sources")
    if not isinstance(locked_sources, list) or not locked_sources:
        raise ManufacturerBaselineError("at least one locked manufacturer source is required")
    for source in locked_sources:
        if not isinstance(source, dict):
            raise ManufacturerBaselineError("locked source must be an object")
        source_id = source.get("source_id")
        if not isinstance(source_id, str) or not source_id.startswith("st_"):
            raise ManufacturerBaselineError(f"non-manufacturer locked source: {source_id!r}")
        source_sha = source.get("sha256")
        if not isinstance(source_sha, str) or len(source_sha) != 64:
            raise ManufacturerBaselineError(f"{source_id}: source SHA-256 is not pinned")

    all_keys = {key.casefold() for key in _walk_keys(baseline)}
    forbidden = sorted(key for key in _BACKEND_DERIVATION_KEYS if key.casefold() in all_keys)
    if forbidden:
        raise ManufacturerBaselineError(
            "backend-derived keys are forbidden in manufacturer baseline: " + ", ".join(forbidden)
        )

    device = baseline["device_profile"]
    memory = device["memory_map"]
    flash = memory["main_flash"]
    flash_start = _hex(flash["start"])
    flash_end = _hex(flash["end"])
    if flash_end != flash_start + int(flash["size_bytes"]) - 1:
        raise ManufacturerBaselineError("main Flash range arithmetic mismatch")
    if int(flash["page_size_bytes"]) * int(flash["page_count"]) != int(flash["size_bytes"]):
        raise ManufacturerBaselineError("main Flash page geometry mismatch")

    sram = memory["sram"]
    if _hex(sram["end"]) != _hex(sram["start"]) + int(sram["size_bytes"]) - 1:
        raise ManufacturerBaselineError("SRAM range arithmetic mismatch")

    profile = baseline["programming_profile"]
    geometry = profile["flash_geometry"]
    if geometry.get("program_unit_bytes") != 2 or geometry.get("program_unit") != "halfword":
        raise ManufacturerBaselineError("STM32F1 baseline must preserve manufacturer half-word programming unit")
    if geometry.get("erase_unit_bytes") != 1024:
        raise ManufacturerBaselineError("STM32F103 medium-density erase page must be 1 KiB")

    operating_vdd = device["operating_electrical"]["vdd_v"]
    programming_vdd = profile["programming_electrical"]["vdd_programming_v"]
    if (operating_vdd.get("min"), operating_vdd.get("max")) != (
        programming_vdd.get("min"),
        programming_vdd.get("max"),
    ):
        raise ManufacturerBaselineError(
            "PM0075 whole-product-range programming claim no longer matches device operating VDD"
        )

    for name in ("SWD", "JTAG"):
        interface = profile["interfaces"][name]
        clock = interface["clock_hz"]
        values = (
            clock.get("manufacturer_min"),
            clock.get("manufacturer_max"),
            clock.get("manufacturer_recommended"),
        )
        if any(value is not None for value in values):
            raise ManufacturerBaselineError(
                f"{name}: manufacturer clock values must remain unknown until manufacturer evidence is added"
            )
        if clock.get("status") != "not_specified_by_locked_manufacturer_sources":
            raise ManufacturerBaselineError(f"{name}: unknown clock evidence state drifted")

    operations = baseline["program_model"]["operations"]
    required_ops = {"unlock_flash_if_locked", "program_halfword", "erase_page", "mass_erase"}
    if set(operations) != required_ops:
        raise ManufacturerBaselineError(f"program model operation set drifted: {sorted(operations)}")

    program_ops = [step.get("op") for step in operations["program_halfword"]]
    expected_program = [
        "poll_bit",
        "set_bit",
        "write_memory",
        "poll_bit",
        "reject_if_any_bit_set",
        "readback_compare",
    ]
    if program_ops != expected_program:
        raise ManufacturerBaselineError("manufacturer-derived half-word program sequence drifted")

    boundary = baseline["qualification_boundary"]
    for field in ("executable_on_hardware", "hardware_runtime_ready", "physical_programming_qualified"):
        if boundary.get(field) is not False:
            raise ManufacturerBaselineError(f"{field} must remain false in the research baseline")

    return baseline


def normalized_operation_trace(
    operation: str,
    baseline_path: Path = DEFAULT_BASELINE,
    lock_path: Path = DEFAULT_LOCK,
) -> list[dict[str, Any]]:
    baseline = validate_baseline(baseline_path, lock_path)
    operations = baseline["program_model"]["operations"]
    if operation not in operations:
        raise ManufacturerBaselineError(
            f"unknown operation {operation!r}; choose one of {', '.join(sorted(operations))}"
        )
    return list(operations[operation])


def semantic_signature(
    baseline_path: Path = DEFAULT_BASELINE,
    lock_path: Path = DEFAULT_LOCK,
) -> dict[str, list[str]]:
    baseline = validate_baseline(baseline_path, lock_path)
    return {
        name: [str(step["op"]) for step in steps]
        for name, steps in baseline["program_model"]["operations"].items()
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Inspect the frozen manufacturer-only STM32F103 programming model")
    parser.add_argument(
        "--operation",
        choices=["unlock_flash_if_locked", "program_halfword", "erase_page", "mass_erase"],
        help="emit one normalized operation trace",
    )
    parser.add_argument("--signature", action="store_true", help="emit semantic operation signatures")
    args = parser.parse_args()

    if args.operation:
        payload: Any = normalized_operation_trace(args.operation)
    elif args.signature:
        payload = semantic_signature()
    else:
        baseline = validate_baseline()
        payload = {
            "result": "PASS",
            "baseline_id": baseline["baseline_id"],
            "target": baseline["target"]["icpn"],
            "status": baseline["status"],
            "hardware_runtime_ready": baseline["qualification_boundary"]["hardware_runtime_ready"],
        }
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ManufacturerBaselineError as exc:
        print(f"manufacturer programming baseline FAIL: {exc}")
        raise SystemExit(1)

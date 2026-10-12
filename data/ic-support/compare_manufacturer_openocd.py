#!/usr/bin/env python3
"""Validate the frozen-manufacturer vs OpenOCD semantic comparison.

This is an analysis tool only. It never executes OpenOCD and never performs
hardware I/O. The manufacturer baseline remains authoritative and immutable.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.json"
LOCK = ROOT / "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.lock.json"
COMPARISON = ROOT / "data/ic-support/openocd-comparison/stm32f103c8t6-openocd-v0.12.0-v1.json"
OPENOCD_RELEASE = ROOT / "release/openocd.json"

ALLOWED_CLASSIFICATIONS = {
    "exact_match",
    "functionally_equivalent",
    "backend_optimization",
    "backend_assumption_or_default",
    "manufacturer_unresolved_backend_value",
    "conflict_or_out_of_spec",
    "backend_extra_requires_manufacturer_validation",
}

REQUIRED_OBSERVATIONS = {
    "flash_register_map",
    "flash_unlock_keys",
    "flash_status_bits",
    "medium_density_page_size",
    "program_alignment",
    "page_erase_core",
    "mass_erase_core",
    "program_core",
    "ram_flash_loader",
    "target_halted_requirement",
    "backend_timeouts",
    "debug_adapter_speed",
    "verify_layering",
    "device_family_probe",
    "flash_size_probe",
    "blue_pill_flash_override",
    "clone_compatibility",
}


class ComparisonError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ComparisonError(f"cannot load {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ComparisonError(f"{path}: expected JSON object")
    return payload


def validate() -> dict[str, Any]:
    baseline_bytes = BASELINE.read_bytes()
    baseline = _load(BASELINE)
    lock = _load(LOCK)
    comparison = _load(COMPARISON)
    release = _load(OPENOCD_RELEASE)

    digest = hashlib.sha256(baseline_bytes).hexdigest()
    expected = lock.get("canonical_file_sha256")
    if digest != expected:
        raise ComparisonError(f"manufacturer baseline digest drift: {digest} != {expected}")

    control = comparison.get("manufacturer_control")
    if not isinstance(control, dict):
        raise ComparisonError("comparison manufacturer_control missing")
    if control.get("baseline_id") != baseline.get("baseline_id"):
        raise ComparisonError("comparison points at the wrong manufacturer baseline")
    if control.get("baseline_sha256") != digest:
        raise ComparisonError("comparison baseline SHA does not match frozen bytes")
    if control.get("freeze_commit") != "2296863cd7c68d76c5e18a6db08fe6e319ebf4cd":
        raise ComparisonError("manufacturer freeze commit drifted")
    if control.get("mutation_allowed") is not False:
        raise ComparisonError("comparison must not authorize manufacturer baseline mutation")

    backend = comparison.get("backend_reference")
    if not isinstance(backend, dict):
        raise ComparisonError("backend_reference missing")
    if backend.get("source_commit") != release.get("source_commit"):
        raise ComparisonError("comparison OpenOCD commit differs from pinned Plasma release")
    if backend.get("version") != release.get("version"):
        raise ComparisonError("comparison OpenOCD version differs from pinned Plasma release")

    observations = comparison.get("observations")
    if not isinstance(observations, list) or not observations:
        raise ComparisonError("comparison observations missing")
    by_id: dict[str, dict[str, Any]] = {}
    counts: Counter[str] = Counter()
    for row in observations:
        if not isinstance(row, dict):
            raise ComparisonError("comparison row must be an object")
        row_id = row.get("id")
        classification = row.get("classification")
        if not isinstance(row_id, str) or not row_id:
            raise ComparisonError("comparison row id missing")
        if row_id in by_id:
            raise ComparisonError(f"duplicate comparison observation: {row_id}")
        if classification not in ALLOWED_CLASSIFICATIONS:
            raise ComparisonError(f"{row_id}: invalid classification {classification!r}")
        if "manufacturer" not in row or "openocd" not in row:
            raise ComparisonError(f"{row_id}: both manufacturer and openocd observations are required")
        if not isinstance(row.get("native_programmer_implication"), str):
            raise ComparisonError(f"{row_id}: native programmer implication missing")
        by_id[row_id] = row
        counts[classification] += 1

    missing = REQUIRED_OBSERVATIONS - set(by_id)
    if missing:
        raise ComparisonError(f"required comparison observations missing: {sorted(missing)}")

    speed = by_id["debug_adapter_speed"]
    if speed["classification"] != "manufacturer_unresolved_backend_value":
        raise ComparisonError("OpenOCD 1 MHz adapter value must not be treated as manufacturer limit")
    manufacturer_speed = speed["manufacturer"]
    if any(manufacturer_speed.get(key) is not None for key in ("min_hz", "max_hz", "recommended_hz")):
        raise ComparisonError("manufacturer SWD/JTAG clock unknowns were improperly filled from backend")

    blue_pill = by_id["blue_pill_flash_override"]
    if blue_pill["classification"] != "conflict_or_out_of_spec":
        raise ComparisonError("Blue Pill 128 KiB override must remain an explicit conflict/out-of-spec case")
    if blue_pill["manufacturer"].get("STM32F103C8T6_flash_kib") != 64:
        raise ComparisonError("exact C8 manufacturer Flash capacity drifted")
    if blue_pill["openocd"].get("forced_flash_kib") != 128:
        raise ComparisonError("OpenOCD Blue Pill override evidence drifted")

    conclusions = comparison.get("conclusions")
    required_false = ("hardware_runtime_ready", "physical_programming_qualified")
    if not isinstance(conclusions, dict) or any(conclusions.get(key) is not False for key in required_false):
        raise ComparisonError("comparison must remain non-hardware-qualified")
    if conclusions.get("manufacturer_baseline_remains_immutable") is not True:
        raise ComparisonError("manufacturer baseline immutability invariant missing")

    return {
        "result": "PASS",
        "comparison_id": comparison["comparison_id"],
        "manufacturer_baseline_sha256": digest,
        "openocd_source_commit": backend["source_commit"],
        "observation_count": len(observations),
        "classification_counts": dict(sorted(counts.items())),
        "hardware_runtime_ready": False,
        "physical_programming_qualified": False,
    }


def main() -> int:
    print(json.dumps(validate(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ComparisonError as exc:
        print(f"manufacturer/OpenOCD comparison FAIL: {exc}")
        raise SystemExit(1)

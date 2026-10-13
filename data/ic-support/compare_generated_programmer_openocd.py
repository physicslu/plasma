#!/usr/bin/env python3
"""Compare generated STM32F103 programmer semantics with the pinned OpenOCD review record.

This validator is post-generation only. It must never feed OpenOCD values back into
the manufacturer-derived generator.
"""

from __future__ import annotations

import importlib.util
import json
import types
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = ROOT / "data/ic-support/generate_stm32f103_programmer.py"
COMPARISON = ROOT / "data/ic-support/openocd-comparison/stm32f103c8t6-openocd-v0.12.0-v1.json"
OPENOCD_RELEASE = ROOT / "release/openocd.json"


class GeneratedOpenOCDComparisonError(RuntimeError):
    pass


def _load_json(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GeneratedOpenOCDComparisonError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GeneratedOpenOCDComparisonError(f"{path}: top level must be an object")
    return value


def _load_generator() -> types.ModuleType:
    spec = importlib.util.spec_from_file_location("stm32f103_programmer_codegen", GENERATOR_PATH)
    if spec is None or spec.loader is None:
        raise GeneratedOpenOCDComparisonError("cannot load STM32F103 programmer generator")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generated_module() -> types.ModuleType:
    generator = _load_generator()
    source = generator.render_source(generator.load_codegen_model())
    try:
        code = compile(source, "<generated-stm32f103-programmer>", "exec")
    except SyntaxError as exc:
        raise GeneratedOpenOCDComparisonError(f"generated programmer does not compile: {exc}") from exc
    module = types.ModuleType("generated_stm32f103_programmer")
    exec(code, module.__dict__)
    return module


def validate(
    *,
    generated: types.ModuleType | None = None,
    comparison: dict[str, Any] | None = None,
    release: dict[str, Any] | None = None,
) -> dict[str, Any]:
    g = generated or generated_module()
    comparison = comparison or _load_json(COMPARISON)
    release = release or _load_json(OPENOCD_RELEASE)

    if g.OPENOCD_USED_FOR_GENERATION is not False:
        raise GeneratedOpenOCDComparisonError("generated source claims OpenOCD was a generation input")
    if g.HARDWARE_RUNTIME_READY is not False:
        raise GeneratedOpenOCDComparisonError("software-only generated source must not be hardware-ready")
    if comparison.get("status") != "post_freeze_comparison":
        raise GeneratedOpenOCDComparisonError("OpenOCD comparison is not post-freeze")
    backend = comparison.get("backend_reference", {})
    if backend.get("source_commit") != release.get("source_commit"):
        raise GeneratedOpenOCDComparisonError("OpenOCD comparison commit differs from pinned release")
    if backend.get("version") != release.get("version"):
        raise GeneratedOpenOCDComparisonError("OpenOCD comparison version differs from pinned release")

    observations = comparison.get("observations")
    if not isinstance(observations, list):
        raise GeneratedOpenOCDComparisonError("OpenOCD comparison observations are missing")
    by_id = {
        row.get("id"): row
        for row in observations
        if isinstance(row, dict) and isinstance(row.get("id"), str)
    }

    def observation(name: str, classification: str) -> dict[str, Any]:
        row = by_id.get(name)
        if row is None:
            raise GeneratedOpenOCDComparisonError(f"missing OpenOCD observation {name}")
        if row.get("classification") != classification:
            raise GeneratedOpenOCDComparisonError(
                f"{name}: expected classification {classification}, got {row.get('classification')}"
            )
        return row

    unlock = observation("flash_unlock_keys", "exact_match")
    generated_keys = [f"0x{value:08X}" for value in g.UNLOCK_KEYS]
    if generated_keys != unlock.get("manufacturer") or generated_keys != unlock.get("openocd"):
        raise GeneratedOpenOCDComparisonError("unlock-key differential mismatch")

    status = observation("flash_status_bits", "exact_match")
    if set(g.STATUS_BITS) != set(status.get("manufacturer", [])):
        raise GeneratedOpenOCDComparisonError("generated status-bit names differ from manufacturer record")
    if set(g.STATUS_BITS) != set(status.get("openocd", [])):
        raise GeneratedOpenOCDComparisonError("generated status-bit names differ from OpenOCD record")

    page = observation("medium_density_page_size", "exact_match")
    if g.PAGE_SIZE != page.get("manufacturer", {}).get("page_size_bytes"):
        raise GeneratedOpenOCDComparisonError("generated page size differs from manufacturer record")
    if g.PAGE_SIZE != page.get("openocd", {}).get("page_size_bytes"):
        raise GeneratedOpenOCDComparisonError("generated page size differs from OpenOCD record")

    alignment = observation("program_alignment", "exact_match")
    if g.PROGRAM_UNIT_BYTES != alignment.get("manufacturer", {}).get("program_unit_bytes"):
        raise GeneratedOpenOCDComparisonError("generated program unit differs from manufacturer record")
    openocd_alignment = alignment.get("openocd", {})
    if (
        g.PROGRAM_UNIT_BYTES != openocd_alignment.get("write_start_alignment")
        or g.PROGRAM_UNIT_BYTES != openocd_alignment.get("write_end_alignment")
    ):
        raise GeneratedOpenOCDComparisonError("generated program alignment differs from OpenOCD record")

    for row_id, signature_id in (
        ("page_erase_core", "page_erase_core"),
        ("mass_erase_core", "mass_erase_core"),
        ("program_core", "program_core"),
    ):
        row = observation(row_id, "exact_match")
        if g.CORE_SIGNATURES.get(signature_id) != row.get("manufacturer"):
            raise GeneratedOpenOCDComparisonError(
                f"{row_id}: generated semantic signature differs from frozen manufacturer side"
            )

    blue_pill = observation("blue_pill_flash_override", "conflict_or_out_of_spec")
    if g.FLASH_SIZE != blue_pill.get("manufacturer", {}).get("STM32F103C8T6_flash_kib", 0) * 1024:
        raise GeneratedOpenOCDComparisonError("generated exact-ICPN Flash size drifted")
    if g.FLASH_SIZE == blue_pill.get("openocd", {}).get("forced_flash_kib", 0) * 1024:
        raise GeneratedOpenOCDComparisonError("generated code absorbed Blue Pill 128-KiB override")

    observation("ram_flash_loader", "backend_optimization")
    observation("target_halted_requirement", "backend_assumption_or_default")
    observation("backend_timeouts", "backend_assumption_or_default")
    observation("debug_adapter_speed", "manufacturer_unresolved_backend_value")

    forbidden_generated_attributes = (
        "RAM_FLASH_LOADER",
        "REQUIRES_TARGET_HALTED",
        "DEFAULT_TIMEOUT",
        "ADAPTER_SPEED_HZ",
    )
    leaked = [name for name in forbidden_generated_attributes if hasattr(g, name)]
    if leaked:
        raise GeneratedOpenOCDComparisonError(
            "backend-only OpenOCD policy leaked into generated source: " + ", ".join(leaked)
        )

    conclusions = comparison.get("conclusions", {})
    if conclusions.get("same_core_flash_programming_semantics") is not True:
        raise GeneratedOpenOCDComparisonError("OpenOCD comparison does not affirm shared core semantics")
    if conclusions.get("manufacturer_baseline_remains_immutable") is not True:
        raise GeneratedOpenOCDComparisonError("manufacturer baseline immutability conclusion is missing")

    return {
        "result": "PASS",
        "generator_schema": g.GENERATOR_SCHEMA,
        "icpn": g.ICPN,
        "openocd_version": backend.get("version"),
        "openocd_source_commit": backend.get("source_commit"),
        "exact_semantic_checks": 7,
        "backend_separation_checks": 5,
        "flash_size_bytes": g.FLASH_SIZE,
        "hardware_runtime_ready": False,
        "physical_programming_qualified": False,
    }


def main() -> int:
    print(json.dumps(validate(), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GeneratedOpenOCDComparisonError as exc:
        print(f"generated programmer/OpenOCD differential FAIL: {exc}")
        raise SystemExit(1)

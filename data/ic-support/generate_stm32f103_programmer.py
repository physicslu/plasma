#!/usr/bin/env python3
"""Generate a software-only STM32F103C8T6 reference programmer from manufacturer-derived data.

OpenOCD is deliberately not an input to this generator. The generated source is a
research artifact for deterministic software validation only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.json"
BASELINE_LOCK = ROOT / "data/ic-support/manufacturer-baseline/stm32f103c8t6-manufacturer-only-v1.lock.json"
PROGRAMMING_PROFILE = ROOT / "data/ic-support/profiles/programming/stm32f1-medium-density-flash-v0.json"
EXECUTION_IR = ROOT / "data/ic-support/execution-ir/stm32f103c-programming-execution-ir-v0.json"

EXPECTED_IR_STEPS = {
    "flash_unlock": ["ensure_bit_state"],
    "flash_program_unit": [
        "clear_status_flags", "enter_mode", "write_memory", "poll_bit",
        "inspect_status", "exit_mode", "verify_memory",
    ],
    "flash_erase_page": [
        "clear_status_flags", "enter_mode", "write_address_register",
        "set_control_bit", "poll_bit", "inspect_status", "exit_mode", "verify_erased",
    ],
    "flash_mass_erase": [
        "authorization_barrier", "clear_status_flags", "enter_mode",
        "set_control_bit", "poll_bit", "inspect_status", "exit_mode",
    ],
    "flash_lock": ["ensure_bit_state"],
}


class GenerationInputError(RuntimeError):
    pass


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise GenerationInputError(f"cannot load {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise GenerationInputError(f"{path}: top level must be an object")
    return value


def _hex(value: str) -> int:
    if not isinstance(value, str) or not value.startswith("0x"):
        raise GenerationInputError(f"expected hexadecimal string, got {value!r}")
    return int(value, 16)


def _operation_map(ir: dict[str, Any]) -> dict[str, dict[str, Any]]:
    operations = ir.get("operations")
    if not isinstance(operations, list):
        raise GenerationInputError("execution IR operations must be a list")
    result: dict[str, dict[str, Any]] = {}
    for operation in operations:
        if not isinstance(operation, dict) or not isinstance(operation.get("operation_id"), str):
            raise GenerationInputError("execution IR operation is malformed")
        operation_id = operation["operation_id"]
        if operation_id in result:
            raise GenerationInputError(f"duplicate execution IR operation {operation_id}")
        result[operation_id] = operation
    return result


def _normalize_manufacturer_core(operation_name: str, steps: list[dict[str, Any]]) -> list[str]:
    tokens: list[str] = []
    for step in steps:
        op = step.get("op")
        if op == "poll_bit" and step.get("bit") == "BSY" and step.get("until") == 0:
            tokens.append("wait_BSY_clear")
        elif op == "set_bit":
            tokens.append(f"set_{step['bit']}")
        elif op == "write_register" and step.get("register") == "FLASH_AR":
            tokens.append("write_AR")
        elif op == "write_memory" and step.get("width_bits") == 16:
            tokens.append("write_halfword")
        elif op == "reject_if_any_bit_set":
            tokens.append("check_" + "_".join(step.get("bits", [])))
        elif op in {"readback_compare", "verify_erased_region", "read_bit", "if_set_write_sequence"}:
            continue
        else:
            raise GenerationInputError(
                f"{operation_name}: unsupported manufacturer operation step {step!r}"
            )
    if operation_name == "program_halfword" and tokens and tokens[0] == "wait_BSY_clear":
        tokens = tokens[1:]
    return tokens


def load_codegen_model() -> dict[str, Any]:
    baseline_bytes = BASELINE.read_bytes()
    baseline = _load(BASELINE)
    lock = _load(BASELINE_LOCK)
    profile = _load(PROGRAMMING_PROFILE)
    ir = _load(EXECUTION_IR)

    digest = hashlib.sha256(baseline_bytes).hexdigest()
    if lock.get("canonical_file_sha256") != digest:
        raise GenerationInputError("frozen manufacturer baseline digest mismatch")
    if baseline.get("status") != "frozen_manufacturer_only":
        raise GenerationInputError("manufacturer baseline must remain frozen")
    if baseline.get("source_policy", {}).get("derivation_authority") != "manufacturer_official_only":
        raise GenerationInputError("manufacturer-only derivation authority is required")

    if profile.get("profile_id") != "stm32f1-medium-density-flash-v0":
        raise GenerationInputError("unexpected Programming Profile")
    evidence = profile.get("evidence")
    if not isinstance(evidence, list) or not evidence:
        raise GenerationInputError("Programming Profile evidence is missing")
    for row in evidence:
        if not isinstance(row, dict) or not str(row.get("source_id", "")).startswith("st_"):
            raise GenerationInputError("Programming Profile evidence must be ST-manufacturer sourced")

    if ir.get("profiles", {}).get("programming") != profile["profile_id"]:
        raise GenerationInputError("Execution IR is not bound to the selected Programming Profile")
    if "STM32F103C8T6" not in {
        row.get("icpn") for row in ir.get("targets", []) if isinstance(row, dict)
    }:
        raise GenerationInputError("Execution IR does not include STM32F103C8T6")

    baseline_registers = baseline["device_profile"]["memory_map"]["flash_interface_registers"]
    profile_registers = profile["data"]["registers"]
    for name, value in profile_registers.items():
        if baseline_registers.get(name) != value:
            raise GenerationInputError(f"{name}: Programming Profile/register baseline mismatch")

    baseline_keys = baseline["programming_profile"]["flash_controller"]["unlock_keys"]
    if profile["data"]["unlock_keys"] != baseline_keys:
        raise GenerationInputError("Programming Profile unlock keys differ from frozen baseline")

    flash = baseline["device_profile"]["memory_map"]["main_flash"]
    geometry = baseline["programming_profile"]["flash_geometry"]
    if profile["data"]["program_granularity_bytes"] != geometry["program_unit_bytes"]:
        raise GenerationInputError("program granularity mismatch")
    if int(flash["page_size_bytes"]) != int(geometry["erase_unit_bytes"]):
        raise GenerationInputError("erase geometry mismatch")

    operations = _operation_map(ir)
    for operation_id, expected_steps in EXPECTED_IR_STEPS.items():
        operation = operations.get(operation_id)
        if operation is None:
            raise GenerationInputError(f"Execution IR missing {operation_id}")
        actual_steps = [step.get("kind") for step in operation.get("steps", [])]
        if actual_steps != expected_steps:
            raise GenerationInputError(
                f"{operation_id}: Execution IR step contract drift: {actual_steps!r}"
            )
    if operations["flash_mass_erase"].get("requires_authorization") is not True:
        raise GenerationInputError("mass erase must remain explicitly authorized")
    if operations.get("rdp_disable_transition", {}).get("runtime_compile_ready") is not False:
        raise GenerationInputError("RDP disable transition must remain non-compilable")

    control_bits = {name: _hex(value) for name, value in profile["data"]["control_bits"].items()}
    status_bits = {name: _hex(value) for name, value in profile["data"]["status_bits"].items()}
    if not {"PG", "PER", "MER", "STRT", "LOCK"} <= set(control_bits):
        raise GenerationInputError("required Flash control bits are missing")
    if not {"BSY", "PGERR", "WRPRTERR", "EOP"} <= set(status_bits):
        raise GenerationInputError("required Flash status bits are missing")

    manufacturer_ops = baseline["program_model"]["operations"]
    return {
        "baseline_id": baseline["baseline_id"],
        "baseline_sha256": digest,
        "profile_id": profile["profile_id"],
        "ir_id": ir["ir_id"],
        "icpn": baseline["target"]["icpn"],
        "flash_start": _hex(flash["start"]),
        "flash_size": int(flash["size_bytes"]),
        "page_size": int(flash["page_size_bytes"]),
        "program_unit": int(geometry["program_unit_bytes"]),
        "registers": {name: _hex(value) for name, value in profile_registers.items()},
        "control_bits": control_bits,
        "status_bits": status_bits,
        "unlock_keys": [_hex(value) for value in profile["data"]["unlock_keys"]],
        "w1c_status_flags": list(profile["data"]["w1c_status_flags"]),
        "core_signatures": {
            "page_erase_core": _normalize_manufacturer_core(
                "erase_page", manufacturer_ops["erase_page"]
            ),
            "mass_erase_core": _normalize_manufacturer_core(
                "mass_erase", manufacturer_ops["mass_erase"]
            ),
            "program_core": _normalize_manufacturer_core(
                "program_halfword", manufacturer_ops["program_halfword"]
            ),
        },
    }


def _format_int_dict(values: dict[str, int]) -> str:
    lines = [f'    "{key}": 0x{value:08X},' for key, value in values.items()]
    return "{\n" + "\n".join(lines) + "\n}"


def render_source(model: dict[str, Any]) -> str:
    core_json = json.dumps(model["core_signatures"], indent=4, sort_keys=True)
    registers = _format_int_dict(model["registers"])
    control_bits = _format_int_dict(model["control_bits"])
    status_bits = _format_int_dict(model["status_bits"])
    keys = ", ".join(f"0x{value:08X}" for value in model["unlock_keys"])
    w1c_names = ", ".join(repr(name) for name in model["w1c_status_flags"])

    return f'''# Generated by data/ic-support/generate_stm32f103_programmer.py.
# DO NOT hand-edit. OpenOCD is not an input to this generated artifact.
from __future__ import annotations

from typing import Protocol

GENERATOR_SCHEMA = "stm32f103-programmer-codegen-v1"
BASELINE_ID = {model["baseline_id"]!r}
BASELINE_SHA256 = {model["baseline_sha256"]!r}
PROGRAMMING_PROFILE_ID = {model["profile_id"]!r}
EXECUTION_IR_ID = {model["ir_id"]!r}
ICPN = {model["icpn"]!r}
OPENOCD_USED_FOR_GENERATION = False
HARDWARE_RUNTIME_READY = False

FLASH_START = 0x{model["flash_start"]:08X}
FLASH_SIZE = 0x{model["flash_size"]:08X}
FLASH_END = FLASH_START + FLASH_SIZE - 1
PAGE_SIZE = 0x{model["page_size"]:X}
PROGRAM_UNIT_BYTES = {model["program_unit"]}

REGISTERS = {registers}
CONTROL_BITS = {control_bits}
STATUS_BITS = {status_bits}
UNLOCK_KEYS = ({keys},)
W1C_STATUS_FLAGS = ({w1c_names},)

ERROR_STATUS_MASK = STATUS_BITS["PGERR"] | STATUS_BITS["WRPRTERR"]
CLEARABLE_STATUS_MASK = ERROR_STATUS_MASK | STATUS_BITS["EOP"]

CORE_SIGNATURES = {core_json}


class RegisterMemoryIO(Protocol):
    def read32(self, address: int) -> int: ...
    def write32(self, address: int, value: int) -> None: ...
    def read16(self, address: int) -> int: ...
    def write16(self, address: int, value: int) -> None: ...


class ProgrammerError(RuntimeError):
    pass


class BusyTimeout(ProgrammerError):
    pass


class FlashStatusError(ProgrammerError):
    pass


class FlashLockError(ProgrammerError):
    pass


class VerifyError(ProgrammerError):
    pass


class AddressError(ProgrammerError):
    pass


class AuthorizationError(ProgrammerError):
    pass


def _poll_budget(max_polls: int) -> int:
    if not isinstance(max_polls, int) or isinstance(max_polls, bool) or max_polls <= 0:
        raise ValueError("max_polls must be a positive caller-supplied policy value")
    return max_polls


def wait_ready(io: RegisterMemoryIO, *, max_polls: int) -> int:
    for _ in range(_poll_budget(max_polls)):
        status = io.read32(REGISTERS["FLASH_SR"])
        if status & STATUS_BITS["BSY"] == 0:
            return status
    raise BusyTimeout("FLASH_SR.BSY did not clear within the caller-supplied poll budget")


def _clear_status(io: RegisterMemoryIO) -> None:
    io.write32(REGISTERS["FLASH_SR"], CLEARABLE_STATUS_MASK)


def _inspect_status(status: int) -> None:
    errors = status & ERROR_STATUS_MASK
    if errors:
        raise FlashStatusError(f"Flash status error flags set: 0x{{errors:08X}}")
    if status & STATUS_BITS["EOP"] == 0:
        raise FlashStatusError("Flash completion flag EOP was not observed")


def _set_control_bit(io: RegisterMemoryIO, bit_name: str) -> None:
    value = io.read32(REGISTERS["FLASH_CR"])
    io.write32(REGISTERS["FLASH_CR"], value | CONTROL_BITS[bit_name])


def _clear_control_bit(io: RegisterMemoryIO, bit_name: str) -> None:
    value = io.read32(REGISTERS["FLASH_CR"])
    io.write32(REGISTERS["FLASH_CR"], value & ~CONTROL_BITS[bit_name])


def _validate_main_flash_range(address: int, size: int, *, alignment: int) -> None:
    if size <= 0:
        raise AddressError("operation size must be positive")
    if address % alignment:
        raise AddressError(f"address 0x{{address:08X}} is not {{alignment}}-byte aligned")
    end = address + size - 1
    if address < FLASH_START or end > FLASH_END:
        raise AddressError(
            f"range 0x{{address:08X}}..0x{{end:08X}} is outside exact {{ICPN}} Main Flash"
        )


def unlock_flash(io: RegisterMemoryIO) -> None:
    control = io.read32(REGISTERS["FLASH_CR"])
    if control & CONTROL_BITS["LOCK"] == 0:
        return
    for key in UNLOCK_KEYS:
        io.write32(REGISTERS["FLASH_KEYR"], key)
    observed = io.read32(REGISTERS["FLASH_CR"])
    if observed & CONTROL_BITS["LOCK"]:
        raise FlashLockError("FLASH_CR.LOCK remained set after the manufacturer unlock sequence")


def lock_flash(io: RegisterMemoryIO) -> None:
    control = io.read32(REGISTERS["FLASH_CR"])
    if control & CONTROL_BITS["LOCK"]:
        return
    io.write32(REGISTERS["FLASH_CR"], control | CONTROL_BITS["LOCK"])
    observed = io.read32(REGISTERS["FLASH_CR"])
    if observed & CONTROL_BITS["LOCK"] == 0:
        raise FlashLockError("FLASH_CR.LOCK did not set")


def verify_halfword(io: RegisterMemoryIO, address: int, expected: int) -> None:
    actual = io.read16(address)
    if actual != expected:
        raise VerifyError(
            f"verify mismatch at 0x{{address:08X}}: expected 0x{{expected:04X}}, got 0x{{actual:04X}}"
        )


def program_halfword(
    io: RegisterMemoryIO,
    address: int,
    value: int,
    *,
    max_polls: int,
) -> None:
    _validate_main_flash_range(address, PROGRAM_UNIT_BYTES, alignment=PROGRAM_UNIT_BYTES)
    if not 0 <= value <= 0xFFFF:
        raise ValueError("halfword value must fit in 16 bits")

    wait_ready(io, max_polls=max_polls)
    _clear_status(io)
    _set_control_bit(io, "PG")
    io.write16(address, value)

    # Unresolved BSY means controller state is uncertain: no normal cleanup.
    status = wait_ready(io, max_polls=max_polls)
    _inspect_status(status)
    _clear_control_bit(io, "PG")
    verify_halfword(io, address, value)


def erase_page(
    io: RegisterMemoryIO,
    page_address: int,
    *,
    max_polls: int,
) -> None:
    _validate_main_flash_range(page_address, PAGE_SIZE, alignment=PAGE_SIZE)

    wait_ready(io, max_polls=max_polls)
    _clear_status(io)
    _set_control_bit(io, "PER")
    io.write32(REGISTERS["FLASH_AR"], page_address)
    _set_control_bit(io, "STRT")

    status = wait_ready(io, max_polls=max_polls)
    _inspect_status(status)
    _clear_control_bit(io, "PER")
    for address in range(page_address, page_address + PAGE_SIZE, PROGRAM_UNIT_BYTES):
        if io.read16(address) != 0xFFFF:
            raise VerifyError(f"page erase verify failed at 0x{{address:08X}}")


def mass_erase(
    io: RegisterMemoryIO,
    *,
    authorized: bool,
    max_polls: int,
) -> None:
    if authorized is not True:
        raise AuthorizationError("mass erase requires explicit authorization")

    wait_ready(io, max_polls=max_polls)
    _clear_status(io)
    _set_control_bit(io, "MER")
    _set_control_bit(io, "STRT")

    status = wait_ready(io, max_polls=max_polls)
    _inspect_status(status)
    _clear_control_bit(io, "MER")
    for address in range(FLASH_START, FLASH_START + FLASH_SIZE, PROGRAM_UNIT_BYTES):
        if io.read16(address) != 0xFFFF:
            raise VerifyError(f"mass erase verify failed at 0x{{address:08X}}")
'''


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="write generated Python source to this path")
    parser.add_argument("--model", action="store_true", help="print the deterministic codegen model as JSON")
    args = parser.parse_args()

    model = load_codegen_model()
    if args.model:
        print(json.dumps(model, indent=2, sort_keys=True))
        return 0

    source = render_source(model)
    if args.output is None:
        print(source, end="")
        return 0
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(source, encoding="utf-8")
    print(json.dumps({"result": "GENERATED", "artifact": str(args.output)}, sort_keys=True))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except GenerationInputError as exc:
        print(f"STM32F103 programmer generation FAIL: {exc}")
        raise SystemExit(1)

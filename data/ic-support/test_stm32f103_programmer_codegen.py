#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import types
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = ROOT / "data/ic-support/generate_stm32f103_programmer.py"

spec = importlib.util.spec_from_file_location("stm32f103_programmer_codegen", GENERATOR_PATH)
assert spec and spec.loader
generator = importlib.util.module_from_spec(spec)
spec.loader.exec_module(generator)


def generated_module() -> types.ModuleType:
    source = generator.render_source(generator.load_codegen_model())
    compile(source, "<generated-stm32f103-programmer>", "exec")
    module = types.ModuleType("generated_stm32f103_programmer")
    exec(compile(source, "<generated-stm32f103-programmer>", "exec"), module.__dict__)
    return module


class FakeFlashController:
    def __init__(self, generated: types.ModuleType) -> None:
        self.g = generated
        self.regs = {
            generated.REGISTERS["FLASH_CR"]: generated.CONTROL_BITS["LOCK"],
            generated.REGISTERS["FLASH_SR"]: 0,
            generated.REGISTERS["FLASH_AR"]: generated.FLASH_START,
        }
        self.flash = bytearray(b"\xff" * generated.FLASH_SIZE)
        self.key_sequence: list[int] = []
        self.busy_reads_after_program = 0
        self.busy_reads_remaining = 0
        self.inject_program_error = False

    def _offset(self, address: int) -> int:
        if not self.g.FLASH_START <= address <= self.g.FLASH_END:
            raise AssertionError(f"fake access outside flash: 0x{address:08X}")
        return address - self.g.FLASH_START

    def read32(self, address: int) -> int:
        if address == self.g.REGISTERS["FLASH_SR"] and self.busy_reads_remaining > 0:
            self.busy_reads_remaining -= 1
            return self.regs.get(address, 0) | self.g.STATUS_BITS["BSY"]
        return self.regs.get(address, 0)

    def write32(self, address: int, value: int) -> None:
        if address == self.g.REGISTERS["FLASH_KEYR"]:
            self.key_sequence.append(value)
            self.key_sequence = self.key_sequence[-len(self.g.UNLOCK_KEYS):]
            if tuple(self.key_sequence) == self.g.UNLOCK_KEYS:
                self.regs[self.g.REGISTERS["FLASH_CR"]] &= ~self.g.CONTROL_BITS["LOCK"]
            return

        if address == self.g.REGISTERS["FLASH_SR"]:
            self.regs[address] = self.regs.get(address, 0) & ~value
            return

        if address == self.g.REGISTERS["FLASH_AR"]:
            self.regs[address] = value
            return

        if address != self.g.REGISTERS["FLASH_CR"]:
            self.regs[address] = value
            return

        self.regs[address] = value
        if not value & self.g.CONTROL_BITS["STRT"]:
            return
        if value & self.g.CONTROL_BITS["LOCK"]:
            self.regs[self.g.REGISTERS["FLASH_SR"]] |= (
                self.g.STATUS_BITS["WRPRTERR"] | self.g.STATUS_BITS["EOP"]
            )
        elif value & self.g.CONTROL_BITS["PER"]:
            start = self.regs[self.g.REGISTERS["FLASH_AR"]]
            offset = self._offset(start)
            self.flash[offset:offset + self.g.PAGE_SIZE] = b"\xff" * self.g.PAGE_SIZE
            self.regs[self.g.REGISTERS["FLASH_SR"]] |= self.g.STATUS_BITS["EOP"]
        elif value & self.g.CONTROL_BITS["MER"]:
            self.flash[:] = b"\xff" * len(self.flash)
            self.regs[self.g.REGISTERS["FLASH_SR"]] |= self.g.STATUS_BITS["EOP"]
        self.regs[address] &= ~self.g.CONTROL_BITS["STRT"]

    def read16(self, address: int) -> int:
        offset = self._offset(address)
        return int.from_bytes(self.flash[offset:offset + 2], "little")

    def write16(self, address: int, value: int) -> None:
        if self.regs[self.g.REGISTERS["FLASH_CR"]] & self.g.CONTROL_BITS["LOCK"]:
            self.regs[self.g.REGISTERS["FLASH_SR"]] |= (
                self.g.STATUS_BITS["WRPRTERR"] | self.g.STATUS_BITS["EOP"]
            )
            return
        if not self.regs[self.g.REGISTERS["FLASH_CR"]] & self.g.CONTROL_BITS["PG"]:
            self.regs[self.g.REGISTERS["FLASH_SR"]] |= (
                self.g.STATUS_BITS["PGERR"] | self.g.STATUS_BITS["EOP"]
            )
            return
        if self.inject_program_error:
            self.regs[self.g.REGISTERS["FLASH_SR"]] |= (
                self.g.STATUS_BITS["PGERR"] | self.g.STATUS_BITS["EOP"]
            )
            return

        offset = self._offset(address)
        current = int.from_bytes(self.flash[offset:offset + 2], "little")
        if current & value != value:
            self.regs[self.g.REGISTERS["FLASH_SR"]] |= (
                self.g.STATUS_BITS["PGERR"] | self.g.STATUS_BITS["EOP"]
            )
            return
        self.flash[offset:offset + 2] = value.to_bytes(2, "little")
        self.regs[self.g.REGISTERS["FLASH_SR"]] |= self.g.STATUS_BITS["EOP"]
        self.busy_reads_remaining = self.busy_reads_after_program


class STM32F103ProgrammerCodegenTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.g = generated_module()

    def test_generation_is_manufacturer_derived_and_non_hardware(self) -> None:
        self.assertFalse(self.g.OPENOCD_USED_FOR_GENERATION)
        self.assertFalse(self.g.HARDWARE_RUNTIME_READY)
        self.assertEqual(self.g.ICPN, "STM32F103C8T6")
        self.assertEqual(self.g.FLASH_SIZE, 64 * 1024)
        self.assertEqual(self.g.PAGE_SIZE, 1024)
        self.assertEqual(self.g.PROGRAM_UNIT_BYTES, 2)
        self.assertEqual(self.g.CONTROL_BITS["LOCK"], 0x80)
        self.assertEqual(self.g.STATUS_BITS["PGERR"], 0x04)
        self.assertFalse(hasattr(self.g, "ADAPTER_SPEED_HZ"))
        self.assertFalse(hasattr(self.g, "DEFAULT_TIMEOUT"))
        self.assertFalse(hasattr(self.g, "RAM_FLASH_LOADER"))

    def test_unlock_program_verify_and_lock(self) -> None:
        io = FakeFlashController(self.g)
        self.g.unlock_flash(io)
        self.assertEqual(io.key_sequence, list(self.g.UNLOCK_KEYS))
        self.assertEqual(io.read32(self.g.REGISTERS["FLASH_CR"]) & self.g.CONTROL_BITS["LOCK"], 0)

        address = self.g.FLASH_START + 2
        self.g.program_halfword(io, address, 0x1234, max_polls=4)
        self.assertEqual(io.read16(address), 0x1234)
        self.assertEqual(io.read32(self.g.REGISTERS["FLASH_CR"]) & self.g.CONTROL_BITS["PG"], 0)

        self.g.lock_flash(io)
        self.assertNotEqual(
            io.read32(self.g.REGISTERS["FLASH_CR"]) & self.g.CONTROL_BITS["LOCK"], 0
        )

    def test_page_erase_is_geometry_bounded_and_verified(self) -> None:
        io = FakeFlashController(self.g)
        self.g.unlock_flash(io)
        io.flash[0:4] = b"\x00\x00\x00\x00"
        self.g.erase_page(io, self.g.FLASH_START, max_polls=4)
        self.assertEqual(io.flash[: self.g.PAGE_SIZE], b"\xff" * self.g.PAGE_SIZE)

        with self.assertRaises(self.g.AddressError):
            self.g.erase_page(io, self.g.FLASH_START + 2, max_polls=4)

    def test_mass_erase_requires_explicit_authorization(self) -> None:
        io = FakeFlashController(self.g)
        self.g.unlock_flash(io)
        io.flash[0:2] = b"\x00\x00"
        with self.assertRaises(self.g.AuthorizationError):
            self.g.mass_erase(io, authorized=False, max_polls=4)
        self.g.mass_erase(io, authorized=True, max_polls=4)
        self.assertEqual(io.flash, b"\xff" * self.g.FLASH_SIZE)

    def test_program_error_is_observed(self) -> None:
        io = FakeFlashController(self.g)
        self.g.unlock_flash(io)
        io.inject_program_error = True
        with self.assertRaises(self.g.FlashStatusError):
            self.g.program_halfword(io, self.g.FLASH_START, 0x1234, max_polls=4)

    def test_unresolved_busy_timeout_does_not_run_normal_cleanup(self) -> None:
        io = FakeFlashController(self.g)
        self.g.unlock_flash(io)
        io.busy_reads_after_program = 10
        with self.assertRaises(self.g.BusyTimeout):
            self.g.program_halfword(io, self.g.FLASH_START, 0x1234, max_polls=2)
        self.assertNotEqual(
            io.read32(self.g.REGISTERS["FLASH_CR"]) & self.g.CONTROL_BITS["PG"], 0
        )

    def test_alignment_and_range_fail_closed(self) -> None:
        io = FakeFlashController(self.g)
        self.g.unlock_flash(io)
        with self.assertRaises(self.g.AddressError):
            self.g.program_halfword(io, self.g.FLASH_START + 1, 0x1234, max_polls=4)
        with self.assertRaises(self.g.AddressError):
            self.g.program_halfword(io, self.g.FLASH_END + 1, 0x1234, max_polls=4)


if __name__ == "__main__":
    unittest.main()

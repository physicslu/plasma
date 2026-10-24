#!/usr/bin/env python3
"""Check linked STM32F103C8 memory, vectors, and generated image content."""

import argparse
from pathlib import Path
import re
import struct
import subprocess


def output(tool, *args):
    return subprocess.check_output([str(tool), *map(str, args)], text=True)


def check(build, binutils):
    elf = build / "plasma-blue-pill-cdc.elf"
    binary = (build / "plasma-blue-pill-cdc.bin").read_bytes()
    assert elf.is_file() and (build / "plasma-blue-pill-cdc.hex").is_file()
    # Resolve all tools from the same extracted binutils package.
    tool = lambda suffix: binutils / f"arm-none-eabi-{suffix}"
    header = output(tool("readelf"), "-W", "-h", elf)
    segments = output(tool("readelf"), "-W", "-l", elf)
    symbols = output(tool("readelf"), "-W", "-s", elf)
    disassembly = output(tool("objdump"), "-d", elf)
    vector_dump = output(tool("objdump"), "-s", "-j", ".isr_vector", elf)
    size = output(tool("size"), elf)
    assert "Machine:                           ARM" in header
    symbol_addresses = {}
    for line in symbols.splitlines():
        fields = line.split()
        if len(fields) >= 8 and re.fullmatch(r"[0-9a-fA-F]{8}", fields[1]):
            symbol_addresses[fields[-1]] = int(fields[1], 16)
    reset = symbol_addresses["Reset_Handler"]
    systick = symbol_addresses["SysTick_Handler"]
    usb_irq = symbol_addresses["USB_LP_CAN1_RX0_IRQHandler"]
    assert f"Entry point 0x{reset:x}" in segments
    assert "<Reset_Handler>:" in disassembly
    assert "<USB_LP_CAN1_RX0_IRQHandler>:" in disassembly
    assert "Contents of section .isr_vector:" in vector_dump
    stack, vector_reset = struct.unpack_from("<II", binary)
    assert stack == 0x20005000, hex(stack)
    assert vector_reset == reset, (hex(vector_reset), hex(reset))
    assert struct.unpack_from("<I", binary, 15 * 4)[0] == systick
    assert struct.unpack_from("<I", binary, (16 + 20) * 4)[0] == usb_irq
    assert len(binary) <= 64 * 1024
    for line in segments.splitlines():
        fields = line.split()
        if fields and fields[0] == "LOAD":
            _, _, virtual, physical, file_size, memory_size, *_ = fields
            virtual, physical = int(virtual, 16), int(physical, 16)
            file_size, memory_size = int(file_size, 16), int(memory_size, 16)
            if 0x08000000 <= virtual < 0x08010000:
                assert virtual + memory_size <= 0x08010000
            else:
                assert 0x20000000 <= virtual and virtual + memory_size <= 0x20005000
            assert 0x08000000 <= physical and physical + file_size <= 0x08010000
    assert b"PLASMA_BLUE_PILL_CDC/0.1" in binary
    assert b"HB version=%s seq=%lu uptime_ms=%lu" in binary
    print(size, end="")
    print(f"PASS: ARM ELF, 64 KiB Flash/20 KiB RAM, vector SP={stack:#x}, Reset={reset:#x}, SysTick={systick:#x}, USB IRQ={usb_irq:#x}, BIN={len(binary)} bytes")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("build", type=Path)
    parser.add_argument("binutils", type=Path)
    args = parser.parse_args()
    check(args.build, args.binutils)


if __name__ == "__main__":
    main()

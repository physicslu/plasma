"""OPP Common ABI v1: explicit, inert register API over an already authorized word port.

No MMIO opening, physical base selection, FPGA loading, or OpenOCD dependency.
Caller owns the approved transport and exclusive SCRATCH lock.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

MAGIC = 0x4D534C50
ABI_VERSION = 0x00010000
READ_OFFSETS = frozenset(range(0, 0x44, 4))
WRITE_OFFSETS = frozenset((0x40,))


class WordPort(Protocol):
    def read32(self, address: int) -> int: ...
    def write32(self, address: int, value: int) -> None: ...
    def write_barrier(self) -> None: ...


@dataclass(frozen=True)
class FPGAInfo:
    image_id: int
    build_id: int
    capabilities: int
    site_present: int
    site_ready: int
    ppu_status: int
    hw_revision: int


class OPPCommonRegisters:
    """Not a transport: only operates on a caller-qualified word port."""

    def __init__(self, port: WordPort, *, base: int) -> None:
        if type(base) is not int or base < 0 or base > 0xFFFFF000 or base & 0xFFF:
            raise ValueError("Explicit page-aligned common register base required")
        self._port = port
        self._base = base

    def _read(self, offset: int) -> int:
        if offset not in READ_OFFSETS:
            raise ValueError("Unspecified common register")
        value = self._port.read32(self._base + offset)
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise RuntimeError("Invalid 32-bit register response")
        return value

    def _write_scratch(self, value: int) -> None:
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("SCRATCH requires unsigned 32-bit word")
        self._port.write32(self._base + 0x40, value)
        self._port.write_barrier()

    def check_compatibility(self) -> None:
        if self._read(0x00) != MAGIC:
            raise RuntimeError("OPP FPGA MAGIC mismatch")
        if self._read(0x04) != ABI_VERSION:
            raise RuntimeError("OPP FPGA ABI v1.0 required")

    def get_fpga_info(self) -> FPGAInfo:
        self.check_compatibility()

        def words(start: int, count: int) -> int:
            return sum(self._read(start + 4 * i) << (32 * i) for i in range(count))

        info = FPGAInfo(
            image_id=words(0x08, 4),
            build_id=words(0x18, 4),
            capabilities=words(0x28, 2),
            site_present=self._read(0x30),
            site_ready=self._read(0x34),
            ppu_status=self._read(0x38),
            hw_revision=self._read(0x3C),
        )
        if info.site_ready & ~info.site_present:
            raise RuntimeError("READY bitmap exceeds PRESENT bitmap")
        if (info.site_present | info.site_ready) & ~0xF:
            raise RuntimeError("OPP v1 supports at most four Sites")
        return info

    def register_self_test(self) -> None:
        """Caller must hold an exclusive SCRATCH lease across this whole call.

        Restore is attempted even on compare/write failure. Restore errors propagate.
        No Site register or DUT power/pin access occurs.
        """
        self.check_compatibility()
        saved = self._read(0x40)
        try:
            for pattern in (0, 0xFFFFFFFF, 0xAAAAAAAA, 0x55555555, 0x12345678):
                self._write_scratch(pattern)
                if self._read(0x40) != pattern:
                    raise RuntimeError("OPP SCRATCH readback mismatch")
        finally:
            self._write_scratch(saved)
            if self._read(0x40) != saved:
                raise RuntimeError("OPP SCRATCH restore mismatch")

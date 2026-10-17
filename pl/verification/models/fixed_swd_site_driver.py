"""Simulation-only async fixed-ABI SWD Site-1 programming transport.

The port is a Cocotb AXI BFM returning (BRESP/RRESP, word) for reads and a
BRESP integer for writes. It contains no OS device calls or FPGA loading.
Do not import as a production real-UIO driver.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


class SimBus(Protocol):
    async def read(self, offset: int) -> tuple[int, int]: ...
    async def write(self, offset: int, value: int, strb: int = 15) -> int: ...


class FixedSWDSliceError(RuntimeError):
    """The simulated transaction is refused; effect may be uncertain."""


@dataclass(frozen=True)
class SWDSliceResult:
    sequence: int
    status: int
    data: int


class FixedSWDSiteSimDriver:
    """One Site, explicit immutable ABI, exactly one outstanding transaction."""

    ABI = 0x00010000
    SITE_STATUS = 0x0C
    CMD = 0x20
    ACK = 0x64
    DONE_SEQ = 0x48
    DONE_STATUS = 0x4C
    DONE_DATA = 0x60

    def __init__(self, bus: SimBus, *, site_id: int = 1, max_polls: int = 6000):
        if site_id != 1 or type(max_polls) is not int or not 1 <= max_polls <= 6000:
            raise ValueError("Only simulation Site 1 and bounded polling supported")
        self.bus = bus
        self.site_id = site_id
        self.max_polls = max_polls
        self.poisoned = False
        self._used_sequences: set[int] = set()

    async def _read(self, offset: int) -> int:
        resp, value = await self.bus.read(offset)
        if resp != 0:
            self.poisoned = True
            raise FixedSWDSliceError(f"Simulation AXI read rejected: 0x{offset:02x}")
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            self.poisoned = True
            raise FixedSWDSliceError("Malformed virtual read")
        return value

    async def _write(self, offset: int, value: int) -> None:
        if await self.bus.write(offset, value) != 0:
            self.poisoned = True
            raise FixedSWDSliceError(f"Simulation AXI write rejected: 0x{offset:02x}")

    async def verify_identity(self) -> None:
        if await self._read(0x00) != self.site_id or await self._read(0x04) != self.ABI:
            self.poisoned = True
            raise FixedSWDSliceError("Site identity / ABI mismatch")
        if (await self._read(0x08)) & 1 != 1:
            self.poisoned = True
            raise FixedSWDSliceError("SWD capability unavailable")

    async def transact(
        self, *, sequence: int, opcode: int, bit_count: int, arg0: int = 0,
        wdata: int = 0, clock_div: int = 2, timeout_ticks: int = 1000000,
    ) -> SWDSliceResult:
        if self.poisoned:
            raise FixedSWDSliceError("Refuse poisoned simulation owner")
        if type(sequence) is not int or not 1 <= sequence <= 0xFFFFFFFF or sequence in self._used_sequences:
            raise ValueError("Sequence must be nonzero and previously unused")
        if (opcode == 1 and bit_count != 32 or opcode == 2 and
            (bit_count != 64 or arg0 != 0 or wdata != 0) or opcode not in (1, 2)):
            raise ValueError("Only SWD transfer/64-bit reset are implemented in RTL slice")
        if type(arg0) is not int or not 0 <= arg0 <= 15 or type(wdata) is not int or not 0 <= wdata <= 0xFFFFFFFF:
            raise ValueError("Invalid SWD argument")
        if not 2 <= clock_div <= 65535 or not 1 <= timeout_ticks <= 0xFFFFFFFF:
            raise ValueError("Invalid clock/timeout")
        await self.verify_identity()
        if await self._read(self.SITE_STATUS) != 1:
            raise FixedSWDSliceError("Site not IDLE")
        try:
            for reg, data in [
                (0x24, sequence), (0x28, 1), (0x2C, 0),
                (0x30, bit_count), (0x34, arg0), (0x38, wdata),
                (0x3C, timeout_ticks), (0x5C, clock_div),
            ]:
                await self._write(reg, data)
            # COMMAND commits last. Simulation ordering is not a real ARM DMB.
            self._used_sequences.add(sequence)
            await self._write(self.CMD, opcode)
            for _ in range(self.max_polls):
                state = await self._read(self.SITE_STATUS)
                if state in (4, 8):
                    break
            else:
                raise FixedSWDSliceError("Polling budget exhausted; no retry")
            if state == 8:
                raise FixedSWDSliceError("RTL Site fault requires independent recovery")
            done = await self._read(self.DONE_SEQ)
            if done != sequence:
                raise FixedSWDSliceError("Stale or mismatched completion sequence")
            status = await self._read(self.DONE_STATUS)
            data = await self._read(self.DONE_DATA)
            await self._write(self.ACK, sequence)
            return SWDSliceResult(sequence, status, data)
        except FixedSWDSliceError:
            self.poisoned = True
            raise

"""Host-only Fixed ABI v1 SWD Site-1 semantic Driver (Cocotb BFM only).

No /dev/uio*, /dev/mem, GPIO, FPGA loading, PHY electrical control, or
production device ownership. Async access is serialized per Site; a Python
deadline is NOT a bound on an actual stuck AXI bus.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Protocol


class SimBus(Protocol):
    async def read(self, offset: int) -> tuple[int, int]: ...
    async def write(self, offset: int, value: int, strb: int = 15) -> int: ...


@dataclass(frozen=True)
class SWDSliceResult:
    sequence: int
    status: int
    data: int
    ack: int = 0
    data_valid: bool = False
    attempts: int = 0
    link_state: int = 0
    raw_status: int = 0


class FixedSWDSliceError(RuntimeError):
    """A refused/uncertain simulated transaction; never an auto-retry signal."""

    def __init__(self, message: str, *, response: SWDSliceResult | None = None):
        super().__init__(message)
        self.response = response


class FixedSWDSiteSimDriver:
    """One Site/owner epoch, strict one-at-a-time commands and bounded polling."""

    ABI = 0x00010000
    SITE_STATUS = 0x0C
    COMMAND = 0x20
    ACK = 0x64
    DONE_SEQ = 0x48
    DONE_STATUS = 0x4C
    DONE_DATA = 0x60
    META = 0x6C
    RAW_STATUS = 0x70
    FATAL_CODES = frozenset((5, 6, 9, 11))  # timeout, aborted, internal, PHY

    def __init__(self, bus: SimBus, *, site_id: int = 1, max_polls: int = 6000):
        if site_id != 1 or type(max_polls) is not int or not 1 <= max_polls <= 6000:
            raise ValueError("Only simulation Site 1 and bounded polling supported")
        self.bus = bus
        self.site_id = site_id
        self.max_polls = max_polls
        self.poisoned = False
        self._used_sequences: set[int] = set()
        self._lock = asyncio.Lock()

    async def _read(self, offset: int) -> int:
        try:
            resp, value = await self.bus.read(offset)
        except Exception as exc:
            self.poisoned = True
            raise FixedSWDSliceError("Virtual AXI read exception") from exc
        if resp != 0 or type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            self.poisoned = True
            raise FixedSWDSliceError(f"Simulation AXI read rejected: 0x{offset:02x}")
        return value

    async def _write(self, offset: int, value: int) -> None:
        try:
            resp = await self.bus.write(offset, value)
        except Exception as exc:
            self.poisoned = True
            raise FixedSWDSliceError("Virtual AXI write exception") from exc
        if resp != 0:
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
        # The mutex is held through setup, commit, polling, snapshot and ACK.
        async with self._lock:
            return await self._transact_locked(
                sequence=sequence, opcode=opcode, bit_count=bit_count,
                arg0=arg0, wdata=wdata, clock_div=clock_div,
                timeout_ticks=timeout_ticks,
            )

    async def _transact_locked(
        self, *, sequence: int, opcode: int, bit_count: int, arg0: int,
        wdata: int, clock_div: int, timeout_ticks: int,
    ) -> SWDSliceResult:
        if self.poisoned:
            raise FixedSWDSliceError("Refuse poisoned simulation owner")
        if type(sequence) is not int or not 1 <= sequence <= 0xFFFFFFFF or sequence in self._used_sequences:
            raise ValueError("Sequence must be nonzero and previously unused in this owner epoch")
        if (opcode == 1 and bit_count != 32 or opcode == 2 and
            (bit_count != 64 or arg0 != 0 or wdata != 0) or opcode not in (1, 2)):
            raise ValueError("Only SWD transfer/64-bit reset are implemented in RTL slice")
        if type(arg0) is not int or not 0 <= arg0 <= 15 or type(wdata) is not int or not 0 <= wdata <= 0xFFFFFFFF:
            raise ValueError("Invalid SWD argument")
        if (type(clock_div) is not int or not 2 <= clock_div <= 65535
                or type(timeout_ticks) is not int or not 1 <= timeout_ticks <= 0xFFFFFFFF):
            raise ValueError("Invalid half-period/timeout")

        await self.verify_identity()
        if await self._read(self.SITE_STATUS) != 1:
            raise FixedSWDSliceError("Site not IDLE")
        try:
            for reg, data in (
                (0x24, sequence), (0x28, 1), (0x2C, 0),
                (0x30, bit_count), (0x34, arg0), (0x38, wdata),
                (0x3C, timeout_ticks), (0x5C, clock_div),
            ):
                await self._write(reg, data)
            # Host-only ordering; a real ARM Device memory barrier is NOT implemented.
            self._used_sequences.add(sequence)
            await self._write(self.COMMAND, opcode)
            for _ in range(self.max_polls):
                state = await self._read(self.SITE_STATUS)
                if state in (4, 8):
                    break
            else:
                raise FixedSWDSliceError("Polling budget exhausted; transaction effect uncertain")

            first = await self._read(self.DONE_SEQ)
            status = await self._read(self.DONE_STATUS)
            data = await self._read(self.DONE_DATA)
            meta = await self._read(self.META)
            raw = await self._read(self.RAW_STATUS)
            second = await self._read(self.DONE_SEQ)
            state_again = await self._read(self.SITE_STATUS)
            if first != sequence or second != first or state_again != state:
                raise FixedSWDSliceError("Stale, unstable or mismatched completion sequence")
            if meta >> 15 or (meta >> 13) & 3 == 3 or raw > 9 or status > 11:
                raise FixedSWDSliceError("Malformed SWD completion metadata")
            result = SWDSliceResult(
                sequence=sequence, status=status, data=data,
                ack=meta & 7, data_valid=bool(meta & 8),
                attempts=(meta >> 4) & 0x1FF,
                link_state=(meta >> 13) & 3, raw_status=raw,
            )
            if status == 0 and opcode == 1:
                if (result.ack != 1 or result.attempts == 0
                        or result.data_valid != bool(arg0 & 2)):
                    raise FixedSWDSliceError("Inconsistent successful SWD response metadata",
                                             response=result)
            if status == 0 and opcode == 2 and result.data_valid:
                raise FixedSWDSliceError("Line reset cannot return data-valid",
                                         response=result)

            # A FAULT response is acknowledged only after the snapshot. This
            # consumes DONE_VALID, not hardware FAULT; never authorizes retry.
            await self._write(self.ACK, sequence)
            if state == 8 or status in self.FATAL_CODES:
                self.poisoned = True
                raise FixedSWDSliceError("SWD FAULT/uncertain result; external recovery required",
                                         response=result)
            return result
        except FixedSWDSliceError:
            self.poisoned = True
            raise

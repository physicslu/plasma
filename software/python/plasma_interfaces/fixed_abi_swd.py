"""Transport-neutral Fixed FPGA ABI v1 PS SWD command controller.

This is production *control logic*, not an authorized Linux MMIO backend.
An already-admitted, Site-scoped read32/write32 transport and a qualified
write_barrier are mandatory. This module never opens hardware, creates a
mapping, loads an FPGA or manages DUT power/reset. No real deployment or
ARMv7 barrier/IO qualification is implied by Host CI.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from threading import RLock
from typing import Protocol


class FixedABIPort(Protocol):
    def read32(self, address: int) -> int: ...
    def write32(self, address: int, value: int) -> None: ...
    def write_barrier(self) -> None: ...


class FixedABIStatus(IntEnum):
    OK = 0
    SWD_WAIT = 1
    SWD_FAULT = 2
    SWD_NO_ACK = 3
    PARITY = 4
    TIMEOUT = 5
    ABORTED = 6
    BAD_ARGUMENT = 7
    ENGINE_UNAVAILABLE = 8
    INTERNAL_FAULT = 9
    NEED_RESET = 10
    PHY_ERROR = 11


@dataclass(frozen=True)
class FixedABIResult:
    sequence: int
    status: FixedABIStatus
    data: int
    ack: int
    data_valid: bool
    attempts: int
    link_state: int
    raw_status: int


class FixedABIError(RuntimeError):
    """Refused or uncertain transaction. Never permission to auto-replay."""

    def __init__(self, message: str, *, result: FixedABIResult | None = None,
                 uncertain_target_effects: bool = False) -> None:
        super().__init__(message)
        self.result = result
        self.uncertain_target_effects = uncertain_target_effects


class FixedABISWDController:
    """One explicitly admitted Site and one owner epoch.

    A separate supervisor must prove hardware identity, generation, Site
    ownership, electrical safety, and the actual MMIO transport. Constructor
    and command methods do not attempt to acquire those privileges.
    """

    VERSION = 0x00010000
    CAP_SWD = 0x1
    ID = 0x00
    ABI = 0x04
    CAPABILITIES = 0x08
    SITE_STATUS = 0x0C
    SITE_ERROR = 0x10
    COMMAND = 0x20
    SEQUENCE = 0x24
    PROTOCOL = 0x28
    FLAGS = 0x2C
    BIT_COUNT = 0x30
    ARG0 = 0x34
    WDATA = 0x38
    TIMEOUT = 0x3C
    DONE_SEQ = 0x48
    DONE_STATUS = 0x4C
    CLOCK_DIV = 0x5C
    DONE_DATA = 0x60
    ACK_SEQ = 0x64
    META = 0x6C
    RAW_STATUS = 0x70
    IDLE, BUSY, DONE, FAULT = 1, 2, 4, 8
    SWD_TRANSFER, SWD_LINE_RESET = 1, 2
    FATAL = frozenset((FixedABIStatus.TIMEOUT, FixedABIStatus.ABORTED,
                       FixedABIStatus.INTERNAL_FAULT, FixedABIStatus.PHY_ERROR))

    def __init__(self, port: FixedABIPort, *, base: int, site_id: int,
                 max_polls: int = 6000) -> None:
        if port is None or any(not callable(getattr(port, attr, None))
                               for attr in ("read32", "write32", "write_barrier")):
            raise ValueError("Explicit word MMIO port and qualified write_barrier required")
        if type(base) is not int or not 0 <= base <= 0xFFFFF000 or base & 0xFFF:
            raise ValueError("Site base must be 4KiB-aligned")
        if type(site_id) is not int or not 1 <= site_id <= 8:
            raise ValueError("Site identity must be 1..8")
        if type(max_polls) is not int or not 1 <= max_polls <= 100000:
            raise ValueError("Invalid bounded poll budget")
        self.port, self.base, self.site_id = port, base, site_id
        self.max_polls = max_polls
        self.poisoned = False
        self._used_sequences: set[int] = set()
        self._lock = RLock()
        # No implicit MMIO read or write during construction.

    def _read(self, offset: int) -> int:
        try:
            value = self.port.read32(self.base + offset)
        except Exception as exc:
            self.poisoned = True
            raise FixedABIError("AXI read uncertain; external recovery required",
                                uncertain_target_effects=True) from exc
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            self.poisoned = True
            raise FixedABIError("Malformed 32-bit MMIO read")
        return value

    def _write(self, offset: int, value: int) -> None:
        try:
            self.port.write32(self.base + offset, value)
        except Exception as exc:
            self.poisoned = True
            raise FixedABIError("AXI write uncertain; external recovery required",
                                uncertain_target_effects=True) from exc

    def _commit_barrier(self) -> None:
        try:
            self.port.write_barrier()
        except Exception as exc:
            self.poisoned = True
            raise FixedABIError("Ordering barrier failed; refuse COMMAND",
                                uncertain_target_effects=True) from exc

    def _identity(self) -> None:
        if (self._read(self.ID) != self.site_id or
                self._read(self.ABI) != self.VERSION or
                not self._read(self.CAPABILITIES) & self.CAP_SWD):
            self.poisoned = True
            raise FixedABIError("Site identity, ABI or SWD capability mismatch")

    def transact(self, *, sequence: int, opcode: int, bit_count: int,
                 arg0: int = 0, wdata: int = 0, clock_div: int = 2,
                 timeout_ticks: int = 1_000_000) -> FixedABIResult:
        """Synchronous Site command, completion snapshot and matching ACK.

        Poll budget does not bound a blocked physical AXI transaction.
        Never auto-retry, reset hardware, clear sticky FAULT or mask errors.
        """
        if type(sequence) is not int or not 1 <= sequence <= 0xFFFFFFFF:
            raise ValueError("Sequence must be nonzero u32")
        if type(opcode) is not int or opcode not in (
                self.SWD_TRANSFER, self.SWD_LINE_RESET):
            raise ValueError("Unsupported command")
        if type(bit_count) is not int or bit_count != (
                32 if opcode == self.SWD_TRANSFER else 64):
            raise ValueError("SWD transfer=32 bits; line reset=64 bits")
        if type(arg0) is not int or not 0 <= arg0 <= 15:
            raise ValueError("Invalid SWD request")
        if type(wdata) is not int or not 0 <= wdata <= 0xFFFFFFFF:
            raise ValueError("Invalid SWD write data")
        if opcode == self.SWD_LINE_RESET and (arg0 or wdata):
            raise ValueError("SWD line reset has no payload")
        if opcode == self.SWD_TRANSFER and arg0 & 2 and wdata:
            raise ValueError("SWD reads must supply zero write data")
        if type(clock_div) is not int or not 2 <= clock_div <= 65535:
            raise ValueError("Invalid SWCLK half-period divider")
        if type(timeout_ticks) is not int or not 1 <= timeout_ticks <= 0xFFFFFFFF:
            raise ValueError("Invalid hardware timeout")
        with self._lock:
            if self.poisoned:
                raise FixedABIError("Site controller poisoned; external recovery required")
            if sequence in self._used_sequences:
                raise ValueError("Sequence reuse forbidden within owner epoch")
            self._identity()
            if self._read(self.SITE_STATUS) != self.IDLE:
                self.poisoned = True
                raise FixedABIError("Site not IDLE; command refused")

            for offset, word in (
                (self.SEQUENCE, sequence), (self.PROTOCOL, 1),
                (self.FLAGS, 0), (self.BIT_COUNT, bit_count),
                (self.ARG0, arg0), (self.WDATA, wdata),
                (self.TIMEOUT, timeout_ticks), (self.CLOCK_DIV, clock_div),
            ):
                self._write(offset, word)
            self._commit_barrier()
            # A failed launch remains uncertain; never reuse this sequence.
            self._used_sequences.add(sequence)
            self._write(self.COMMAND, opcode)

            for _ in range(self.max_polls):
                state = self._read(self.SITE_STATUS)
                if state in (self.DONE, self.FAULT):
                    break
                if state not in (self.IDLE, self.BUSY):
                    self.poisoned = True
                    raise FixedABIError("Malformed Site state after COMMAND",
                                        uncertain_target_effects=True)
            else:
                self.poisoned = True
                raise FixedABIError("Poll budget expired; hardware may remain active",
                                    uncertain_target_effects=True)

            first = self._read(self.DONE_SEQ)
            status_word = self._read(self.DONE_STATUS)
            data = self._read(self.DONE_DATA)
            meta = self._read(self.META)
            raw = self._read(self.RAW_STATUS)
            second = self._read(self.DONE_SEQ)
            again = self._read(self.SITE_STATUS)
            if (first != sequence or second != first or again != state or
                    status_word > 11 or raw > 9 or meta >> 15 or
                    (meta >> 13) & 3 == 3):
                self.poisoned = True
                raise FixedABIError("Mismatched/unstable completion or invalid metadata",
                                    uncertain_target_effects=True)

            result = FixedABIResult(
                sequence=sequence, status=FixedABIStatus(status_word), data=data,
                ack=meta & 7, data_valid=bool(meta & 8),
                attempts=(meta >> 4) & 0x1FF,
                link_state=(meta >> 13) & 3, raw_status=raw,
            )
            if result.status == FixedABIStatus.OK and opcode == self.SWD_TRANSFER:
                if (result.ack != 1 or result.attempts < 1 or
                        result.data_valid != bool(arg0 & 2)):
                    self.poisoned = True
                    raise FixedABIError("Invalid successful SWD response metadata",
                                        result=result, uncertain_target_effects=True)
            if (result.status == FixedABIStatus.OK and
                    opcode == self.SWD_LINE_RESET and result.data_valid):
                self.poisoned = True
                raise FixedABIError("Line reset unexpectedly returned data",
                                    result=result, uncertain_target_effects=True)

            # ACK clears completion validity, NOT the sticky Site FAULT.
            self._write(self.ACK_SEQ, sequence)
            if state == self.FAULT or result.status in self.FATAL:
                self.poisoned = True
                raise FixedABIError("Site FAULT; independent recovery required",
                                    result=result, uncertain_target_effects=True)
            return result

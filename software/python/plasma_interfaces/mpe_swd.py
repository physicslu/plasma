"""PLASMA MPE v1 transaction-level PS control API (HOST-ONLY CANDIDATE).

NEW hardware ABI: no legacy GPIO, WordPort bitbang, SWD-03 or fixed-image
driver imported. A qualified caller injects an independently owned 32-bit
device-MMIO port plus ARMv7 DMB. No device is opened during construction.
This module is NOT an OpenOCD adapter, UIO binding or hardware admission.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from threading import RLock
from typing import Protocol


MPE_BASE = 0x43C00000
MPE_MAGIC = 0x4D504531
MPE_ABI = 0x00010000


class MpeWordAccess(Protocol):
    def read32(self, address: int) -> int: ...
    def write32(self, address: int, value: int) -> None: ...
    def write_barrier(self) -> None: ...


class MpeStatus(IntEnum):
    OK = 0
    BAD_CONFIG = 1
    NEED_RESET = 2
    SWD_WAIT = 3
    SWD_FAULT = 4
    BAD_ACK = 5
    PARITY = 6
    TIMEOUT = 7
    ABORTED = 8


@dataclass(frozen=True)
class MpeResult:
    site_id: int
    tag: int
    status: MpeStatus
    ack: int
    data: int
    data_valid: bool
    attempts: int
    link_state: int


class MpeAccessError(RuntimeError):
    """Unknown result or false admission; never permission to replay writes."""


class MpeSWDController:
    """One explicitly admitted Site context; one command in flight.

    External Broker owns global FPGA mapping and per-Site lease. The driver's
    RLock only serializes calls on this object, not the shared address space.
    A bounded poll loop does NOT bound a hung ARM AXI transaction.
    """

    SITE_STRIDE = 0x1000
    STATUS = 0x04
    HALF = 0x08
    TIMEOUT = 0x0C
    TX = 0x10
    PUSH = 0x14
    META = 0x18
    RX = 0x1C
    POP = 0x20
    CONTROL = 0x28
    ERROR = 0x2C
    IDLE = 0
    FAULT_STATUSES = frozenset((MpeStatus.PARITY, MpeStatus.TIMEOUT,
                                MpeStatus.ABORTED, MpeStatus.BAD_ACK))

    def __init__(self, port: MpeWordAccess, *, site_id: int,
                 max_polls: int = 100000) -> None:
        if type(site_id) is not int or site_id not in (1, 2):
            raise ValueError("This Z2 Image implements only Site 1 or Site 2")
        if type(max_polls) is not int or not 1 <= max_polls <= 1000000:
            raise ValueError("Bounded polling budget required")
        if port is None or not all(callable(getattr(port, name, None)) for name
                                   in ("read32", "write32", "write_barrier")):
            raise TypeError("Qualified explicit 32-bit MMIO + barrier required")
        self._port = port
        self.site_id = site_id
        self.base = MPE_BASE + self.SITE_STRIDE * site_id
        self.max_polls = max_polls
        self.poisoned = False
        self._used_tags: set[int] = set()
        self._lock = RLock()
        # Intentionally no implicit I/O, FPGA load, network or credentials.

    def _check_active(self) -> None:
        if self.poisoned:
            raise MpeAccessError("MPE owner poisoned; independent recovery required")

    def _read(self, absolute: int) -> int:
        try:
            value = self._port.read32(absolute)
            if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                raise ValueError("Malformed native 32-bit result")
            return value
        except BaseException as exc:
            self.poisoned = True
            raise MpeAccessError("Uncertain MPE device read; recovery required") from exc

    def _write(self, absolute: int, value: int) -> None:
        try:
            self._port.write32(absolute, value)
        except BaseException as exc:
            self.poisoned = True
            raise MpeAccessError("Uncertain MPE device write; recovery required") from exc

    def _barrier(self) -> None:
        try:
            self._port.write_barrier()
        except BaseException as exc:
            self.poisoned = True
            raise MpeAccessError("MPE write-ordering barrier failure") from exc

    def probe(self) -> None:
        """Identity is necessary but not sufficient for hardware admission."""
        with self._lock:
            self._check_active()
            if (self._read(MPE_BASE) != MPE_MAGIC or
                    self._read(MPE_BASE + 4) != MPE_ABI or
                    self._read(MPE_BASE + 8) != 3 or
                    self._read(self.base) != (0x00010000 | self.site_id)):
                self.poisoned = True
                raise MpeAccessError("MPE Image / Site / ABI identity mismatch")

    def enable(self) -> None:
        """Explicit owner-directed enable; never turn on attached DUT power."""
        with self._lock:
            self.probe()
            status = self._read(self.base + self.STATUS)
            if status & 0xE:
                self.poisoned = True
                raise MpeAccessError("Site not quiescent or sticky FAULT")
            self._write(self.base + self.CONTROL, 1)
            self._barrier()
            if self._read(self.base + self.STATUS) & 0xF != 1:
                self.poisoned = True
                raise MpeAccessError("Site enable failed")

    @staticmethod
    def _validate(tag: int, *, line_reset: bool, ap: bool, read: bool,
                  address: int, data: int, half: int, timeout: int) -> None:
        if type(tag) is not int or not 1 <= tag <= 0xFFFF:
            raise ValueError("Nonzero 16-bit tag required")
        if not all(type(flag) is bool for flag in (line_reset, ap, read)):
            raise TypeError("SWD operation flags must be explicit bool")
        if type(address) is not int or address not in (0, 4, 8, 12):
            raise ValueError("SWD DP/AP address must be 0,4,8 or 12")
        if type(data) is not int or not 0 <= data <= 0xFFFFFFFF:
            raise ValueError("Exact u32 payload required")
        if line_reset and (ap or read or address or data):
            raise ValueError("LINE_RESET must not carry DP/AP or payload")
        if read and data:
            raise ValueError("Read commands have no write data")
        if type(half) is not int or not 2 <= half <= 0xFFFF:
            raise ValueError("SWCLK half-period must be 2..65535")
        if type(timeout) is not int or not 1 <= timeout <= 0xFFFFFFFF:
            raise ValueError("Nonzero hardware timeout required")

    def transact(self, *, tag: int, line_reset: bool = False, ap: bool = False,
                 read: bool = False, address: int = 0, data: int = 0,
                 half: int = 500, timeout: int = 1000000) -> MpeResult:
        """Submit exactly one atomic tagged command and return raw SWD result.

        WAIT/FAULT are reported without automatic retry. A timeout on a write
        never implies target flash or DP side-effects can be undone.
        """
        self._validate(tag, line_reset=line_reset, ap=ap, read=read,
                       address=address, data=data, half=half, timeout=timeout)
        with self._lock:
            self._check_active()
            if tag in self._used_tags:
                raise ValueError("Tag must be unique within this owner epoch")
            self.probe()
            status = self._read(self.base + self.STATUS)
            if status != 1:
                self.poisoned = bool(status & 8)
                raise MpeAccessError("Site not ENABLED/IDLE; refuse launch")
            command = ((tag << 16) | (0x100 if line_reset else 0) |
                       ((address >> 2) << 2) | (2 if read else 0) |
                       (1 if ap else 0))
            for offset, value in (
                (self.HALF, half), (self.TIMEOUT, timeout), (self.TX, data),
            ):
                self._write(self.base + offset, value)
            self._barrier()
            # Mark tag consumed even if a subsequently reported write fails.
            self._used_tags.add(tag)
            self._write(self.base + self.PUSH, command)
            self._barrier()
            for _ in range(self.max_polls):
                state = self._read(self.base + self.STATUS)
                if state & 4:
                    break
                if state & 8 and not state & 4:
                    self.poisoned = True
                    raise MpeAccessError("Sticky hardware fault before completion")
            else:
                self.poisoned = True
                raise MpeAccessError("Completion poll budget exhausted; uncertain write effect")
            word0 = self._read(self.base + self.META)
            value = self._read(self.base + self.RX)
            word1 = self._read(self.base + self.META)
            if (word0 != word1 or (word0 >> 16) != tag or
                    (word0 >> 14) & 3 or (word0 & 0xF) > 8):
                self.poisoned = True
                raise MpeAccessError("Mismatched/unstable completion; do not POP or replay")
            try:
                result = MpeResult(
                    site_id=self.site_id, tag=tag,
                    status=MpeStatus(word0 & 15), ack=(word0 >> 4) & 7,
                    data=value if (word0 >> 7) & 1 else 0,
                    data_valid=bool((word0 >> 7) & 1),
                    attempts=(word0 >> 8) & 15,
                    link_state=(word0 >> 12) & 3,
                )
            except ValueError as exc:
                self.poisoned = True
                raise MpeAccessError("Unexpected completion status") from exc
            if (result.data_valid and (not read or result.status != MpeStatus.OK)
                    or result.data_valid and result.ack != 1):
                self.poisoned = True
                raise MpeAccessError("Invalid data-valid/ACK completion")
            self._write(self.base + self.POP, tag)
            self._barrier()
            if result.status in self.FAULT_STATUSES:
                self.poisoned = True
            return result

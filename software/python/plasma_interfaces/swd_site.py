"""Host-only candidate PS control logic for the independent AXI SWD Site IP.

This module never opens /dev/mem, a device, a socket, or a credential. Its
caller must first own a verified Image/Manifest and exclusive Site lease, and
inject an ARMv7-qualified aligned 32-bit MMIO backend with write barriers.
Host tests cannot qualify the access width, actual Z2 PS7 bus, pads or DUT.

OpenOCD 0.12.0 remote_bitbang is JTAG-only. This is NOT an OpenOCD adapter,
and no legacy WordPort/GPIO fallback is present.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
from threading import RLock
from typing import Protocol


SITE_BASES = {1: 0x43C01000, 2: 0x43C02000}
FCLK_HZ = 100_000_000
MIN_HALF_PERIOD = 4
MAX_HALF_PERIOD = 0xFFFF


class SiteWordAccess(Protocol):
    def read32(self, address: int) -> int: ...
    def write32(self, address: int, value: int) -> None: ...
    def write_barrier(self) -> None: ...


class SiteStatus(IntEnum):
    OK = 0
    BAD_CONFIG = 1
    NEED_RESET = 2
    WAIT = 3
    FAULT = 4
    BAD_ACK = 5
    PARITY = 6
    TIMEOUT = 7
    ABORTED = 8


class SiteAccessError(RuntimeError):
    """Uncertain hardware state; never permission to replay a SWD write."""


@dataclass(frozen=True)
class SiteCompletion:
    tag: int
    status: SiteStatus
    ack: int
    data: int
    data_valid: bool
    attempts: int
    link_state: int


def encode_transfer(*, ap: bool, read: bool, address: int) -> int:
    """Private 9-bit command encoding; caller owns target retry policy."""
    if type(ap) is not bool or type(read) is not bool:
        raise TypeError("ap and read must be explicit booleans")
    if type(address) is not int or address not in (0, 4, 8, 12):
        raise ValueError("SWD DP/AP address must be 0, 4, 8 or 12")
    return int(ap) | (int(read) << 1) | ((address >> 2) << 2)


def encode_swj(bit_count: int) -> int:
    """0 means 64 ones for line reset; 1..32 means TX_DATA LSB-first."""
    if type(bit_count) is not int or not 0 <= bit_count <= 32:
        raise ValueError("Only atomic 1..32-bit SWJ or line reset supported")
    return 0x100 | bit_count


def decode_completion(meta: int, data: int) -> SiteCompletion:
    try:
        status = SiteStatus(meta & 0xF)
    except ValueError as exc:
        raise SiteAccessError("Unknown SWD completion status") from exc
    return SiteCompletion(tag=meta >> 16, status=status,
                          ack=(meta >> 4) & 7, data=data,
                          data_valid=bool((meta >> 7) & 1),
                          attempts=(meta >> 8) & 15,
                          link_state=(meta >> 12) & 3)


class SwdSiteController:
    """One Site, one exclusive external lease; no implicit device operations.

    All methods performing MMIO serialize through a local lock; that lock is
    NOT a cross-process Site lease. A failed MMIO operation poisons the object.
    A write with an uncertain outcome is never retried automatically.
    """

    ID = 0x00
    STATUS = 0x04
    HALF = 0x08
    TIMEOUT = 0x0C
    TX = 0x10
    PUSH = 0x14
    META = 0x18
    RX = 0x1C
    POP = 0x20
    LEVELS = 0x24
    CONTROL = 0x28
    ERROR = 0x2C
    IRQ_ENABLE = 0x30
    IRQ_PENDING = 0x34
    MODE = 0x38
    DEBUG_DRIVE = 0x3C
    DEBUG_SAMPLE = 0x40

    def __init__(self, port: SiteWordAccess, *, site_id: int,
                 max_polls: int = 100_000) -> None:
        if type(site_id) is not int or site_id not in SITE_BASES:
            raise ValueError("Only physical Site 1 and 2 are implemented")
        if type(max_polls) is not int or not 1 <= max_polls <= 1_000_000:
            raise ValueError("Bounded positive poll count required")
        if not all(callable(getattr(port, name, None)) for name in
                   ("read32", "write32", "write_barrier")):
            raise TypeError("Explicit qualified 32-bit MMIO port required")
        self.port = port
        self.site_id = site_id
        self.base = SITE_BASES[site_id]
        self.max_polls = max_polls
        self.poisoned = False
        self._tags: set[int] = set()
        self._in_order: list[int] = []
        self._lock = RLock()

    def _check(self) -> None:
        if self.poisoned:
            raise SiteAccessError("Site state uncertain; external recovery required")

    def _read(self, offset: int) -> int:
        self._check()
        try:
            value = self.port.read32(self.base + offset)
            if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                raise ValueError("Invalid 32-bit MMIO read")
            return value
        except BaseException as exc:
            self.poisoned = True
            raise SiteAccessError("Uncertain MMIO read; no retry") from exc

    def _write(self, offset: int, value: int) -> None:
        self._check()
        try:
            if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                raise ValueError("Invalid 32-bit MMIO write")
            self.port.write32(self.base + offset, value)
            self.port.write_barrier()
        except BaseException as exc:
            self.poisoned = True
            raise SiteAccessError("Uncertain MMIO write; no replay") from exc

    def probe(self) -> None:
        """Identity check only, NOT FPGA Image/electrical authorization."""
        with self._lock:
            if self._read(self.ID) != (0x00030000 | self.site_id):
                self.poisoned = True
                raise SiteAccessError("Incorrect independent SWD Site identity")

    def enter_normal(self, *, irq: bool = False) -> None:
        with self._lock:
            if self._read(self.MODE) != 0:
                raise SiteAccessError("Site must be disabled and externally leased")
            self._write(self.MODE, 1)
            self._write(self.IRQ_ENABLE, int(irq))
            self._write(self.CONTROL, 1)
            if self._read(self.MODE) != 1 or not self._read(self.STATUS) & 1:
                self.poisoned = True
                raise SiteAccessError("Normal mode admission failed")

    def set_clock_hz(self, target_hz: int) -> int:
        """Round *down* to an achievable per-Site SWCLK; no DUT qualification."""
        if type(target_hz) is not int or target_hz <= 0:
            raise ValueError("Positive integral SWCLK required")
        if target_hz > 12_500_000:
            raise ValueError("Unqualified request above 12.5MHz design ceiling")
        period = (FCLK_HZ + (2 * target_hz) - 1) // (2 * target_hz)
        if not MIN_HALF_PERIOD <= period <= MAX_HALF_PERIOD:
            raise ValueError("SWCLK outside provisional 12.5MHz divider range")
        with self._lock:
            self._write(self.HALF, period)
            if self._read(self.HALF) != period:
                self.poisoned = True
                raise SiteAccessError("SWCLK divider readback mismatch")
        return FCLK_HZ // (2 * period)

    def enqueue(self, *, tag: int, command: int, data: int = 0) -> None:
        if type(tag) is not int or not 1 <= tag <= 0xFFFF:
            raise ValueError("Nonzero 16-bit command tag required")
        if type(command) is not int or not 0 <= command <= 0x1FF:
            raise ValueError("Invalid command bits")
        if command & 0x100:
            if (command & 255) > 32:
                raise ValueError("Unsupported atomic SWJ length")
        elif command & 0xF0:
            raise ValueError("Reserved DP/AP command bits")
        if type(data) is not int or not 0 <= data <= 0xFFFFFFFF:
            raise ValueError("32-bit TX word required")
        with self._lock:
            if tag in self._tags:
                raise ValueError("Reusing command tag could replay/alias a write")
            levels = self._read(self.LEVELS)
            if ((levels >> 7) & 31) == 16 or self._read(self.MODE) != 1:
                raise SiteAccessError("Site not in normal mode or command FIFO full")
            if self._read(self.ERROR) & 1:
                raise SiteAccessError("Fault latched; no enqueue")
            self._write(self.TX, data)
            self._write(self.PUSH, (tag << 16) | command)
            # Acknowledged device write is not proof of DUT execution.
            self._tags.add(tag)
            self._in_order.append(tag)

    def next_completion(self) -> SiteCompletion:
        with self._lock:
            for _ in range(self.max_polls):
                if self._read(self.LEVELS) & 2:
                    break
            else:
                self.poisoned = True
                raise SiteAccessError("No completion within bounded host polls")
            meta = self._read(self.META)
            data = self._read(self.RX)
            try:
                result = decode_completion(meta, data)
            except SiteAccessError:
                self.poisoned = True
                raise
            if not self._in_order or result.tag != self._in_order[0]:
                self.poisoned = True
                raise SiteAccessError("Unexpected response tag/order; recovery required")
            self._write(self.POP, result.tag)
            self._in_order.pop(0)
            return result

    def ack_irq(self) -> None:
        with self._lock:
            if self._read(self.IRQ_PENDING) & 1:
                self._write(self.IRQ_PENDING, 1)

    def disable_if_idle(self) -> None:
        with self._lock:
            if self._in_order or self._read(self.LEVELS) != 0:
                raise SiteAccessError("Pending commands or completions")
            self._write(self.CONTROL, 0)
            self._write(self.MODE, 0)

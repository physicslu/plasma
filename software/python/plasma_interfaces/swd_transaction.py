"""SWD-05: PS-side SWD-03 AXI4-Lite transaction driver (transport only).

One instance owns exactly one Site's transaction aperture and serialized
command/response state. An MMIO backend MUST be explicitly injected; there
is deliberately no /dev/mem, UIO, PYNQ overlay, FPGA-load or service path here.
No target Flash, OpenOCD, power/voltage or programming qualification is implied.

The AXI backend must provide synchronous 32-bit read32/write32 operations,
including raising on AXI SLVERR/DECERR. A Python deadline does not bound
a Linux AXI bus stall. Do not use with physical Z2 before approved HIL.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum
import time
from typing import Callable, Protocol


class WordMMIO(Protocol):
    def read32(self, address: int) -> int: ...
    def write32(self, address: int, value: int) -> None: ...


class SWDStatus(IntEnum):
    OK = 0
    BAD_CONFIG = 1
    NEED_RESET = 2
    WAIT_LIMIT = 3
    FAULT = 4
    BAD_ACK = 5
    PARITY = 6
    TIMEOUT = 7
    ABORTED = 8
    PHY_ERROR = 9


class SWDAck(IntEnum):
    NONE = 0
    OK = 1
    WAIT = 2
    FAULT = 4


class SWDLink(IntEnum):
    RESET_REQUIRED = 0
    DPIDR_REQUIRED = 1
    CONNECTED = 2


@dataclass(frozen=True)
class SWDTiming:
    half_period_cycles: int = 2
    turnaround_cycles: int = 1
    idle_cycles: int = 8
    max_wait_retries: int = 0
    timeout_cycles: int = 1_000_000
    error_data_phase: bool = False

    def __post_init__(self) -> None:
        for key, value, lower, upper in (
            ("half_period_cycles", self.half_period_cycles, 2, 65535),
            ("turnaround_cycles", self.turnaround_cycles, 1, 4),
            ("idle_cycles", self.idle_cycles, 8, 255),
            ("max_wait_retries", self.max_wait_retries, 0, 255),
            ("timeout_cycles", self.timeout_cycles, 1, 0xFFFFFFFF),
        ):
            if type(value) is not int or not lower <= value <= upper:
                raise ValueError(f"{key} must be {lower}..{upper}")
        if type(self.error_data_phase) is not bool:
            raise ValueError("error_data_phase must be bool")


@dataclass(frozen=True)
class SWDResponse:
    status: SWDStatus
    ack: int
    data_valid: bool
    attempts: int
    rdata: int
    link_state: SWDLink


class SWDDriverError(RuntimeError):
    """A hardware or protocol failure. No automatic command replay."""

    def __init__(self, reason: str, *,
                 uncertain_target_effects: bool = False,
                 response: SWDResponse | None = None) -> None:
        super().__init__(reason)
        self.uncertain_target_effects = uncertain_target_effects
        self.response = response


class SWDTransactionDriver:
    """SWD-03 ABI v1 driver. Never auto-reset, clear sticky state or replay writes.

    For AP reads, use read_ap_raw() to get the *posted* wire result; the
    read_ap_posted() helper explicitly reads DP RDBUFF after issuing AP READ.
    Neither operation performs MEM-AP address/bank selection.
    """

    ABI = 0x00
    COMMAND = 0x04
    CONFIG = 0x08
    WDATA = 0x0C
    HALF = 0x10
    TURN = 0x14
    IDLE = 0x18
    RETRIES = 0x1C
    TIMEOUT = 0x20
    STATUS = 0x24
    META = 0x28
    RDATA = 0x2C

    START = 1
    ABORT = 2
    ACK_RESPONSE = 4

    BUSY_BIT = 0x1
    READY_BIT = 0x2
    RESP_VALID_BIT = 0x4

    def __init__(
        self,
        backend: WordMMIO,
        *,
        base: int = 0x40003000,
        site_id: int = 1,
        timing: SWDTiming | None = None,
        poll_budget: int = 10000,
        poll_interval_s: float = 0.0005,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        max_poll_seconds: float = 2.0,
    ) -> None:
        if backend is None or not callable(getattr(backend, "read32", None)) \
                or not callable(getattr(backend, "write32", None)):
            raise ValueError("Explicit read32/write32 MMIO backend is required")
        if type(base) is not int or base < 0 or base > 0xFFFFF000 \
                or base & 0xFFF:
            raise ValueError("Base must be a 4KiB-aligned physical address")
        if type(site_id) is not int or not 1 <= site_id <= 8:
            raise ValueError("Site ID must be one-based (1..8)")
        if type(poll_budget) is not int or not 1 <= poll_budget <= 100000:
            raise ValueError("Invalid bounded poll budget")
        if not 0 <= poll_interval_s <= 0.05 or not 0 < max_poll_seconds <= 60:
            raise ValueError("Invalid polling deadline")
        if not callable(clock) or not callable(sleep):
            raise ValueError("clock and sleep must be callable")
        self.backend = backend
        self.base = base
        self.site_id = site_id
        self.timing = timing if timing is not None else SWDTiming()
        self.poll_budget = poll_budget
        self.poll_interval_s = poll_interval_s
        self.max_poll_seconds = max_poll_seconds
        self._clock, self._sleep = clock, sleep
        self._poisoned = False
        self._launched = False
        self._write_issued = False
        self._was_write = False
        # Never write or initialize a hardware register during construction.
        if self._read(self.ABI) != 1:
            raise SWDDriverError("SWD-03 AXI ABI mismatch; expected version 1")

    @property
    def poisoned(self) -> bool:
        """Uncertain AXI/target state: refuse further operations."""
        return self._poisoned

    def _read(self, offset: int) -> int:
        try:
            value = self.backend.read32(self.base + offset)
        except Exception as exc:
            self._poisoned = True
            raise SWDDriverError(
                f"AXI MMIO read failed at +0x{offset:02X}",
                uncertain_target_effects=self._write_issued,
            ) from exc
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            self._poisoned = True
            raise SWDDriverError("MMIO backend returned invalid 32-bit value")
        return value

    def _write(self, offset: int, value: int) -> None:
        try:
            self.backend.write32(self.base + offset, value)
        except Exception as exc:
            self._poisoned = True
            raise SWDDriverError(
                f"AXI MMIO write failed at +0x{offset:02X}",
                uncertain_target_effects=self._write_issued,
            ) from exc

    def _state(self) -> tuple[int, SWDLink]:
        word = self._read(self.STATUS)
        if word & ~0x1F:
            self._poisoned = True
            raise SWDDriverError("Reserved SWD STATUS bits are set")
        raw_link = (word >> 3) & 3
        if raw_link == 3:
            self._poisoned = True
            raise SWDDriverError("Invalid SWD link-state encoding")
        if (word & self.READY_BIT) and (word & (self.BUSY_BIT | self.RESP_VALID_BIT)):
            self._poisoned = True
            raise SWDDriverError("Inconsistent hardware READY/BUSY/RESP_VALID")
        return word, SWDLink(raw_link)

    def _require_ready(self) -> SWDLink:
        if self._poisoned:
            raise SWDDriverError("Driver poisoned; require hardware/OS recovery")
        bits, link = self._state()
        if not bits & self.READY_BIT or bits & (self.BUSY_BIT | self.RESP_VALID_BIT):
            raise SWDDriverError("SWD transaction not idle; no implicit abort")
        return link

    def _poll_response(self) -> SWDResponse:
        deadline = self._clock() + self.max_poll_seconds
        for _ in range(self.poll_budget):
            status, link = self._state()
            if status & self.RESP_VALID_BIT:
                meta = self._read(self.META)
                data = self._read(self.RDATA)
                check_status, check_link = self._state()
                if not check_status & self.RESP_VALID_BIT or check_link != link \
                        or self._read(self.META) != meta \
                        or self._read(self.RDATA) != data:
                    self._poisoned = True
                    raise SWDDriverError("Response changed before explicit ACK",
                                         uncertain_target_effects=self._write_issued)
                status_code = meta & 0xF
                if status_code not in SWDStatus._value2member_map_:
                    self._poisoned = True
                    raise SWDDriverError("Unknown hardware SWD response status")
                attempts = (meta >> 8) & 0x1FF
                if meta >> 17:
                    self._poisoned = True
                    raise SWDDriverError("Response META reserved bits set")
                return SWDResponse(
                    status=SWDStatus(status_code), ack=(meta >> 4) & 7,
                    data_valid=bool(meta & 0x80), attempts=attempts,
                    rdata=data, link_state=link,
                )
            if self._clock() >= deadline:
                break
            if self.poll_interval_s:
                self._sleep(self.poll_interval_s)
        self._poisoned = True
        raise SWDDriverError(
            "SWD response polling deadline exhausted; no implicit ABORT/replay",
            uncertain_target_effects=self._write_issued,
        )

    def _finish(self) -> SWDResponse:
        result = self._poll_response()
        # Only after stable response snapshot: ACK explicitly, never reissue
        # command. An AXI error while ACKing may mean it was consumed.
        self._write(self.COMMAND, self.ACK_RESPONSE)
        self._launched = False
        self._write_issued = False
        current, _ = self._state()
        if current & (self.BUSY_BIT | self.RESP_VALID_BIT) \
                or not current & self.READY_BIT:
            self._poisoned = True
            raise SWDDriverError("SWD response not consumed after ACK")
        if result.status is not SWDStatus.OK:
            raise SWDDriverError(
                f"SWD transaction {result.status.name}: ACK={result.ack} attempts={result.attempts}",
                uncertain_target_effects=result.status in {
                    SWDStatus.TIMEOUT, SWDStatus.ABORTED,
                    SWDStatus.BAD_ACK, SWDStatus.PARITY, SWDStatus.PHY_ERROR,
                } and self._was_write,
                response=result,
            )
        return result

    def _execute(self, *, op: int, ap: bool = False, read: bool = False,
                 address: int = 0, data: int = 0) -> SWDResponse:
        link = self._require_ready()
        if type(op) is not int or op not in (0, 1):
            raise ValueError("op must be 0=transfer or 1=line reset")
        if type(ap) is not bool or type(read) is not bool:
            raise ValueError("AP/read flags must be bool")
        if type(address) is not int or address not in (0, 4, 8, 12):
            raise ValueError("SWD address must be aligned 0,4,8,12")
        if type(data) is not int or not 0 <= data <= 0xFFFFFFFF:
            raise ValueError("SWD write data must be u32")
        if op == 0 and link is SWDLink.RESET_REQUIRED:
            raise SWDDriverError("SWD link requires explicit line_reset()")
        if op == 0 and link is SWDLink.DPIDR_REQUIRED \
                and (ap or not read or address != 0):
            raise SWDDriverError("SWD link requires DP DPIDR read first")
        if op == 0 and link is SWDLink.CONNECTED and not read and ap:
            # AP writes are supported by the transport; no automatic retry.
            pass
        config = (op | (int(ap) << 1) | (int(read) << 2)
                  | (address << 3)
                  | (int(self.timing.error_data_phase) << 7))
        # A configuration write is only legal while hardware idle. Snapshot
        # all registers; no concurrent software user may share this aperture.
        self._was_write = (op == 0 and not read)
        self._write_issued = False
        for offset, value in (
            (self.CONFIG, config), (self.WDATA, data),
            (self.HALF, self.timing.half_period_cycles),
            (self.TURN, self.timing.turnaround_cycles),
            (self.IDLE, self.timing.idle_cycles),
            (self.RETRIES, self.timing.max_wait_retries),
            (self.TIMEOUT, self.timing.timeout_cycles),
        ):
            self._write(offset, value)
        # START may have reached hardware even if backend reports an error.
        self._write_issued = self._was_write
        self._launched = True
        self._write(self.COMMAND, self.START)
        return self._finish()

    def line_reset(self) -> SWDResponse:
        return self._execute(op=1)

    def read_dp(self, address: int) -> int:
        result = self._execute(op=0, read=True, address=address)
        if result.ack != SWDAck.OK or not result.data_valid or result.attempts < 1:
            self._poisoned = True
            raise SWDDriverError("SWD DP read: invalid successful metadata",
                                 response=result)
        return result.rdata

    def write_dp(self, address: int, value: int) -> SWDResponse:
        result = self._execute(op=0, address=address, data=value)
        if result.ack != SWDAck.OK or result.data_valid or result.attempts < 1:
            self._poisoned = True
            raise SWDDriverError("SWD DP write: invalid successful metadata",
                                 uncertain_target_effects=True, response=result)
        return result

    def read_ap_raw(self, address: int) -> int:
        """Return raw SWD wire response, which may be a previous AP result."""
        result = self._execute(op=0, ap=True, read=True, address=address)
        if result.ack != SWDAck.OK or not result.data_valid or result.attempts < 1:
            self._poisoned = True
            raise SWDDriverError("SWD AP read: invalid successful metadata",
                                 response=result)
        return result.rdata

    def read_ap_posted(self, address: int) -> int:
        """Issue raw AP read then DP RDBUFF; not a memory-operation API."""
        self.read_ap_raw(address)
        return self.read_dp(12)

    def write_ap_raw(self, address: int, value: int) -> SWDResponse:
        result = self._execute(op=0, ap=True, address=address, data=value)
        if result.ack != SWDAck.OK or result.data_valid or result.attempts < 1:
            self._poisoned = True
            raise SWDDriverError("SWD AP write: invalid successful metadata",
                                 uncertain_target_effects=True, response=result)
        return result

    def abort(self) -> SWDResponse:
        """Explicit local cancellation, *only* when STATUS confirms BUSY.

        No auto-abort after poll/AXI error; those cases may require out-of-band
        hardware recovery. Aborted writes can have target-side effects.
        """
        if self._poisoned:
            raise SWDDriverError("Driver poisoned; cannot safely issue ABORT")
        status, _ = self._state()
        if not status & self.BUSY_BIT or status & self.RESP_VALID_BIT:
            raise SWDDriverError("ABORT only allowed for a known active command")
        # Existing in-flight target effects cannot be excluded.
        self._was_write = True
        self._write_issued = True
        self._write(self.COMMAND, self.ABORT)
        return self._finish()

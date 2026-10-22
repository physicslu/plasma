"""LT02 PS→PL scratchpad transport over an injected native 32-bit MMIO lease.

This is NOT a PL REST endpoint and has no implicit hardware access. In
particular it never opens /dev/mem, changes FPGA images or retries writes.
"""
from __future__ import annotations

from dataclasses import dataclass
from time import perf_counter_ns
from threading import Lock
from typing import Protocol
import zlib

from .linux_mmio import MMIOAperture

MAGIC = 0x4C543032
ABI_VERSION = 0x00010000
CAPABILITIES = 0x00000001
CAPACITY = 2048
MAX_CASE_BYTES = 1024 * 1024
WINDOW_START = 0x100

REG_MAGIC = 0x00
REG_ABI = 0x04
REG_CAPABILITIES = 0x08
REG_CAPACITY = 0x0C
REG_COMMAND = 0x10
REG_STATUS = 0x14
REG_WRITES = 0x18
REG_READS = 0x1C

_READABLE = frozenset({REG_MAGIC, REG_ABI, REG_CAPABILITIES, REG_CAPACITY,
                       REG_STATUS, REG_WRITES, REG_READS}
                      | set(range(WINDOW_START, WINDOW_START + CAPACITY, 4)))
_WRITABLE = frozenset({REG_COMMAND}
                      | set(range(WINDOW_START, WINDOW_START + CAPACITY, 4)))


class LoopTestError(RuntimeError):
    """Fail-closed: no implicit retry after a potentially completed write."""


class WordPort(Protocol):
    def read32(self, address: int) -> int: ...
    def write32(self, address: int, value: int) -> None: ...


def loopback_aperture(base: int) -> MMIOAperture:
    """Exact LinuxMMIO allowlist; no mappings created by this function."""
    if type(base) is not int or base < 0 or base > 0xFFFFF000 or base & 0xFFF:
        raise ValueError("LT02 base must be a 4KiB-aligned u32 aperture")
    return MMIOAperture(base, readable=_READABLE, writable=_WRITABLE)


@dataclass(frozen=True)
class LoopTestResult:
    payload: bytes
    payload_length: int
    chunks: int
    data_word_writes: int
    data_word_reads: int
    tx_crc32: str
    rx_crc32: str
    elapsed_ns: int


class LoopTestDriver:
    """Synchronous Site transport; caller must bind an approved independent aperture.

    Site ID validation does NOT authorize a physical Site: the caller must
    independently verify the loaded FPGA manifest and actual HWH.
    """

    def __init__(self, port: WordPort, *, base: int, site_id: int = 1) -> None:
        if type(site_id) is not int or not 1 <= site_id <= 8:
            raise LoopTestError("LT02 Site ID must be one-based 1..8")
        loopback_aperture(base)
        self._port = port
        self.base = base
        self.site_id = site_id
        self._case_lock = Lock()
        self._poisoned = False
        for offset, expected in (
            (REG_MAGIC, MAGIC), (REG_ABI, ABI_VERSION),
            (REG_CAPABILITIES, CAPABILITIES), (REG_CAPACITY, CAPACITY),
        ):
            actual = self._read(offset)
            if actual != expected:
                raise LoopTestError(
                    f"LT02 register 0x{offset:03X} mismatch: "
                    f"expected 0x{expected:08X}, got 0x{actual:08X}"
                )
        if self._read(REG_STATUS) != 1:
            raise LoopTestError("LT02 is not ready")

    def _read(self, offset: int) -> int:
        value = self._port.read32(self.base + offset)
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise LoopTestError("Malformed 32-bit MMIO result")
        return value

    def _write(self, offset: int, word: int) -> None:
        if type(word) is not int or not 0 <= word <= 0xFFFFFFFF:
            raise LoopTestError("Word outside 32-bit range")
        self._port.write32(self.base + offset, word)

    @property
    def poisoned(self) -> bool:
        """After an uncertain data-path failure, this instance cannot be reused."""
        with self._case_lock:
            return self._poisoned

    def echo(self, payload: bytes) -> LoopTestResult:
        """Serialize cases; poison on uncertain data-path errors, never retry."""
        with self._case_lock:
            if self._poisoned:
                raise LoopTestError("LT02 driver poisoned; explicit hardware recovery required")
            # Caller mistakes must not poison hardware that was never accessed.
            if not isinstance(payload, bytes):
                raise TypeError("payload must be immutable bytes")
            if not 1 <= len(payload) <= MAX_CASE_BYTES:
                raise ValueError("payload length must be 1..1048576 bytes")
            try:
                return self._echo_exclusive(payload)
            except BaseException:
                # A write may have completed before the exception. Invalidate
                # this driver rather than accidentally replaying a partial case.
                self._poisoned = True
                raise

    def _echo_exclusive(self, payload: bytes) -> LoopTestResult:
        """Write once, read once and verify PL counters for each bounded chunk.

        Raises on the FIRST mismatch. Never retry, even on an MMIO exception:
        hardware write completion may be uncertain. The caller owns recovery.
        """
        if not isinstance(payload, bytes):
            raise TypeError("payload must be immutable bytes")
        if not 1 <= len(payload) <= MAX_CASE_BYTES:
            raise ValueError("payload length must be 1..1048576 bytes")
        start = perf_counter_ns()
        chunks = 0
        words_written = words_read = 0
        received = bytearray()
        for origin in range(0, len(payload), CAPACITY):
            chunk = payload[origin:origin + CAPACITY]
            words = (len(chunk) + 3) // 4
            before_writes = self._read(REG_WRITES)
            before_reads = self._read(REG_READS)
            for index in range(words):
                part = chunk[4 * index:4 * index + 4]
                self._write(WINDOW_START + 4 * index,
                            int.from_bytes(part.ljust(4, bytes(1)), "little"))
            for index in range(words):
                received.extend(self._read(WINDOW_START + 4 * index).to_bytes(4, "little"))
            # Trim padding per chunk, not just once at the end.
            del received[origin + len(chunk):]
            after_writes = self._read(REG_WRITES)
            after_reads = self._read(REG_READS)
            if ((after_writes - before_writes) & 0xFFFFFFFF) != words:
                raise LoopTestError(f"LT02 chunk {chunks}: DATA write count mismatch")
            if ((after_reads - before_reads) & 0xFFFFFFFF) != words:
                raise LoopTestError(f"LT02 chunk {chunks}: DATA read count mismatch")
            if received[origin:origin + len(chunk)] != chunk:
                raise LoopTestError(f"LT02 chunk {chunks}: payload mismatch")
            chunks += 1
            words_written += words
            words_read += words
        output = bytes(received)
        elapsed = perf_counter_ns() - start
        return LoopTestResult(
            payload=output, payload_length=len(payload), chunks=chunks,
            data_word_writes=words_written, data_word_reads=words_read,
            tx_crc32=f"{zlib.crc32(payload):08x}",
            rx_crc32=f"{zlib.crc32(output):08x}",
            elapsed_ns=elapsed,
        )

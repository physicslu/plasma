"""PLASMA native Linux MMIO: one process owner, many independently claimed Sites.

Hardware access is NEVER automatic. The caller must supply immutable register
allowlists, open the backend explicitly and bind each Site to one aperture.
The backend is not an FPGA loader and never configures clocks, power or PL.

A native memoryview('I') emits the desired 32-bit accesses on the *qualified*
ARMv7 CPython build; Python does not guarantee access width, memory barriers or
device mappings on arbitrary platforms. AXI aborts may SIGBUS or hang Linux;
they cannot reliably be caught by a Python exception or poll timeout.
"""
from __future__ import annotations

from dataclasses import dataclass
import fcntl
import mmap
import os
from pathlib import Path
import sys
from threading import RLock
from typing import Iterable


class MMIOError(RuntimeError):
    """Rejected operation, ownership conflict, or recoverable MMIO failure."""


class MMIOClosed(MMIOError):
    """The backend/lease is no longer usable after close or PL reload."""


def _u32(value: int, name: str) -> int:
    if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
        raise MMIOError(f"{name} must be an unsigned 32-bit integer")
    return value


@dataclass(frozen=True)
class MMIOAperture:
    """An approved page-aligned AXI4-Lite window and exact register offsets.

    The read/write sets are independent: write-only COMMAND and read-only
    STATUS must not be conflated. Offsets are bytes relative to base.
    """

    base: int
    readable: frozenset[int]
    writable: frozenset[int]
    size: int = 4096

    def __post_init__(self) -> None:
        _u32(self.base, "aperture base")
        if self.base % mmap.ALLOCATIONGRANULARITY:
            raise MMIOError("aperture base must be page aligned")
        if type(self.size) is not int or self.size <= 0 \
                or self.size % mmap.ALLOCATIONGRANULARITY \
                or self.base + self.size > 0x100000000:
            raise MMIOError("aperture size/range must be page aligned and bounded")
        if type(self.readable) is not frozenset or type(self.writable) is not frozenset:
            raise MMIOError("register offsets must be immutable frozensets")
        if not (self.readable or self.writable):
            raise MMIOError("empty register allowlist")
        for offset in self.readable | self.writable:
            if type(offset) is not int or not 0 <= offset <= self.size - 4 \
                    or offset & 3:
                raise MMIOError("register offsets must be aligned 32-bit words")


def swd03_aperture(base: int) -> MMIOAperture:
    """Construct the SWD-03 ABI v1 aperture for a hardware-verified base.

    A logical Site ID does not imply another physical SWD-03 instance exists.
    """
    return MMIOAperture(
        base=base,
        readable=frozenset((0x00, 0x08, 0x0C, 0x10, 0x14, 0x18,
                            0x1C, 0x20, 0x24, 0x28, 0x2C)),
        writable=frozenset((0x04, 0x08, 0x0C, 0x10, 0x14,
                            0x18, 0x1C, 0x20)),
    )


class SiteMMIO:
    """Non-transferable owner token implementing SWD-05 WordMMIO."""

    def __init__(self, parent: LinuxMMIO, base: int, site_id: int) -> None:
        self._parent = parent
        self.base = base
        self.site_id = site_id
        self._active = True

    def read32(self, address: int) -> int:
        with self._parent._mutex:
            self._guard(address)
            return self._parent.read32(address)

    def write32(self, address: int, value: int) -> None:
        with self._parent._mutex:
            self._guard(address)
            self._parent.write32(address, value)

    def _guard(self, address: int) -> None:
        if not self._active:
            raise MMIOClosed("Site lease is released/invalidated")
        if type(address) is not int or not self.base <= address \
                < self.base + self._parent._apertures[self.base].size:
            raise MMIOError("Site MMIO address escapes owned aperture")
        if self._parent._owners.get(self.base) is not self:
            raise MMIOClosed("Site ownership is no longer valid")

    def close(self) -> None:
        with self._parent._mutex:
            if self._parent._owners.get(self.base) is self:
                del self._parent._owners[self.base]
            self._active = False

    def __enter__(self) -> SiteMMIO:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class LinuxMMIO:
    """Thread-safe register access and mapping lifecycle.

    The process lock is cooperative/advisory: external privileged processes,
    a different lock path and kernel drivers are NOT excluded by flock().
    The owner must quiesce all Site drivers before reprogramming the PL.
    Individual read/write calls hold a short-lived RLock; multi-register
    SWD sequences remain serialized by SWDTransactionDriver's Site lock.
    """

    def __init__(
        self,
        apertures: Iterable[MMIOAperture],
        *,
        device: str = "/dev/mem",
        owner_lock: str = "/run/lock/plasma-mmio.lock",
        readonly: bool = False,
    ) -> None:
        items = tuple(apertures)
        if not items:
            raise MMIOError("at least one explicit aperture is required")
        self._apertures: dict[int, MMIOAperture] = {}
        for item in items:
            if not isinstance(item, MMIOAperture):
                raise MMIOError("invalid aperture definition")
            if any(item.base < other.base + other.size and
                   other.base < item.base + item.size
                   for other in self._apertures.values()):
                raise MMIOError("overlapping MMIO apertures")
            self._apertures[item.base] = item
        if type(device) is not str or not device.startswith("/") \
                or type(owner_lock) is not str or not owner_lock.startswith("/"):
            raise MMIOError("device and owner_lock must be absolute paths")
        if type(readonly) is not bool:
            raise MMIOError("readonly must be bool")
        self.device, self.owner_lock, self.readonly = device, owner_lock, readonly
        self._mutex = RLock()
        self._fd: int | None = None
        self._lock_fd: int | None = None
        self._pid: int | None = None
        self._pages: dict[int, mmap.mmap] = {}
        self._words: dict[int, memoryview] = {}
        self._owners: dict[int, SiteMMIO] = {}
        self._poisoned = False
        self._retired = False

    def __enter__(self) -> LinuxMMIO:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def open(self) -> None:
        with self._mutex:
            if self._retired or self._fd is not None:
                raise MMIOClosed("backend is already opened or permanently retired")
            if sys.byteorder != "little":
                raise MMIOError("native word mapping requires little-endian platform")
            lock_fd = os.open(
                self.owner_lock, os.O_CREAT | os.O_RDWR | os.O_CLOEXEC |
                getattr(os, "O_NOFOLLOW", 0), 0o600,
            )
            try:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise MMIOError("MMIO owned by another cooperating process") from exc
                access = os.O_RDONLY if self.readonly else os.O_RDWR
                fd = os.open(self.device, access | os.O_SYNC | os.O_CLOEXEC)
            except BaseException:
                os.close(lock_fd)
                raise
            self._fd, self._lock_fd, self._pid = fd, lock_fd, os.getpid()

    def _check_active(self) -> None:
        if self._retired or self._fd is None:
            raise MMIOClosed("backend not opened or closed")
        if self._pid != os.getpid():
            raise MMIOClosed("MMIO mapping cannot be inherited by a forked process")
        if self._poisoned:
            raise MMIOError("backend poisoned; do not retry hardware access")

    def claim_site(self, site_id: int, base: int) -> SiteMMIO:
        """Assign exactly one active driver to a hardware aperture."""
        with self._mutex:
            self._check_active()
            if type(site_id) is not int or not 1 <= site_id <= 8:
                raise MMIOError("Site identity must be one-based 1..8")
            if type(base) is not int or base not in self._apertures:
                raise MMIOError("Site aperture must be explicitly configured")
            if base in self._owners or any(owner.site_id == site_id
                                           for owner in self._owners.values()):
                raise MMIOError("Site ID/aperture already claimed")
            lease = SiteMMIO(self, base, site_id)
            self._owners[base] = lease
            return lease

    def _register(self, address: int, *, write: bool) -> tuple[MMIOAperture, int]:
        _u32(address, "MMIO address")
        if address & 3:
            raise MMIOError("32-bit MMIO address must be 4-byte aligned")
        for aperture in self._apertures.values():
            if aperture.base <= address < aperture.base + aperture.size:
                offset = address - aperture.base
                if offset not in (aperture.writable if write else aperture.readable):
                    raise MMIOError("register is not present in access allowlist")
                if write and self.readonly:
                    raise MMIOError("backend is read-only")
                return aperture, offset // 4
        raise MMIOError("address outside approved AXI apertures")

    def _map_words(self, aperture: MMIOAperture) -> memoryview:
        if aperture.base not in self._pages:
            if self._fd is None:
                raise MMIOClosed("backend is not open")
            prot = mmap.PROT_READ | (0 if self.readonly else mmap.PROT_WRITE)
            page = mmap.mmap(self._fd, aperture.size,
                             flags=mmap.MAP_SHARED, prot=prot,
                             offset=aperture.base)
            view: memoryview | None = None
            try:
                view = memoryview(page).cast("I")
                if view.itemsize != 4:
                    raise MMIOError("native unsigned integer is not 32 bits")
            except BaseException:
                if view is not None:
                    view.release()
                page.close()
                raise
            self._pages[aperture.base] = page
            self._words[aperture.base] = view
        return self._words[aperture.base]

    def read32(self, address: int) -> int:
        # Validate even when the backend is closed, before opening any mapping.
        with self._mutex:
            aperture, idx = self._register(address, write=False)
            self._check_active()
            try:
                return self._map_words(aperture)[idx]
            except (OSError, ValueError, BufferError, IndexError) as exc:
                self._poisoned = True
                raise MMIOError("MMIO read uncertain; no automatic retry") from exc

    def write32(self, address: int, value: int) -> None:
        with self._mutex:
            aperture, idx = self._register(address, write=True)
            _u32(value, "MMIO data")
            self._check_active()
            try:
                # Never use struct.pack_into: ARMv7 may issue byte stores.
                self._map_words(aperture)[idx] = value
            except (OSError, ValueError, BufferError, IndexError) as exc:
                self._poisoned = True
                raise MMIOError("MMIO write uncertain; no automatic retry") from exc

    def quiesce_for_reload(self) -> None:
        """Retire mappings only when *all* active Site leases have been released.

        A platform owner must ALSO verify no asynchronous commands, kernel
        users or external processes are using PL. This method never loads PL.
        """
        with self._mutex:
            self._check_active()
            if self._owners:
                raise MMIOError("cannot reload FPGA with active Site owners")
            self.close()

    def close(self) -> None:
        """Idempotent, final close. All leases fail closed after invalidation."""
        with self._mutex:
            self._retired = True
            for owner in self._owners.values():
                owner._active = False
            self._owners.clear()
            for view in self._words.values():
                view.release()
            self._words.clear()
            try:
                for page in self._pages.values():
                    page.close()
                self._pages.clear()
            finally:
                if self._fd is not None:
                    os.close(self._fd)
                    self._fd = None
                if self._lock_fd is not None:
                    os.close(self._lock_fd)
                    self._lock_fd = None


"""Host-only UIO mapping backend candidate for PLASMA Phase 2A.

Never opens a character device. Explicitly maps ONLY an ordinary regular-file
UIO simulation; a future, separately approved real-UIO adapter must qualify
the kernel/DT/bridge, non-cooperating owners, physical AXI safety and ARMv7
native-word semantics. No FPGA Manager or hardware configuration path exists.

UIO mmap offset = map_index * PAGE_SIZE, not AXI physical address. The
sysfs map's byte `offset` is added to the pointer returned from mmap.
"""
from __future__ import annotations

from dataclasses import dataclass
import fcntl
import mmap
import os
from pathlib import Path
import re
import stat
import sys
from threading import RLock

from .linux_mmio import MMIOAperture, MMIOClosed, MMIOError, MMIOStats


@dataclass(frozen=True)
class UIOPin:
    """Expected device/resource identity from an externally reviewed board plan.

    This is a Host-only exact-match pin, not image provenance or permission
    to access an actual /dev/uio* character device.
    """

    device_name: str
    label: str
    platform_device: str
    driver: str
    map_index: int
    physical_base: int
    size: int
    byte_offset: int = 0

    def __post_init__(self) -> None:
        if not re.fullmatch(r"uio[0-9]+", self.device_name):
            raise MMIOError("Exact UIO device name required")
        for value in (self.label, self.platform_device, self.driver):
            if not value or "/" in value or value in (".", ".."):
                raise MMIOError("UIO identity pin must be a nonempty basename")
        if type(self.map_index) is not int or not 0 <= self.map_index <= 7:
            raise MMIOError("UIO map index outside supported map0..map7")
        if type(self.physical_base) is not int or not 0 <= self.physical_base < 2**32:
            raise MMIOError("Invalid pinned physical base")
        if type(self.size) is not int or not 0 < self.size <= 0x1000000 \
                or self.physical_base + self.size > 2**32:
            raise MMIOError("Invalid pinned UIO map length")
        page = mmap.PAGESIZE
        if type(self.byte_offset) is not int or not 0 <= self.byte_offset < page \
                or self.byte_offset != self.physical_base % page:
            raise MMIOError("UIO byte offset must match physical page offset")
        if self.byte_offset + self.size > 0x1000000 + page:
            raise MMIOError("UIO mapping too large")


def _sysnum(path: Path) -> int:
    try:
        text = path.read_text().strip()
        value = int(text, 0)
    except (ValueError, OSError) as exc:
        raise MMIOError("UIO sysfs register/resource unreadable") from exc
    if not 0 <= value <= 2**32:
        raise MMIOError("Invalid UIO sysfs resource value")
    return value


def _name(path: Path) -> str:
    try:
        if not path.is_symlink():
            raise MMIOError("Expected bound UIO symlink missing")
        return path.resolve(strict=True).name
    except (OSError, RuntimeError) as exc:
        raise MMIOError("Unresolvable UIO binding") from exc


def _read_resource(path: Path) -> tuple[int, int, int]:
    addr = _sysnum(path / "addr")
    size = _sysnum(path / "size")
    offset = _sysnum(path / "offset")
    if not 0 < size <= 0x1000000 or addr + size > 2**32 \
            or offset >= mmap.PAGESIZE or offset != addr % mmap.PAGESIZE:
        raise MMIOError("Malformed UIO physical resource or page offset")
    return addr, size, offset


class UIOSiteLease:
    """Single non-transferable Site owner with checked 32-bit register access."""

    def __init__(self, parent: UIOBackend, site_id: int, base: int) -> None:
        self._parent = parent
        self.site_id = site_id
        self.base = base
        self._generation = parent.generation
        self._active = True

    def read32(self, address: int) -> int:
        return self._parent._word(self, address, write=False)

    def write32(self, address: int, value: int) -> None:
        self._parent._word(self, address, write=True, value=value)

    def close(self) -> None:
        with self._parent._mutex:
            if self._parent._owners.get(self.base) is self:
                del self._parent._owners[self.base]
            self._active = False

    def __enter__(self) -> UIOSiteLease:
        return self

    def __exit__(self, *_: object) -> None:
        self.close()


class UIOBackend:
    """Single-UIO, multiple-Site, ordinary-file-only Host implementation.

    Existing LinuxMMIO and this backend share the exact advisory lock path.
    There is no hardware ownership guarantee against rogue privileged
    processes or kernel DMA; a separate FPGA Configuration Owner is required.
    """

    def __init__(
        self, pin: UIOPin, apertures: tuple[MMIOAperture, ...],
        *, sysroot: Path, device_file: Path, owner_lock: Path,
        generation: int, readonly: bool = True,
    ) -> None:
        if not isinstance(pin, UIOPin):
            raise MMIOError("UIO pin missing")
        if not apertures or type(apertures) is not tuple:
            raise MMIOError("Provide immutable nonempty Site aperture tuple")
        if type(generation) is not int or generation <= 0:
            raise MMIOError("Supervisor-supplied generation must be positive")
        if type(readonly) is not bool:
            raise MMIOError("readonly must be bool")
        if not all(isinstance(a, MMIOAperture) for a in apertures):
            raise MMIOError("Invalid Site aperture")
        bounds = [(x.base, x.base + x.size) for x in apertures]
        for i, (lo, hi) in enumerate(bounds):
            if lo < pin.physical_base or hi > pin.physical_base + pin.size \
                    or any(lo < b and a < hi for a, b in bounds[:i]):
                raise MMIOError("Site aperture outside pin or overlaps a peer")
        if not all(isinstance(x, Path) and x.is_absolute()
                   for x in (sysroot, device_file, owner_lock)):
            raise MMIOError("Explicit absolute Host paths required")
        if owner_lock == device_file or str(device_file).startswith("/dev/"):
            raise MMIOError("Host-only backend forbids real device paths")
        self.pin, self.apertures = pin, {a.base: a for a in apertures}
        self.sysroot, self.device_file, self.owner_lock = sysroot, device_file, owner_lock
        self.readonly, self.generation = readonly, generation
        self._mutex = RLock()
        self._owners: dict[int, UIOSiteLease] = {}
        self._fd: int | None = None
        self._lock_fd: int | None = None
        self._map: mmap.mmap | None = None
        self._words: memoryview | None = None
        self._pid: int | None = None
        self._retired = False
        self._poisoned = False
        self._read_count = 0
        self._write_count = 0

    def _check_sysfs(self) -> None:
        """Fail closed on unknown/overlapping UIO mappings or resource drift."""
        root = self.sysroot / "class/uio"
        try:
            candidates = sorted(p for p in root.iterdir()
                                if re.fullmatch(r"uio[0-9]+", p.name))
        except OSError as exc:
            raise MMIOError("UIO inventory unavailable") from exc
        if not candidates:
            raise MMIOError("No UIO resources available")
        found = False
        pin = self.pin
        for device in candidates:
            try:
                maps = sorted(p for p in (device / "maps").iterdir()
                              if re.fullmatch(r"map[0-9]+", p.name))
            except OSError as exc:
                raise MMIOError("UIO map inventory unavailable") from exc
            if not maps:
                raise MMIOError("UIO map inventory empty")
            for entry in maps:
                addr, size, off = _read_resource(entry)
                is_pin = device.name == pin.device_name and \
                         entry.name == f"map{pin.map_index}"
                if is_pin:
                    found = True
                    if (addr, size, off) != (pin.physical_base, pin.size,
                                             pin.byte_offset):
                        raise MMIOError("UIO pinned physical mapping drift")
                elif addr < pin.physical_base + pin.size \
                        and pin.physical_base < addr + size:
                    raise MMIOError("Competing UIO physical resource overlap")
            if device.name == pin.device_name:
                try:
                    label = (device / "name").read_text().strip()
                except OSError as exc:
                    raise MMIOError("UIO device name unavailable") from exc
                if label != pin.label or _name(device / "device") != pin.platform_device \
                        or _name(device / "device/driver") != pin.driver:
                    raise MMIOError("UIO name, platform device or driver changed")
        if not found:
            raise MMIOError("Pinned UIO map is absent")

    def _check_active(self) -> None:
        if self._retired or self._fd is None:
            raise MMIOClosed("UIO backend not open or retired")
        if self._pid != os.getpid():
            raise MMIOClosed("Inherited UIO mmap/fd across fork forbidden")
        if self._poisoned:
            raise MMIOError("UIO backend poisoned; recovery required")

    def open(self) -> None:
        with self._mutex:
            if self._retired or self._fd is not None:
                raise MMIOClosed("UIO backend already open or retired")
            if sys.byteorder != "little":
                raise MMIOError("Native 32-bit map requires little-endian CPU")
            self._check_sysfs()
            # Crucially reject character devices BEFORE opening their fd.
            try:
                meta = self.device_file.lstat()
                if not stat.S_ISREG(meta.st_mode):
                    raise MMIOError("Phase 2A permits ordinary test files only")
                lock_fd = os.open(self.owner_lock, os.O_CREAT | os.O_RDWR |
                                  os.O_CLOEXEC | getattr(os, "O_NOFOLLOW", 0),
                                  0o600)
            except OSError as exc:
                raise MMIOError("Host fixture or ownership lock unavailable") from exc
            fd: int | None = None
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                access = os.O_RDONLY if self.readonly else os.O_RDWR
                fd = os.open(self.device_file, access | os.O_CLOEXEC |
                             getattr(os, "O_NOFOLLOW", 0))
                info = os.fstat(fd)
                if not stat.S_ISREG(info.st_mode) or (info.st_dev, info.st_ino) != \
                        (meta.st_dev, meta.st_ino):
                    raise MMIOError("Host fixture replaced during open")
                aligned_size = ((self.pin.byte_offset + self.pin.size
                                 + mmap.PAGESIZE - 1) // mmap.PAGESIZE) * mmap.PAGESIZE
                if info.st_size < self.pin.map_index * mmap.PAGESIZE + aligned_size:
                    raise MMIOError("Host fixture too short for UIO selector")
                self._check_sysfs()
            except BaseException as exc:
                if fd is not None:
                    os.close(fd)
                os.close(lock_fd)
                if isinstance(exc, MMIOError):
                    raise
                raise MMIOError("UIO Host owner refused/open failed") from exc
            self._fd, self._lock_fd, self._pid = fd, lock_fd, os.getpid()

    def __enter__(self) -> UIOBackend:
        self.open()
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def claim_site(self, site_id: int, base: int) -> UIOSiteLease:
        with self._mutex:
            self._check_active()
            if type(site_id) is not int or not 1 <= site_id <= 8 or \
                    type(base) is not int or base not in self.apertures:
                raise MMIOError("Unapproved Site ID or aperture")
            if base in self._owners or any(p.site_id == site_id
                                           for p in self._owners.values()):
                raise MMIOError("Site aperture/identity already claimed")
            lease = UIOSiteLease(self, site_id, base)
            self._owners[base] = lease
            return lease

    def _view(self) -> memoryview:
        if self._words is None:
            if self._fd is None:
                raise MMIOClosed("UIO fd not open")
            count = ((self.pin.byte_offset + self.pin.size +
                      mmap.PAGESIZE - 1) // mmap.PAGESIZE) * mmap.PAGESIZE
            prot = mmap.PROT_READ | (0 if self.readonly else mmap.PROT_WRITE)
            page = mmap.mmap(self._fd, count, flags=mmap.MAP_SHARED, prot=prot,
                             offset=self.pin.map_index * mmap.PAGESIZE)
            view = None
            try:
                view = memoryview(page).cast("I")
                if view.itemsize != 4:
                    raise MMIOError("Native unsigned integer is not 32-bit")
            except BaseException:
                if view is not None:
                    view.release()
                page.close()
                raise
            self._map, self._words = page, view
        return self._words

    def _word(self, lease: UIOSiteLease, address: int, *, write: bool,
              value: int = 0) -> int | None:
        with self._mutex:
            self._check_active()
            if not lease._active or self._owners.get(lease.base) is not lease \
                    or lease._generation != self.generation:
                raise MMIOClosed("UIO Site lease revoked or wrong generation")
            if type(address) is not int or not 0 <= address <= 0xFFFFFFFF \
                    or address % 4:
                raise MMIOError("Only physical u32-aligned addresses permitted")
            ap = self.apertures[lease.base]
            offset = address - ap.base
            if not 0 <= offset <= ap.size - 4 or offset not in \
                    (ap.writable if write else ap.readable):
                raise MMIOError("Register outside Site access allowlist")
            if write and (self.readonly or type(value) is not int
                          or not 0 <= value <= 0xFFFFFFFF):
                raise MMIOError("Read-only backend or invalid u32 value")
            index_bytes = self.pin.byte_offset + address - self.pin.physical_base
            if index_bytes % 4:
                raise MMIOError("UIO map pointer is not aligned to u32")
            try:
                self._check_sysfs()
                view = self._view()
                if write:
                    view[index_bytes // 4] = value  # native aligned word, never pack_into
                    self._write_count += 1
                    return None
                result = view[index_bytes // 4]
                self._read_count += 1
                return result
            except (OSError, ValueError, BufferError, IndexError, MMIOError) as exc:
                self._poisoned = True
                raise MMIOError("UIO access/ownership state uncertain; no retry") from exc

    def stats(self) -> MMIOStats:
        with self._mutex:
            return MMIOStats(read32=self._read_count, write32=self._write_count)

    def quiesce_for_reload(self) -> None:
        """Retire this Host backend; does not authorize or perform FPGA load."""
        with self._mutex:
            self._check_active()
            if self._owners:
                raise MMIOError("Cannot quiesce UIO with active Site leases")
            self.close()

    def close(self) -> None:
        with self._mutex:
            if self._retired and self._fd is None and self._map is None:
                return
            self._retired = True
            self.generation += 1  # old handles irrevocably invalid
            for owner in self._owners.values():
                owner._active = False
            self._owners.clear()
            if self._words is not None:
                self._words.release()
                self._words = None
            try:
                if self._map is not None:
                    self._map.close()
                    self._map = None
            finally:
                if self._fd is not None:
                    os.close(self._fd)
                    self._fd = None
                if self._lock_fd is not None:
                    os.close(self._lock_fd)
                    self._lock_fd = None

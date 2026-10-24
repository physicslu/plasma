"""Fixed ABI v1 Site-1 -> LinuxMMIO word-port adapter (no automatic hardware).

The exact read/write allowlists are copied from the reviewed fixed-image ABI
candidate. Instantiating this port neither opens /dev/mem nor grants Site,
board, bus or electrical admission. A real port requires an explicitly
loaded SHA-pinned native ARMv7-A DMB SY library; the host-test alternative
only works with an already-open REGULAR FILE, never a character device.
"""
from __future__ import annotations

import ctypes
import hashlib
import os
from pathlib import Path
import platform
import re
import stat
import sys
from collections.abc import Callable

from .linux_mmio import MMIOAperture, MMIOClosed, MMIOError, SiteMMIO

# pl/verification/fixed_image_abi_v1_gate1.json: regions[site_1].registers
_FIXED_SITE1_READ = frozenset((
    0x00, 0x04, 0x08, 0x0C, 0x10, 0x14, 0x18, 0x1C, 0x44,
    0x48, 0x4C, 0x50, 0x58, 0x60, 0x68, 0x6C, 0x70,
))
_FIXED_SITE1_WRITE = frozenset((
    0x20, 0x24, 0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C,
    0x40, 0x54, 0x5C, 0x64,
))


def fixed_abi_site1_aperture(site_base: int) -> MMIOAperture:
    """Site 1 SWD/SPI-candidate layout; Site 2..8 are NOT instantiated."""
    return MMIOAperture(site_base, _FIXED_SITE1_READ, _FIXED_SITE1_WRITE)


class ARMv7DMBBarrier:
    """SHA-pinned explicit ARMv7-A shared-library DMB, NOT hardware approval.

    This is a native primitive loader, not an ELF/ABI/kernel/PS7 qualifier.
    Never compile or load a library as a side effect of a Python import.
    """

    def __init__(self, absolute_library: str, *, sha256: str) -> None:
        if not isinstance(absolute_library, str) or not os.path.isabs(absolute_library):
            raise MMIOError("Explicit absolute native barrier library path required")
        if not isinstance(sha256, str) or not re.fullmatch(r"[0-9a-f]{64}", sha256):
            raise MMIOError("Explicit exact native library SHA256 required")
        if (platform.machine().lower() not in ("armv7l", "armv7", "armv7-a")
                or sys.byteorder != "little" or ctypes.sizeof(ctypes.c_void_p) != 4):
            raise MMIOError("ARMv7-A little-endian 32-bit runtime required")
        path = Path(absolute_library)
        try:
            st = path.lstat()
            if not stat.S_ISREG(st.st_mode) or path.is_symlink():
                raise MMIOError("Native barrier must be a regular, non-symlink file")
            # Detect bytes differing from the approved library before dlopen.
            if hashlib.sha256(path.read_bytes()).hexdigest() != sha256:
                raise MMIOError("Native barrier library digest mismatch")
            lib = ctypes.CDLL(str(path))
            fn = lib.plasma_mmio_dmb_sy
            fn.argtypes = []
            fn.restype = None
        except (OSError, AttributeError) as exc:
            raise MMIOError("Cannot load approved native DMB barrier") from exc
        self._lib = lib  # keep the ELF mapped for callback lifetime
        self._fn = fn
        self.sha256 = sha256

    def __call__(self) -> None:
        self._fn()


class FixedABISite1WordPort:
    """Narrow FixedABISWDController port over one explicitly owned SiteMMIO.

    A production port requires ARMv7DMBBarrier. A host_test_barrier is
    permitted ONLY for an already-open regular-file backed LinuxMMIO.
    This layer never acquires leases, opens devices, or retries side effects.
    """

    def __init__(
        self,
        lease: SiteMMIO,
        *,
        barrier: ARMv7DMBBarrier | None = None,
        host_test_barrier: Callable[[], None] | None = None,
    ) -> None:
        if not isinstance(lease, SiteMMIO):
            raise MMIOError("An already-owned native SiteMMIO lease is required")
        if lease.site_id != 1 or lease.base & 0xFFF:
            raise MMIOError("Only an aligned, actually instantiated Site 1 is supported")
        if (barrier is None) == (host_test_barrier is None):
            raise MMIOError("Choose exactly one native barrier or host-only test barrier")
        if barrier is not None and not isinstance(barrier, ARMv7DMBBarrier):
            raise MMIOError("Real MMIO requires an ARMv7DMBBarrier object")
        parent = lease._parent
        if host_test_barrier is not None:
            if not callable(host_test_barrier):
                raise MMIOError("Host-only barrier must be callable")
            try:
                # Refuse character devices even if a test caller gave /dev/mem
                # an alias. Do not follow a symlink for a synthetic device.
                path = Path(parent.device)
                if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
                    raise MMIOError("Test barrier forbidden on non-regular device")
            except OSError as exc:
                raise MMIOError("Host-only test device identity unavailable") from exc
        with parent._mutex:
            lease._guard(lease.base)
            parent._check_active()
            if parent.readonly:
                raise MMIOError("Fixed-ABI SWD Site requires writable MMIO")
            aperture = parent._apertures[lease.base]
            if not _FIXED_SITE1_READ.issubset(aperture.readable) or (
                    not _FIXED_SITE1_WRITE.issubset(aperture.writable)):
                raise MMIOError("MMIO aperture lacks exact Fixed ABI Site 1 access policy")
        self._lease = lease
        self._barrier = barrier if barrier is not None else host_test_barrier

    @property
    def base(self) -> int:
        return self._lease.base

    def _check_address(self, address: int, write: bool) -> None:
        if type(address) is not int or address & 3:
            raise MMIOError("Fixed ABI requires aligned integer 32-bit address")
        valid = _FIXED_SITE1_WRITE if write else _FIXED_SITE1_READ
        if address - self.base not in valid:
            raise MMIOError("Fixed ABI register not in access allowlist")

    def read32(self, address: int) -> int:
        self._check_address(address, write=False)
        return self._lease.read32(address)

    def write32(self, address: int, value: int) -> None:
        self._check_address(address, write=True)
        self._lease.write32(address, value)

    def write_barrier(self) -> None:
        # Hold the SAME MMIO parent mutex used by native reads/writes/close
        # while validating the lease and executing the native ordering hook.
        parent = self._lease._parent
        with parent._mutex:
            self._lease._guard(self.base)
            parent._check_active()
            try:
                assert self._barrier is not None
                self._barrier()
            except BaseException:
                parent._poisoned = True  # do not issue COMMAND after uncertainty
                raise

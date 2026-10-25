"""Explicit Z2 Site 1 Blue Pill SWD GPIO word-port; never opens a device.

Reuses PLASMA's existing LinuxMMIO/SiteMMIO and SHA-pinned ARMv7 DMB.
The hardware owner must independently qualify BIT/HWH, bus aperture,
electrical safety, exclusive access, and Golden recovery availability.
Successful sessions leave the SWD Image loaded; Restore is separately selected.
A regular-file test barrier never grants hardware admission.
"""
from __future__ import annotations

import os
from pathlib import Path
import stat
from collections.abc import Callable

from .fixed_abi_mmio_port import ARMv7DMBBarrier
from .linux_mmio import MMIOAperture, MMIOError, SiteMMIO

BLUEPILL_SWD_BASE = 0x40008000
_READ = frozenset((0x00, 0x04, 0x0C))
_WRITE = frozenset((0x08,))


def bluepill_z2_aperture() -> MMIOAperture:
    """A **candidate**, never a verified physical AXI aperture."""
    return MMIOAperture(BLUEPILL_SWD_BASE, _READ, _WRITE)


class BluepillZ2WordPort:
    """Narrow WordPort for the existing RemoteBitbangSWD control algorithm.

    Construction is inert: no /dev/mem, /dev/uio, FPGA Manager, power or
    privileged mapping is performed here. Real ownership is external.
    """

    def __init__(
        self,
        lease: SiteMMIO,
        *,
        barrier: ARMv7DMBBarrier | None = None,
        host_test_barrier: Callable[[], None] | None = None,
    ) -> None:
        if not isinstance(lease, SiteMMIO) or lease.site_id != 1:
            raise MMIOError("Exact, already-owned Site 1 lease required")
        if lease.base != BLUEPILL_SWD_BASE:
            raise MMIOError("Candidate Blue Pill SWD base mismatch")
        if (barrier is None) == (host_test_barrier is None):
            raise MMIOError("Choose exactly one ARMv7 DMB or host-only barrier")
        if barrier is not None and not isinstance(barrier, ARMv7DMBBarrier):
            raise MMIOError("Real device access requires verified native ARMv7 DMB")
        parent = lease._parent
        if host_test_barrier is not None:
            if not callable(host_test_barrier):
                raise MMIOError("Host-only barrier must be callable")
            try:
                path = Path(parent.device)
                if path.is_symlink() or not stat.S_ISREG(path.stat().st_mode):
                    raise MMIOError("Host-test barrier limited to a regular file")
            except OSError as exc:
                raise MMIOError("Cannot verify host-test file identity") from exc
        with parent._mutex:
            lease._guard(BLUEPILL_SWD_BASE)
            parent._check_active()
            if parent.readonly:
                raise MMIOError("Blue Pill GPIO port requires writable Site")
            aperture = parent._apertures[lease.base]
            if aperture.readable != _READ or aperture.writable != _WRITE:
                raise MMIOError("Exact Blue Pill candidate access policy required")
        self._lease = lease
        self._barrier = barrier if barrier is not None else host_test_barrier

    def _guard(self, address: int, *, write: bool) -> None:
        if type(address) is not int or address & 3:
            raise MMIOError("Only aligned 32-bit addresses are legal")
        allowed = _WRITE if write else _READ
        if address - BLUEPILL_SWD_BASE not in allowed:
            raise MMIOError("Access outside fixed read/write register allowlist")

    def read32(self, address: int) -> int:
        self._guard(address, write=False)
        return self._lease.read32(address)

    def write32(self, address: int, value: int) -> None:
        self._guard(address, write=True)
        if type(value) is not int or value & ~7 or value < 0:
            raise MMIOError("Only DRIVE bits SWCLK/SWDIO/OE may be written")
        self._lease.write32(address, value)

    def write_barrier(self) -> None:
        parent = self._lease._parent
        with parent._mutex:
            self._lease._guard(BLUEPILL_SWD_BASE)
            parent._check_active()
            try:
                assert self._barrier is not None
                self._barrier()
            except BaseException:
                parent._poisoned = True
                raise

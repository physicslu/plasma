"""Inert ABI-v5 SWD Site access adapter over the existing LinuxMMIO lease.

A caller MUST first qualify a matched FPGA Image/Manifest, PS7 AXI aperture,
Board/voltage, Root Guard, Linux permission and an exclusive SiteMMIO lease.
Construction performs no device open, mapping, FPGA configuration or read.
The ARMv7 DMB primitive does NOT alone prove native LDR/STR width or device
mapping attributes; this remains an explicit target qualification blocker.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import stat

from .fixed_abi_mmio_port import ARMv7DMBBarrier
from .linux_mmio import MMIOAperture, MMIOError, SiteMMIO
from .swd_site import SITE_BASES

# These are precise RTL-readable/writable AXI-Lite registers; 0x3C/0x40
# were removed with SWD Debug Mode and must NEVER be exposed as GPIO.
_SWD_READ = frozenset((
    0x00, 0x04, 0x08, 0x0C, 0x18, 0x1C,
    0x24, 0x28, 0x2C, 0x30, 0x34, 0x38,
))
_SWD_WRITE = frozenset((
    0x08, 0x0C, 0x10, 0x14, 0x20, 0x28, 0x2C, 0x30, 0x34, 0x38,
    0x44, 0x48, 0x4C, 0x50, 0x54, 0x58, 0x5C, 0x60, 0x64,
))


def swd_site_aperture(site_id: int) -> MMIOAperture:
    """Host-defined v5 candidate only; never proves a physical PS7 window."""
    if type(site_id) is not int or site_id not in SITE_BASES:
        raise MMIOError("Only candidate SWD Site 1/2 apertures exist")
    return MMIOAperture(SITE_BASES[site_id], _SWD_READ, _SWD_WRITE)


class SwdNativeLinuxMMIOPort:
    """One already-leased SiteMMIO word port for SwdSiteController.

    Real access requires a SHA-checked ARMv7DMBBarrier. The alternative
    callback is restricted to an opened REGULAR FILE for host-only regression
    (never device nodes, symlinks or a writable hardware aperture).
    All word access uses existing LinuxMMIO's native 32-bit memoryview.
    The actual ARMv7 LDR/STR disassembly/device mapping is NOT_RUN.
    """

    def __init__(
        self,
        lease: SiteMMIO,
        *,
        barrier: ARMv7DMBBarrier | None = None,
        host_test_barrier: Callable[[], None] | None = None,
    ) -> None:
        if not isinstance(lease, SiteMMIO):
            raise MMIOError("Explicit already-owned SiteMMIO required")
        if type(lease.site_id) is not int or lease.site_id not in SITE_BASES:
            raise MMIOError("Only SWD Site 1/2 are implemented")
        if lease.base != SITE_BASES[lease.site_id]:
            raise MMIOError("SWD Site ID / AXI base mismatch")
        if (barrier is None) == (host_test_barrier is None):
            raise MMIOError("Provide exactly one native DMB or host-only test barrier")
        if barrier is not None and not isinstance(barrier, ARMv7DMBBarrier):
            raise MMIOError("Real MMIO requires SHA-checked native ARMv7 DMB")
        parent = lease._parent
        with parent._mutex:
            lease._guard(lease.base)
            parent._check_active()
            if parent.readonly:
                raise MMIOError("SWD FIFO/command MMIO requires a writable mapping")
            aperture = parent._apertures[lease.base]
            if aperture != swd_site_aperture(lease.site_id):
                raise MMIOError("Exact ABI-v5 Site read/write aperture required")
            if host_test_barrier is not None:
                if not callable(host_test_barrier):
                    raise MMIOError("Host-only barrier must be callable")
                path = Path(parent.device)
                try:
                    st = path.lstat()
                except OSError as exc:
                    raise MMIOError("Host-only file identity not available") from exc
                if path.is_symlink() or not stat.S_ISREG(st.st_mode):
                    raise MMIOError("Host-only barrier forbidden on device or symlink")
        self._lease = lease
        self._barrier = barrier if barrier is not None else host_test_barrier

    @property
    def site_id(self) -> int:
        return self._lease.site_id

    @property
    def base(self) -> int:
        return self._lease.base

    def _allowed(self, address: int, *, write: bool) -> None:
        if type(address) is not int or address & 3:
            raise MMIOError("Only aligned integer word addresses allowed")
        offsets = _SWD_WRITE if write else _SWD_READ
        if address - self.base not in offsets:
            raise MMIOError("Register outside ABI-v5 access allowlist")

    def read32(self, address: int) -> int:
        self._allowed(address, write=False)
        return self._lease.read32(address)

    def write32(self, address: int, value: int) -> None:
        self._allowed(address, write=True)
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise MMIOError("Unsigned full 32-bit value required")
        self._lease.write32(address, value)

    def write_barrier(self) -> None:
        # Synchronize with underlying reads, writes and close. On uncertainty
        # poison the shared parent, so all Site leases stop using the mapping.
        parent = self._lease._parent
        with parent._mutex:
            self._lease._guard(self.base)
            parent._check_active()
            try:
                assert self._barrier is not None
                self._barrier()
            except BaseException:
                parent._poisoned = True
                raise

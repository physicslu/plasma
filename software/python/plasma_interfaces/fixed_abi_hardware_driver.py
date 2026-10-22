"""Protocol-neutral Fixed ABI v1 PS/PL admission and Site MMIO boundary.

The caller supplies a trusted board aperture, exact image/build manifest,
and an already-qualified 32-bit port.  This module NEVER opens a device,
grants a hardware lease, validates voltage/pins, or loads an FPGA image.
Site command sequencing remains in protocol controllers (SWD today).
Host simulation of this class is not physical AXI/MMIO qualification.
"""
from __future__ import annotations

from threading import RLock
from typing import Protocol

from .fixed_abi_mmio_port import _FIXED_SITE1_READ, _FIXED_SITE1_WRITE


class HardwareABIPort(Protocol):
    def read32(self, address: int) -> int: ...
    def write32(self, address: int, value: int) -> None: ...
    def write_barrier(self) -> None: ...


class HardwareABIAdmissionError(RuntimeError):
    """An ABI/image/Site identity or ownership precondition failed."""


def _u32(value: object) -> bool:
    return type(value) is int and 0 <= value <= 0xFFFFFFFF


class FixedABIHardwareDriver:
    """Admit only physically advertised Site apertures for one owner epoch.

    The strict manifest comparison is admission input, not authentication;
    a trusted outside supervisor still owns actual board and DUT safety.
    """

    MAGIC = 0x4D534C50
    ABI_VERSION = 0x00010000

    def __init__(self, port: HardwareABIPort, *, ppu_base: int,
                 image_id: tuple[int, int, int, int],
                 build_id: tuple[int, int, int, int],
                 site_bitmap: int) -> None:
        if port is None or any(not callable(getattr(port, key, None))
                               for key in ("read32", "write32", "write_barrier")):
            raise ValueError("An explicitly qualified 32-bit/barrier port is required")
        if not _u32(ppu_base) or ppu_base & 0xFFFF or ppu_base > 0xFFFF0000:
            raise ValueError("PPU base must be 64KiB aligned and bounded")
        if (type(image_id) is not tuple or type(build_id) is not tuple or
                len(image_id) != 4 or len(build_id) != 4 or
                not all(_u32(v) for v in image_id + build_id)):
            raise ValueError("Exact four-word trusted Image and Build IDs required")
        if type(site_bitmap) is not int or not 1 <= site_bitmap <= 0xFF:
            raise ValueError("Expected physically populated Site bitmap required")
        self._port = port
        self.base = ppu_base
        self.expected_image_id = image_id
        self.expected_build_id = build_id
        self.expected_site_bitmap = site_bitmap
        self._lock = RLock()
        self._admitted = False
        self._poisoned = False
        self._leased_sites: dict[int, FixedABISitePort] = {}
        # No automatic MMIO during construction.

    def _read(self, address: int) -> int:
        try:
            value = self._port.read32(address)
        except Exception as exc:
            self._poisoned = True
            raise HardwareABIAdmissionError("Uncertain AXI read; supervisor recovery required") from exc
        if not _u32(value):
            self._poisoned = True
            raise HardwareABIAdmissionError("Malformed 32-bit AXI response")
        return value

    def admit(self) -> None:
        with self._lock:
            if self._poisoned:
                raise HardwareABIAdmissionError("Hardware ABI driver poisoned")
            if self._admitted:
                raise HardwareABIAdmissionError("Admission cannot be repeated within owner epoch")
            try:
                values = [self._read(self.base + off) for off in (
                    0x00, 0x04, 0x08, 0x0C, 0x10, 0x14,
                    0x18, 0x1C, 0x20, 0x24, 0x28, 0x2C,
                    0x30, 0x34, 0x44, 0x48,
                )]
                if (values[0:2] != [self.MAGIC, self.ABI_VERSION] or
                        tuple(values[2:6]) != self.expected_image_id or
                        tuple(values[6:10]) != self.expected_build_id or
                        values[10] != 1 or values[11] != 0 or
                        values[12] != self.expected_site_bitmap or
                        values[13] & ~values[12] or
                        values[14] != 1 or values[15] != 4096):
                    raise HardwareABIAdmissionError(
                        "Global ABI, image/build, presence, capability or map mismatch")
            except BaseException:
                self._poisoned = True
                raise
            self._admitted = True

    def open_site(self, site_id: int) -> FixedABISitePort:
        if type(site_id) is not int or not 1 <= site_id <= 8:
            raise ValueError("Site identity must be one-based 1..8")
        with self._lock:
            if self._poisoned or not self._admitted:
                raise HardwareABIAdmissionError("No valid global owner admission")
            if not self.expected_site_bitmap & (1 << (site_id - 1)):
                raise HardwareABIAdmissionError("Uninstantiated Site forbidden")
            if site_id in self._leased_sites:
                raise HardwareABIAdmissionError("Site already owned in this epoch")
            base = self.base + 0x4000 + (site_id - 1) * 0x1000
            try:
                ready = self._read(self.base + 0x34)
                if not ready & (1 << (site_id - 1)) or (
                        self._read(base) != site_id or
                        self._read(base + 4) != self.ABI_VERSION or
                        not self._read(base + 8) & 1 or
                        self._read(base + 12) != 1):
                    raise HardwareABIAdmissionError("Site not ready or identity/capability mismatch")
            except BaseException:
                self._poisoned = True
                raise
            site = FixedABISitePort(self, base=base, site_id=site_id)
            self._leased_sites[site_id] = site
            return site


class FixedABISitePort:
    """One Site's allowlisted 32-bit words over an injected shared bus.

    Site-specific command locks and uncertain-command policy remain in the
    production protocol controller. The bus lock only serializes word I/O.
    """

    def __init__(self, owner: FixedABIHardwareDriver, *, base: int,
                 site_id: int) -> None:
        self.owner = owner
        self.base = base
        self.site_id = site_id

    def _guard(self, address: int, *, write: bool) -> None:
        if self.owner._poisoned or not self.owner._admitted:
            raise HardwareABIAdmissionError("Global ABI admission revoked")
        if (self.owner._leased_sites.get(self.site_id) is not self or
                self.base != self.owner.base + 0x4000 +
                (self.site_id - 1) * 0x1000):
            raise HardwareABIAdmissionError("Unowned or forged Site port")
        offsets = _FIXED_SITE1_WRITE if write else _FIXED_SITE1_READ
        if type(address) is not int or address - self.base not in offsets:
            raise HardwareABIAdmissionError("Illegal, unaligned or cross-Site register access")

    def read32(self, address: int) -> int:
        with self.owner._lock:
            self._guard(address, write=False)
            return self.owner._read(address)

    def write32(self, address: int, value: int) -> None:
        with self.owner._lock:
            self._guard(address, write=True)
            if not _u32(value):
                raise ValueError("32-bit word value required")
            self.owner._port.write32(address, value)

    def write_barrier(self) -> None:
        with self.owner._lock:
            if self.owner._poisoned or not self.owner._admitted:
                raise HardwareABIAdmissionError("Global ABI admission revoked")
            self.owner._port.write_barrier()

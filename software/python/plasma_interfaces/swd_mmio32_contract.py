"""Host-only word-width PS7 AXI/MMIO boundary; opens NO device/mmap.

The injected backend must issue a single native 32-bit LDR/STR per word,
plus the required barriers. Python tests prove only address and call ordering:
actual ARMv7 instruction width, memory mapping, AXI and HIL NOT_RUN.
"""
from __future__ import annotations

from .swd_site import SITE_BASES


class Word32MappedWindow:
    """One Site's isolated 4-KiB aperture around an injected mapped-word API.

    Required backend: read_word(offset), write_word(offset,value),
    read_barrier(), write_barrier(). No /dev/mem, /dev/uio or mapping here.
    """

    def __init__(self, backend: object, *, site_id: int):
        if type(site_id) is not int or site_id not in SITE_BASES:
            raise ValueError("Only Site 1/2 supported")
        if not all(callable(getattr(backend, method, None)) for method in
                   ("read_word", "write_word", "read_barrier", "write_barrier")):
            raise TypeError("Injected native word backend and read/write barriers required")
        self._backend = backend
        self.base = SITE_BASES[site_id]
        self.site_id = site_id

    def _offset(self, address: int) -> int:
        if type(address) is not int or not self.base <= address < self.base + 4096:
            raise ValueError("Outside this Site's independent AXI page")
        if address & 3:
            raise ValueError("Unaligned native 32-bit MMIO access")
        return address - self.base

    def read32(self, address: int) -> int:
        value = self._backend.read_word(self._offset(address))
        self._backend.read_barrier()
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("Native backend supplied invalid 32-bit read")
        return value

    def write32(self, address: int, value: int) -> None:
        offset = self._offset(address)
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise ValueError("Full-word unsigned 32-bit write required")
        self._backend.write_word(offset, value)

    def write_barrier(self) -> None:
        self._backend.write_barrier()

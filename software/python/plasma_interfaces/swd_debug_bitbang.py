"""Host-only, byte-level SWD remote_bitbang protocol core for one Site.

Not a socket listener or qualified OpenOCD release. OpenOCD v0.12.0 is
JTAG-only; an exact source-and-binary qualified SWD build, PS-local UNIX
transport, actual ARM MMIO and physical admission remain BLOCKED/NOT_RUN.

This codec handles only SWD bytes documented by upstream openocd commit
cb0c224e936091156ecf3025ba05657408ed64c8. It does not interpret JTAG,
reset/power commands, or optional remote sleeps; use_remote_sleep must be off.
"""
from __future__ import annotations

from threading import RLock
from typing import Callable

from .swd_site import SITE_BASES, SiteAccessError, SiteWordAccess


class BitbangProtocolError(SiteAccessError):
    """Unsupported request or unsafe SWDIO ownership transition."""


class SwdDebugBitbangCore:
    """Finite SWD byte interpreter; one externally owned Site lease.

    Requires a live lease_check callback, but cannot certify the external
    owner/FPGA Image on its own. No socket, process, hardware or credential
    is opened. On any uncertain MMIO action, fail and require host recovery.
    """

    MODE = 0x38
    DRIVE = 0x3C
    SAMPLE = 0x40

    def __init__(self, port: SiteWordAccess, *, site_id: int,
                 lease_check: Callable[[], None]) -> None:
        if type(site_id) is not int or site_id not in SITE_BASES:
            raise ValueError("Unknown independent SWD Site")
        if not callable(lease_check) or not all(
                callable(getattr(port, name, None)) for name in
                ("read32", "write32", "write_barrier")):
            raise TypeError("Explicit lease and qualified 32-bit port required")
        self.base = SITE_BASES[site_id]
        self.site_id = site_id
        self._port = port
        self._lease_check = lease_check
        self._lock = RLock()
        self.clk = 0
        self.data = 0
        self.oe = 0
        self.open = False
        self.poisoned = False

    def _lease(self) -> None:
        try:
            self._lease_check()
        except BaseException as exc:
            self.poisoned = True
            raise BitbangProtocolError("Site lease lost; stop output") from exc

    def _read(self, offset: int) -> int:
        try:
            value = self._port.read32(self.base + offset)
            if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                raise ValueError("Malformed device read")
            return value
        except BaseException as exc:
            self.poisoned = True
            raise SiteAccessError("Uncertain SWD bitbang MMIO read") from exc

    def _write(self, offset: int, value: int) -> None:
        try:
            self._port.write32(self.base + offset, value)
            self._port.write_barrier()
        except BaseException as exc:
            self.poisoned = True
            raise SiteAccessError("Uncertain SWD bitbang MMIO write") from exc

    def begin(self) -> None:
        with self._lock:
            if self.open or self.poisoned:
                raise BitbangProtocolError("Debug session already owned or poisoned")
            self._lease()
            if self._read(0) != (0x30000 | self.site_id):
                self.poisoned = True
                raise BitbangProtocolError("Wrong independent Site ABI")
            if self._read(self.MODE) != 0:
                raise BitbangProtocolError("Site not disabled before Debug admission")
            self._write(self.MODE, 2)
            if self._read(self.MODE) != 2:
                self.poisoned = True
                raise BitbangProtocolError("Debug mode admission failed")
            self.open = True

    def _drive(self, clk: int, data: int, oe: int) -> None:
        """Meet RTL rule: SWDIO data/OE changes only with SWCLK LOW."""
        if self.clk and clk and (data != self.data or oe != self.oe):
            raise BitbangProtocolError("Cannot change SWDIO while SWCLK HIGH")
        if self.clk and (not clk or data != self.data or oe != self.oe):
            self._write(self.DRIVE, (self.oe << 2) | (self.data << 1))
            self.clk = 0
        if data != self.data or oe != self.oe:
            self._write(self.DRIVE, (oe << 2) | (data << 1))
            self.data, self.oe = data, oe
        if clk != self.clk:
            self._write(self.DRIVE, (oe << 2) | (data << 1) | clk)
            self.clk = clk

    def handle(self, request: bytes) -> bytes:
        """Process exactly one OpenOCD remote_bitbang SWD ASCII byte."""
        with self._lock:
            if not self.open or self.poisoned:
                raise BitbangProtocolError("No active qualified Debug session")
            self._lease()
            if type(request) is not bytes or len(request) != 1:
                raise BitbangProtocolError("Exactly one protocol byte required")
            if request == b"O":
                if self.clk:
                    raise BitbangProtocolError("SWDIO enable at SWCLK HIGH")
                self._drive(self.clk, self.data, 1)
            elif request == b"o":
                if self.clk:
                    raise BitbangProtocolError("SWDIO release at SWCLK HIGH")
                self._drive(self.clk, self.data, 0)
            elif request == b"c":
                return b"1" if self._read(self.SAMPLE) & 1 else b"0"
            elif request in (b"d", b"e", b"f", b"g"):
                code = request[0] - ord("d")
                self._drive(code >> 1, code & 1, self.oe)
            elif request == b"Q":
                self.close()
            else:
                # B/b, R, 0..7 and reset bytes are JTAG/unsafe here;
                # Z/z optional sleep is deliberately unsupported.
                raise BitbangProtocolError("Unsupported SWD debug opcode")
            return b""

    def close(self) -> None:
        """Best-effort explicit output quiescence; failed MMIO stays poisoned."""
        with self._lock:
            if not self.open or self.poisoned:
                raise BitbangProtocolError("Unsafe or inactive session: external recovery")
            self._lease()
            self._drive(0, self.data, 0)
            self._write(self.MODE, 0)
            self.open = False

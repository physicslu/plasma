"""One-Site OpenOCD remote_bitbang SWD -> candidate PL GPIO word-port.

Gate 1 / Path 1: host-only library. This does not open /dev/uio*, /dev/mem,
an FPGA Manager, a network listener or a target power supply. The caller must
inject an independently authenticated, exclusive, 32-bit MMIO port, and bind
one verified PL GPIO image to the address below. Simulation is not hardware
admission. No register address is accepted from a socket client.
"""
from __future__ import annotations

import os
from pathlib import Path
import socket
import stat
from typing import Protocol


class WordPort(Protocol):
    def read32(self, address: int) -> int: ...
    def write32(self, address: int, value: int) -> None: ...
    def write_barrier(self) -> None: ...


class SWDBitbangError(RuntimeError):
    """Unsupported wire command or uncertain/unqualified PL transaction."""


class RemoteBitbangSWD:
    """Subset of upstream OpenOCD SWD remote_bitbang, one fixed Site only.

    OpenOCD 0.12.0+dev source:
    5088db4c9154ca833c6d558381074b33672e127a,
    src/jtag/drivers/remote_bitbang.c.
    Commands: O/o SWDIO output enable, d..g SWCLK/SWDIO levels, c sample,
    r reset-deasserted (no physical NRST), B/b ignored, Q quit.
    Explicitly reject any active reset, JTAG, delay or unknown command.
    """

    MAGIC = 0x50425357  # "WSBP" fixed candidate identification, not attestation
    VERSION = 0x00010000
    REG_ID = 0x00
    REG_VERSION = 0x04
    REG_DRIVE = 0x08
    REG_SAMPLE = 0x0C
    SWCLK = 1
    SWDIO = 2
    OE = 4

    def __init__(self, port: WordPort, *, base: int) -> None:
        if (port is None or any(not callable(getattr(port, attr, None))
                for attr in ("read32", "write32", "write_barrier"))):
            raise ValueError("Qualified read32/write32/write_barrier port required")
        if type(base) is not int or not 0 <= base <= 0xFFFFF000 or base & 0xFFF:
            raise ValueError("Exact 4-KiB aligned Site base required")
        self.port = port
        self.base = base
        self.admitted = False
        self.poisoned = False
        self.closed = False
        self._clock = 0
        self._swdio = 1
        self._oe = False

    def _read(self, offset: int) -> int:
        try:
            value = self.port.read32(self.base + offset)
            if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
                raise ValueError("Malformed 32-bit response")
            return value
        except Exception as exc:
            self.poisoned = True
            raise SWDBitbangError("Uncertain PL read; external recovery required") from exc

    def _barrier(self) -> None:
        try:
            self.port.write_barrier()
        except Exception as exc:
            self.poisoned = True
            raise SWDBitbangError("Uncertain write ordering; external recovery required") from exc

    def _drive(self) -> None:
        value = (self._clock * self.SWCLK | self._swdio * self.SWDIO |
                 int(self._oe) * self.OE)
        try:
            self.port.write32(self.base + self.REG_DRIVE, value)
        except Exception as exc:
            self.poisoned = True
            raise SWDBitbangError("Uncertain PL write; external recovery required") from exc

    def admit(self) -> None:
        if self.closed or self.poisoned or self.admitted:
            raise SWDBitbangError("Admission is not repeatable")
        if (self._read(self.REG_ID) != self.MAGIC or
                self._read(self.REG_VERSION) != self.VERSION):
            self.poisoned = True
            raise SWDBitbangError("Wrong PL image or GPIO ABI")
        # Safe PL reset value: SWCLK=0, SWDIO=1, OE=0; never guess
        # whether an external target is electrically safe.
        if self._read(self.REG_SAMPLE) & 0x0E != 0x08:
            self.poisoned = True
            raise SWDBitbangError("PL outputs not in reset-safe state")
        self.admitted = True

    def close(self) -> None:
        if self.closed:
            return
        if self.admitted and not self.poisoned:
            self._clock, self._swdio, self._oe = 0, 1, False
            self._drive()
            self._barrier()
        self.admitted = False
        self.closed = True

    def exchange(self, commands: bytes) -> bytes:
        if not self.admitted or self.poisoned or self.closed:
            raise SWDBitbangError("Bridge not admitted or already closed")
        if type(commands) is not bytes:
            raise TypeError("Wire protocol requires bytes")
        responses = bytearray()
        for index, cmd in enumerate(commands):
            if cmd == ord("Q"):
                self.close()
                if index != len(commands) - 1:
                    raise SWDBitbangError("Trailing bytes after quit are prohibited")
                break
            if cmd == ord("O"):
                self._oe = True
                self._drive()
                self._barrier()
            elif cmd == ord("o"):
                self._oe = False
                self._drive()
                self._barrier()
            elif ord("d") <= cmd <= ord("g"):
                pair = cmd - ord("d")
                self._clock = (pair >> 1) & 1
                self._swdio = pair & 1
                self._drive()
                # This proof prioritizes physically ordered SWCLK edges over
                # throughput; a posted write must not collapse two edges.
                self._barrier()
            elif cmd == ord("c"):
                self._barrier()
                responses.append(ord("1") if self._read(self.REG_SAMPLE) & 1
                                 else ord("0"))
            elif cmd in (ord("r"), ord("B"), ord("b")):
                # r: both resets deasserted; no NRST or TRST capability.
                # B/b: optional cosmetic LED, no hardware mapping.
                pass
            else:
                self.close()
                raise SWDBitbangError("Unsupported reset/JTAG/delay/wire command")
        return bytes(responses)


def serve_connection(conn: socket.socket, bridge: RemoteBitbangSWD,
                     *, command_limit: int = 20_000_000) -> int:
    """Serve one already accepted local connection; never create a listener.

    This does not authorize actual hardware. The owner is responsible for
    trusted, local-only endpoint ownership, timeout and Board/Power proof.
    """
    if type(command_limit) is not int or not 1 <= command_limit <= 20_000_000:
        raise ValueError("Bounded command limit required")
    count = 0
    try:
        bridge.admit()
        while not bridge.closed:
            block = conn.recv(4096)
            if not block:
                raise SWDBitbangError("Unexpected EOF before Q")
            count += len(block)
            if count > command_limit:
                raise SWDBitbangError("Remote bitbang command budget exhausted")
            result = bridge.exchange(block)
            if result:
                conn.sendall(result)
        return count
    finally:
        bridge.close()


def serve_local_unix_once(path: str | Path, bridge: RemoteBitbangSWD,
                          *, idle_timeout_s: float = 30.0) -> int:
    """Bind exactly one user-owned local SWD session, only when called.

    Does not construct a real MMIO port, perform FPGA reconfiguration, or
    assert target power/reset. The invoking trusted supervisor must supply
    an independently admitted Site. A successful session leaves the FPGA Image
    loaded; Golden Restore is an optional, separate protected Root operation.
    """
    location = Path(path)
    if not location.is_absolute() or location.is_symlink() or location.exists():
        raise ValueError("Fresh absolute UNIX socket path required")
    parent = location.parent
    info = parent.stat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or
            info.st_mode & 0o077):
        raise ValueError("Socket directory must be private and owner-controlled")
    if type(idle_timeout_s) not in (float, int) or not 0 < idle_timeout_s <= 120:
        raise ValueError("Bounded socket idle timeout required")
    if len(os.fsencode(location)) >= 100:
        raise ValueError("UNIX socket path too long")
    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    created_inode = None
    try:
        previous_umask = os.umask(0o177)
        try:
            server.bind(str(location))
            os.chmod(location, 0o600)
            created_inode = location.lstat().st_ino
        finally:
            os.umask(previous_umask)
        server.listen(1)
        server.settimeout(float(idle_timeout_s))
        conn, _ = server.accept()
        with conn:
            conn.settimeout(float(idle_timeout_s))
            return serve_connection(conn, bridge)
    finally:
        server.close()
        if created_inode is not None:
            try:
                info = location.lstat()
                if stat.S_ISSOCK(info.st_mode) and info.st_ino == created_inode:
                    location.unlink()
            except FileNotFoundError:
                pass

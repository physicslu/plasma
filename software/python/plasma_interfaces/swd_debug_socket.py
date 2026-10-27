"""Bounded host-only connected UNIX transport for the guarded SWD Debug codec.

This module NEVER binds/listens for sockets, opens an FPGA/MMIO device, spawns
OpenOCD, or authorizes a Site. The caller injects an already connected AF_UNIX
stream, qualified SiteWordAccess, and a live external ownership/lease check.
The OpenOCD v0.12.0 remote_bitbang driver is JTAG-only. SWD bridge release
remains BLOCKED_VERSION_UNQUALIFIED until actual pinned-binary compatibility
and ARMv7/physical HIL are separately proven.
"""
from __future__ import annotations

import math
import socket

from .swd_debug_bitbang import BitbangProtocolError, SwdDebugBitbangCore


def serve_connected_unix(
    core: SwdDebugBitbangCore,
    connection: socket.socket,
    *,
    max_commands: int = 4096,
    timeout_seconds: float = 1.0,
) -> int:
    """Run at most max_commands single-byte SWD requests; Q terminates.

    Fail closed on EOF, timeout, unsupported bytes, count overflow or lost
    lease. Best-effort mode quiescence on errors; poisoned/uncertain MMIO
    requires the external protected recovery path, never a blind replay.
    The injected socket remains owned by the caller and is never listened on.
    """
    if not isinstance(core, SwdDebugBitbangCore):
        raise TypeError("Explicit SWD bitbang core required")
    if not isinstance(connection, socket.socket) or (
        connection.family != socket.AF_UNIX
        or (connection.type & socket.SOCK_STREAM) != socket.SOCK_STREAM
    ):
        raise BitbangProtocolError("AF_UNIX connected stream required; TCP forbidden")
    if type(max_commands) is not int or not 1 <= max_commands <= 100_000:
        raise ValueError("Bounded positive command limit required")
    if (type(timeout_seconds) not in (int, float)
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 60):
        raise ValueError("Bounded positive socket read timeout required")
    connection.settimeout(timeout_seconds)
    core.begin()
    try:
        for index in range(max_commands):
            try:
                request = connection.recv(1)
            except (OSError, TimeoutError) as exc:
                raise BitbangProtocolError("Socket reception failed or timed out") from exc
            if not request:
                raise BitbangProtocolError("Socket disconnected without Debug Q")
            reply = core.handle(request)
            if reply:
                try:
                    connection.sendall(reply)
                except (OSError, TimeoutError) as exc:
                    raise BitbangProtocolError("Socket response could not be delivered") from exc
            if request == b"Q":
                return index + 1
        raise BitbangProtocolError("Debug command limit reached without Q")
    finally:
        if core.open and not core.poisoned:
            core.close()

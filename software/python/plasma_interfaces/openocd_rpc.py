from __future__ import annotations

import asyncio
import math
from typing import Final

from plasma_core.errors import ErrorCode, PlasmaError


TCL_RPC_TERMINATOR: Final[bytes] = b"\x1a"
DEFAULT_MAX_RESPONSE_BYTES: Final[int] = 4 * 1024 * 1024


class OpenOCDRpcClient:
    """Async client for OpenOCD's local Tcl RPC machine interface.

    The protocol is a raw TCP request/response stream. Commands and responses are
    delimited by byte 0x1A. A timed-out or cancelled request invalidates the
    connection because a late response would otherwise desynchronize subsequent
    request/response framing.
    """

    def __init__(
        self,
        host: str,
        port: int,
        *,
        connect_timeout_s: float = 2.0,
        command_timeout_s: float = 30.0,
        max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES,
    ) -> None:
        if host not in {"127.0.0.1", "::1"}:
            raise ValueError("OpenOCD Tcl RPC must use an explicit loopback address")
        if not isinstance(port, int) or isinstance(port, bool) or not 1 <= port <= 65535:
            raise ValueError("OpenOCD Tcl RPC port must be in range 1..65535")
        for label, value in (
            ("connect_timeout_s", connect_timeout_s),
            ("command_timeout_s", command_timeout_s),
        ):
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{label} must be a positive finite number")
        if not isinstance(max_response_bytes, int) or max_response_bytes <= 0:
            raise ValueError("max_response_bytes must be a positive integer")

        self.host = host
        self.port = port
        self.connect_timeout_s = float(connect_timeout_s)
        self.command_timeout_s = float(command_timeout_s)
        self.max_response_bytes = max_response_bytes
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    @staticmethod
    def _validate_command(command: str) -> str:
        if not isinstance(command, str) or not command.strip():
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "OpenOCD Tcl RPC command is required")
        if any(ch in command for ch in ("\x00", "\x1a", "\n", "\r")):
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "OpenOCD Tcl RPC command contains forbidden framing/control characters",
            )
        return command

    async def _connect_unlocked(self) -> None:
        if self.connected:
            return
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_connection(
                    self.host,
                    self.port,
                    limit=self.max_response_bytes + 1,
                ),
                timeout=self.connect_timeout_s,
            )
        except asyncio.CancelledError:
            raise
        except TimeoutError as exc:
            raise PlasmaError(
                ErrorCode.CONNECTION_TIMEOUT,
                "OpenOCD Tcl RPC connection timed out",
                recoverable=True,
                original_exception=exc,
                context={"host": self.host, "port": self.port},
            ) from exc
        except OSError as exc:
            raise PlasmaError(
                ErrorCode.CONNECTION_FAILED,
                "OpenOCD Tcl RPC connection failed",
                recoverable=True,
                original_exception=exc,
                context={"host": self.host, "port": self.port},
            ) from exc
        self._reader = reader
        self._writer = writer

    async def connect(self) -> None:
        async with self._lock:
            await self._connect_unlocked()

    async def _close_unlocked(self) -> None:
        writer = self._writer
        self._reader = None
        self._writer = None
        if writer is None:
            return
        writer.close()
        try:
            await writer.wait_closed()
        except (ConnectionError, OSError):
            pass

    async def close(self) -> None:
        async with self._lock:
            await self._close_unlocked()

    async def command(self, command: str, *, timeout_s: float | None = None) -> str:
        command = self._validate_command(command)
        timeout = self.command_timeout_s if timeout_s is None else float(timeout_s)
        if not math.isfinite(timeout) or timeout <= 0:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                "OpenOCD Tcl RPC timeout must be a positive finite number",
            )

        async with self._lock:
            await self._connect_unlocked()
            reader = self._reader
            writer = self._writer
            assert reader is not None and writer is not None
            try:
                writer.write(command.encode("utf-8") + TCL_RPC_TERMINATOR)
                await writer.drain()
                framed = await asyncio.wait_for(
                    reader.readuntil(TCL_RPC_TERMINATOR),
                    timeout=timeout,
                )
            except asyncio.CancelledError:
                await self._close_unlocked()
                raise
            except TimeoutError as exc:
                await self._close_unlocked()
                raise PlasmaError(
                    ErrorCode.OPERATION_TIMEOUT,
                    "OpenOCD Tcl RPC command timed out",
                    recoverable=True,
                    original_exception=exc,
                    context={"host": self.host, "port": self.port},
                ) from exc
            except asyncio.LimitOverrunError as exc:
                await self._close_unlocked()
                raise PlasmaError(
                    ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE,
                    "OpenOCD Tcl RPC response exceeds configured limit",
                    recoverable=True,
                    original_exception=exc,
                    context={"max_response_bytes": self.max_response_bytes},
                ) from exc
            except (asyncio.IncompleteReadError, ConnectionError, OSError) as exc:
                await self._close_unlocked()
                raise PlasmaError(
                    ErrorCode.INTERFACE_FAILURE,
                    "OpenOCD Tcl RPC connection closed before a complete response",
                    recoverable=True,
                    original_exception=exc,
                    context={"host": self.host, "port": self.port},
                ) from exc

            payload = framed[:-1]
            if len(payload) > self.max_response_bytes:
                await self._close_unlocked()
                raise PlasmaError(
                    ErrorCode.PROTOCOL_PAYLOAD_TOO_LARGE,
                    "OpenOCD Tcl RPC response exceeds configured limit",
                    recoverable=True,
                    context={"max_response_bytes": self.max_response_bytes},
                )
            try:
                return payload.decode("utf-8")
            except UnicodeDecodeError as exc:
                await self._close_unlocked()
                raise PlasmaError(
                    ErrorCode.INTERFACE_FAILURE,
                    "OpenOCD Tcl RPC returned non-UTF-8 data",
                    recoverable=True,
                    original_exception=exc,
                ) from exc

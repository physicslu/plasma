from __future__ import annotations

import asyncio
import json
import os
import time
import uuid
from pathlib import Path
from typing import Any

from plasma_core.errors import ErrorCode, PlasmaError


DEFAULT_QUIESCE_TTL_S = 20
MIN_QUIESCE_TTL_S = 2
MAX_QUIESCE_TTL_S = 60
MAX_CONTROL_REQUEST_BYTES = 64 * 1024


class RuntimeControlError(RuntimeError):
    pass


class RuntimeQuiesceGate:
    """Server-authoritative gate used to make restart admission race-free.

    The gate is checked under the SiteManager execution lock. A bounded lease
    prevents a failed/crashed activation client from permanently blocking Jobs.
    """

    def __init__(self) -> None:
        self._token: str | None = None
        self._deadline_monotonic: float | None = None

    def _expire_if_needed(self) -> None:
        if self._token is None or self._deadline_monotonic is None:
            return
        if time.monotonic() >= self._deadline_monotonic:
            self._token = None
            self._deadline_monotonic = None

    def active(self) -> bool:
        self._expire_if_needed()
        return self._token is not None

    def acquire(self, ttl_s: int) -> dict[str, Any]:
        if isinstance(ttl_s, bool) or not isinstance(ttl_s, int):
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "quiesce ttl_s must be an integer")
        if ttl_s < MIN_QUIESCE_TTL_S or ttl_s > MAX_QUIESCE_TTL_S:
            raise PlasmaError(
                ErrorCode.INVALID_ARGUMENT,
                f"quiesce ttl_s must be {MIN_QUIESCE_TTL_S}..{MAX_QUIESCE_TTL_S}",
            )
        self._expire_if_needed()
        if self._token is not None:
            raise PlasmaError(
                ErrorCode.PPU_BUSY,
                "PPU runtime activation quiesce is already active",
                recoverable=True,
            )
        token = f"quiesce-{uuid.uuid4().hex}"
        self._token = token
        self._deadline_monotonic = time.monotonic() + ttl_s
        return {"token": token, "ttl_s": ttl_s}

    def release(self, token: str) -> None:
        self._expire_if_needed()
        if self._token is None:
            return
        if token != self._token:
            raise PlasmaError(ErrorCode.INVALID_ARGUMENT, "quiesce token does not match active lease")
        self._token = None
        self._deadline_monotonic = None

    def snapshot(self) -> dict[str, Any]:
        self._expire_if_needed()
        remaining = None
        if self._deadline_monotonic is not None:
            remaining = max(0.0, self._deadline_monotonic - time.monotonic())
        return {
            "active": self._token is not None,
            "ttl_remaining_s": remaining,
        }


class RuntimeControlServer:
    """Local Unix-socket control plane for authoritative quiesce operations."""

    def __init__(self, manager: Any, socket_path: Path) -> None:
        self.manager = manager
        self.socket_path = socket_path.expanduser().resolve()
        self._server: asyncio.AbstractServer | None = None

    async def start(self) -> None:
        self.socket_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass
        self._server = await asyncio.start_unix_server(self._handle, path=str(self.socket_path))
        os.chmod(self.socket_path, 0o600)

    async def close(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        try:
            self.socket_path.unlink()
        except FileNotFoundError:
            pass

    async def _handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        try:
            raw = await reader.readline()
            if not raw or len(raw) > MAX_CONTROL_REQUEST_BYTES:
                raise RuntimeControlError("runtime control request is empty or too large")
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, dict):
                raise RuntimeControlError("runtime control request must be a JSON object")
            operation = request.get("operation")
            if operation == "quiesce":
                if set(request) != {"operation", "ttl_s"}:
                    raise RuntimeControlError("quiesce request fields are invalid")
                result = self.manager.acquire_runtime_quiesce(request["ttl_s"])
            elif operation == "status":
                if set(request) != {"operation"}:
                    raise RuntimeControlError("status request fields are invalid")
                result = self.manager.runtime_quiesce_snapshot()
            elif operation == "release":
                if set(request) != {"operation", "token"} or not isinstance(request.get("token"), str):
                    raise RuntimeControlError("release request fields are invalid")
                self.manager.release_runtime_quiesce(request["token"])
                result = self.manager.runtime_quiesce_snapshot()
            else:
                raise RuntimeControlError("unsupported runtime control operation")
            payload = {"ok": True, "result": result}
        except (UnicodeDecodeError, json.JSONDecodeError, RuntimeControlError, PlasmaError) as exc:
            payload = {
                "ok": False,
                "error": {
                    "message": str(exc),
                    "code": exc.code.value if isinstance(exc, PlasmaError) else "runtime_control_error",
                },
            }
        writer.write((json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8"))
        try:
            await writer.drain()
        finally:
            writer.close()
            await writer.wait_closed()

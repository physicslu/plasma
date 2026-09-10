from __future__ import annotations

import argparse
import json
import os
import socket
import socketserver
import subprocess
from pathlib import Path
from typing import Any, Callable


MAX_MESSAGE_BYTES = 64 * 1024
DEFAULT_QUIESCE_TTL_S = 20


class RuntimeActivationHelperError(RuntimeError):
    pass


def _unix_request(path: Path, payload: dict[str, Any], *, timeout_s: float = 5.0) -> dict[str, Any]:
    raw = (json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8")
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(timeout_s)
            client.connect(str(path))
            client.sendall(raw)
            response = bytearray()
            while b"\n" not in response:
                chunk = client.recv(65536)
                if not chunk:
                    break
                response.extend(chunk)
                if len(response) > MAX_MESSAGE_BYTES:
                    raise RuntimeActivationHelperError("local control response exceeds limit")
    except OSError as exc:
        raise RuntimeActivationHelperError(f"local control socket unavailable: {exc}") from exc
    try:
        parsed = json.loads(bytes(response).split(b"\n", 1)[0].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, IndexError) as exc:
        raise RuntimeActivationHelperError("local control response is invalid JSON") from exc
    if not isinstance(parsed, dict):
        raise RuntimeActivationHelperError("local control response must be an object")
    return parsed


def _restart_server() -> None:
    try:
        subprocess.run(
            ["systemctl", "restart", "plasma-server.service"],
            check=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise RuntimeActivationHelperError(f"plasma-server.service restart failed: {exc}") from exc


class RuntimeActivationExecutor:
    """The only privileged operation exposed is restart of plasma-server.service."""

    def __init__(
        self,
        server_control_socket: Path,
        *,
        restart_server: Callable[[], None] = _restart_server,
    ) -> None:
        self.server_control_socket = server_control_socket.expanduser().resolve()
        self.restart_server = restart_server

    def execute(self, request: dict[str, Any]) -> dict[str, Any]:
        required = {"operation", "expected_ppu_id", "quiesce_ttl_s"}
        if set(request) != required or request.get("operation") != "restart_server":
            raise RuntimeActivationHelperError("runtime activation helper request is not allowlisted")
        expected_ppu_id = request.get("expected_ppu_id")
        ttl_s = request.get("quiesce_ttl_s")
        if not isinstance(expected_ppu_id, str) or not expected_ppu_id or len(expected_ppu_id) > 256:
            raise RuntimeActivationHelperError("expected_ppu_id is invalid")
        if isinstance(ttl_s, bool) or not isinstance(ttl_s, int) or not 2 <= ttl_s <= 60:
            raise RuntimeActivationHelperError("quiesce_ttl_s must be 2..60 seconds")

        response = _unix_request(
            self.server_control_socket,
            {"operation": "quiesce", "ttl_s": ttl_s},
        )
        if response.get("ok") is not True:
            error = response.get("error") if isinstance(response.get("error"), dict) else {}
            raise RuntimeActivationHelperError(str(error.get("message") or "server rejected runtime quiesce"))
        result = response.get("result")
        if not isinstance(result, dict) or result.get("ppu_id") != expected_ppu_id:
            token = result.get("token") if isinstance(result, dict) else None
            if isinstance(token, str):
                try:
                    _unix_request(self.server_control_socket, {"operation": "release", "token": token})
                except RuntimeActivationHelperError:
                    pass
            raise RuntimeActivationHelperError("runtime quiesce PPU identity does not match activation request")

        token = result.get("token")
        try:
            self.restart_server()
        except Exception:
            if isinstance(token, str):
                try:
                    _unix_request(self.server_control_socket, {"operation": "release", "token": token})
                except RuntimeActivationHelperError:
                    pass
            raise
        return {
            "restarted_service": "plasma-server.service",
            "expected_ppu_id": expected_ppu_id,
            "quiesce_acquired": True,
        }


class _RuntimeActivationServer(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, socket_path: str, executor: RuntimeActivationExecutor) -> None:
        self.executor = executor
        super().__init__(socket_path, _RuntimeActivationRequestHandler)


class _RuntimeActivationRequestHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        raw = self.rfile.readline(MAX_MESSAGE_BYTES + 1)
        try:
            if not raw or len(raw) > MAX_MESSAGE_BYTES:
                raise RuntimeActivationHelperError("runtime activation helper request is empty or too large")
            request = json.loads(raw.decode("utf-8"))
            if not isinstance(request, dict):
                raise RuntimeActivationHelperError("runtime activation helper request must be an object")
            result = self.server.executor.execute(request)
            payload = {"ok": True, "result": result}
        except (UnicodeDecodeError, json.JSONDecodeError, RuntimeActivationHelperError) as exc:
            payload = {"ok": False, "error": {"message": str(exc), "error_type": "RUNTIME_ACTIVATION_HELPER_ERROR"}}
        self.wfile.write((json.dumps(payload, separators=(",", ":"), sort_keys=True) + "\n").encode("utf-8"))


def serve(socket_path: Path, server_control_socket: Path) -> None:
    socket_path = socket_path.expanduser().resolve()
    socket_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        socket_path.unlink()
    except FileNotFoundError:
        pass
    server = _RuntimeActivationServer(str(socket_path), RuntimeActivationExecutor(server_control_socket))
    try:
        os.chmod(socket_path, 0o660)
        server.serve_forever(poll_interval=0.25)
    finally:
        server.server_close()
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser(description="Plasma bounded runtime activation helper")
    parser.add_argument("--socket", type=Path, required=True)
    parser.add_argument("--server-control-socket", type=Path, required=True)
    args = parser.parse_args()
    serve(args.socket, args.server_control_socket)


if __name__ == "__main__":
    main()

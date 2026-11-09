"""G13: bind every PPU Gateway (:18080) write to the current controller.

LOM-P2A-2 (P2A-0 spec §6.1, ADR-0008). The Gateway runs unprivileged and never
holds the controller credential. For each ``POST`` it

1. classifies the route with the SAME predicates the handlers dispatch on; an
   unclassified route fails closed (403) before its body is read;
2. forwards the ``PLASMA-PPU-HMAC-V1`` header to the root Bootstrap controller
   admission socket (nonce consumed there, before the body is read);
3. reads the bounded body and forwards method, exact request target, body
   SHA256 and operation class; the Bootstrap verifies against the controller
   record it re-reads for this request, applies the mode policy
   (``RECOVERY_ONLY`` denies normal writes) and holds the transition fence
   shared;
4. dispatches the write and MACs the response through the same connection;
   closing the connection ends the fence hold.

There is no session, token cache or generation shortcut: a revoked
controller's next request fails because the record changed. The generation is
reported to clients but never accepted as a credential. ``--host-lab-
unauthenticated-writes`` is an explicit host-lab mode for emulators and tests;
the deployed PPU unit always passes ``--controller-admission-socket``.
"""
from __future__ import annotations

import hashlib
import json
import re
import socket
from http import HTTPStatus
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

RESPONSE_HEADER = "X-Plasma-PPU-Response-Auth"
CHALLENGE_PATH = "/api/auth/challenge"
_LINE_LIMIT = 65536
_SEGMENT = r"[^/]+"


class AdmissionUnavailable(RuntimeError):
    pass


class ControllerAdmissionConnection:
    """One request = one Unix-socket connection (its lifetime is the fence hold)."""

    def __init__(self, path: Path, timeout_s: float = 15.0) -> None:
        self._sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._sock.settimeout(timeout_s)
        try:
            self._sock.connect(str(path))
        except OSError as exc:
            self._sock.close()
            raise AdmissionUnavailable("controller admission service is unavailable") from exc
        self._reader = self._sock.makefile("rb")

    def call(self, message: Mapping[str, Any]) -> dict[str, Any]:
        try:
            self._sock.sendall(json.dumps(message, sort_keys=True).encode() + b"\n")
            line = self._reader.readline(_LINE_LIMIT)
        except OSError as exc:
            raise AdmissionUnavailable("controller admission service failed") from exc
        if not line:
            raise AdmissionUnavailable("controller admission service closed the connection")
        reply = json.loads(line)
        if not isinstance(reply, dict):
            raise AdmissionUnavailable("controller admission reply is invalid")
        return reply

    def close(self) -> None:
        try:
            self._reader.close()
        finally:
            self._sock.close()


class ControllerWriteAdmissionMixin:
    """Must precede every handler class that implements ``do_POST`` in the MRO."""

    controller_admission_socket: Path | None = None
    host_lab_unauthenticated_writes: bool = False
    _admission: ControllerAdmissionConnection | None = None
    _admitted_raw_body: bytes | None = None

    @classmethod
    def configure_controller_admission(cls, *, socket_path: Path | None,
                                       host_lab_unauthenticated_writes: bool) -> None:
        if (socket_path is None) == (not host_lab_unauthenticated_writes):
            raise RuntimeError(
                "Gateway writes need exactly one of --controller-admission-socket "
                "(PPU) or --host-lab-unauthenticated-writes (host lab)")
        cls.controller_admission_socket = socket_path
        cls.host_lab_unauthenticated_writes = host_lab_unauthenticated_writes

    # -- inventory: every POST route the Gateway dispatches (G13)
    def controller_operation(self, path: str) -> str | None:
        normalized = path.rstrip("/") or path
        if normalized == "/api/settings/sites/activation":
            return "site.activation"
        if self._site_settings_id(path) is not None:  # type: ignore[attr-defined]
            return "site.settings.write"
        if (self.is_phase2_network_post_path(path)  # type: ignore[attr-defined]
                or normalized in {"/api/settings/gateway", "/api/mock/runtime"}):
            return "ppu.settings.write"
        if normalized == "/api/jobs":
            return "site.job.submit"
        if re.fullmatch(rf"/api/jobs/{_SEGMENT}/cancel", path):
            return "site.job.cancel"
        if normalized in {"/api/engineering/diagnostics/loopback",
                          "/api/engineering/diagnostics/openocd-control-plane",
                          "/api/engineering/session"}:
            return "engineering.write"
        if self._engineering_target(path) is not None:  # type: ignore[attr-defined]
            return "engineering.write"
        return None

    def _admission_refusal(self, status: int, code: str, **extra: Any) -> None:
        self._admission = None
        self._json(status, {"ok": False, "error": {"code": code, **extra}})  # type: ignore[attr-defined]

    def _relay_refusal(self, reply: Mapping[str, Any]) -> None:
        status = reply.get("status") if type(reply.get("status")) is int else 401
        code = reply.get("code") or reply.get("error") or "CONTROLLER_UNAUTHENTICATED"
        detail = reply.get("detail")
        extra: dict[str, Any] = {}
        if isinstance(detail, dict) and type(detail.get("controller_generation")) is int:
            extra["controller_generation"] = detail["controller_generation"]  # not a secret
        elif detail is not None:
            extra["detail"] = detail
        if code == "unauthorized":
            code = "CONTROLLER_UNAUTHENTICATED"
        self._admission_refusal(status, str(code), **extra)

    def do_GET(self) -> None:  # noqa: N802
        if urlparse(self.path).path == CHALLENGE_PATH and self.controller_admission_socket is not None:
            try:
                connection = ControllerAdmissionConnection(self.controller_admission_socket)
                try:
                    reply = connection.call({"op": "challenge"})
                finally:
                    connection.close()
            except (AdmissionUnavailable, ValueError):
                self._admission_refusal(HTTPStatus.SERVICE_UNAVAILABLE, "CONTROLLER_ADMISSION_UNAVAILABLE")
                return
            self._json(HTTPStatus.OK, reply)  # type: ignore[attr-defined]
            return
        super().do_GET()  # type: ignore[misc]

    def do_POST(self) -> None:  # noqa: N802
        self._admission, self._admitted_raw_body = None, None
        socket_path = self.controller_admission_socket
        if socket_path is None:
            if self.host_lab_unauthenticated_writes:
                super().do_POST()  # type: ignore[misc]
                return
            self._admission_refusal(HTTPStatus.SERVICE_UNAVAILABLE, "CONTROLLER_ADMISSION_NOT_CONFIGURED")
            return
        path = urlparse(self.path).path
        operation = self.controller_operation(path)
        if operation is None:
            self._admission_refusal(HTTPStatus.FORBIDDEN, "CONTROLLER_OPERATION_UNCLASSIFIED")
            return
        try:
            connection = ControllerAdmissionConnection(socket_path)
        except AdmissionUnavailable:
            self._admission_refusal(HTTPStatus.SERVICE_UNAVAILABLE, "CONTROLLER_ADMISSION_UNAVAILABLE")
            return
        try:
            reply = connection.call({"op": "admit_header",
                                     "authorization": self.headers.get("Authorization")})  # type: ignore[attr-defined]
            if reply.get("ok") is not True:
                self._relay_refusal(reply)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))  # type: ignore[attr-defined]
            except ValueError:
                length = -1
            if length < 0 or length > self.max_body_bytes:  # type: ignore[attr-defined]
                self._admission_refusal(HTTPStatus.BAD_REQUEST, "invalid_request_body_size")
                return
            raw = self.rfile.read(length) if length else b""  # type: ignore[attr-defined]
            reply = connection.call({"op": "admit", "method": "POST", "target": self.path,
                                     "operation": operation,
                                     "body_sha256": hashlib.sha256(raw).hexdigest()})
            if reply.get("ok") is not True:
                self._relay_refusal(reply)
                return
            self._admission, self._admitted_raw_body = connection, raw
            super().do_POST()  # type: ignore[misc]
        except (AdmissionUnavailable, ValueError):
            if self._admission is None:
                self._admission_refusal(HTTPStatus.SERVICE_UNAVAILABLE, "CONTROLLER_ADMISSION_UNAVAILABLE")
        finally:
            self._admission, self._admitted_raw_body = None, None
            connection.close()          # ends the shared transition-fence hold

    def _raw_body(self) -> bytes:
        if self._admitted_raw_body is not None:
            if not self._admitted_raw_body:
                raise ValueError("invalid request body size")
            return self._admitted_raw_body
        return super()._raw_body()  # type: ignore[misc]

    def _extra_response_headers(self, status: int, data: bytes) -> dict[str, str]:
        connection = self._admission
        if connection is None:
            return {}
        try:
            reply = connection.call({"op": "sign_response", "status": int(status),
                                     "body_sha256": hashlib.sha256(data).hexdigest()})
        except (AdmissionUnavailable, ValueError):
            reply = {}
        header = reply.get("header")
        if reply.get("ok") is not True or type(header) is not str:
            # Unproven response: P2A-1 clients treat it as OUTCOME_UNKNOWN/refusal.
            self._admission = None
            return {}
        return {RESPONSE_HEADER: header}

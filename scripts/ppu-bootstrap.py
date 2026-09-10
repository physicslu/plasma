#!/usr/bin/env python3
"""Minimal PPU factory/recovery bootstrap control surface.

This module intentionally uses only the Python standard library and remains
compatible with the stock PYNQ-Z2 Python 3.10 runtime.  It is independent from
the Plasma application runtime that it observes and will later manage.

Phase 1 is read-only over HTTP.  Runtime mutation is deliberately absent until
the deployment engine and authenticated Control Station transport exist.
"""

from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import os
import sys
from dataclasses import asdict, dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Mapping
from urllib.parse import urlparse

BOOTSTRAP_API_VERSION = "1"
BOOTSTRAP_VERSION = "0.1.0"
DEFAULT_PORT = 18081
MAX_IDENTITY_BYTES = 64 * 1024


class BootstrapError(RuntimeError):
    """Raised when the bootstrap cannot establish trustworthy local state."""


@dataclass(frozen=True)
class BootstrapPaths:
    product_root: Path = Path("/opt/plasma")
    state_root: Path = Path("/var/lib/plasma-bootstrap")
    machine_id_path: Path = Path("/etc/machine-id")

    @property
    def current(self) -> Path:
        return self.product_root / "current"

    @property
    def identity_file(self) -> Path:
        return self.state_root / "identity.json"


@dataclass(frozen=True)
class BootstrapIdentity:
    device_id: str
    ppu_id: str | None
    facility_id: str | None
    hardware_revision: str | None


@dataclass(frozen=True)
class RuntimeStatus:
    state: str
    release_id: str | None
    product_version: str | None
    git_sha: str | None
    target: str | None
    reason: str | None = None


def _read_json_object(path: Path, *, max_bytes: int = MAX_IDENTITY_BYTES) -> dict[str, Any]:
    try:
        size = path.stat().st_size
    except OSError as exc:
        raise BootstrapError(f"cannot stat JSON file {path}: {exc}") from exc
    if size < 0 or size > max_bytes:
        raise BootstrapError(f"JSON file exceeds bootstrap safety limit: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BootstrapError(f"cannot read JSON file {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise BootstrapError(f"JSON file must contain an object: {path}")
    return payload


def _single_line_optional(value: object, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value or "\n" in value or "\r" in value:
        raise BootstrapError(f"identity field {field} must be a non-empty single-line string or null")
    return value


def _machine_device_id(path: Path) -> str:
    try:
        raw = path.read_text(encoding="utf-8").strip().lower()
    except (OSError, UnicodeDecodeError) as exc:
        raise BootstrapError(f"cannot read machine identity {path}: {exc}") from exc
    if len(raw) < 16 or len(raw) > 128 or any(ch not in "0123456789abcdef-" for ch in raw):
        raise BootstrapError("machine identity is malformed")
    # Do not expose the OS machine-id verbatim over the product API.  A stable,
    # domain-separated identifier is sufficient for pre-commissioning identity.
    digest = hashlib.sha256(("plasma-ppu-bootstrap-v1:" + raw).encode("ascii")).hexdigest()
    return "ppu-device-" + digest[:24]


def load_identity(paths: BootstrapPaths) -> BootstrapIdentity:
    device_id = _machine_device_id(paths.machine_id_path)
    if not paths.identity_file.exists():
        return BootstrapIdentity(device_id, None, None, None)
    payload = _read_json_object(paths.identity_file)
    schema = payload.get("schema_version")
    if schema != 1:
        raise BootstrapError(f"unsupported bootstrap identity schema: {schema!r}")
    recorded_device = payload.get("device_id")
    if recorded_device is not None and recorded_device != device_id:
        raise BootstrapError("bootstrap identity device_id does not match this PPU")
    return BootstrapIdentity(
        device_id=device_id,
        ppu_id=_single_line_optional(payload.get("ppu_id"), "ppu_id"),
        facility_id=_single_line_optional(payload.get("facility_id"), "facility_id"),
        hardware_revision=_single_line_optional(payload.get("hardware_revision"), "hardware_revision"),
    )


def _release_id(manifest: Mapping[str, Any]) -> str:
    version = manifest.get("product_version")
    git_sha = manifest.get("git_sha")
    if not isinstance(version, str) or not version:
        raise BootstrapError("active release product_version is invalid")
    if (
        not isinstance(git_sha, str)
        or len(git_sha) != 40
        or any(ch not in "0123456789abcdefABCDEF" for ch in git_sha)
    ):
        raise BootstrapError("active release git_sha is invalid")
    return f"{version}-{git_sha[:12].lower()}"


def inspect_runtime(paths: BootstrapPaths) -> RuntimeStatus:
    current = paths.current
    if not current.exists() and not current.is_symlink():
        return RuntimeStatus("runtime_absent", None, None, None, None)
    if not current.is_symlink():
        return RuntimeStatus(
            "recovery_required", None, None, None, None, "managed current path is not a symlink"
        )
    try:
        resolved = current.resolve(strict=True)
        resolved.relative_to((paths.product_root / "releases").resolve())
    except (OSError, ValueError) as exc:
        return RuntimeStatus("recovery_required", None, None, None, None, f"unsafe current release: {exc}")
    manifest_path = resolved / "release.json"
    try:
        manifest = _read_json_object(manifest_path)
        if manifest.get("role") != "ppu" or manifest.get("target") != "linux-armv7l":
            raise BootstrapError("active release role/target is not ppu/linux-armv7l")
        rid = _release_id(manifest)
    except BootstrapError as exc:
        return RuntimeStatus("recovery_required", None, None, None, None, str(exc))
    if resolved.name != rid:
        return RuntimeStatus(
            "recovery_required",
            rid,
            str(manifest.get("product_version")),
            str(manifest.get("git_sha")).lower(),
            str(manifest.get("target")),
            "active release directory does not match release identity",
        )
    return RuntimeStatus(
        "runtime_active",
        rid,
        str(manifest.get("product_version")),
        str(manifest.get("git_sha")).lower(),
        str(manifest.get("target")),
    )


def status_document(paths: BootstrapPaths) -> dict[str, Any]:
    identity = load_identity(paths)
    runtime = inspect_runtime(paths)
    return {
        "schema_version": 1,
        "bootstrap": {
            "api_version": BOOTSTRAP_API_VERSION,
            "version": BOOTSTRAP_VERSION,
            "state": "bootstrap_ready",
        },
        "identity": asdict(identity),
        "runtime": asdict(runtime),
        "fpga": {
            "pl_version": None,
            "pl_compatibility": "not_managed",
            "pl_qualification": "not_qualified",
        },
        "capabilities": {
            "runtime_deployment": False,
            "identity_update": False,
            "fpga_update": False,
        },
    }


def render_systemd_unit(*, python_executable: str, script_path: str, host: str, port: int) -> str:
    _validate_host_port(host, port)
    return "\n".join(
        [
            "[Unit]",
            "Description=Plasma PPU Bootstrap / Recovery Service",
            "After=network-online.target",
            "Wants=network-online.target",
            "",
            "[Service]",
            "Type=simple",
            "User=root",
            "Group=root",
            "Restart=on-failure",
            "RestartSec=2",
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "ProtectHome=true",
            f"ExecStart={python_executable} {script_path} serve --host {host} --port {port}",
            "",
            "[Install]",
            "WantedBy=multi-user.target",
            "",
        ]
    )


def _validate_host_port(host: str, port: int) -> tuple[str, int]:
    try:
        address = ipaddress.ip_address(host)
    except ValueError as exc:
        raise BootstrapError("bootstrap host must be an explicit IP address") from exc
    if address.version != 4 or address.is_multicast or address.is_unspecified:
        raise BootstrapError("bootstrap host must be an explicit non-multicast IPv4 address")
    if port < 1 or port > 65535:
        raise BootstrapError("bootstrap port must be 1..65535")
    return str(address), port


class _BootstrapHTTPServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self, address: tuple[str, int], paths: BootstrapPaths):
        self.bootstrap_paths = paths
        super().__init__(address, _BootstrapHandler)


class _BootstrapHandler(BaseHTTPRequestHandler):
    server_version = "PlasmaBootstrap/1"

    @property
    def paths(self) -> BootstrapPaths:
        return self.server.bootstrap_paths  # type: ignore[attr-defined]

    def log_message(self, fmt: str, *args: object) -> None:
        sys.stderr.write("bootstrap-http " + (fmt % args) + "\n")

    def _json(self, status: HTTPStatus, payload: Mapping[str, Any]) -> None:
        body = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        path = urlparse(self.path).path
        try:
            if path == "/v1/health":
                self._json(
                    HTTPStatus.OK,
                    {
                        "ok": True,
                        "service": "plasma-ppu-bootstrap",
                        "api_version": BOOTSTRAP_API_VERSION,
                        "bootstrap_version": BOOTSTRAP_VERSION,
                    },
                )
                return
            if path == "/v1/status":
                self._json(HTTPStatus.OK, status_document(self.paths))
                return
            self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})
        except BootstrapError as exc:
            self._json(
                HTTPStatus.SERVICE_UNAVAILABLE,
                {"ok": False, "error": "bootstrap_state_invalid", "message": str(exc)},
            )

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        # Deliberately fail closed in Phase 1.  Do not create an unauthenticated
        # remote root-mutation surface before the deployment/auth contracts exist.
        self._json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"ok": False, "error": "mutation_not_enabled"},
        )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Plasma PPU factory/recovery bootstrap")
    parser.add_argument("--product-root", type=Path, default=Path("/opt/plasma"))
    parser.add_argument("--state-root", type=Path, default=Path("/var/lib/plasma-bootstrap"))
    parser.add_argument("--machine-id", type=Path, default=Path("/etc/machine-id"))
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("inspect", help="print bootstrap/identity/runtime state as JSON")

    serve = sub.add_parser("serve", help="serve the read-only bootstrap API")
    serve.add_argument("--host", required=True, help="explicit IPv4 bind address")
    serve.add_argument("--port", type=int, default=DEFAULT_PORT)

    unit = sub.add_parser("render-systemd-unit", help="render the bootstrap systemd unit")
    unit.add_argument("--host", required=True)
    unit.add_argument("--port", type=int, default=DEFAULT_PORT)
    unit.add_argument("--python", dest="python_executable", default="/usr/bin/python3")
    unit.add_argument("--script", dest="script_path", default="/opt/plasma/bootstrap/ppu-bootstrap.py")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    paths = BootstrapPaths(args.product_root, args.state_root, args.machine_id)
    if args.command == "inspect":
        print(json.dumps(status_document(paths), indent=2, sort_keys=True))
        return 0
    if args.command == "render-systemd-unit":
        print(
            render_systemd_unit(
                python_executable=args.python_executable,
                script_path=args.script_path,
                host=args.host,
                port=args.port,
            ),
            end="",
        )
        return 0
    if args.command == "serve":
        host, port = _validate_host_port(args.host, args.port)
        server = _BootstrapHTTPServer((host, port), paths)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        return 0
    raise AssertionError(f"unreachable command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

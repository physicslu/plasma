#!/usr/bin/env python3
"""Ephemeral integration test for the z2like-demo managed Nginx ingress.

This test runs entirely on a disposable CI host. It renders the production
server block from plasmactl-z2like-demo-managed-ingress, validates it with the
real nginx parser, starts nginx unprivileged on a high loopback port, and drives
requests through fake Gateway/Bootstrap upstreams bound to the runner's private
IPv4 address.

It is intentionally not a substitute for SWPC/Cloudflare live acceptance. Its
purpose is to shift Nginx syntax, route, method and rewrite failures left into PR
CI before an operator touches SWPC host state.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
INGRESS = ROOT / "scripts" / "plasmactl-z2like-demo-managed-ingress"
RESERVED_PORTS = {9900, 18080, 18081}
UPLOAD_ID = "0123456789abcdef0123456789abcdef"


class GateError(RuntimeError):
    pass


class RequestRecorder:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._items: list[tuple[str, str, str]] = []

    def add(self, role: str, method: str, path: str) -> None:
        with self._lock:
            self._items.append((role, method, path))

    def snapshot(self) -> list[tuple[str, str, str]]:
        with self._lock:
            return list(self._items)


RECORDER = RequestRecorder()


class FakeUpstreamHandler(BaseHTTPRequestHandler):
    server_version = "PlasmaEphemeralUpstream/1"

    def log_message(self, _format: str, *_args: object) -> None:
        return

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def _handle(self) -> None:
        role = str(getattr(self.server, "plasma_role"))
        RECORDER.add(role, self.command, self.path)

        if role == "gateway":
            if self.command == "GET" and self.path == "/api/health/ready":
                self._json(
                    HTTPStatus.OK,
                    {"ok": True, "gateway": "alive", "execution": "ready"},
                )
                return
            if self.command == "GET" and self.path == "/api/settings/sites":
                self._json(HTTPStatus.OK, {"ok": True, "sites": []})
                return
            if self.command == "POST" and self.path == "/api/jobs":
                self._json(HTTPStatus.CREATED, {"ok": True, "job": {"job_id": "ephemeral"}})
                return
            self._json(HTTPStatus.OK, {"ok": True, "role": role, "path": self.path})
            return

        if self.command == "GET" and self.path == "/v1/status":
            self._json(
                HTTPStatus.OK,
                {"ok": True, "bootstrap": {"state": "bootstrap_ready"}},
            )
            return
        if self.command == "POST" and self.path == "/v1/uploads":
            self._json(HTTPStatus.CREATED, {"ok": True, "upload": {"upload_id": UPLOAD_ID}})
            return
        if self.command == "POST" and self.path in {
            f"/v1/uploads/{UPLOAD_ID}/chunks",
            f"/v1/uploads/{UPLOAD_ID}/commit",
        }:
            self._json(HTTPStatus.OK, {"ok": True, "path": self.path})
            return
        if self.command == "POST" and self.path == "/v1/deployments":
            self._json(HTTPStatus.ACCEPTED, {"ok": True, "deployment": {"state": "queued"}})
            return
        self._json(HTTPStatus.NOT_FOUND, {"ok": False, "error": "not_found"})

    do_GET = _handle
    do_POST = _handle


class ReusableThreadingHTTPServer(ThreadingHTTPServer):
    allow_reuse_address = True


class RunningServer:
    def __init__(self, host: str, port: int, role: str) -> None:
        try:
            self.server = ReusableThreadingHTTPServer((host, port), FakeUpstreamHandler)
        except OSError as exc:
            raise GateError(f"cannot bind ephemeral {role} upstream at {host}:{port}: {exc}") from exc
        setattr(self.server, "plasma_role", role)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "RunningServer":
        self.thread.start()
        return self

    def __exit__(self, *_exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def private_ipv4() -> str:
    candidates: list[str] = []
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("198.18.0.1", 9))
        candidates.append(str(sock.getsockname()[0]))
    except OSError:
        pass
    finally:
        sock.close()

    try:
        for item in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            candidates.append(str(item[4][0]))
    except socket.gaierror:
        pass

    for candidate in candidates:
        if candidate and not candidate.startswith("127.") and candidate != "0.0.0.0":
            return candidate
    raise GateError("cannot determine a non-loopback IPv4 address for fake upstreams")


def reserve_loopback_port() -> int:
    for _ in range(20):
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(("127.0.0.1", 0))
            port = int(sock.getsockname()[1])
        finally:
            sock.close()
        if port > 1024 and port not in RESERVED_PORTS:
            return port
    raise GateError("cannot reserve a high loopback port for ephemeral nginx")


def render_server_block(host: str, managed_port: int) -> str:
    env = dict(os.environ)
    env.update(
        {
            "PLASMA_Z2LIKE_DEMO_MANAGED_PORT": str(managed_port),
            "PLASMA_Z2LIKE_DEMO_GATEWAY_ROOT": f"http://{host}:18080",
            "PLASMA_Z2LIKE_DEMO_BOOTSTRAP_ROOT": f"http://{host}:18081",
        }
    )

    # Exercise the production validation contract before rendering. status is
    # read-only and does not inspect or mutate host Nginx state.
    checked = subprocess.run(
        [str(INGRESS), "status"],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
        check=False,
    )
    if checked.returncode != 0:
        raise GateError(f"managed ingress validation failed: {checked.stderr.strip()}")

    rendered = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1" help >/dev/null; render_nginx',
            "_",
            str(INGRESS),
        ],
        cwd=ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
        check=False,
    )
    if rendered.returncode != 0 or "server {" not in rendered.stdout:
        raise GateError(
            "cannot render production Nginx server block: "
            f"rc={rendered.returncode} stderr={rendered.stderr.strip()!r}"
        )
    return rendered.stdout


def request(base: str, path: str, *, method: str = "GET") -> tuple[int, dict[str, Any] | None]:
    data = b"{}" if method in {"POST", "PUT", "PATCH"} else None
    req = urllib.request.Request(
        base + path,
        method=method,
        data=data,
        headers={"Content-Type": "application/json", "Accept": "application/json"},
    )
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(req, timeout=5) as response:
            status = int(response.status)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
    try:
        payload = json.loads(raw.decode("utf-8")) if raw else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        payload = None
    return status, payload if isinstance(payload, dict) else None


def expect_status(base: str, path: str, expected: int, *, method: str = "GET") -> dict[str, Any] | None:
    status, payload = request(base, path, method=method)
    if status != expected:
        raise GateError(f"{method} {path} returned HTTP {status}, expected {expected}: {payload!r}")
    return payload


def expect_record(role: str, method: str, path: str) -> None:
    if (role, method, path) not in RECORDER.snapshot():
        raise GateError(f"upstream did not observe expected request: {(role, method, path)!r}")


def run_gate() -> dict[str, Any]:
    if os.geteuid() == 0:
        raise GateError("ephemeral Nginx integration must run as a non-root CI user")
    if not INGRESS.is_file():
        raise GateError(f"managed ingress script is missing: {INGRESS}")
    if subprocess.run(["nginx", "-v"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode != 0:
        raise GateError("nginx executable is unavailable; install it in the disposable CI runner")

    host = private_ipv4()
    managed_port = reserve_loopback_port()
    server_block = render_server_block(host, managed_port)

    with tempfile.TemporaryDirectory(prefix="plasma-nginx-ephemeral-") as temporary:
        tmp = Path(temporary)
        for name in ("client_body", "proxy"):
            (tmp / name).mkdir()
        config = tmp / "nginx.conf"
        log = tmp / "nginx.log"
        config.write_text(
            "daemon off;\n"
            "master_process off;\n"
            f"error_log {log} info;\n"
            f"pid {tmp / 'nginx.pid'};\n"
            "events {}\n"
            "http {\n"
            "  access_log off;\n"
            f"  client_body_temp_path {tmp / 'client_body'};\n"
            f"  proxy_temp_path {tmp / 'proxy'};\n"
            f"{server_block}\n"
            "}\n",
            encoding="utf-8",
        )

        syntax = subprocess.run(
            ["nginx", "-p", f"{tmp}/", "-c", str(config), "-t"],
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=10,
            check=False,
        )
        if syntax.returncode != 0:
            raise GateError(f"rendered Nginx config failed nginx -t:\n{syntax.stdout}")

        with RunningServer(host, 18080, "gateway"), RunningServer(host, 18081, "bootstrap"):
            with log.open("a", encoding="utf-8") as log_stream:
                nginx = subprocess.Popen(
                    ["nginx", "-p", f"{tmp}/", "-c", str(config)],
                    stdout=log_stream,
                    stderr=subprocess.STDOUT,
                    text=True,
                )
                try:
                    base = f"http://127.0.0.1:{managed_port}"
                    deadline = time.monotonic() + 5
                    while True:
                        try:
                            status, _ = request(base, "/api/health/ready")
                            if status == 200:
                                break
                        except OSError:
                            pass
                        if nginx.poll() is not None:
                            raise GateError(f"ephemeral nginx exited early with rc={nginx.returncode}")
                        if time.monotonic() >= deadline:
                            raise GateError("ephemeral nginx did not become reachable")
                        time.sleep(0.05)

                    ready = expect_status(base, "/api/health/ready", 200)
                    if not ready or ready.get("ok") is not True or ready.get("execution") != "ready":
                        raise GateError(f"Gateway readiness payload was not preserved: {ready!r}")
                    expect_record("gateway", "GET", "/api/health/ready")

                    expect_status(base, "/api/settings/sites", 200)
                    expect_record("gateway", "GET", "/api/settings/sites")
                    expect_status(base, "/api/settings/gateway", 403, method="POST")
                    expect_status(base, "/api/jobs", 403)
                    expect_status(base, "/api/jobs", 201, method="POST")
                    expect_record("gateway", "POST", "/api/jobs")

                    bootstrap = expect_status(base, "/__plasma/bootstrap/v1/status", 200)
                    if not bootstrap or bootstrap.get("bootstrap", {}).get("state") != "bootstrap_ready":
                        raise GateError(f"Bootstrap status payload was not preserved: {bootstrap!r}")
                    expect_record("bootstrap", "GET", "/v1/status")
                    expect_status(base, "/__plasma/bootstrap/v1/status", 403, method="POST")
                    expect_status(base, "/__plasma/bootstrap/v1/uploads", 403)

                    expect_status(base, "/__plasma/bootstrap/v1/uploads", 201, method="POST")
                    expect_record("bootstrap", "POST", "/v1/uploads")
                    expect_status(
                        base,
                        f"/__plasma/bootstrap/v1/uploads/{UPLOAD_ID}/chunks",
                        200,
                        method="POST",
                    )
                    expect_record("bootstrap", "POST", f"/v1/uploads/{UPLOAD_ID}/chunks")
                    expect_status(
                        base,
                        f"/__plasma/bootstrap/v1/uploads/{UPLOAD_ID}/commit",
                        200,
                        method="POST",
                    )
                    expect_record("bootstrap", "POST", f"/v1/uploads/{UPLOAD_ID}/commit")
                    expect_status(base, "/__plasma/bootstrap/v1/deployments", 202, method="POST")
                    expect_record("bootstrap", "POST", "/v1/deployments")

                    before = len(RECORDER.snapshot())
                    expect_status(base, "/__plasma/bootstrap/v1/not-allowlisted", 404)
                    expect_status(base, "/api/not-allowlisted", 404)
                    after = len(RECORDER.snapshot())
                    if after != before:
                        raise GateError("unknown paths escaped the Nginx deny boundary to an upstream")
                finally:
                    if nginx.poll() is None:
                        nginx.terminate()
                        try:
                            nginx.wait(timeout=5)
                        except subprocess.TimeoutExpired:
                            nginx.kill()
                            nginx.wait(timeout=5)

        if nginx.returncode not in {0, -15}:
            detail = log.read_text(encoding="utf-8", errors="replace") if log.exists() else ""
            raise GateError(f"ephemeral nginx shutdown was abnormal: rc={nginx.returncode}\n{detail}")

    return {
        "result": "PASS",
        "gate": "z2like-demo-ephemeral-nginx-integration",
        "nginx_syntax": "PASS",
        "gateway_positive_route": "PASS",
        "bootstrap_prefix_projection": "PASS",
        "bootstrap_chunk_rewrite": "PASS",
        "method_allowlist": "PASS",
        "unknown_route_blocking": "PASS",
        "execution": "disposable-ci-host",
        "requires_swpc": False,
        "hardware_boundary": "closed",
        "not_claimed": [
            "Cloudflare route correctness",
            "Render deployment state",
            "SWPC host reload behavior",
            "PYNQ-Z2 hardware",
            "PL/FPGA",
            "real IC programming",
        ],
    }


def main() -> int:
    try:
        result = run_gate()
    except (GateError, OSError, subprocess.SubprocessError) as exc:
        print(f"z2like-demo-nginx-ephemeral: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

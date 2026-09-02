#!/usr/bin/env python3
"""Run a source-tree-independent smoke test against an extracted Control Station runtime."""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request, build_opener


class SmokeError(RuntimeError):
    pass


_DIRECT_HTTP = build_opener(ProxyHandler({}))


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, object] | None = None,
    timeout: float = 2.0,
) -> tuple[int, dict[str, object]]:
    body = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    try:
        with _DIRECT_HTTP.open(request, timeout=timeout) as response:
            raw = response.read()
            status = int(response.status)
    except HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    except (URLError, TimeoutError) as exc:
        raise SmokeError(f"request failed: {url}: {exc}") from exc
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmokeError(f"response is not JSON: {url}: status={status}") from exc
    if not isinstance(decoded, dict):
        raise SmokeError(f"response JSON root is not an object: {url}")
    return status, decoded


def _run_probe(
    args: list[str],
    *,
    cwd: Path,
    env: dict[str, str],
    label: str,
    timeout_s: float = 10.0,
) -> None:
    try:
        completed = subprocess.run(
            args,
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=timeout_s,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        output = exc.stdout or ""
        raise SmokeError(f"{label} timed out\n{output}") from exc
    if completed.returncode != 0:
        raise SmokeError(
            f"{label} failed with code {completed.returncode}\n{completed.stdout}"
        )
    print(f"{label}: PASS", flush=True)


def _probe_manager_bootstrap(
    manager_entry: Path,
    manager_config: Path,
    *,
    temp_root: Path,
    env: dict[str, str],
) -> None:
    _run_probe(
        [sys.executable, str(manager_entry), "--help"],
        cwd=temp_root,
        env=env,
        label="Control Station packaged Manager import/argparse probe",
    )
    config_probe = (
        "import sys; "
        "sys.path.insert(0, sys.argv[1]); "
        "from plasma_manager.config import load_manager_config; "
        "load_manager_config(sys.argv[2]); "
        "print('config-ok')"
    )
    _run_probe(
        [sys.executable, "-c", config_probe, str(manager_entry), str(manager_config)],
        cwd=temp_root,
        env=env,
        label="Control Station packaged Manager config probe",
    )
    socket_probe = (
        "import sys; "
        "sys.path.insert(0, sys.argv[1]); "
        "from plasma_manager.server import PlasmaManagerHandler, PlasmaManagerHTTPServer; "
        "server=PlasmaManagerHTTPServer(('127.0.0.1', 0), PlasmaManagerHandler); "
        "print(server.server_port); "
        "server.server_close()"
    )
    _run_probe(
        [sys.executable, "-c", socket_probe, str(manager_entry)],
        cwd=temp_root,
        env=env,
        label="Control Station packaged Manager socket-bind probe",
    )


def _wait_for_manager(port: int, process: subprocess.Popen[bytes], deadline_s: float = 20.0) -> None:
    deadline = time.monotonic() + deadline_s
    url = f"http://127.0.0.1:{port}/api/health/live"
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SmokeError(f"Manager exited before readiness with code {process.returncode}")
        try:
            status, payload = _request_json(url, timeout=0.5)
            if status == 200 and payload.get("ok") is True and payload.get("service") == "plasma-manager":
                return
        except SmokeError:
            pass
        time.sleep(0.15)
    raise SmokeError("Manager readiness timed out")


class _FakePPUHandler(BaseHTTPRequestHandler):
    ppu_id = "runtime-smoke-ppu"

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    @classmethod
    def _ppu(cls) -> dict[str, object]:
        return {
            "ppu_id": cls.ppu_id,
            "facility_id": "runtime-smoke-facility",
            "model": "runtime-smoke",
            "display_name": "Runtime Smoke PPU",
            "site_count": 2,
            "enabled_site_count": 2,
            "capabilities": {
                "max_supported_sites": 2,
                "operations": ["erase", "program", "verify", "read"],
            },
        }

    def do_GET(self) -> None:
        if self.path == "/api/health/live":
            self._json(200, {"ok": True, "service": "plasma-web-rest-gateway", "gateway": "alive"})
            return
        if self.path == "/api/health/ready":
            self._json(
                200,
                {
                    "ok": True,
                    "gateway": "alive",
                    "execution": "ready",
                    "ppu_id": self.ppu_id,
                },
            )
            return
        if self.path == "/api/node":
            self._json(
                200,
                {
                    "ok": True,
                    "contract_version": "1",
                    "node_role": "ppu",
                    "manager_required": False,
                    "ppu": self._ppu(),
                    "links": {
                        "status": "/api/status",
                        "jobs": "/api/jobs",
                        "liveness": "/api/health/live",
                        "readiness": "/api/health/ready",
                    },
                },
            )
            return
        if self.path == "/api/status":
            self._json(
                200,
                {
                    "ok": True,
                    "ppu": self._ppu(),
                    "sites": [
                        {
                            "site_id": 1,
                            "enabled": True,
                            "state": "idle",
                            "current_job_id": None,
                            "queued_jobs": 0,
                            "interface": "SWD",
                            "target": "runtime-smoke-target",
                        },
                        {
                            "site_id": 2,
                            "enabled": True,
                            "state": "idle",
                            "current_job_id": None,
                            "queued_jobs": 0,
                            "interface": "SWD",
                            "target": "runtime-smoke-target",
                        },
                    ],
                },
            )
            return
        self._json(404, {"ok": False, "error": {"message": "not found"}})


def _verify_registry_lifecycle_via_console(
    port: int,
    process: subprocess.Popen[bytes],
    *,
    fake_ppu_endpoint: str,
    node_executable: str,
    cwd: Path,
    env: dict[str, str],
    deadline_s: float = 30.0,
) -> None:
    if process.poll() is not None:
        raise SmokeError(f"Console exited before readiness with code {process.returncode}")
    script = r"""
const base = process.argv[1];
const endpoint = process.argv[2];
const deadline = Date.now() + Number(process.argv[3]);
const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

async function request(path, init = {}) {
  const response = await fetch(`${base}${path}`, {
    ...init,
    headers: {
      Accept: "application/json",
      ...(init.body ? { "Content-Type": "application/json" } : {}),
      ...(init.headers ?? {}),
    },
    signal: AbortSignal.timeout(5000),
  });
  const text = await response.text();
  let payload = null;
  try { payload = JSON.parse(text); } catch {}
  return { status: response.status, payload, text };
}

let registry = null;
while (Date.now() < deadline) {
  try {
    registry = await request("/api/manager/registry");
    if (registry.status === 200 && registry.payload?.ok === true) break;
  } catch {}
  await sleep(150);
}
if (!registry || registry.status !== 200 || registry.payload?.ok !== true) {
  console.error(`registry readiness failed: ${JSON.stringify(registry)}`);
  process.exit(2);
}
if (registry.payload.mutable !== true || registry.payload.storage !== "file") {
  console.error(`registry is not mutable file-backed state: ${registry.text}`);
  process.exit(2);
}
if (!Array.isArray(registry.payload.ppus) || registry.payload.ppus.length !== 0) {
  console.error(`registry should start empty: ${registry.text}`);
  process.exit(2);
}

const added = await request("/api/manager/registry", {
  method: "POST",
  body: JSON.stringify({ alias: "runtime-smoke-ppu", endpoint }),
});
if (added.status !== 201 || added.payload?.entry?.lifecycle !== "pending") {
  console.error(`registry add failed: status=${added.status} body=${added.text}`);
  process.exit(2);
}

let fleet = null;
while (Date.now() < deadline) {
  try {
    fleet = await request("/api/fleet");
    const ppu = fleet.payload?.ppus?.find?.((item) => item.alias === "runtime-smoke-ppu");
    if (
      fleet.status === 200
      && ppu?.observation?.state === "current"
      && ppu?.transport_state === "reachable"
      && ppu?.execution_state === "ready"
      && ppu?.identity?.ppu_id === "runtime-smoke-ppu"
      && ppu?.identity_conflict === false
      && ppu?.degraded === false
      && ppu?.topology?.site_count === 2
    ) break;
  } catch {}
  await sleep(150);
}
const trusted = fleet?.payload?.ppus?.find?.((item) => item.alias === "runtime-smoke-ppu");
if (
  fleet?.status !== 200
  || trusted?.observation?.state !== "current"
  || trusted?.execution_state !== "ready"
  || trusted?.topology?.site_count !== 2
) {
  console.error(`trusted Fleet observation not reached: ${JSON.stringify(fleet)}`);
  process.exit(2);
}

const enabled = await request("/api/manager/registry/runtime-smoke-ppu", {
  method: "PATCH",
  body: JSON.stringify({ lifecycle: "commissioned" }),
});
if (enabled.status !== 200 || enabled.payload?.entry?.lifecycle !== "commissioned") {
  console.error(`Validate & Enable failed: status=${enabled.status} body=${enabled.text}`);
  process.exit(2);
}

const removed = await request("/api/manager/registry/runtime-smoke-ppu", { method: "DELETE" });
if (removed.status !== 200 || removed.payload?.removed?.alias !== "runtime-smoke-ppu") {
  console.error(`registry remove failed: status=${removed.status} body=${removed.text}`);
  process.exit(2);
}

const finalRegistry = await request("/api/manager/registry");
if (
  finalRegistry.status !== 200
  || !Array.isArray(finalRegistry.payload?.ppus)
  || finalRegistry.payload.ppus.length !== 0
) {
  console.error(`registry did not end empty: status=${finalRegistry.status} body=${finalRegistry.text}`);
  process.exit(2);
}

console.log("Add -> trusted observation -> Validate & Enable -> Remove: PASS");
"""
    try:
        completed = subprocess.run(
            [
                node_executable,
                "--input-type=module",
                "-e",
                script,
                f"http://127.0.0.1:{port}",
                fake_ppu_endpoint,
                str(int(deadline_s * 1000)),
            ],
            cwd=cwd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=deadline_s + 10,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise SmokeError(f"Console/BFF registry lifecycle smoke timed out\n{exc.stdout or ''}") from exc
    if completed.returncode != 0:
        raise SmokeError(
            "Console/BFF -> Manager registry lifecycle smoke failed; "
            f"last observation: {completed.stdout.strip()}"
        )
    if process.poll() is not None:
        raise SmokeError(f"Console exited during registry lifecycle smoke with code {process.returncode}")


def _verify_registry_persistence(path: Path) -> None:
    if not path.is_file():
        raise SmokeError(f"Manager runtime registry state file was not created: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise SmokeError(f"Manager runtime registry state is not valid JSON: {path}") from exc
    if payload.get("schema_version") != 1 or payload.get("ppus") != []:
        raise SmokeError(f"Manager runtime registry final state is invalid: {payload!r}")


def _terminate(process: subprocess.Popen[bytes] | None) -> None:
    """Best-effort cleanup that must never hide the primary smoke result."""
    if process is None or process.poll() is not None:
        return
    try:
        process.terminate()
    except OSError:
        return
    try:
        process.wait(timeout=5)
        return
    except subprocess.TimeoutExpired:
        pass
    try:
        process.kill()
    except OSError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        return


def run_smoke(runtime_dir: Path, *, node_executable: str = "node") -> None:
    runtime_dir = runtime_dir.resolve()
    console_dir = runtime_dir / "console"
    console_entry = console_dir / "server.js"
    manager_entry = runtime_dir / "manager" / "manager.pyz"
    runtime_manifest = runtime_dir / "control-station-runtime.json"
    for required in (console_entry, manager_entry, runtime_manifest):
        if not required.is_file():
            raise SmokeError(f"runtime payload is missing required file: {required}")

    resolved_node = shutil.which(node_executable)
    if resolved_node is None:
        raise SmokeError(f"Node executable not found: {node_executable}")

    manager_port = _free_port()
    console_port = _free_port()
    fake_ppu_port = _free_port()
    fake_ppu_endpoint = f"http://127.0.0.1:{fake_ppu_port}"

    manager_process: subprocess.Popen[bytes] | None = None
    console_process: subprocess.Popen[bytes] | None = None
    fake_ppu_server = ThreadingHTTPServer(("127.0.0.1", fake_ppu_port), _FakePPUHandler)
    fake_ppu_thread = threading.Thread(target=fake_ppu_server.serve_forever, daemon=True)
    fake_ppu_thread.start()
    with tempfile.TemporaryDirectory(prefix="plasma-control-station-smoke-") as temporary:
        temp_root = Path(temporary)
        manager_config = temp_root / "manager.yaml"
        registry_state = temp_root / "manager-registry.json"
        manager_config.write_text(
            "\n".join(
                [
                    "manager:",
                    "  host: 127.0.0.1",
                    f"  port: {manager_port}",
                    "  request_timeout_s: 0.2",
                    "  poll_interval_s: 0.1",
                    f"  registry_state_path: {registry_state}",
                    "ppus: []",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        manager_log = (temp_root / "manager.log").open("wb")
        console_log = (temp_root / "console.log").open("wb")
        clean_env = dict(os.environ)
        for name in ("PYTHONPATH", "PYTHONHOME", "NODE_PATH", "NPM_CONFIG_PREFIX"):
            clean_env.pop(name, None)
        clean_env["NO_PROXY"] = "127.0.0.1,localhost"
        clean_env["no_proxy"] = "127.0.0.1,localhost"
        clean_env["PYTHONUNBUFFERED"] = "1"
        try:
            _probe_manager_bootstrap(
                manager_entry,
                manager_config,
                temp_root=temp_root,
                env=clean_env,
            )
            manager_process = subprocess.Popen(
                [sys.executable, str(manager_entry), "--config", str(manager_config)],
                cwd=temp_root,
                env=clean_env,
                stdout=manager_log,
                stderr=subprocess.STDOUT,
            )
            _wait_for_manager(manager_port, manager_process)
            print("Control Station packaged Manager readiness: PASS", flush=True)

            console_env = {
                **clean_env,
                "HOST": "127.0.0.1",
                "PORT": str(console_port),
                "PLASMA_CONTROL_STATION_MODE": "managed",
                "PLASMA_FLEET_UI_ENABLED": "1",
                "PLASMA_MANAGER_API_URL": f"http://127.0.0.1:{manager_port}",
                "PLASMA_MANAGER_PPU_ALIAS": "runtime-smoke-ppu",
            }
            console_process = subprocess.Popen(
                [resolved_node, str(console_entry)],
                cwd=console_dir,
                env=console_env,
                stdout=console_log,
                stderr=subprocess.STDOUT,
            )
            _verify_registry_lifecycle_via_console(
                console_port,
                console_process,
                fake_ppu_endpoint=fake_ppu_endpoint,
                node_executable=resolved_node,
                cwd=console_dir,
                env=console_env,
            )
            _verify_registry_persistence(registry_state)
            print("Control Station packaged Console/BFF -> Manager registry lifecycle: PASS", flush=True)
        except Exception as exc:
            manager_log.flush()
            console_log.flush()
            manager_text = (temp_root / "manager.log").read_text(encoding="utf-8", errors="replace")
            console_text = (temp_root / "console.log").read_text(encoding="utf-8", errors="replace")
            raise SmokeError(
                f"{exc}\n--- manager.log ---\n{manager_text}\n--- console.log ---\n{console_text}"
            ) from exc
        finally:
            _terminate(console_process)
            _terminate(manager_process)
            manager_log.close()
            console_log.close()
            fake_ppu_server.shutdown()
            fake_ppu_server.server_close()
            fake_ppu_thread.join(timeout=2)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smoke-test an extracted Plasma Control Station runtime")
    parser.add_argument("runtime_dir", type=Path)
    parser.add_argument("--node", default="node")
    args = parser.parse_args(argv)
    try:
        run_smoke(args.runtime_dir, node_executable=args.node)
    except (SmokeError, OSError) as exc:
        print(f"control-station-runtime-smoke: {exc}", file=sys.stderr)
        return 2
    print("Control Station clean runtime smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

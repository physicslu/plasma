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
import time
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class SmokeError(RuntimeError):
    pass


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
        with urlopen(request, timeout=timeout) as response:
            raw = response.read()
            status = int(response.status)
    except HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    except URLError as exc:
        raise SmokeError(f"request failed: {url}: {exc}") from exc
    try:
        decoded = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SmokeError(f"response is not JSON: {url}: status={status}") from exc
    if not isinstance(decoded, dict):
        raise SmokeError(f"response JSON root is not an object: {url}")
    return status, decoded


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


def _wait_for_console(port: int, process: subprocess.Popen[bytes], deadline_s: float = 30.0) -> None:
    deadline = time.monotonic() + deadline_s
    url = f"http://127.0.0.1:{port}/api/manager/diagnostics/loopback"
    payload = {"endpoint": "ps", "timeout_ms": 100, "payload": "runtime-smoke"}
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise SmokeError(f"Console exited before readiness with code {process.returncode}")
        try:
            status, response = _request_json(url, method="POST", payload=payload, timeout=2.0)
            error = response.get("error")
            if (
                status == 504
                and isinstance(error, dict)
                and error.get("code") == "ppu_transport_error"
            ):
                return
        except SmokeError:
            pass
        time.sleep(0.2)
    raise SmokeError("Console/BFF -> Manager runtime smoke timed out")


def _terminate(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


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

    manager_process: subprocess.Popen[bytes] | None = None
    console_process: subprocess.Popen[bytes] | None = None
    with tempfile.TemporaryDirectory(prefix="plasma-control-station-smoke-") as temporary:
        temp_root = Path(temporary)
        manager_config = temp_root / "manager.yaml"
        manager_config.write_text(
            "\n".join(
                [
                    "manager:",
                    "  host: 127.0.0.1",
                    f"  port: {manager_port}",
                    "  request_timeout_s: 0.2",
                    "  poll_interval_s: 60",
                    "ppus:",
                    "  - alias: runtime-smoke-ppu",
                    f"    endpoint: http://127.0.0.1:{fake_ppu_port}",
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
        try:
            manager_process = subprocess.Popen(
                [sys.executable, str(manager_entry), "--config", str(manager_config)],
                cwd=temp_root,
                env=clean_env,
                stdout=manager_log,
                stderr=subprocess.STDOUT,
            )
            _wait_for_manager(manager_port, manager_process)

            console_env = {
                **clean_env,
                "HOST": "127.0.0.1",
                "PORT": str(console_port),
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
            _wait_for_console(console_port, console_process)
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

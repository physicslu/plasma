#!/usr/bin/env python3
"""Run the packaged PPU PS-only runtime inside an ARMv7 Linux userspace.

This harness is intentionally hardware-closed. It proves that the immutable PPU
runtime can execute under an ARMv7 Python runtime, start Plasma Server and the
REST Gateway, become ready, and complete the real Gateway -> Server PS Loopback
path. It does not emulate Zynq hardware, systemd boot, PL, Site I/O, target power,
or real IC programming.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Sequence


MIN_PYTHON = (3, 11)
ARMV7_ARCHITECTURES = {"armv7l", "armv7"}


class ARMv7AcceptanceError(RuntimeError):
    pass


def _validate_architecture(machine: str) -> str:
    normalized = machine.strip().lower()
    if normalized not in ARMV7_ARCHITECTURES:
        raise ARMv7AcceptanceError(
            f"runtime is not executing as ARMv7: platform.machine()={machine!r}"
        )
    return normalized


def _validate_python(version_info: Sequence[int]) -> str:
    version = tuple(int(part) for part in version_info[:3])
    if version[:2] < MIN_PYTHON:
        raise ARMv7AcceptanceError(
            f"Python {version[0]}.{version[1]}.{version[2]} < required 3.11"
        )
    return f"{version[0]}.{version[1]}.{version[2]}"


def _load_runtime_manifest(runtime_dir: Path) -> dict[str, Any]:
    path = runtime_dir / "ppu-runtime.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ARMv7AcceptanceError(f"cannot read PPU runtime manifest: {exc}") from exc
    if payload.get("role") != "ppu":
        raise ARMv7AcceptanceError("runtime manifest role is not ppu")
    expected_boundary = {
        "loads_fpga": False,
        "accesses_pl": False,
        "changes_target_power": False,
        "programs_real_ic": False,
    }
    if payload.get("hardware_boundary") != expected_boundary:
        raise ARMv7AcceptanceError(
            f"PPU hardware boundary is not closed: {payload.get('hardware_boundary')!r}"
        )
    return payload


def _write_config(work_dir: Path, *, server_port: int) -> Path:
    config_dir = work_dir / "config"
    config_dir.mkdir(parents=True, exist_ok=True)
    output_root = work_dir / "output"
    log_root = work_dir / "logs"
    output_root.mkdir(parents=True, exist_ok=True)
    log_root.mkdir(parents=True, exist_ok=True)
    path = config_dir / "ppu-armv7.yaml"
    path.write_text(
        "\n".join(
            [
                "ppu:",
                "  id: ci-armv7-ppu",
                "  facility_id: ci",
                "  model: qemu-armv7",
                "  display_name: Plasma ARMv7 CI Runtime",
                "",
                "server:",
                "  host: 127.0.0.1",
                f"  port: {server_port}",
                "  max_supported_sites: 8",
                "  max_concurrent_jobs: 1",
                "  max_queue_depth_per_site: 16",
                f"  output_root: {output_root}",
                f"  log_root: {log_root}",
                "  max_metadata_bytes: 65536",
                "  max_map_bytes: 1048576",
                "  max_binary_bytes: 67108864",
                "",
                "sites: []",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _request_json(
    url: str,
    *,
    method: str = "GET",
    body: dict[str, Any] | None = None,
    timeout_s: float = 2.0,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout_s) as response:
            status = int(response.status)
            raw = response.read()
    except urllib.error.HTTPError as exc:
        status = int(exc.code)
        raw = exc.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ARMv7AcceptanceError(f"non-JSON response from {url}: HTTP {status}") from exc
    if not isinstance(payload, dict):
        raise ARMv7AcceptanceError(f"JSON response from {url} is not an object")
    return status, payload


def _tail(path: Path, *, max_chars: int = 8000) -> str:
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return "<log unavailable>"
    return text[-max_chars:]


def _ensure_running(process: subprocess.Popen[bytes], label: str, log_path: Path) -> None:
    code = process.poll()
    if code is not None:
        raise ARMv7AcceptanceError(
            f"{label} exited before acceptance completed with code {code}\n{_tail(log_path)}"
        )


def _wait_ready(
    base_url: str,
    *,
    deadline_s: float,
    server: subprocess.Popen[bytes],
    gateway: subprocess.Popen[bytes],
    server_log: Path,
    gateway_log: Path,
) -> dict[str, Any]:
    deadline = time.monotonic() + deadline_s
    last: str | None = None
    while time.monotonic() < deadline:
        _ensure_running(server, "Plasma Server", server_log)
        _ensure_running(gateway, "PPU Gateway", gateway_log)
        try:
            status, payload = _request_json(f"{base_url}/api/health/ready")
            if (
                status == 200
                and payload.get("ok") is True
                and payload.get("gateway") == "alive"
                and payload.get("execution") == "ready"
            ):
                return payload
            last = f"HTTP {status}: {payload!r}"
        except (ARMv7AcceptanceError, OSError) as exc:
            last = str(exc)
        time.sleep(0.2)
    raise ARMv7AcceptanceError(
        "Gateway readiness deadline exceeded"
        + (f": {last}" if last else "")
        + f"\n--- server.log ---\n{_tail(server_log)}"
        + f"\n--- gateway.log ---\n{_tail(gateway_log)}"
    )


def _validate_loopback_response(
    *,
    status: int,
    response: dict[str, Any],
    encoded: str,
    crc32: str,
) -> dict[str, Any]:
    if status != 200 or response.get("ok") is not True:
        raise ARMv7AcceptanceError(f"PS Loopback failed: HTTP {status}: {response!r}")
    loopback = response.get("loopback")
    if not isinstance(loopback, dict):
        raise ARMv7AcceptanceError("PS Loopback response is missing loopback evidence")
    if loopback.get("endpoint") != "ps" or loopback.get("source") != "ps":
        raise ARMv7AcceptanceError("PS Loopback response did not originate from PS")
    if loopback.get("tx_crc32") != crc32 or loopback.get("rx_crc32") != crc32:
        raise ARMv7AcceptanceError("PS Loopback CRC evidence does not match")
    if response.get("payload_base64") != encoded:
        raise ARMv7AcceptanceError("PS Loopback payload does not match")
    return loopback


def _run_loopback(base_url: str) -> dict[str, Any]:
    payload = b"\x00"
    encoded = base64.b64encode(payload).decode("ascii")
    crc32 = f"{zlib.crc32(payload) & 0xFFFFFFFF:08x}"
    status, response = _request_json(
        f"{base_url}/api/engineering/diagnostics/loopback",
        method="POST",
        body={
            "endpoint": "ps",
            "test_id": "armv7-runtime-acceptance",
            "sequence": 1,
            "pattern": "zero",
            "seed": "",
            "payload_length": len(payload),
            "payload_base64": encoded,
            "tx_crc32": crc32,
            "timeout_ms": 10_000,
        },
        timeout_s=15.0,
    )
    return _validate_loopback_response(
        status=status,
        response=response,
        encoded=encoded,
        crc32=crc32,
    )


def _terminate(process: subprocess.Popen[bytes] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_acceptance(
    *,
    runtime_dir: Path,
    work_dir: Path,
    server_port: int,
    gateway_port: int,
    deadline_s: float,
) -> dict[str, Any]:
    architecture = _validate_architecture(platform.machine())
    python_version = _validate_python(sys.version_info)
    runtime_dir = runtime_dir.resolve()
    work_dir = work_dir.resolve()
    app = runtime_dir / "ppu" / "ppu.pyz"
    if not app.is_file():
        raise ARMv7AcceptanceError(f"PPU zipapp is missing: {app}")
    manifest = _load_runtime_manifest(runtime_dir)
    catalog = runtime_dir / str(
        ((manifest.get("data") or {}).get("device_catalog_manifest"))
    )
    if not catalog.is_file():
        raise ARMv7AcceptanceError(f"production Device Catalog manifest is missing: {catalog}")

    work_dir.mkdir(parents=True, exist_ok=True)
    config_path = _write_config(work_dir, server_port=server_port)
    server_log = work_dir / "server.log"
    gateway_log = work_dir / "gateway.log"
    gateway_output = work_dir / "gateway-output"
    gateway_output.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PLASMA_DEVICE_CATALOG_MANIFEST"] = str(catalog)

    server: subprocess.Popen[bytes] | None = None
    gateway: subprocess.Popen[bytes] | None = None
    try:
        with server_log.open("wb") as server_stream, gateway_log.open("wb") as gateway_stream:
            server = subprocess.Popen(
                [sys.executable, str(app), "server", "--config", str(config_path)],
                cwd=work_dir,
                env=env,
                stdout=server_stream,
                stderr=subprocess.STDOUT,
            )
            gateway = subprocess.Popen(
                [
                    sys.executable,
                    str(app),
                    "gateway",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(gateway_port),
                    "--plasma-host",
                    "127.0.0.1",
                    "--plasma-port",
                    str(server_port),
                    "--output-root",
                    str(gateway_output),
                ],
                cwd=work_dir,
                env=env,
                stdout=gateway_stream,
                stderr=subprocess.STDOUT,
            )
            base_url = f"http://127.0.0.1:{gateway_port}"
            readiness = _wait_ready(
                base_url,
                deadline_s=deadline_s,
                server=server,
                gateway=gateway,
                server_log=server_log,
                gateway_log=gateway_log,
            )
            loopback = _run_loopback(base_url)
            _ensure_running(server, "Plasma Server", server_log)
            _ensure_running(gateway, "PPU Gateway", gateway_log)
    finally:
        _terminate(gateway)
        _terminate(server)

    return {
        "result": "PASS",
        "evidence_level": "armv7-userspace-emulation",
        "architecture": architecture,
        "python_version": python_version,
        "runtime_role": manifest.get("role"),
        "gateway_readiness": {
            "gateway": readiness.get("gateway"),
            "execution": readiness.get("execution"),
        },
        "ps_loopback": {
            "endpoint": loopback.get("endpoint"),
            "source": loopback.get("source"),
            "tx_crc32": loopback.get("tx_crc32"),
            "rx_crc32": loopback.get("rx_crc32"),
        },
        "not_claimed": [
            "PYNQ-Z2 hardware",
            "systemd boot/reboot",
            "PS-to-PL",
            "Site I/O",
            "target power",
            "real IC programming",
        ],
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plasma PPU ARMv7 runtime acceptance")
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--work-dir", required=True, type=Path)
    parser.add_argument("--server-port", type=int, default=9900)
    parser.add_argument("--gateway-port", type=int, default=18080)
    parser.add_argument("--deadline-s", type=float, default=30.0)
    args = parser.parse_args(argv)
    try:
        result = run_acceptance(
            runtime_dir=args.runtime_dir,
            work_dir=args.work_dir,
            server_port=args.server_port,
            gateway_port=args.gateway_port,
            deadline_s=args.deadline_s,
        )
    except (ARMv7AcceptanceError, OSError, subprocess.SubprocessError) as exc:
        print(f"ppu-armv7-runtime-acceptance: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

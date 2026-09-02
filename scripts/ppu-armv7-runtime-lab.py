#!/usr/bin/env python3
"""One-command SWPC/QEMU ARMv7 runtime laboratory for the packaged PPU.

Host mode builds and validates the PPU runtime, repairs ARM binfmt when needed,
and launches this same script inside an ARMv7 Python container. Container mode
runs a pure-stdlib ThreadingHTTPServer control, then starts Plasma Server/Gateway
and measures live/ready/loopback request paths. The lab is software-only and
does not claim Z2 hardware.
"""

from __future__ import annotations

import argparse
import base64
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
import platform
import shutil
import statistics
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zlib
from pathlib import Path
from typing import Any, Sequence

ARM_IMAGE = "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c"
BINFMT_IMAGE = "docker.io/tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0"
DEFAULT_REQUESTS = 1000
DEFAULT_CONTROL_CHECKPOINTS = (1000, 5000, 10000)
DEFAULT_RUNTIME_REL = Path(".work/ppu-runtime")
DEFAULT_REPORT_REL = Path(".work/reports/ppu-armv7-runtime-lab.json")
RESULT_MARKER = "PLASMA_ARMV7_LAB_RESULT="
CONTROL_PORT = 18081


class LabError(RuntimeError):
    pass


def _run(command: Sequence[str], *, cwd: Path | None = None, capture: bool = False) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), cwd=cwd, text=True, capture_output=capture, check=True)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _docker_preflight() -> None:
    if shutil.which("docker") is None:
        raise LabError("docker is not available on PATH")
    probe = [
        "docker", "run", "--rm", "--platform", "linux/arm/v7", ARM_IMAGE,
        "python3", "-c", "import platform; print(platform.machine())",
    ]
    try:
        result = _run(probe, capture=True)
    except subprocess.CalledProcessError:
        _run(["docker", "run", "--privileged", "--rm", BINFMT_IMAGE, "--install", "arm"])
        result = _run(probe, capture=True)
    if result.stdout.strip() not in {"armv7l", "armv7"}:
        raise LabError(f"ARMv7 preflight returned {result.stdout.strip()!r}")


def _build_runtime(repo: Path, runtime_dir: Path) -> None:
    python = repo / "software/python/.venv/bin/python"
    if not python.is_file():
        raise LabError(f"SWPC build venv is missing: {python}")
    if runtime_dir.exists():
        try:
            shutil.rmtree(runtime_dir)
        except PermissionError as exc:
            raise LabError(
                f"cannot replace {runtime_dir}; fix ownership first (expected host-owned, container-mounted read-only)"
            ) from exc
    runtime_dir.parent.mkdir(parents=True, exist_ok=True)
    _run([str(python), "scripts/ppu-runtime.py", "build", "--output-dir", str(runtime_dir)], cwd=repo)
    _run([str(python), "scripts/ppu-runtime.py", "validate", str(runtime_dir)], cwd=repo)
    app = runtime_dir / "ppu/ppu.pyz"
    if not app.is_file():
        raise LabError(f"runtime build did not produce {app}")


def _parse_result(stdout: str) -> dict[str, Any]:
    for line in reversed(stdout.splitlines()):
        if line.startswith(RESULT_MARKER):
            value = json.loads(line[len(RESULT_MARKER) :])
            if isinstance(value, dict):
                return value
    raise LabError("ARMv7 container did not emit a lab result marker")


def _parse_checkpoints(value: str) -> tuple[int, ...]:
    try:
        checkpoints = tuple(int(item.strip()) for item in value.split(",") if item.strip())
    except ValueError as exc:
        raise argparse.ArgumentTypeError("control checkpoints must be comma-separated positive integers") from exc
    if not checkpoints or any(item < 1 for item in checkpoints) or tuple(sorted(set(checkpoints))) != checkpoints:
        raise argparse.ArgumentTypeError("control checkpoints must be unique positive integers in ascending order")
    return checkpoints


def _host_mode(args: argparse.Namespace) -> int:
    repo = _repo_root()
    runtime_dir = (repo / args.runtime_dir).resolve() if not args.runtime_dir.is_absolute() else args.runtime_dir.resolve()
    report_path = (repo / args.report).resolve() if not args.report.is_absolute() else args.report.resolve()
    _docker_preflight()
    _build_runtime(repo, runtime_dir)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    checkpoints = ",".join(str(item) for item in args.control_checkpoints)
    command = [
        "docker", "run", "--rm", "--platform", "linux/arm/v7",
        "-v", f"{runtime_dir}:/runtime:ro",
        "-v", f"{Path(__file__).resolve()}:/lab.py:ro",
        ARM_IMAGE,
        "python3", "/lab.py", "--inside", "--runtime-dir", "/runtime", "--requests", str(args.requests),
        "--control-checkpoints", checkpoints,
    ]
    print("Plasma ARMv7 Runtime Lab")
    print(f"runtime: {runtime_dir}")
    print(f"report : {report_path}")
    completed = _run(command, capture=True)
    print(completed.stdout, end="")
    result = _parse_result(completed.stdout)
    report_path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"host-owned report written: {report_path}")
    return 0


def _request_json(url: str, *, method: str = "GET", body: dict[str, Any] | None = None, timeout_s: float = 15.0) -> dict[str, Any]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout_s) as response:
            payload = json.load(response)
    except (urllib.error.URLError, json.JSONDecodeError) as exc:
        raise LabError(f"request failed for {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise LabError(f"response is not an object: {url}")
    return payload


def _proc_metrics(pid: int) -> dict[str, int]:
    status: dict[str, str] = {}
    for line in Path(f"/proc/{pid}/status").read_text().splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            status[key] = value.strip()
    rss = int(status.get("VmRSS", "0 kB").split()[0])
    return {
        "rss_kib": rss,
        "threads": int(status.get("Threads", "0")),
        "fds": len(list(Path(f"/proc/{pid}/fd").iterdir())),
    }


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = min(len(ordered) - 1, max(0, round((len(ordered) - 1) * percentile)))
    return ordered[index]


def _loopback_body(sequence: int) -> tuple[dict[str, Any], str]:
    payload = bytes(range(256)) * 4
    encoded = base64.b64encode(payload).decode("ascii")
    crc = f"{zlib.crc32(payload) & 0xFFFFFFFF:08x}"
    return ({
        "endpoint": "ps", "test_id": f"armv7-lab-{sequence:06d}", "sequence": sequence,
        "pattern": "incrementing", "seed": "", "payload_length": len(payload),
        "payload_base64": encoded, "tx_crc32": crc, "timeout_ms": 10000,
    }, crc)


def _exercise(name: str, count: int, request_fn, gateway_pid: int, server_pid: int) -> dict[str, Any]:
    before_gateway = _proc_metrics(gateway_pid)
    before_server = _proc_metrics(server_pid)
    latencies: list[float] = []
    for index in range(1, count + 1):
        started = time.perf_counter()
        request_fn(index)
        latencies.append((time.perf_counter() - started) * 1000)
        if index % max(1, count // 10) == 0:
            print(f"{name}: {index}/{count} PASS")
    after_gateway = _proc_metrics(gateway_pid)
    after_server = _proc_metrics(server_pid)
    return {
        "requests": count,
        "latency_ms": {
            "min": round(min(latencies), 3), "avg": round(statistics.fmean(latencies), 3),
            "p95": round(_percentile(latencies, 0.95), 3), "p99": round(_percentile(latencies, 0.99), 3),
            "max": round(max(latencies), 3),
        },
        "gateway_before": before_gateway,
        "gateway_after": after_gateway,
        "gateway_delta": {key: after_gateway[key] - before_gateway[key] for key in after_gateway},
        "server_before": before_server,
        "server_after": after_server,
        "server_delta": {key: after_server[key] - before_server[key] for key in after_server},
    }


class _ControlHandler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_GET(self) -> None:
        payload = b'{"ok":true}'
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args: Any) -> None:
        return


def _control_server_mode() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", CONTROL_PORT), _ControlHandler)
    server.daemon_threads = True
    server.serve_forever()
    return 0


def _wait_control(process: subprocess.Popen[Any], timeout_s: float = 15.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise LabError("ThreadingHTTPServer control exited before readiness")
        try:
            if _request_json(f"http://127.0.0.1:{CONTROL_PORT}/").get("ok") is True:
                return
        except LabError:
            pass
        time.sleep(0.1)
    raise LabError("ThreadingHTTPServer control readiness deadline exceeded")


def _run_control_experiment(checkpoints: tuple[int, ...]) -> dict[str, Any]:
    process: subprocess.Popen[Any] | None = None
    try:
        process = subprocess.Popen([sys.executable, "/lab.py", "--control-server"])
        _wait_control(process)
        baseline = _proc_metrics(process.pid)
        samples: list[dict[str, Any]] = []
        previous = 0
        for checkpoint in checkpoints:
            for index in range(previous + 1, checkpoint + 1):
                data = _request_json(f"http://127.0.0.1:{CONTROL_PORT}/")
                if data.get("ok") is not True:
                    raise LabError(f"invalid control response at request {index}")
            metrics = _proc_metrics(process.pid)
            samples.append({
                "requests": checkpoint,
                "metrics": metrics,
                "delta_from_baseline": {key: metrics[key] - baseline[key] for key in metrics},
            })
            print(f"stdlib-threading-control: {checkpoint}/{checkpoints[-1]} checkpoint")
            previous = checkpoint
        final_delta = samples[-1]["delta_from_baseline"]
        return {
            "implementation": "python-stdlib-ThreadingHTTPServer",
            "plasma_imported": False,
            "baseline": baseline,
            "checkpoints": samples,
            "rss_kib_per_request_final": round(final_delta["rss_kib"] / checkpoints[-1], 6),
        }
    finally:
        _terminate(process)


def _write_config(work: Path) -> Path:
    work.mkdir(parents=True, exist_ok=True)
    path = work / "ppu.yaml"
    path.write_text(
        "ppu:\n  id: swpc-armv7-runtime-lab\n  facility_id: swpc-qemu\n  model: qemu-armv7\n  display_name: Plasma ARMv7 Runtime Lab\n\n"
        "server:\n  host: 127.0.0.1\n  port: 9900\n  max_supported_sites: 8\n  max_concurrent_jobs: 1\n"
        "  max_queue_depth_per_site: 16\n  output_root: /work/output\n  log_root: /work/logs\n"
        "  max_metadata_bytes: 65536\n  max_map_bytes: 1048576\n  max_binary_bytes: 67108864\n\nsites: []\n"
    )
    return path


def _terminate(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _wait_ready(base_url: str, server: subprocess.Popen[Any], gateway: subprocess.Popen[Any], timeout_s: float = 30.0) -> float:
    started = time.perf_counter()
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if server.poll() is not None or gateway.poll() is not None:
            raise LabError("Server or Gateway exited before readiness")
        try:
            data = _request_json(f"{base_url}/api/health/ready", timeout_s=2)
            if data.get("ok") is True and data.get("gateway") == "alive" and data.get("execution") == "ready":
                return (time.perf_counter() - started) * 1000
        except LabError:
            pass
        time.sleep(0.2)
    raise LabError("Gateway readiness deadline exceeded")


def _inside_mode(args: argparse.Namespace) -> int:
    if platform.machine().lower() not in {"armv7", "armv7l"}:
        raise LabError(f"inside mode requires ARMv7, got {platform.machine()}")
    if sys.version_info < (3, 11):
        raise LabError(f"inside mode requires Python >=3.11, got {platform.python_version()}")
    runtime = args.runtime_dir.resolve()
    app = runtime / "ppu/ppu.pyz"
    if not app.is_file():
        raise LabError(f"PPU zipapp is missing: {app}")
    manifest = json.loads((runtime / "ppu-runtime.json").read_text())
    catalog = runtime / str((manifest.get("data") or {}).get("device_catalog_manifest"))
    control = _run_control_experiment(args.control_checkpoints)
    work = Path("/work")
    config = _write_config(work)
    for directory in (work / "output", work / "logs", work / "gateway-output"):
        directory.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PLASMA_DEVICE_CATALOG_MANIFEST"] = str(catalog)
    server = gateway = None
    try:
        server = subprocess.Popen([sys.executable, str(app), "server", "--config", str(config)], cwd=work, env=env)
        gateway = subprocess.Popen([
            sys.executable, str(app), "gateway", "--host", "127.0.0.1", "--port", "18080",
            "--plasma-host", "127.0.0.1", "--plasma-port", "9900", "--output-root", str(work / "gateway-output"),
        ], cwd=work, env=env)
        base = "http://127.0.0.1:18080"
        readiness_ms = _wait_ready(base, server, gateway)
        live = _exercise("health/live", args.requests, lambda _: _request_json(f"{base}/api/health/live"), gateway.pid, server.pid)
        ready = _exercise("health/ready", args.requests, lambda _: _request_json(f"{base}/api/health/ready"), gateway.pid, server.pid)

        def loop(index: int) -> None:
            body, crc = _loopback_body(index)
            response = _request_json(f"{base}/api/engineering/diagnostics/loopback", method="POST", body=body)
            evidence = response.get("loopback") or {}
            if response.get("ok") is not True or evidence.get("source") != "ps" or evidence.get("tx_crc32") != crc or evidence.get("rx_crc32") != crc:
                raise LabError(f"invalid PS Loopback evidence at sequence {index}")

        loopback = _exercise("ps-loopback", args.requests, loop, gateway.pid, server.pid)
        time.sleep(30)
        gateway_live_per_request = live["gateway_delta"]["rss_kib"] / args.requests
        control_per_request = control["rss_kib_per_request_final"]
        ratio = gateway_live_per_request / control_per_request if control_per_request > 0 else None
        result = {
            "functional_result": "PASS",
            "resource_result": "INVESTIGATE",
            "overall_result": "INVESTIGATE",
            "evidence_level": "swpc-qemu-armv7-userspace",
            "architecture": platform.machine(),
            "python_version": platform.python_version(),
            "runtime_bytes": sum(path.stat().st_size for path in runtime.rglob("*") if path.is_file()),
            "readiness_ms": round(readiness_ms, 3),
            "stdlib_threading_control": control,
            "resource_comparison": {
                "gateway_health_live_rss_kib_per_request": round(gateway_live_per_request, 6),
                "control_rss_kib_per_request": control_per_request,
                "gateway_to_control_ratio": round(ratio, 6) if ratio is not None else None,
                "interpretation": "compare request-normalized RSS growth; matching slopes support a QEMU/ThreadingHTTPServer environment effect",
            },
            "paths": {"health_live": live, "health_ready": ready, "ps_loopback": loopback},
            "stable_after_30s": {"gateway": _proc_metrics(gateway.pid), "server": _proc_metrics(server.pid)},
            "not_claimed": ["PYNQ-Z2 hardware", "systemd boot/reboot", "PS-to-PL", "Site I/O", "target power", "real IC programming", "native Z2 memory stability"],
        }
        print(RESULT_MARKER + json.dumps(result, sort_keys=True), flush=True)
        return 0
    finally:
        _terminate(gateway)
        _terminate(server)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plasma PPU ARMv7 runtime lab")
    parser.add_argument("--inside", action="store_true")
    parser.add_argument("--control-server", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--runtime-dir", type=Path, default=DEFAULT_RUNTIME_REL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_REL)
    parser.add_argument("--requests", type=int, default=DEFAULT_REQUESTS)
    parser.add_argument(
        "--control-checkpoints",
        type=_parse_checkpoints,
        default=DEFAULT_CONTROL_CHECKPOINTS,
        help="cumulative pure-stdlib ThreadingHTTPServer request checkpoints (default: 1000,5000,10000)",
    )
    args = parser.parse_args(argv)
    if args.requests < 1:
        parser.error("--requests must be >= 1")
    try:
        if args.control_server:
            return _control_server_mode()
        return _inside_mode(args) if args.inside else _host_mode(args)
    except (LabError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"ppu-armv7-runtime-lab: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Persistent ARMv7 userspace target for the SWPC ``z2like-demo`` scenario.

The process runs inside a Docker/QEMU ``linux/arm/v7`` container. It owns the
simulation-only process lifecycle for:

* independent authenticated PPU Bootstrap on :18081;
* the currently activated packaged Plasma Server on :9900; and
* the currently activated packaged Plasma Gateway on :18080.

It deliberately does not emulate systemd, PYNQ, PL, electrical Site I/O, target
power or a real IC. SWPC is the simulation environment; this ARMv7 process is
the single canonical ``z2like-demo`` PPU backend.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import secrets
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Sequence

TARGET_MARKER = "PLASMA_Z2LIKE_DEMO_QEMU_TARGET"
DEFAULT_PRODUCT_ROOT = Path("/opt/plasma")
DEFAULT_CONFIG_ROOT = Path("/etc/plasma")
DEFAULT_BOOTSTRAP_STATE = Path("/var/lib/plasma-bootstrap")
DEFAULT_RUNTIME_STATE = Path("/var/lib/plasma")
DEFAULT_LOG_ROOT = Path("/var/log/plasma")
BOOTSTRAP_PORT = 18081
GATEWAY_PORT = 18080
SERVER_PORT = 9900


class TargetError(RuntimeError):
    pass


def _require_target() -> None:
    if os.environ.get(TARGET_MARKER) != "1":
        raise TargetError("z2like-demo target requires explicit simulation marker")
    if platform.system() != "Linux":
        raise TargetError("z2like-demo target requires Linux")
    machine = platform.machine().lower()
    if machine not in {"armv7", "armv7l"}:
        raise TargetError(f"z2like-demo target requires ARMv7 execution, got {machine}")


def _request_json(url: str, timeout_s: float = 2.0) -> dict[str, Any]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout_s) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (OSError, urllib.error.URLError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TargetError(f"request failed for {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise TargetError(f"response is not a JSON object: {url}")
    return payload


def _wait_url(url: str, predicate, timeout_s: float, *processes: subprocess.Popen[Any]) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last = "no response"
    while time.monotonic() < deadline:
        for process in processes:
            if process.poll() is not None:
                raise TargetError(f"process exited before readiness: pid={process.pid} rc={process.returncode}")
        try:
            payload = _request_json(url)
            if predicate(payload):
                return payload
            last = repr(payload)
        except TargetError as exc:
            last = str(exc)
        time.sleep(0.1)
    raise TargetError(f"readiness deadline exceeded for {url}: {last}")


def _terminate(process: subprocess.Popen[Any] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def _ensure_machine_id(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        value = path.read_text(encoding="utf-8").strip().lower()
        if len(value) < 16 or any(ch not in "0123456789abcdef-" for ch in value):
            raise TargetError(f"persistent simulation machine-id is malformed: {path}")
        return
    temporary = path.with_name(path.name + ".new")
    temporary.write_text(secrets.token_hex(16) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    os.replace(temporary, path)


def _ensure_token(service_script: Path, state_root: Path, machine_id: Path) -> None:
    token_file = state_root / "control-token"
    if token_file.exists():
        if token_file.stat().st_mode & 0o077:
            raise TargetError("persistent Bootstrap token permissions are too broad")
        return
    completed = subprocess.run(
        [
            sys.executable,
            str(service_script),
            "--state-root",
            str(state_root),
            "--machine-id",
            str(machine_id),
            "provision-token",
        ],
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
        timeout=10,
    )
    if completed.returncode != 0:
        raise TargetError(f"cannot provision Bootstrap token: {completed.stderr.strip()}")


def _release_identity(current: Path) -> str | None:
    if not current.exists() and not current.is_symlink():
        return None
    if not current.is_symlink():
        raise TargetError(f"managed current path is not a symlink: {current}")
    try:
        resolved = current.resolve(strict=True)
    except OSError as exc:
        raise TargetError(f"cannot resolve active release: {exc}") from exc
    manifest_path = resolved / "release.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TargetError(f"active release manifest is unreadable: {exc}") from exc
    if not isinstance(manifest, dict) or manifest.get("role") != "ppu" or manifest.get("target") != "linux-armv7l":
        raise TargetError("active release is not a canonical linux-armv7l PPU release")
    version = manifest.get("product_version")
    sha = manifest.get("git_sha")
    if not isinstance(version, str) or not isinstance(sha, str) or len(sha) != 40:
        raise TargetError("active release identity is invalid")
    expected = f"{version}-{sha[:12].lower()}"
    if resolved.name != expected:
        raise TargetError("active release directory does not match release identity")
    return expected


def _runtime_environment(current: Path) -> dict[str, str]:
    manifest_path = current / "runtime" / "ppu-runtime.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise TargetError(f"runtime manifest is unreadable: {exc}") from exc
    data = manifest.get("data") if isinstance(manifest, dict) else None
    catalog_rel = data.get("device_catalog_manifest") if isinstance(data, dict) else None
    if not isinstance(catalog_rel, str) or not catalog_rel or catalog_rel.startswith("/") or ".." in Path(catalog_rel).parts:
        raise TargetError("runtime Device Catalog path is invalid")
    catalog = current / "runtime" / catalog_rel
    if not catalog.is_file():
        raise TargetError(f"runtime Device Catalog is missing: {catalog}")
    env = dict(os.environ)
    env["PYTHONUNBUFFERED"] = "1"
    env["PLASMA_DEVICE_CATALOG_MANIFEST"] = str(catalog)
    return env


def _start_runtime(
    *,
    product_root: Path,
    config_root: Path,
    state_root: Path,
    log_root: Path,
    gateway_host: str,
) -> tuple[str, subprocess.Popen[Any], subprocess.Popen[Any]]:
    current_link = product_root / "current"
    release_id = _release_identity(current_link)
    if release_id is None:
        raise TargetError("cannot start runtime while no release is active")
    current = current_link.resolve(strict=True)
    app = current / "runtime" / "ppu" / "ppu.pyz"
    config = config_root / "ppu.yaml"
    if not app.is_file() or not config.is_file():
        raise TargetError("active release/configuration is incomplete")
    for directory in (state_root / "output", state_root / "gateway-output", log_root):
        directory.mkdir(parents=True, exist_ok=True)
    env = _runtime_environment(current)
    server = subprocess.Popen(
        [sys.executable, str(app), "server", "--config", str(config)],
        cwd=state_root,
        env=env,
    )
    gateway = subprocess.Popen(
        [
            sys.executable,
            str(app),
            "gateway",
            "--ppu-config",
            str(config),
            "--host",
            gateway_host,
            "--port",
            str(GATEWAY_PORT),
            "--plasma-host",
            "127.0.0.1",
            "--plasma-port",
            str(SERVER_PORT),
            "--output-root",
            str(state_root / "gateway-output"),
        ],
        cwd=state_root,
        env=env,
    )
    try:
        _wait_url(
            f"http://127.0.0.1:{GATEWAY_PORT}/api/health/ready",
            lambda payload: payload.get("ok") is True
            and payload.get("gateway") == "alive"
            and payload.get("execution") == "ready",
            30.0,
            server,
            gateway,
        )
    except Exception:
        _terminate(gateway)
        _terminate(server)
        raise
    return release_id, server, gateway


def _run(args: argparse.Namespace) -> int:
    _require_target()
    scripts = args.scripts.resolve()
    product_root = args.product_root.resolve()
    config_root = args.config_root.resolve()
    bootstrap_state = args.bootstrap_state_root.resolve()
    runtime_state = args.runtime_state_root.resolve()
    log_root = args.log_root.resolve()
    machine_id = bootstrap_state / "machine-id"
    service_script = scripts / "ppu-bootstrap-service.py"
    bootstrap_script = scripts / "ppu-bootstrap.py"
    kit_tool = scripts / "z2like-demo-qemu-kit.py"
    for path in (service_script, bootstrap_script, kit_tool):
        if not path.is_file():
            raise TargetError(f"simulation dependency is missing: {path}")
    for directory in (product_root, config_root, bootstrap_state, runtime_state, log_root):
        directory.mkdir(parents=True, exist_ok=True)
    _ensure_machine_id(machine_id)
    _ensure_token(service_script, bootstrap_state, machine_id)

    bootstrap = subprocess.Popen(
        [
            sys.executable,
            str(service_script),
            "--product-root",
            str(product_root),
            "--state-root",
            str(bootstrap_state),
            "--machine-id",
            str(machine_id),
            "--bootstrap-script",
            str(bootstrap_script),
            "--kit-tool",
            str(kit_tool),
            "serve",
            "--host",
            args.bind_host,
            "--port",
            str(BOOTSTRAP_PORT),
        ],
        env={**os.environ, TARGET_MARKER: "1"},
    )
    _wait_url(
        f"http://127.0.0.1:{BOOTSTRAP_PORT}/v1/health",
        lambda payload: payload.get("ok") is True and payload.get("service") == "plasma-ppu-bootstrap",
        15.0,
        bootstrap,
    )
    print(
        "z2like-demo-qemu-target: Bootstrap ready; "
        "evidence boundary=SWPC/QEMU ARMv7 userspace only",
        flush=True,
    )

    stopping = False

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal stopping
        print(f"z2like-demo-qemu-target: received signal {signum}; stopping", flush=True)
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    active_release: str | None = None
    failed_release: str | None = None
    server: subprocess.Popen[Any] | None = None
    gateway: subprocess.Popen[Any] | None = None
    try:
        while not stopping:
            if bootstrap.poll() is not None:
                raise TargetError(f"Bootstrap exited unexpectedly: rc={bootstrap.returncode}")
            desired_release = _release_identity(product_root / "current")
            if desired_release != failed_release:
                failed_release = None
            runtime_dead = (
                (server is not None and server.poll() is not None)
                or (gateway is not None and gateway.poll() is not None)
            )
            needs_transition = desired_release != active_release or runtime_dead
            if needs_transition:
                _terminate(gateway)
                _terminate(server)
                server = gateway = None
                active_release = None
                if desired_release is not None and desired_release != failed_release:
                    try:
                        release_id, server, gateway = _start_runtime(
                            product_root=product_root,
                            config_root=config_root,
                            state_root=runtime_state,
                            log_root=log_root,
                            gateway_host=args.bind_host,
                        )
                    except TargetError as exc:
                        # Activation failure must not kill Bootstrap. The deployment
                        # coordinator needs Bootstrap to remain reachable while its
                        # health deadline expires and the installer restores the
                        # previous release. Do not retry the same failed symlink;
                        # wait for the rollback/current-link transition.
                        failed_release = desired_release
                        print(
                            f"z2like-demo-qemu-target: Runtime activation failed for {desired_release}: {exc}",
                            file=sys.stderr,
                            flush=True,
                        )
                    else:
                        active_release = release_id
                        print(f"z2like-demo-qemu-target: Runtime active {release_id}", flush=True)
            time.sleep(0.1)
    finally:
        _terminate(gateway)
        _terminate(server)
        _terminate(bootstrap)
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Persistent SWPC/QEMU ARMv7 simulated Z2 target")
    parser.add_argument("--scripts", type=Path, default=Path("/sim"))
    parser.add_argument("--product-root", type=Path, default=DEFAULT_PRODUCT_ROOT)
    parser.add_argument("--config-root", type=Path, default=DEFAULT_CONFIG_ROOT)
    parser.add_argument("--bootstrap-state-root", type=Path, default=DEFAULT_BOOTSTRAP_STATE)
    parser.add_argument("--runtime-state-root", type=Path, default=DEFAULT_RUNTIME_STATE)
    parser.add_argument("--log-root", type=Path, default=DEFAULT_LOG_ROOT)
    parser.add_argument("--bind-host", default="0.0.0.0")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        return _run(args)
    except (OSError, subprocess.SubprocessError, TargetError) as exc:
        print(f"z2like-demo-qemu-target: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

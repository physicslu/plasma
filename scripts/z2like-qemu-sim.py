#!/usr/bin/env python3
"""Persistent SWPC QEMU/ARMv7 simulated Z2 backend for z2like-demo.

This is a software simulation appliance, not PYNQ-Z2 HIL.  SWPC is the only
simulation environment; the ARMv7 container is the canonical z2like-demo PPU
backend.  The container exposes the same private profile ports as a real z2-ps
node (Gateway :18080, Bootstrap :18081) on a dedicated Docker bridge address,
so the local Manager can exercise Browser -> BFF -> Manager -> Bootstrap without
reusing the SWPC x86_64 surrogate or widening its restricted :18081 listener.

The simulation deliberately does not emulate systemd.  Bootstrap kit admission,
release verification, immutable release selection, ARMv7 PPU execution and
activation rollback are exercised, while real Z2 systemd/reboot semantics remain
unqualified.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from types import ModuleType
from typing import Any, Mapping, Sequence

ARM_IMAGE = "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c"
BINFMT_IMAGE = "docker.io/tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0"
CONTAINER_NAME = "plasma-z2like-qemu"
NETWORK_NAME = "plasma-z2like-sim"
NETWORK_SUBNET = "172.29.33.0/24"
APPLIANCE_IP = "172.29.33.21"
STATE_VOLUME = "plasma-z2like-qemu-state"
GATEWAY_PORT = 18080
BOOTSTRAP_PORT = 18081
DEFAULT_EVIDENCE_REL = Path(".work/z2like-qemu-sim/install.json")


class SimError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(
    command: Sequence[str],
    *,
    capture: bool = False,
    check: bool = True,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(list(command), text=True, capture_output=capture, check=check)


def _docker_preflight() -> None:
    if shutil.which("docker") is None:
        raise SimError("docker is not available on PATH")
    probe = [
        "docker", "run", "--rm", "--platform", "linux/arm/v7", ARM_IMAGE,
        "python3", "-c", "import platform; print(platform.machine())",
    ]
    result = _run(probe, capture=True, check=False)
    if result.returncode != 0:
        repair = _run(
            ["docker", "run", "--privileged", "--rm", BINFMT_IMAGE, "--install", "arm"],
            capture=True,
            check=False,
        )
        if repair.returncode != 0:
            raise SimError(f"cannot install ARM binfmt: {repair.stdout.strip()}")
        result = _run(probe, capture=True, check=False)
    if result.returncode != 0 or result.stdout.strip() not in {"armv7", "armv7l"}:
        raise SimError(f"ARMv7 Docker preflight failed: {result.stdout.strip()}")


def _docker_json(*args: str) -> Any:
    completed = _run(["docker", *args], capture=True, check=False)
    if completed.returncode != 0:
        return None
    try:
        return json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise SimError(f"docker returned invalid JSON for {' '.join(args)}") from exc


def _ensure_network() -> None:
    existing = _docker_json("network", "inspect", NETWORK_NAME)
    if existing is None:
        _run(["docker", "network", "create", "--driver", "bridge", "--subnet", NETWORK_SUBNET, NETWORK_NAME])
        return
    if not isinstance(existing, list) or len(existing) != 1:
        raise SimError(f"unexpected Docker network inspection for {NETWORK_NAME}")
    configs = ((existing[0].get("IPAM") or {}).get("Config") or [])
    subnets = {str(item.get("Subnet")) for item in configs if isinstance(item, dict)}
    if NETWORK_SUBNET not in subnets:
        raise SimError(f"existing Docker network {NETWORK_NAME} does not own {NETWORK_SUBNET}")


def _container_inspect() -> dict[str, Any] | None:
    payload = _docker_json("inspect", CONTAINER_NAME)
    if payload is None:
        return None
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise SimError("unexpected Docker container inspection result")
    return payload[0]


def _http_json(url: str, timeout_s: float = 3.0) -> dict[str, Any]:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(url, timeout=timeout_s) as response:
            payload = json.load(response)
    except (OSError, urllib.error.URLError, json.JSONDecodeError) as exc:
        raise SimError(f"request failed for {url}: {exc}") from exc
    if not isinstance(payload, dict):
        raise SimError(f"response is not an object: {url}")
    return payload


def _wait_bootstrap(timeout_s: float = 45.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last = "no response"
    while time.monotonic() < deadline:
        try:
            payload = _http_json(f"http://{APPLIANCE_IP}:{BOOTSTRAP_PORT}/v1/health")
            if payload.get("ok") is True:
                return payload
            last = repr(payload)
        except SimError as exc:
            last = str(exc)
        time.sleep(0.25)
    raise SimError(f"QEMU Bootstrap readiness deadline exceeded: {last}")


def _host_up() -> int:
    _docker_preflight()
    _ensure_network()
    repo = _repo_root()
    scripts = repo / "scripts"
    current = _container_inspect()
    if current is not None:
        image = str((current.get("Config") or {}).get("Image", ""))
        networks = (current.get("NetworkSettings") or {}).get("Networks") or {}
        address = str((networks.get(NETWORK_NAME) or {}).get("IPAddress", ""))
        if image != ARM_IMAGE or address != APPLIANCE_IP:
            raise SimError("existing plasma-z2like-qemu container does not match the canonical simulation contract")
        if bool((current.get("State") or {}).get("Running")):
            _wait_bootstrap()
            _write_host_evidence(DEFAULT_EVIDENCE_REL)
            print(f"already running: http://{APPLIANCE_IP}:{BOOTSTRAP_PORT}")
            return 0
        _run(["docker", "start", CONTAINER_NAME])
    else:
        _run(
            [
                "docker", "run", "-d",
                "--name", CONTAINER_NAME,
                "--platform", "linux/arm/v7",
                "--restart", "unless-stopped",
                "--network", NETWORK_NAME,
                "--ip", APPLIANCE_IP,
                "--mount", f"type=volume,src={STATE_VOLUME},dst=/state",
                "--mount", f"type=bind,src={scripts},dst=/plasma-scripts,readonly",
                "--mount", f"type=bind,src={Path(__file__).resolve()},dst=/z2like-qemu-sim.py,readonly",
                ARM_IMAGE,
                "python3", "/z2like-qemu-sim.py", "inside",
            ]
        )
    _wait_bootstrap()
    _write_host_evidence(DEFAULT_EVIDENCE_REL)
    print("SWPC QEMU ARMv7 simulated Z2 is running")
    print(f"Gateway:   http://{APPLIANCE_IP}:{GATEWAY_PORT}")
    print(f"Bootstrap: http://{APPLIANCE_IP}:{BOOTSTRAP_PORT}")
    print("qualification: simulation only; real PYNQ-Z2 HIL NOT QUALIFIED")
    return 0


def _host_down() -> int:
    current = _container_inspect()
    if current is None:
        print("not running")
        return 0
    _run(["docker", "rm", "-f", CONTAINER_NAME])
    print(f"removed container {CONTAINER_NAME}; persistent state volume {STATE_VOLUME} was retained")
    return 0


def _host_token(rotate: bool) -> int:
    current = _container_inspect()
    if current is None or not bool((current.get("State") or {}).get("Running")):
        raise SimError("QEMU simulated Z2 is not running")
    command = ["docker", "exec", CONTAINER_NAME, "python3", "/z2like-qemu-sim.py", "inside-token"]
    if rotate:
        command.append("--rotate")
    completed = _run(command, capture=True)
    token = completed.stdout.strip()
    if not token:
        raise SimError("Bootstrap token command returned no token")
    print(token)
    return 0


def _write_host_evidence(relative: Path) -> dict[str, Any]:
    repo = _repo_root()
    path = relative if relative.is_absolute() else repo / relative
    status = _http_json(f"http://{APPLIANCE_IP}:{BOOTSTRAP_PORT}/v1/status")
    runtime = status.get("runtime") if isinstance(status.get("runtime"), dict) else {}
    payload = {
        "schema_version": 1,
        "role": "ppu-simulation",
        "simulation_environment": "SWPC",
        "backend": "qemu-armv7",
        "platform": "linux-armv7l",
        "z2_equivalent": False,
        "hardware_boundary": "closed",
        "container": CONTAINER_NAME,
        "network": NETWORK_NAME,
        "gateway_bind": f"{APPLIANCE_IP}:{GATEWAY_PORT}",
        "bootstrap_bind": f"{APPLIANCE_IP}:{BOOTSTRAP_PORT}",
        "runtime_state": runtime.get("state"),
        "release_id": runtime.get("release_id"),
        "git_sha": runtime.get("git_sha"),
        "device_id": ((status.get("identity") or {}).get("device_id") if isinstance(status.get("identity"), dict) else None),
        "fpga_update": False,
        "real_z2_hil": "not_qualified",
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def _host_status(write_evidence: bool) -> int:
    current = _container_inspect()
    running = current is not None and bool((current.get("State") or {}).get("Running"))
    print(f"environment: SWPC")
    print(f"backend:     QEMU ARMv7 simulated Z2")
    print(f"container:   {CONTAINER_NAME} ({'running' if running else 'stopped'})")
    print(f"Gateway:     http://{APPLIANCE_IP}:{GATEWAY_PORT}")
    print(f"Bootstrap:   http://{APPLIANCE_IP}:{BOOTSTRAP_PORT}")
    if not running:
        return 1
    bootstrap = _http_json(f"http://{APPLIANCE_IP}:{BOOTSTRAP_PORT}/v1/status")
    print(json.dumps(bootstrap, indent=2, sort_keys=True))
    try:
        ready = _http_json(f"http://{APPLIANCE_IP}:{GATEWAY_PORT}/api/health/ready")
        print("Gateway readiness:")
        print(json.dumps(ready, indent=2, sort_keys=True))
    except SimError:
        print("Gateway readiness: runtime absent/unavailable")
    if write_evidence:
        payload = _write_host_evidence(DEFAULT_EVIDENCE_REL)
        print(f"evidence: {_repo_root() / DEFAULT_EVIDENCE_REL} ({payload['runtime_state']})")
    return 0


def _load_script(path: Path, module_name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise SimError(f"cannot load simulation dependency: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SimulatedAppliance:
    def __init__(self, scripts: Path) -> None:
        self.scripts = scripts
        self.product_root = Path("/state/product")
        self.bootstrap_state = Path("/state/bootstrap")
        self.machine_id = Path("/state/machine-id")
        self.config_root = Path("/state/config")
        self.config = self.config_root / "ppu.yaml"
        self.work = Path("/state/work")
        self.runtime_lock = threading.RLock()
        self.server_process: subprocess.Popen[Any] | None = None
        self.gateway_process: subprocess.Popen[Any] | None = None
        self.bootstrap_core = _load_script(scripts / "ppu-bootstrap.py", "z2like_qemu_bootstrap_core")
        self.bootstrap_service = _load_script(scripts / "ppu-bootstrap-service.py", "z2like_qemu_bootstrap_service")
        self.bootstrap_kit = _load_script(scripts / "ppu-bootstrap-kit.py", "z2like_qemu_bootstrap_kit")
        self.installer = _load_script(scripts / "ppu-z2-installer-core.py", "z2like_qemu_installer_core")
        self._prepare_state()

    def _prepare_state(self) -> None:
        for directory in (
            self.product_root / "releases",
            self.product_root / "install",
            self.bootstrap_state,
            self.config_root,
            self.work / "output",
            self.work / "logs",
            self.work / "gateway-output",
        ):
            directory.mkdir(parents=True, exist_ok=True)
        if not self.machine_id.exists():
            self.machine_id.write_text(secrets.token_hex(16) + "\n", encoding="utf-8")
            self.machine_id.chmod(0o400)
        token_file = self.bootstrap_state / "control-token"
        if not token_file.exists():
            self.bootstrap_service.provision_token(token_file)

    def _identity(self) -> dict[str, Any] | None:
        path = self.bootstrap_state / "identity.json"
        if not path.exists():
            return None
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None

    def _write_identity(self, *, device_id: str, ppu_id: str, facility_id: str) -> None:
        path = self.bootstrap_state / "identity.json"
        payload = {
            "schema_version": 1,
            "device_id": device_id,
            "ppu_id": ppu_id,
            "facility_id": facility_id,
            "hardware_revision": "qemu-armv7-simulation",
        }
        temporary = path.with_name(path.name + ".new")
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        temporary.chmod(0o600)
        os.replace(temporary, path)

    def _write_initial_config(self, *, ppu_id: str, facility_id: str, display_name: str) -> None:
        if self.config.exists():
            identity = self._identity() or {}
            if identity.get("ppu_id") not in {None, ppu_id} or identity.get("facility_id") not in {None, facility_id}:
                raise SimError("simulation appliance identity cannot change across Runtime upgrades")
            return
        sites = []
        for site_id in range(1, 9):
            site: dict[str, Any] = {
                "id": site_id,
                "enabled": site_id == 1,
                "interface": "mock",
                "target": "STM32F103C8T6",
            }
            if site_id == 1:
                site["mock"] = {"flash_size": 262144, "default_delay_s": 0.02, "progress_steps": 5}
            sites.append(site)
        payload = {
            "ppu": {
                "id": ppu_id,
                "facility_id": facility_id,
                "model": "QEMU-ARMv7-Z2-SIM",
                "display_name": display_name,
            },
            "server": {
                "host": "127.0.0.1",
                "port": 9900,
                "max_supported_sites": 8,
                "max_concurrent_jobs": 2,
                "max_queue_depth_per_site": 16,
                "output_root": str(self.work / "output"),
                "log_root": str(self.work / "logs"),
                "max_metadata_bytes": 65536,
                "max_map_bytes": 1048576,
                "max_binary_bytes": 67108864,
            },
            "sites": sites,
        }
        self.config.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    @staticmethod
    def _terminate(process: subprocess.Popen[Any] | None) -> None:
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    def stop_runtime(self) -> None:
        with self.runtime_lock:
            self._terminate(self.gateway_process)
            self._terminate(self.server_process)
            self.gateway_process = None
            self.server_process = None

    def _current_release(self) -> Path | None:
        current = self.product_root / "current"
        if not current.exists() and not current.is_symlink():
            return None
        if not current.is_symlink():
            raise SimError("simulation current path is not a symlink")
        target = current.resolve(strict=True)
        target.relative_to((self.product_root / "releases").resolve())
        return target

    def _wait_gateway(self, timeout_s: float = 30.0) -> dict[str, Any]:
        deadline = time.monotonic() + timeout_s
        last = "no response"
        while time.monotonic() < deadline:
            if self.server_process is None or self.gateway_process is None:
                raise SimError("runtime processes are not started")
            if self.server_process.poll() is not None or self.gateway_process.poll() is not None:
                raise SimError("runtime process exited before readiness")
            try:
                payload = _http_json(f"http://127.0.0.1:{GATEWAY_PORT}/api/health/ready")
                if payload.get("ok") is True and payload.get("execution") == "ready":
                    return payload
                last = repr(payload)
            except SimError as exc:
                last = str(exc)
            time.sleep(0.2)
        raise SimError(f"simulation Gateway readiness deadline exceeded: {last}")

    def start_runtime(self) -> dict[str, Any] | None:
        with self.runtime_lock:
            release = self._current_release()
            if release is None:
                return None
            app = release / "runtime" / "ppu" / "ppu.pyz"
            manifest_path = release / "runtime" / "ppu-runtime.json"
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            data = manifest.get("data") if isinstance(manifest, dict) else None
            catalog_rel = data.get("device_catalog_manifest") if isinstance(data, dict) else None
            if not app.is_file() or not isinstance(catalog_rel, str):
                raise SimError("active simulation release is missing canonical PPU runtime files")
            if not self.config.is_file():
                raise SimError("simulation PPU config is missing")
            catalog = release / "runtime" / catalog_rel
            if not catalog.is_file():
                raise SimError("simulation Device Catalog manifest is missing")
            self.stop_runtime()
            env = dict(os.environ)
            env["PYTHONUNBUFFERED"] = "1"
            env["PLASMA_DEVICE_CATALOG_MANIFEST"] = str(catalog)
            self.server_process = subprocess.Popen(
                [sys.executable, str(app), "server", "--config", str(self.config)],
                cwd=self.work,
                env=env,
            )
            self.gateway_process = subprocess.Popen(
                [
                    sys.executable,
                    str(app),
                    "gateway",
                    "--ppu-config",
                    str(self.config),
                    "--host",
                    "0.0.0.0",
                    "--port",
                    str(GATEWAY_PORT),
                    "--plasma-host",
                    "127.0.0.1",
                    "--plasma-port",
                    "9900",
                    "--output-root",
                    str(self.work / "gateway-output"),
                    "--engineering-configured-mock",
                ],
                cwd=self.work,
                env=env,
            )
            return self._wait_gateway()

    def _atomic_current(self, target: Path | None) -> None:
        current = self.product_root / "current"
        temporary = current.with_name(current.name + ".new")
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        if target is None:
            try:
                current.unlink()
            except FileNotFoundError:
                pass
            return
        os.symlink(str(target), str(temporary))
        os.replace(temporary, current)

    def deployment_runner(self, paths: Any, upload_id: str, request: Mapping[str, Any]) -> Mapping[str, Any]:
        upload_root = Path(paths.uploads_root)
        artifact = upload_root / f"{upload_id}.tar.gz"
        sidecar = Path(str(artifact) + ".sha256")
        previous = self._current_release()
        with tempfile.TemporaryDirectory(prefix="z2like-qemu-deploy-", dir=self.work) as temporary:
            kit = self.bootstrap_kit.verify_kit(
                artifact,
                sidecar=sidecar,
                extract_to=Path(temporary) / "kit",
            )
            verified = self.installer.verify_release(
                kit.ppu_artifact,
                sidecar=kit.ppu_sidecar,
                extract_to=Path(temporary) / "ppu",
            )
            target = self.product_root / "releases" / verified.release_id
            self.installer._copy_release(verified, target)
            self._write_initial_config(
                ppu_id=str(request["ppu_id"]),
                facility_id=str(request["facility_id"]),
                display_name=str(request["display_name"]),
            )
            base_paths = self.bootstrap_core.BootstrapPaths(self.product_root, self.bootstrap_state, self.machine_id)
            device_id = self.bootstrap_core.load_identity(base_paths).device_id
            self._write_identity(
                device_id=device_id,
                ppu_id=str(request["ppu_id"]),
                facility_id=str(request["facility_id"]),
            )
            self._atomic_current(target)
            try:
                readiness = self.start_runtime()
            except Exception:
                self.stop_runtime()
                self._atomic_current(previous)
                if previous is not None:
                    self.start_runtime()
                raise
            install_evidence = {
                "schema_version": 1,
                "result": "PASS",
                "role": "ppu-simulation",
                "platform": "linux-armv7l",
                "simulation_environment": "SWPC",
                "backend": "qemu-armv7",
                "release_id": verified.release_id,
                "git_sha": verified.git_sha,
                "kit_release_id": kit.release_id,
                "kit_sha256": kit.kit_sha256,
                "systemd_qualified": False,
                "fpga_update": False,
            }
            evidence_path = self.product_root / "install" / "last-install.json"
            evidence_path.write_text(json.dumps(install_evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")
            return {
                "schema_version": 1,
                "result": "PASS",
                "operation": "simulation_deploy",
                "release_id": verified.release_id,
                "kit_release_id": kit.release_id,
                "kit_sha256": kit.kit_sha256,
                "gateway_ready": readiness,
                "simulation_environment": "SWPC",
                "backend": "qemu-armv7",
                "systemd_qualified": False,
                "publisher_authenticity": "not_yet_qualified",
                "fpga_update": False,
            }

    def serve(self) -> int:
        if platform.machine().lower() not in {"armv7", "armv7l"}:
            raise SimError(f"inside mode requires ARMv7, got {platform.machine()}")
        try:
            self.start_runtime()
        except SimError as exc:
            print(f"z2like-qemu-sim: existing runtime not started: {exc}", file=sys.stderr)
        paths = self.bootstrap_service.ServicePaths(
            product_root=self.product_root,
            state_root=self.bootstrap_state,
            machine_id_path=self.machine_id,
            bootstrap_script=self.scripts / "ppu-bootstrap.py",
            kit_tool=self.scripts / "ppu-bootstrap-kit.py",
        )
        server = self.bootstrap_service.BootstrapHTTPServer(
            ("0.0.0.0", BOOTSTRAP_PORT),
            paths=paths,
            base_module=self.bootstrap_core,
            deployment_runner=self.deployment_runner,
        )
        try:
            server.serve_forever()
        finally:
            server.server_close()
            self.stop_runtime()
        return 0

    def token(self, *, rotate: bool) -> str:
        token_file = self.bootstrap_state / "control-token"
        if rotate:
            return str(self.bootstrap_service.provision_token(token_file, rotate=True))
        return str(self.bootstrap_service.load_token(token_file))


def _inside() -> int:
    appliance = SimulatedAppliance(Path("/plasma-scripts"))
    return appliance.serve()


def _inside_token(rotate: bool) -> int:
    appliance = SimulatedAppliance(Path("/plasma-scripts"))
    print(appliance.token(rotate=rotate))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="SWPC QEMU ARMv7 simulated Z2 backend")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("up", help="start or verify the persistent simulated Z2")
    sub.add_parser("down", help="remove only the simulation container; retain state volume")
    status = sub.add_parser("status", help="show Bootstrap/Gateway state")
    status.add_argument("--write-evidence", action="store_true")
    token = sub.add_parser("token", help="print the local Bootstrap pairing token")
    token.add_argument("--rotate", action="store_true")
    sub.add_parser("evidence", help="refresh host-side simulation evidence")
    sub.add_parser("inside", help=argparse.SUPPRESS)
    inside_token = sub.add_parser("inside-token", help=argparse.SUPPRESS)
    inside_token.add_argument("--rotate", action="store_true")
    args = parser.parse_args(argv)
    try:
        if args.command == "up":
            return _host_up()
        if args.command == "down":
            return _host_down()
        if args.command == "status":
            return _host_status(bool(args.write_evidence))
        if args.command == "token":
            return _host_token(bool(args.rotate))
        if args.command == "evidence":
            payload = _write_host_evidence(DEFAULT_EVIDENCE_REL)
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0
        if args.command == "inside":
            return _inside()
        if args.command == "inside-token":
            return _inside_token(bool(args.rotate))
        raise AssertionError("unreachable command")
    except (SimError, OSError, ValueError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"z2like-qemu-sim: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

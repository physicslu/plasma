#!/usr/bin/env python3
"""Static IPv4 fault-injection acceptance for production Manager commissioning.

Each scenario creates a fresh isolated Docker topology with two packaged ARMv7
Virtual PPUs. Only the test helper receives CAP_NET_ADMIN. The real production
Manager drives commissioning; crash scenarios use a test-only launcher for the
first process and restart with the unmodified production Manager.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import platform
import shutil
import signal
import socket
import subprocess
import sys
import time
import urllib.error
from pathlib import Path
from typing import Any, Mapping, Sequence

LAB_SUBNET = "192.168.78.0/24"
LAB_GATEWAY = "192.168.78.1"
PPU_A_ID = "virtual-ppu-a"
PPU_B_ID = "virtual-ppu-b"
PPU_A_INITIAL_IP = "192.168.78.10"
PPU_B_INITIAL_IP = "192.168.78.11"
CANDIDATE_IP = "192.168.78.21"
TIMEOUT_CANDIDATE_IP = "192.168.78.22"
PPU_A_CONTROL_IP = "192.168.78.40"
PPU_B_CONTROL_IP = "192.168.78.41"
PPU_PORT = 18080
ROLLBACK_TIMEOUT_S = 8
CAP_NET_ADMIN = 12
DEFAULT_WORK_REL = Path(".work/static-ipv4-fault-injection")
DEFAULT_REPORT_REL = Path(".work/reports/static-ipv4-fault-injection.json")
RESULT_MARKER = "PLASMA_STATIC_IPV4_FAULT_INJECTION_RESULT="


class FaultLabError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _load_module(path: Path, name: str) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise FaultLabError(f"cannot load module: {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _run(
    command: Sequence[str],
    *,
    cwd: Path | None = None,
    check: bool = True,
    env: Mapping[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(command),
        cwd=cwd,
        text=True,
        capture_output=True,
        check=check,
        env=dict(env) if env is not None else None,
    )


def _sha256(path: Path) -> str:
    """Hash a private PPU journal without weakening its 0600 permissions.

    The packaged PPU runs as uid 0 in a rootful Docker deployment and persists
    the activation journal with tempfile.mkstemp(), so the bind-mounted host
    file can correctly be root:root 0600. Read it through a no-network,
    no-capability, read-only disposable container instead of assuming the host
    integration uid can open it directly.
    """
    ppu_work = path.parent.parent.resolve()
    canonical = ppu_work / "gateway-output" / "ppu-network-activation.json"
    if path.resolve() != canonical:
        raise FaultLabError(f"refusing to hash non-canonical PPU activation journal: {path}")
    phase2 = _load_module(
        _repo_root() / "scripts/ppu-network-phase2-acceptance.py",
        "_plasma_fault_evidence_phase2",
    )
    reader = (
        "import hashlib\n"
        "from pathlib import Path\n"
        "path = Path('/work/gateway-output/ppu-network-activation.json')\n"
        "if not path.is_file():\n"
        "    raise SystemExit('canonical activation journal missing')\n"
        "digest = hashlib.sha256()\n"
        "with path.open('rb') as handle:\n"
        "    for block in iter(lambda: handle.read(1024 * 1024), b''):\n"
        "        digest.update(block)\n"
        "print(digest.hexdigest())\n"
    )
    result = phase2._run([
        "docker", "run", "--rm",
        "--platform", "linux/arm/v7",
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "-v", f"{ppu_work}:/work:ro",
        phase2.ARM_IMAGE,
        "python3", "-c", reader,
    ])
    digest = result.stdout.strip()
    if len(digest) != 64 or any(ch not in "0123456789abcdef" for ch in digest):
        raise FaultLabError(f"invalid activation journal SHA-256 evidence: {digest!r}")
    return digest


def _make_stale_work_host_removable(phase2: Any, root: Path) -> None:
    """Repair disposable bind-mount permissions without sudo or host privileges.

    Packaged PPU containers run as uid 0 inside Docker and can leave dated log
    directories owned by host uid 0. The integration user then cannot remove a
    previous lab workspace. A no-network, no-capability disposable container
    using the same pinned ARMv7 image makes only that bind-mounted test tree
    removable before the host process deletes it.
    """
    if not root.exists():
        return
    repair = (
        "from pathlib import Path\n"
        "root = Path('/work')\n"
        "paths = [root, *root.rglob('*')]\n"
        "for path in paths:\n"
        "    try:\n"
        "        if path.is_dir():\n"
        "            path.chmod(0o777)\n"
        "        elif path.is_file():\n"
        "            path.chmod(0o666)\n"
        "    except OSError:\n"
        "        pass\n"
    )
    phase2._run([
        "docker", "run", "--rm",
        "--platform", "linux/arm/v7",
        "--network", "none",
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "-v", f"{root}:/work",
        phase2.ARM_IMAGE,
        "python3", "-c", repair,
    ])


def _write_manager_config(
    path: Path,
    *,
    port: int,
    registry_state: Path,
    ppu_b_endpoint: str,
) -> None:
    path.write_text(
        "manager:\n"
        "  host: 127.0.0.1\n"
        f"  port: {port}\n"
        "  request_timeout_s: 1.0\n"
        "  poll_interval_s: 0.2\n"
        f"  registry_state_path: {registry_state.resolve()}\n"
        "ppus:\n"
        "  - alias: ppu-a\n"
        f"    endpoint: http://{PPU_A_INITIAL_IP}:{PPU_PORT}\n"
        "  - alias: ppu-b\n"
        f"    endpoint: {ppu_b_endpoint}\n",
        encoding="utf-8",
    )


def _journal_path(registry_state: Path) -> Path:
    return registry_state.with_name(f"{registry_state.stem}-network-commissioning.json")


def _read_durable_record(registry_state: Path) -> dict[str, Any]:
    path = _journal_path(registry_state)
    if not path.is_file():
        raise FaultLabError(f"Manager commissioning journal missing: {path}")
    payload = json.loads(path.read_text(encoding="utf-8"))
    record = ((payload.get("transactions") or {}).get("ppu-a") if isinstance(payload, dict) else None)
    if not isinstance(record, dict):
        raise FaultLabError("durable Manager commissioning record missing for ppu-a")
    return record


def _find_activation_journal(ppu_work: Path) -> Path:
    path = ppu_work / "gateway-output" / "ppu-network-activation.json"
    if not path.is_file():
        raise FaultLabError(f"PPU activation journal missing at canonical path: {path}")
    return path


def _start_fault_ppu(
    *,
    phase2: Any,
    runtime: Path,
    phase2_script: Path,
    fault_helper_script: Path,
    network: str,
    ppu_name: str,
    helper_name: str,
    work: Path,
    control_ip: str,
    managed_ip: str,
    fault_mode: str,
) -> None:
    phase2._run([
        "docker", "run", "-d", "--name", ppu_name,
        "--platform", "linux/arm/v7",
        "--network", network, "--ip", control_ip,
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges:true",
        "-v", f"{runtime}:/runtime:ro",
        "-v", f"{work}:/work",
        "-v", f"{phase2_script}:/acceptance.py:ro",
        phase2.ARM_IMAGE,
        "python3", "/acceptance.py",
        "--inside-ppu", "--runtime-dir", "/runtime", "--work-dir", "/work",
    ])
    phase2._run([
        "docker", "run", "-d", "--name", helper_name,
        "--platform", "linux/arm/v7",
        "--network", f"container:{ppu_name}",
        "--cap-drop", "ALL", "--cap-add", "NET_ADMIN",
        "--security-opt", "no-new-privileges:true",
        "-v", f"{work}:/work",
        "-v", f"{phase2_script}:/acceptance.py:ro",
        "-v", f"{fault_helper_script}:/fault-helper.py:ro",
        phase2.ARM_IMAGE,
        "python3", "/fault-helper.py",
        "--phase2-script", "/acceptance.py",
        "--helper-socket", "/work/network-helper.sock",
        "--managed-initial-address", managed_ip,
        "--managed-prefix", "24",
        "--fault-mode", fault_mode,
    ])
    deadline = time.monotonic() + 10.0
    socket_path = work / "network-helper.sock"
    while time.monotonic() < deadline and not socket_path.exists():
        time.sleep(0.05)
    if not socket_path.exists():
        raise FaultLabError(f"network helper socket did not appear for {ppu_name}")
    if phase2._has_cap(phase2._cap_eff(ppu_name), CAP_NET_ADMIN):
        raise FaultLabError(f"{ppu_name} Gateway unexpectedly has CAP_NET_ADMIN")
    if not phase2._has_cap(phase2._cap_eff(helper_name), CAP_NET_ADMIN):
        raise FaultLabError(f"{helper_name} is missing CAP_NET_ADMIN")


def _add_helper_alias(
    *,
    phase2: Any,
    helper_name: str,
    fault_helper_script: Path,
    phase2_script: Path,
    address: str,
) -> None:
    phase2._run([
        "docker", "exec", helper_name,
        "python3", "/fault-helper.py",
        "--phase2-script", "/acceptance.py",
        "--interface", "eth0",
        "--managed-prefix", "24",
        "--oneshot-add", address,
    ])


def _start_crash_manager(
    *,
    repo: Path,
    python: Path,
    config: Path,
    log_path: Path,
    crash_state: str,
) -> tuple[subprocess.Popen[str], Any]:
    env = dict(os.environ)
    python_root = str(repo / "software/python")
    env["PYTHONPATH"] = python_root + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONUNBUFFERED"] = "1"
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [
            str(python),
            "scripts/manager-network-commissioning-crash-injector.py",
            "--config", str(config),
            "--crash-after-state", crash_state,
        ],
        cwd=repo,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return process, handle


def _wait_process_exit(process: subprocess.Popen[str], *, timeout_s: float = 8.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if process.poll() is not None:
            return
        time.sleep(0.05)
    raise FaultLabError("crash-injected Manager did not terminate")


def _commission(virtual: Any, manager_base: str, address: str, key: str) -> tuple[int, dict[str, Any]]:
    desired = {
        "mode": "static",
        "address": address,
        "prefix_length": 24,
        "gateway": LAB_GATEWAY,
        "dns_servers": [LAB_GATEWAY],
    }
    return virtual._http_json(
        f"{manager_base}/api/registry/ppu-a/network-commissioning",
        method="POST",
        body={"desired": desired, "rollback_timeout_s": ROLLBACK_TIMEOUT_S},
        headers={"Idempotency-Key": key},
        timeout_s=ROLLBACK_TIMEOUT_S + 7,
    )


def _commissioning_record(virtual: Any, manager_base: str) -> dict[str, Any]:
    status, payload = virtual._http_json(f"{manager_base}/api/registry/ppu-a/network-commissioning")
    record = payload.get("commissioning")
    if status != 200 or not isinstance(record, dict):
        raise FaultLabError(f"Manager commissioning record unavailable: HTTP {status}: {payload!r}")
    return record


def _registry_endpoints(virtual: Any, manager_base: str) -> tuple[str | None, str | None]:
    status, payload = virtual._http_json(f"{manager_base}/api/registry")
    if status != 200:
        raise FaultLabError(f"Manager registry unavailable: HTTP {status}: {payload!r}")
    return virtual._registry_endpoint(payload, "ppu-a"), virtual._registry_endpoint(payload, "ppu-b")


def _activation(virtual: Any, endpoint: str) -> dict[str, Any]:
    status, payload = virtual._http_json(f"{endpoint}/api/settings/ppu-network/activation")
    activation = payload.get("activation")
    if status != 200 or not isinstance(activation, dict):
        raise FaultLabError(f"PPU activation unavailable at {endpoint}: HTTP {status}: {payload!r}")
    return activation


def _wait_activation(virtual: Any, endpoint: str, state: str, *, timeout_s: float = 14.0) -> dict[str, Any]:
    return virtual._wait_json(
        f"{endpoint}/api/settings/ppu-network/activation",
        lambda payload: isinstance(payload.get("activation"), dict) and payload["activation"].get("state") == state,
        timeout_s=timeout_s,
        label=f"activation {state} at {endpoint}",
    )["activation"]


class ScenarioTopology:
    def __init__(
        self,
        *,
        name: str,
        repo: Path,
        python: Path,
        runtime: Path,
        phase2: Any,
        virtual: Any,
        root: Path,
        ppu_a_fault_mode: str = "normal",
        ppu_b_initial_ip: str = PPU_B_INITIAL_IP,
        ppu_b_registry_ip: str = PPU_B_INITIAL_IP,
        manager_crash_state: str | None = None,
        add_wrong_candidate_to_b: bool = False,
    ) -> None:
        self.name = name
        self.repo = repo
        self.python = python
        self.runtime = runtime
        self.phase2 = phase2
        self.virtual = virtual
        self.work = root / name
        self.ppu_a_fault_mode = ppu_a_fault_mode
        self.ppu_b_initial_ip = ppu_b_initial_ip
        self.ppu_b_registry_ip = ppu_b_registry_ip
        self.manager_crash_state = manager_crash_state
        self.add_wrong_candidate_to_b = add_wrong_candidate_to_b
        self.manager_port = virtual._free_port()
        self.manager_base = f"http://127.0.0.1:{self.manager_port}"
        self.manager_config = self.work / "manager.yaml"
        self.registry_state = self.work / "manager-ppu-registry.json"
        suffix = f"{name}-{os.getpid()}-{int(time.time() * 1000)}".replace("_", "-")
        self.network = f"plasma-fault-{suffix}"[:63]
        self.ppu_a = f"plasma-fault-a-{suffix}"[:63]
        self.helper_a = f"plasma-fault-a-helper-{suffix}"[:63]
        self.ppu_b = f"plasma-fault-b-{suffix}"[:63]
        self.helper_b = f"plasma-fault-b-helper-{suffix}"[:63]
        self.ppu_a_work: Path | None = None
        self.ppu_b_work: Path | None = None
        self.manager: subprocess.Popen[str] | None = None
        self.log_handles: list[Any] = []
        self.uplink = virtual._host_uplink_interface()
        self.uplink_before = virtual._host_interface_signature(self.uplink)

    def start(self) -> None:
        self.work.mkdir(parents=True)
        self.ppu_a_work = self.virtual._prepare_work(self.work, "ppu-a", PPU_A_ID)
        self.ppu_b_work = self.virtual._prepare_work(self.work, "ppu-b", PPU_B_ID)
        _write_manager_config(
            self.manager_config,
            port=self.manager_port,
            registry_state=self.registry_state,
            ppu_b_endpoint=f"http://{self.ppu_b_registry_ip}:{PPU_PORT}",
        )
        self.phase2._run(["docker", "network", "create", "--subnet", LAB_SUBNET, "--gateway", LAB_GATEWAY, self.network])
        phase2_script = self.repo / "scripts/ppu-network-phase2-acceptance.py"
        fault_helper = self.repo / "scripts/static-ipv4-fault-helper.py"
        _start_fault_ppu(
            phase2=self.phase2,
            runtime=self.runtime,
            phase2_script=phase2_script,
            fault_helper_script=fault_helper,
            network=self.network,
            ppu_name=self.ppu_a,
            helper_name=self.helper_a,
            work=self.ppu_a_work,
            control_ip=PPU_A_CONTROL_IP,
            managed_ip=PPU_A_INITIAL_IP,
            fault_mode=self.ppu_a_fault_mode,
        )
        _start_fault_ppu(
            phase2=self.phase2,
            runtime=self.runtime,
            phase2_script=phase2_script,
            fault_helper_script=fault_helper,
            network=self.network,
            ppu_name=self.ppu_b,
            helper_name=self.helper_b,
            work=self.ppu_b_work,
            control_ip=PPU_B_CONTROL_IP,
            managed_ip=self.ppu_b_initial_ip,
            fault_mode="normal",
        )
        self.virtual._wait_json(
            f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}/api/node",
            lambda payload: self.virtual._ppu_id(payload) == PPU_A_ID,
            label=f"{self.name} PPU A old endpoint",
        )
        self.virtual._wait_json(
            f"http://{self.ppu_b_initial_ip}:{PPU_PORT}/api/node",
            lambda payload: self.virtual._ppu_id(payload) == PPU_B_ID,
            label=f"{self.name} PPU B endpoint",
        )
        if self.add_wrong_candidate_to_b:
            _add_helper_alias(
                phase2=self.phase2,
                helper_name=self.helper_b,
                fault_helper_script=fault_helper,
                phase2_script=phase2_script,
                address=CANDIDATE_IP,
            )
            self.virtual._wait_json(
                f"http://{CANDIDATE_IP}:{PPU_PORT}/api/node",
                lambda payload: self.virtual._ppu_id(payload) == PPU_B_ID,
                label=f"{self.name} wrong-device candidate endpoint",
            )
        self._start_manager(self.manager_crash_state)
        self.wait_manager_ready()

    def _start_manager(self, crash_state: str | None) -> None:
        if crash_state is None:
            process, handle = self.virtual._start_manager(
                self.repo,
                self.python,
                self.manager_config,
                self.work / f"manager-{len(self.log_handles)}.log",
            )
        else:
            process, handle = _start_crash_manager(
                repo=self.repo,
                python=self.python,
                config=self.manager_config,
                log_path=self.work / f"manager-crash-{crash_state}.log",
                crash_state=crash_state,
            )
        self.manager = process
        self.log_handles.append(handle)
        if self.virtual._has_cap(self.virtual._cap_eff(process.pid), CAP_NET_ADMIN):
            raise FaultLabError("Plasma Manager unexpectedly has CAP_NET_ADMIN")

    def wait_manager_ready(self) -> None:
        self.virtual._wait_json(
            f"{self.manager_base}/api/health/live",
            lambda payload: payload.get("ok") is True and payload.get("manager") == "alive",
            label=f"{self.name} Manager liveness",
        )
        fleet = self.virtual._wait_json(
            f"{self.manager_base}/api/fleet",
            self.virtual._fleet_ready,
            timeout_s=20,
            label=f"{self.name} trusted fleet",
        )
        if not self.virtual._fleet_ready(fleet):
            raise FaultLabError(f"{self.name}: Manager fleet is not trusted")

    def restart_production_manager(self) -> None:
        if self.manager is not None:
            self.virtual._stop_process(self.manager)
        time.sleep(0.15)
        self._start_manager(None)
        self.virtual._wait_json(
            f"{self.manager_base}/api/health/live",
            lambda payload: payload.get("ok") is True and payload.get("manager") == "alive",
            timeout_s=10,
            label=f"{self.name} restarted Manager",
        )

    def assert_host_untouched(self) -> None:
        after = self.virtual._host_interface_signature(self.uplink)
        if after != self.uplink_before:
            raise FaultLabError(f"host uplink {self.uplink} changed during {self.name}")

    def close(self) -> None:
        if self.manager is not None:
            self.virtual._stop_process(self.manager)
        for handle in self.log_handles:
            try:
                handle.close()
            except Exception:
                pass
        self.phase2._docker_rm(self.helper_b)
        self.phase2._docker_rm(self.helper_a)
        self.phase2._docker_rm(self.ppu_b)
        self.phase2._docker_rm(self.ppu_a)
        self.phase2._docker_network_rm(self.network)
        self.assert_host_untouched()


def _scenario_duplicate_candidate(**common: Any) -> dict[str, Any]:
    topology = ScenarioTopology(
        name="duplicate-candidate",
        ppu_b_initial_ip=CANDIDATE_IP,
        ppu_b_registry_ip=CANDIDATE_IP,
        **common,
    )
    topology.start()
    try:
        status, _ = _commission(topology.virtual, topology.manager_base, CANDIDATE_IP, "fault-duplicate-candidate")
        if status == 200:
            raise FaultLabError("duplicate candidate unexpectedly commissioned")
        record = _commissioning_record(topology.virtual, topology.manager_base)
        if record.get("state") != "failed":
            raise FaultLabError(f"duplicate candidate state is not failed: {record!r}")
        a_endpoint, b_endpoint = _registry_endpoints(topology.virtual, topology.manager_base)
        if a_endpoint != f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}" or b_endpoint != f"http://{CANDIDATE_IP}:{PPU_PORT}":
            raise FaultLabError("duplicate candidate corrupted Manager registry")
        activation = _activation(topology.virtual, f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}")
        if activation.get("state") != "idle":
            raise FaultLabError(f"duplicate candidate unexpectedly started PPU activation: {activation!r}")
        return {"terminal_state": "failed", "activation_state": "idle", "registry_preserved": True}
    finally:
        topology.close()


def _scenario_wrong_identity(**common: Any) -> dict[str, Any]:
    topology = ScenarioTopology(
        name="wrong-identity",
        ppu_a_fault_mode="apply-noop",
        add_wrong_candidate_to_b=True,
        **common,
    )
    topology.start()
    try:
        status, _ = _commission(topology.virtual, topology.manager_base, CANDIDATE_IP, "fault-wrong-identity")
        if status == 200:
            raise FaultLabError("wrong candidate identity unexpectedly commissioned")
        record = _commissioning_record(topology.virtual, topology.manager_base)
        if record.get("state") != "rolled_back" or record.get("error_code") != "candidate_identity_mismatch":
            raise FaultLabError(f"wrong identity did not fail closed: {record!r}")
        a_endpoint, _ = _registry_endpoints(topology.virtual, topology.manager_base)
        if a_endpoint != f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}":
            raise FaultLabError("wrong identity repointed Manager registry")
        activation = _wait_activation(topology.virtual, f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}", "rolled_back")
        candidate = topology.virtual._wait_json(
            f"http://{CANDIDATE_IP}:{PPU_PORT}/api/node",
            lambda payload: topology.virtual._ppu_id(payload) == PPU_B_ID,
            label="wrong identity candidate still belongs to PPU B",
        )
        if topology.virtual._ppu_id(candidate) != PPU_B_ID:
            raise FaultLabError("wrong identity evidence disappeared")
        return {
            "terminal_state": "rolled_back",
            "error_code": "candidate_identity_mismatch",
            "ppu_activation": activation.get("state"),
            "candidate_ppu_id": PPU_B_ID,
        }
    finally:
        topology.close()


def _scenario_reconnect_timeout(**common: Any) -> dict[str, Any]:
    topology = ScenarioTopology(
        name="reconnect-timeout",
        ppu_a_fault_mode="apply-drop",
        **common,
    )
    topology.start()
    try:
        status, _ = _commission(topology.virtual, topology.manager_base, TIMEOUT_CANDIDATE_IP, "fault-reconnect-timeout")
        if status == 200:
            raise FaultLabError("unreachable candidate unexpectedly commissioned")
        record = _commissioning_record(topology.virtual, topology.manager_base)
        if record.get("state") != "rolled_back" or record.get("error_code") != "candidate_endpoint_unreachable":
            raise FaultLabError(f"reconnect timeout did not roll back: {record!r}")
        old_node = topology.virtual._wait_json(
            f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}/api/node",
            lambda payload: topology.virtual._ppu_id(payload) == PPU_A_ID,
            timeout_s=12,
            label="old endpoint restored after reconnect timeout",
        )
        if topology.virtual._ppu_id(old_node) != PPU_A_ID:
            raise FaultLabError("old endpoint restored with wrong identity")
        a_endpoint, _ = _registry_endpoints(topology.virtual, topology.manager_base)
        if a_endpoint != f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}":
            raise FaultLabError("reconnect timeout repointed Manager registry")
        return {"terminal_state": "rolled_back", "error_code": "candidate_endpoint_unreachable", "old_endpoint_restored": True}
    finally:
        topology.close()


def _scenario_helper_failure(**common: Any) -> dict[str, Any]:
    topology = ScenarioTopology(
        name="helper-apply-failure",
        ppu_a_fault_mode="apply-error",
        **common,
    )
    topology.start()
    try:
        status, _ = _commission(topology.virtual, topology.manager_base, CANDIDATE_IP, "fault-helper-apply")
        if status == 200:
            raise FaultLabError("helper apply failure unexpectedly commissioned")
        record = _commissioning_record(topology.virtual, topology.manager_base)
        if record.get("state") != "rolled_back":
            raise FaultLabError(f"helper failure did not terminate rolled_back: {record!r}")
        activation = _wait_activation(topology.virtual, f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}", "rolled_back")
        if activation.get("reason") != "apply_failed" or "injected apply failure" not in str(activation.get("error")):
            raise FaultLabError(f"PPU helper-failure evidence is incomplete: {activation!r}")
        a_endpoint, _ = _registry_endpoints(topology.virtual, topology.manager_base)
        if a_endpoint != f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}":
            raise FaultLabError("helper failure repointed Manager registry")
        return {
            "terminal_state": "rolled_back",
            "ppu_reason": "apply_failed",
            "registry_preserved": True,
        }
    finally:
        topology.close()


def _issue_until_crash(topology: ScenarioTopology, address: str, key: str) -> None:
    try:
        _commission(topology.virtual, topology.manager_base, address, key)
    except Exception:
        pass
    if topology.manager is None:
        raise FaultLabError("crash scenario has no Manager process")
    _wait_process_exit(topology.manager)


def _scenario_manager_crash_before_commit(**common: Any) -> dict[str, Any]:
    topology = ScenarioTopology(
        name="manager-crash-before-commit",
        manager_crash_state="identity_verified",
        **common,
    )
    topology.start()
    try:
        _issue_until_crash(topology, CANDIDATE_IP, "fault-crash-before-commit")
        durable = _read_durable_record(topology.registry_state)
        if durable.get("state") != "identity_verified":
            raise FaultLabError(f"pre-commit crash did not persist identity_verified: {durable!r}")
        topology.restart_production_manager()
        recovered = _commissioning_record(topology.virtual, topology.manager_base)
        if recovered.get("state") != "recovery_required" or recovered.get("error_code") != "manager_restart_before_commit_boundary":
            raise FaultLabError(f"pre-commit restart did not fail closed: {recovered!r}")
        a_endpoint, _ = _registry_endpoints(topology.virtual, topology.manager_base)
        if a_endpoint != f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}":
            raise FaultLabError("pre-commit crash mutated Manager registry")
        activation = _wait_activation(
            topology.virtual,
            f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}",
            "rolled_back",
            timeout_s=ROLLBACK_TIMEOUT_S + 8,
        )
        topology.wait_manager_ready()
        retry_status, retry_payload = _commission(
            topology.virtual,
            topology.manager_base,
            CANDIDATE_IP,
            "fault-crash-before-commit-retry",
        )
        retry_error = retry_payload.get("error")
        retry_record = retry_payload.get("commissioning")
        if (
            retry_status != 409
            or not isinstance(retry_error, dict)
            or retry_error.get("code") != "network_commissioning_busy"
            or not isinstance(retry_record, dict)
            or retry_record.get("state") != "recovery_required"
        ):
            raise FaultLabError(
                "recovery_required was not the authoritative retry blocker: "
                f"HTTP {retry_status}: {retry_payload!r}"
            )
        return {
            "durable_crash_state": "identity_verified",
            "restart_state": "recovery_required",
            "new_commissioning_blocked": True,
            "blocking_error_code": "network_commissioning_busy",
            "trusted_fleet_restored_before_retry": True,
            "ppu_activation": activation.get("state"),
        }
    finally:
        topology.close()


def _scenario_manager_crash_after_commit(**common: Any) -> dict[str, Any]:
    topology = ScenarioTopology(
        name="manager-crash-after-commit",
        manager_crash_state="activation_committed",
        **common,
    )
    topology.start()
    try:
        _issue_until_crash(topology, CANDIDATE_IP, "fault-crash-after-commit")
        durable = _read_durable_record(topology.registry_state)
        if durable.get("state") != "activation_committed":
            raise FaultLabError(f"post-commit crash did not persist activation_committed: {durable!r}")
        a_before = None
        if topology.registry_state.exists():
            try:
                registry_payload = json.loads(topology.registry_state.read_text(encoding="utf-8"))
                records = registry_payload.get("ppus") if isinstance(registry_payload, dict) else None
                if isinstance(records, list):
                    for item in records:
                        if isinstance(item, dict) and item.get("alias") == "ppu-a":
                            a_before = item.get("endpoint")
            except Exception:
                a_before = None
        if a_before not in {None, f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}"}:
            raise FaultLabError(f"registry changed before post-commit crash boundary: {a_before!r}")
        assert topology.ppu_a_work is not None
        ppu_journal = _find_activation_journal(topology.ppu_a_work)
        ppu_hash_before = _sha256(ppu_journal)
        candidate_activation = _activation(topology.virtual, f"http://{CANDIDATE_IP}:{PPU_PORT}")
        if candidate_activation.get("state") != "committed":
            raise FaultLabError(f"PPU is not committed at crash boundary: {candidate_activation!r}")
        topology.restart_production_manager()
        recovered = _commissioning_record(topology.virtual, topology.manager_base)
        if recovered.get("state") != "completed":
            raise FaultLabError(f"post-commit restart did not finish reconciliation: {recovered!r}")
        a_endpoint, _ = _registry_endpoints(topology.virtual, topology.manager_base)
        if a_endpoint != f"http://{CANDIDATE_IP}:{PPU_PORT}":
            raise FaultLabError("post-commit restart did not reconcile Manager registry")
        ppu_hash_after = _sha256(ppu_journal)
        if ppu_hash_after != ppu_hash_before:
            raise FaultLabError("Manager-local restart recovery unexpectedly changed PPU activation journal")
        topology.virtual._wait_unreachable(f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}/api/node")
        return {
            "durable_crash_state": "activation_committed",
            "restart_state": "completed",
            "registry_reconciled": True,
            "ppu_journal_unchanged_across_manager_restart": True,
        }
    finally:
        topology.close()


def _main(args: argparse.Namespace) -> int:
    if platform.system() != "Linux":
        raise FaultLabError("Static IPv4 fault injection requires a Linux integration host")
    if shutil.which("docker") is None or shutil.which("ip") is None:
        raise FaultLabError("docker and iproute2 are required")

    repo = _repo_root()
    virtual = _load_module(repo / "scripts/virtual-ppu-network-lab.py", "_plasma_virtual_ppu_network_lab")
    phase2 = virtual._phase2_module(repo)
    python = phase2._host_python(repo)
    git_sha = virtual._git_sha(repo)
    root = (repo / args.work_dir).resolve() if not args.work_dir.is_absolute() else args.work_dir.resolve()
    report = (repo / args.report).resolve() if not args.report.is_absolute() else args.report.resolve()

    phase2._docker_preflight()
    if root.exists():
        _make_stale_work_host_removable(phase2, root)
        shutil.rmtree(root)
    root.mkdir(parents=True)
    report.parent.mkdir(parents=True, exist_ok=True)

    runtime, release_artifact = virtual._runtime_from_args(repo, args, phase2, python, root, git_sha)

    common = {
        "repo": repo,
        "python": python,
        "runtime": runtime,
        "phase2": phase2,
        "virtual": virtual,
        "root": root,
    }
    scenarios = (
        ("duplicate_candidate", _scenario_duplicate_candidate),
        ("wrong_ppu_id", _scenario_wrong_identity),
        ("reconnect_timeout", _scenario_reconnect_timeout),
        ("helper_apply_failure", _scenario_helper_failure),
        ("manager_crash_before_commit", _scenario_manager_crash_before_commit),
        ("manager_crash_after_commit", _scenario_manager_crash_after_commit),
    )
    results: dict[str, Any] = {}
    total = len(scenarios)
    for index, (name, scenario) in enumerate(scenarios, start=1):
        label = name.replace("_", " ").title()
        print(f"[RUN ] {index}/{total} {label}", flush=True)
        started = time.monotonic()
        try:
            results[name] = scenario(**common)
        except Exception:
            elapsed = time.monotonic() - started
            print(f"[FAIL] {index}/{total} {label} ({elapsed:.1f}s)", flush=True)
            raise
        elapsed = time.monotonic() - started
        print(f"[PASS] {index}/{total} {label} ({elapsed:.1f}s)", flush=True)

    uplink = virtual._host_uplink_interface()
    result = {
        "overall_result": "PASS",
        "evidence_level": "linux-host-real-manager-qemu-armv7-static-ipv4-fault-injection",
        "git_sha": git_sha,
        "host_uplink": uplink,
        "release_artifact": release_artifact,
        "scenarios": results,
        "not_claimed": [
            "PYNQ-Z2 hardware",
            "final PYNQ-Z2 Linux network-manager backend",
            "DHCP endpoint migration",
            "production DNS/default-route mutation",
            "boot-time network persistence",
            "PS-to-PL",
            "Site I/O",
            "real IC programming",
        ],
    }
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("# Plasma Static IPv4 Fault Injection Lab")
    print()
    print(f"Git SHA                     : {git_sha}")
    print(f"Evidence level              : {result['evidence_level']}")
    for name, _ in scenarios:
        print(f"[PASS] {name.replace('_', ' ').title()}")
    print("----------------------------")
    print()
    print("DUPLICATE CANDIDATE         : PASS")
    print("WRONG PPU_ID + ROLLBACK     : PASS")
    print("RECONNECT TIMEOUT + ROLLBACK: PASS")
    print("HELPER FAILURE FAIL-CLOSED  : PASS")
    print("MANAGER CRASH PRE-COMMIT    : PASS")
    print("MANAGER CRASH POST-COMMIT   : PASS")
    print("HOST UPLINK UNTOUCHED       : PASS")
    print("Z2 NETWORK BACKEND CLAIM    : NONE")
    print("OVERALL RESULT              : PASS")
    print("-----------------------------------")
    print()
    print(f"# JSON report                  : {report}")
    print()
    print(RESULT_MARKER + json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Static IPv4 fault-injection acceptance")
    parser.add_argument("--runtime-dir", type=Path)
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_REL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_REL)
    args = parser.parse_args(argv)
    try:
        return _main(args)
    except (FaultLabError, OSError, subprocess.SubprocessError, json.JSONDecodeError, KeyError, ValueError) as exc:
        print(f"static-ipv4-fault-injection-lab: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
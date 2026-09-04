#!/usr/bin/env python3
"""Virtual PPU Network Lab acceptance with the production Plasma Manager.

The host owns the Manager process only. Two packaged ARMv7 PPUs run in an
isolated Docker bridge. Each PPU's unprivileged Gateway shares a network
namespace with a separate NET_ADMIN helper that alone mutates the lab-managed
IPv4 address on eth0.

This lab proves the Manager-owned static IPv4 commissioning transaction across
a real endpoint migration. It does not claim PYNQ-Z2 or production Linux
network-backend validation.
"""
from __future__ import annotations

import argparse
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
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

LAB_SUBNET = "192.168.78.0/24"
LAB_GATEWAY = "192.168.78.1"
PPU_A_ID = "virtual-ppu-a"
PPU_B_ID = "virtual-ppu-b"
PPU_A_INITIAL_IP = "192.168.78.10"
PPU_B_INITIAL_IP = "192.168.78.11"
PPU_A_CANDIDATE_IP = "192.168.78.21"
PPU_A_CONTROL_IP = "192.168.78.40"
PPU_B_CONTROL_IP = "192.168.78.41"
PPU_PORT = 18080
ROLLBACK_TIMEOUT_S = 20
CAP_NET_ADMIN = 12
DEFAULT_WORK_REL = Path(".work/virtual-ppu-network-lab")
DEFAULT_REPORT_REL = Path(".work/reports/virtual-ppu-network-lab.json")
RESULT_MARKER = "PLASMA_VIRTUAL_PPU_NETWORK_LAB_RESULT="


class LabError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _phase2_module(repo: Path) -> Any:
    path = repo / "scripts/ppu-network-phase2-acceptance.py"
    spec = importlib.util.spec_from_file_location("_plasma_ppu_network_phase2_acceptance", path)
    if spec is None or spec.loader is None:
        raise LabError(f"cannot load Phase 2 acceptance module: {path}")
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


def _git_sha(repo: Path) -> str:
    sha = _run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
    if len(sha) != 40:
        raise LabError(f"unexpected git SHA: {sha!r}")
    return sha


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as server:
        server.bind(("127.0.0.1", 0))
        return int(server.getsockname()[1])


def _http_json(
    url: str,
    *,
    method: str = "GET",
    body: Mapping[str, Any] | None = None,
    headers: Mapping[str, str] | None = None,
    timeout_s: float = 2.0,
) -> tuple[int, dict[str, Any]]:
    data = None
    request_headers = {"Accept": "application/json"}
    if headers:
        request_headers.update(headers)
    if body is not None:
        data = json.dumps(dict(body), separators=(",", ":"), sort_keys=True).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_s) as response:
            raw = response.read()
            payload = json.loads(raw) if raw else {}
            if not isinstance(payload, dict):
                raise LabError(f"HTTP payload is not an object: {url}")
            return int(response.status), payload
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            payload = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            payload = {"raw": raw.decode("utf-8", "replace")}
        if not isinstance(payload, dict):
            payload = {"payload": payload}
        return int(exc.code), payload


def _probe(url: str, *, timeout_s: float = 0.8) -> dict[str, Any]:
    try:
        status, payload = _http_json(url, timeout_s=timeout_s)
        return {"reachable": True, "status": status, "payload": payload}
    except (OSError, TimeoutError, urllib.error.URLError, json.JSONDecodeError, LabError) as exc:
        return {"reachable": False, "error": f"{type(exc).__name__}: {exc}"}


def _wait_json(url: str, predicate, *, timeout_s: float = 12.0, label: str) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        probe = _probe(url)
        if probe.get("reachable") is True and probe.get("status") == 200:
            payload = probe.get("payload")
            if isinstance(payload, dict):
                last = payload
                if predicate(payload):
                    return payload
        time.sleep(0.1)
    raise LabError(f"timeout waiting for {label}: {last!r}")


def _wait_unreachable(url: str, *, timeout_s: float = 5.0) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        if _probe(url).get("reachable") is not True:
            return
        time.sleep(0.1)
    raise LabError(f"endpoint remained reachable: {url}")


def _ppu_id(payload: Mapping[str, Any]) -> str:
    ppu = payload.get("ppu")
    value = ppu.get("ppu_id") if isinstance(ppu, dict) else None
    if not isinstance(value, str) or not value:
        raise LabError("/api/node omitted canonical ppu_id")
    return value


def _write_ppu_config(work: Path, *, ppu_id: str) -> None:
    (work / "ppu.yaml").write_text(
        "ppu:\n"
        f"  id: {ppu_id}\n"
        "  facility_id: virtual-network-lab\n"
        "  model: qemu-armv7-manager-lab\n"
        f"  display_name: {ppu_id}\n\n"
        "server:\n"
        "  host: 127.0.0.1\n"
        "  port: 9900\n"
        "  max_supported_sites: 1\n"
        "  max_concurrent_jobs: 1\n"
        "  max_queue_depth_per_site: 4\n"
        "  output_root: /work/server-output\n"
        "  log_root: /work/logs\n"
        "  max_metadata_bytes: 65536\n"
        "  max_map_bytes: 1048576\n"
        "  max_binary_bytes: 67108864\n\n"
        "sites:\n"
        "  - id: 1\n"
        "    enabled: true\n"
        "    interface: mock\n"
        "    target: MOCK-IC\n"
        "    operation_timeout_s: 5.0\n"
        "    max_retries: 0\n"
        "    retry_backoff_s: 0.01\n"
        "    mock:\n"
        "      flash_size: 65536\n"
        "      default_delay_s: 0.01\n"
        "      progress_steps: 2\n",
        encoding="utf-8",
    )


def _write_manager_config(path: Path, *, port: int, registry_state: Path) -> None:
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
        f"    endpoint: http://{PPU_B_INITIAL_IP}:{PPU_PORT}\n",
        encoding="utf-8",
    )


def _host_uplink_interface() -> str:
    if Path("/sys/class/net/eth0").exists():
        return "eth0"
    result = _run(["ip", "-j", "route", "show", "default"], check=False)
    if result.returncode != 0:
        raise LabError("cannot determine host uplink interface")
    routes = json.loads(result.stdout or "[]")
    for route in routes:
        dev = route.get("dev") if isinstance(route, dict) else None
        if isinstance(dev, str) and dev:
            return dev
    raise LabError("host has no default-route interface")


def _host_interface_signature(interface: str) -> tuple[tuple[str, str, int, str], ...]:
    result = _run(["ip", "-j", "addr", "show", "dev", interface])
    payload = json.loads(result.stdout)
    rows: list[tuple[str, str, int, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            continue
        for addr in item.get("addr_info") or []:
            if not isinstance(addr, dict):
                continue
            family = addr.get("family")
            local = addr.get("local")
            prefix = addr.get("prefixlen")
            scope = addr.get("scope")
            if isinstance(family, str) and isinstance(local, str) and isinstance(prefix, int) and isinstance(scope, str):
                rows.append((family, local, prefix, scope))
    return tuple(sorted(rows))


def _cap_eff(pid: int) -> int:
    for line in Path(f"/proc/{pid}/status").read_text(encoding="utf-8").splitlines():
        if line.startswith("CapEff:"):
            return int(line.split()[1], 16)
    raise LabError(f"cannot read CapEff for pid {pid}")


def _has_cap(value: int, cap: int) -> bool:
    return bool(value & (1 << cap))


def _start_manager(repo: Path, python: Path, config: Path, log_path: Path) -> tuple[subprocess.Popen[str], Any]:
    env = dict(os.environ)
    pythonpath = str(repo / "software/python")
    env["PYTHONPATH"] = pythonpath + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONUNBUFFERED"] = "1"
    handle = log_path.open("w", encoding="utf-8")
    process = subprocess.Popen(
        [str(python), "-m", "plasma_manager.server", "--config", str(config)],
        cwd=repo,
        env=env,
        stdout=handle,
        stderr=subprocess.STDOUT,
        text=True,
        start_new_session=True,
    )
    return process, handle


def _stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
        process.wait(timeout=3)


def _fleet_ready(payload: Mapping[str, Any]) -> bool:
    ppus = payload.get("ppus")
    if not isinstance(ppus, list) or len(ppus) != 2:
        return False
    aliases = {item.get("alias"): item for item in ppus if isinstance(item, dict)}
    for alias, expected_id in (("ppu-a", PPU_A_ID), ("ppu-b", PPU_B_ID)):
        item = aliases.get(alias)
        if not isinstance(item, dict):
            return False
        ppu = item.get("ppu")
        if (
            item.get("gateway_live") is not True
            or item.get("execution_ready") is not True
            or item.get("contract_compatible") is not True
            or item.get("identity_conflict") is not False
            or item.get("errors")
            or not isinstance(ppu, dict)
            or ppu.get("ppu_id") != expected_id
        ):
            return False
    return True


def _registry_endpoint(payload: Mapping[str, Any], alias: str) -> str | None:
    entries = payload.get("ppus")
    if not isinstance(entries, list):
        return None
    for entry in entries:
        if isinstance(entry, dict) and entry.get("alias") == alias:
            endpoint = entry.get("endpoint")
            return endpoint if isinstance(endpoint, str) else None
    return None


def _runtime_from_args(repo: Path, args: argparse.Namespace, phase2: Any, python: Path, work: Path, git_sha: str) -> tuple[Path, str | None]:
    if args.runtime_dir is not None:
        runtime = args.runtime_dir.resolve()
        if not (runtime / "ppu/ppu.pyz").is_file():
            raise LabError(f"runtime missing ppu/ppu.pyz: {runtime}")
        _run([str(python), "scripts/ppu-runtime.py", "validate", str(runtime)], cwd=repo)
        return runtime, None
    build_work = work / "runtime-build"
    build_work.mkdir()
    version = phase2._product_version(repo)
    runtime, archive, _release_sha = phase2._build_release(repo, build_work, python, git_sha, version)
    return runtime, archive.name


def _prepare_work(work: Path, name: str, ppu_id: str) -> Path:
    path = work / name
    path.mkdir(parents=True)
    for directory in (path / "server-output", path / "gateway-output", path / "logs"):
        directory.mkdir()
        directory.chmod(0o777)
    path.chmod(0o777)
    _write_ppu_config(path, ppu_id=ppu_id)
    return path


def _start_virtual_ppu(
    *,
    phase2: Any,
    runtime: Path,
    phase2_script: Path,
    network: str,
    ppu_name: str,
    helper_name: str,
    work: Path,
    control_ip: str,
    managed_ip: str,
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
        phase2.ARM_IMAGE,
        "python3", "/acceptance.py",
        "--helper", "--helper-socket", "/work/network-helper.sock",
        "--managed-initial-address", managed_ip, "--managed-prefix", "24",
    ])
    deadline = time.monotonic() + 10
    socket_path = work / "network-helper.sock"
    while time.monotonic() < deadline and not socket_path.exists():
        time.sleep(0.05)
    if not socket_path.exists():
        raise LabError(f"network helper socket did not appear for {ppu_name}")
    if _has_cap(phase2._cap_eff(ppu_name), CAP_NET_ADMIN):
        raise LabError(f"{ppu_name} Gateway unexpectedly has CAP_NET_ADMIN")
    if not _has_cap(phase2._cap_eff(helper_name), CAP_NET_ADMIN):
        raise LabError(f"{helper_name} is missing CAP_NET_ADMIN")


def _main(args: argparse.Namespace) -> int:
    if platform.system() != "Linux":
        raise LabError("Virtual PPU Network Lab requires a Linux host with direct Docker bridge routing")
    if shutil.which("docker") is None or shutil.which("ip") is None:
        raise LabError("docker and iproute2 are required")

    repo = _repo_root()
    phase2 = _phase2_module(repo)
    python = phase2._host_python(repo)
    git_sha = _git_sha(repo)
    work = (repo / args.work_dir).resolve() if not args.work_dir.is_absolute() else args.work_dir.resolve()
    report = (repo / args.report).resolve() if not args.report.is_absolute() else args.report.resolve()
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)
    report.parent.mkdir(parents=True, exist_ok=True)

    phase2._docker_preflight()
    runtime, release_artifact = _runtime_from_args(repo, args, phase2, python, work, git_sha)

    ppu_a_work = _prepare_work(work, "ppu-a", PPU_A_ID)
    ppu_b_work = _prepare_work(work, "ppu-b", PPU_B_ID)
    manager_port = _free_port()
    manager_config = work / "manager.yaml"
    registry_state = work / "manager-ppu-registry.json"
    _write_manager_config(manager_config, port=manager_port, registry_state=registry_state)

    suffix = f"{os.getpid()}-{int(time.time())}"
    network = f"plasma-virtual-net-{suffix}"
    ppu_a = f"plasma-vppu-a-{suffix}"
    helper_a = f"plasma-vppu-a-helper-{suffix}"
    ppu_b = f"plasma-vppu-b-{suffix}"
    helper_b = f"plasma-vppu-b-helper-{suffix}"
    phase2_script = repo / "scripts/ppu-network-phase2-acceptance.py"
    manager: subprocess.Popen[str] | None = None
    manager_log = None
    checks: dict[str, str] = {}
    uplink = _host_uplink_interface()
    uplink_before = _host_interface_signature(uplink)

    try:
        phase2._run(["docker", "network", "create", "--subnet", LAB_SUBNET, "--gateway", LAB_GATEWAY, network])
        checks["isolated_network"] = "PASS"

        _start_virtual_ppu(
            phase2=phase2, runtime=runtime, phase2_script=phase2_script, network=network,
            ppu_name=ppu_a, helper_name=helper_a, work=ppu_a_work,
            control_ip=PPU_A_CONTROL_IP, managed_ip=PPU_A_INITIAL_IP,
        )
        _start_virtual_ppu(
            phase2=phase2, runtime=runtime, phase2_script=phase2_script, network=network,
            ppu_name=ppu_b, helper_name=helper_b, work=ppu_b_work,
            control_ip=PPU_B_CONTROL_IP, managed_ip=PPU_B_INITIAL_IP,
        )
        checks["gateway_no_net_admin"] = "PASS"
        checks["helper_has_net_admin"] = "PASS"

        node_a = _wait_json(
            f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}/api/node",
            lambda payload: _ppu_id(payload) == PPU_A_ID,
            label="Virtual PPU A initial endpoint",
        )
        node_b = _wait_json(
            f"http://{PPU_B_INITIAL_IP}:{PPU_PORT}/api/node",
            lambda payload: _ppu_id(payload) == PPU_B_ID,
            label="Virtual PPU B initial endpoint",
        )
        if _ppu_id(node_a) == _ppu_id(node_b):
            raise LabError("Virtual PPU identities are not unique")
        checks["two_distinct_ppu_identities"] = "PASS"
        checks["old_endpoint_reachable"] = "PASS"

        manager, manager_log = _start_manager(repo, python, manager_config, work / "manager.log")
        if _has_cap(_cap_eff(manager.pid), CAP_NET_ADMIN):
            raise LabError("Plasma Manager unexpectedly has CAP_NET_ADMIN")
        checks["manager_no_net_admin"] = "PASS"

        manager_base = f"http://127.0.0.1:{manager_port}"
        _wait_json(
            f"{manager_base}/api/health/live",
            lambda payload: payload.get("ok") is True and payload.get("manager") == "alive",
            label="Plasma Manager liveness",
        )
        fleet = _wait_json(
            f"{manager_base}/api/fleet",
            _fleet_ready,
            timeout_s=20,
            label="trusted two-PPU Manager fleet observation",
        )
        if not _fleet_ready(fleet):
            raise LabError("Manager fleet observation is not trusted")
        checks["manager_trusted_fleet"] = "PASS"

        _, registry_before = _http_json(f"{manager_base}/api/registry")
        old_endpoint = f"http://{PPU_A_INITIAL_IP}:{PPU_PORT}"
        candidate_endpoint = f"http://{PPU_A_CANDIDATE_IP}:{PPU_PORT}"
        if _registry_endpoint(registry_before, "ppu-a") != old_endpoint:
            raise LabError("Manager registry does not point ppu-a at the old endpoint")
        if _registry_endpoint(registry_before, "ppu-b") != f"http://{PPU_B_INITIAL_IP}:{PPU_PORT}":
            raise LabError("Manager registry ppu-b foundation entry is incorrect")
        checks["registry_old_endpoint"] = "PASS"

        desired = {
            "mode": "static",
            "address": PPU_A_CANDIDATE_IP,
            "prefix_length": 24,
            "gateway": LAB_GATEWAY,
            "dns_servers": [LAB_GATEWAY],
        }
        status, commissioned = _http_json(
            f"{manager_base}/api/registry/ppu-a/network-commissioning",
            method="POST",
            body={"desired": desired, "rollback_timeout_s": ROLLBACK_TIMEOUT_S},
            headers={"Idempotency-Key": f"virtual-network-lab-{git_sha[:12]}"},
            timeout_s=ROLLBACK_TIMEOUT_S + 8,
        )
        if status != 200:
            raise LabError(f"Manager commissioning failed: HTTP {status}: {commissioned!r}")
        record = commissioned.get("commissioning")
        if not isinstance(record, dict) or record.get("state") != "completed":
            raise LabError(f"Manager commissioning did not complete: {record!r}")
        if record.get("old_endpoint") != old_endpoint or record.get("candidate_endpoint") != candidate_endpoint:
            raise LabError("Manager commissioning endpoint evidence is incorrect")
        if record.get("ppu_id") != PPU_A_ID:
            raise LabError("Manager commissioning did not preserve immutable ppu_id")
        checks["manager_commissioning_completed"] = "PASS"
        checks["same_ppu_id_verified"] = "PASS"

        candidate_node = _wait_json(
            f"{candidate_endpoint}/api/node",
            lambda payload: _ppu_id(payload) == PPU_A_ID,
            label="Virtual PPU A candidate endpoint",
        )
        if _ppu_id(candidate_node) != PPU_A_ID:
            raise LabError("candidate endpoint identity mismatch")
        _wait_unreachable(f"{old_endpoint}/api/node")
        checks["real_endpoint_migration"] = "PASS"
        checks["old_endpoint_removed"] = "PASS"

        activation_status, activation_payload = _http_json(
            f"{candidate_endpoint}/api/settings/ppu-network/activation"
        )
        activation = activation_payload.get("activation")
        if activation_status != 200 or not isinstance(activation, dict) or activation.get("state") != "committed":
            raise LabError(f"PPU activation is not committed: {activation_payload!r}")
        checks["ppu_activation_committed"] = "PASS"

        _, registry_after = _http_json(f"{manager_base}/api/registry")
        if _registry_endpoint(registry_after, "ppu-a") != candidate_endpoint:
            raise LabError("Manager registry compare-and-swap did not adopt the candidate endpoint")
        if _registry_endpoint(registry_after, "ppu-b") != f"http://{PPU_B_INITIAL_IP}:{PPU_PORT}":
            raise LabError("unrelated ppu-b registry entry changed")
        checks["registry_compare_and_swap"] = "PASS"

        journal_status, journal_payload = _http_json(
            f"{manager_base}/api/registry/ppu-a/network-commissioning"
        )
        journal = journal_payload.get("commissioning")
        if journal_status != 200 or not isinstance(journal, dict) or journal.get("state") != "completed":
            raise LabError(f"Manager commissioning journal is not completed: {journal_payload!r}")
        journal_path = registry_state.with_name(f"{registry_state.stem}-network-commissioning.json")
        if not journal_path.is_file():
            raise LabError("Manager network commissioning journal was not persisted")
        persisted = json.loads(journal_path.read_text(encoding="utf-8"))
        persisted_record = ((persisted.get("transactions") or {}).get("ppu-a") if isinstance(persisted, dict) else None)
        if not isinstance(persisted_record, dict) or persisted_record.get("state") != "completed":
            raise LabError("durable Manager commissioning journal does not record completed")
        checks["durable_manager_journal"] = "PASS"

        if _host_interface_signature(uplink) != uplink_before:
            raise LabError(f"host uplink {uplink} changed during isolated network commissioning")
        checks["host_uplink_untouched"] = "PASS"

        result = {
            "overall_result": "PASS",
            "evidence_level": "linux-host-real-manager-qemu-armv7-isolated-network",
            "git_sha": git_sha,
            "release_artifact": release_artifact,
            "manager": {
                "host": "127.0.0.1",
                "port": manager_port,
                "cap_net_admin": False,
                "commissioning_state": record["state"],
            },
            "virtual_ppus": {
                "ppu-a": {
                    "ppu_id": PPU_A_ID,
                    "old_endpoint": old_endpoint,
                    "candidate_endpoint": candidate_endpoint,
                },
                "ppu-b": {
                    "ppu_id": PPU_B_ID,
                    "endpoint": f"http://{PPU_B_INITIAL_IP}:{PPU_PORT}",
                    "purpose": "fault-injection-foundation",
                },
            },
            "checks": checks,
            "privilege_separation": {
                "manager_cap_net_admin": False,
                "gateway_cap_net_admin": False,
                "helper_cap_net_admin": True,
            },
            "host_uplink": uplink,
            "not_claimed": [
                "PYNQ-Z2 hardware",
                "final PYNQ-Z2 Linux network-manager backend",
                "DHCP endpoint migration",
                "DNS mutation",
                "default-route mutation",
                "boot-time network persistence",
                "static IPv4 fault injection",
                "PS-to-PL",
                "Site I/O",
                "real IC programming",
            ],
        }
        report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        _print_summary(result, report)
        return 0
    finally:
        _stop_process(manager)
        if manager_log is not None and not manager_log.closed:
            manager_log.close()
        for name in (helper_b, ppu_b, helper_a, ppu_a):
            phase2._docker_rm(name)
        phase2._docker_network_rm(network)


def _print_summary(result: Mapping[str, Any], report: Path) -> None:
    print("=" * 76)
    print("Plasma Virtual PPU Network Lab")
    print("=" * 76)
    print(f"Git SHA                     : {result['git_sha']}")
    print(f"Evidence level              : {result['evidence_level']}")
    for name, value in result["checks"].items():
        print(f"[{value}] {name.replace('_', ' ').title()}")
    print("-" * 76)
    print("REAL MANAGER COMMISSIONING  : PASS")
    print("REAL ENDPOINT MIGRATION      : PASS")
    print("REGISTRY CAS + JOURNAL       : PASS")
    print("HOST UPLINK UNTOUCHED        : PASS")
    print("Z2 NETWORK BACKEND CLAIM     : NONE")
    print("OVERALL RESULT               : PASS")
    print("-" * 76)
    print(f"JSON report                  : {report}")
    print("=" * 76)
    print(RESULT_MARKER + json.dumps(dict(result), sort_keys=True))


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Plasma Virtual PPU Network Lab acceptance")
    parser.add_argument("--work-dir", type=Path, default=DEFAULT_WORK_REL)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT_REL)
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=None,
        help="Reuse an already validated PPU runtime instead of building a release",
    )
    args = parser.parse_args(argv)
    try:
        return _main(args)
    except (
        LabError,
        OSError,
        subprocess.SubprocessError,
        json.JSONDecodeError,
        KeyError,
        ValueError,
        urllib.error.URLError,
    ) as exc:
        print(f"virtual-ppu-network-lab: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

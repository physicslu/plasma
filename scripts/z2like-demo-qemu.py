#!/usr/bin/env python3
"""Operate the canonical ``z2like-demo`` scenario on the SWPC simulation host.

SWPC remains the single Plasma simulation environment.  This script gives the
``z2like-demo`` website exactly one PPU backend: a persistent QEMU ARMv7
simulated Z2 on a private Docker bridge.

The public website terminates only on the dedicated Control Station Console/BFF
(:18390).  Manager (:18380), QEMU Gateway (:18080) and QEMU Bootstrap (:18081)
remain private.  Existing ``swpc-z2like`` host ports 18080/18081/18082 are not
reused or widened; that x86_64 profile remains an engineering surrogate.
"""

from __future__ import annotations

import argparse
import ipaddress
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Mapping, Sequence

ARM_IMAGE = "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c"
BINFMT_IMAGE = "docker.io/tonistiigi/binfmt@sha256:400a4873b838d1b89194d982c45e5fb3cda4593fbfd7e08a02e76b03b21166f0"
TARGET_MARKER = "PLASMA_Z2LIKE_DEMO_QEMU_TARGET"
CONTAINER = "plasma-z2like-demo-qemu"
NETWORK = "plasma-z2like-demo"
DEFAULT_SUBNET = "172.30.77.0/24"
DEFAULT_PPU_IP = "172.30.77.2"
DEFAULT_ALIAS = "z2like-qemu"
MANAGER_PORT = 18380
CONSOLE_PORT = 18390
BOOTSTRAP_PORT = 18081
GATEWAY_PORT = 18080
UNIT_MARKER = "# Managed by Plasma z2like-demo QEMU scenario"
VOLUMES = {
    "product": "plasma-z2like-demo-product",
    "config": "plasma-z2like-demo-config",
    "bootstrap": "plasma-z2like-demo-bootstrap",
    "runtime": "plasma-z2like-demo-runtime",
    "logs": "plasma-z2like-demo-logs",
}


class DemoError(RuntimeError):
    pass


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _run(
    argv: Sequence[str],
    *,
    capture: bool = False,
    check: bool = True,
    timeout: float | None = None,
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        list(argv),
        check=check,
        text=True,
        capture_output=capture,
        timeout=timeout,
    )


def _docker(*args: str, capture: bool = False, check: bool = True, timeout: float | None = None):
    return _run(["docker", *args], capture=capture, check=check, timeout=timeout)


def _require_command(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise DemoError(f"required command is unavailable: {name}")
    return path


def _validate_topology(subnet_text: str, ppu_ip_text: str) -> tuple[str, str]:
    try:
        subnet = ipaddress.ip_network(subnet_text, strict=True)
        ppu_ip = ipaddress.ip_address(ppu_ip_text)
    except ValueError as exc:
        raise DemoError(f"invalid QEMU Docker network configuration: {exc}") from exc
    if subnet.version != 4 or ppu_ip.version != 4 or ppu_ip not in subnet:
        raise DemoError("QEMU PPU IPv4 must belong to the configured IPv4 subnet")
    if ppu_ip in {subnet.network_address, subnet.broadcast_address}:
        raise DemoError("QEMU PPU IPv4 cannot be network/broadcast address")
    return str(subnet), str(ppu_ip)


def _require_clean_committed_source(repo: Path) -> None:
    if not (repo / ".git").is_dir():
        raise DemoError(f"repository metadata is missing: {repo}")
    changes = _run(
        ["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=normal"],
        capture=True,
    ).stdout.strip()
    if changes:
        raise DemoError("repository must be clean before activating the persistent z2like-demo target")


def _docker_preflight() -> None:
    _require_command("docker")
    probe = [
        "run",
        "--rm",
        "--platform",
        "linux/arm/v7",
        ARM_IMAGE,
        "python3",
        "-c",
        "import platform; print(platform.machine())",
    ]
    result = _docker(*probe, capture=True, check=False, timeout=60)
    if result.returncode != 0:
        _docker("run", "--privileged", "--rm", BINFMT_IMAGE, "--install", "arm", timeout=60)
        result = _docker(*probe, capture=True, check=False, timeout=60)
    machine = result.stdout.strip().lower()
    if result.returncode != 0 or machine not in {"armv7", "armv7l"}:
        raise DemoError(
            "ARMv7 QEMU/binfmt preflight failed; z2like-demo backend cannot be started safely"
        )


def _network_exists() -> bool:
    return _docker("network", "inspect", NETWORK, capture=True, check=False).returncode == 0


def _ensure_network(subnet: str) -> None:
    if not _network_exists():
        _docker("network", "create", "--driver", "bridge", "--subnet", subnet, NETWORK)
        return
    payload = json.loads(_docker("network", "inspect", NETWORK, capture=True).stdout)
    try:
        observed = payload[0]["IPAM"]["Config"][0]["Subnet"]
    except (IndexError, KeyError, TypeError) as exc:
        raise DemoError("existing z2like-demo Docker network has unreadable IPAM configuration") from exc
    if str(ipaddress.ip_network(observed, strict=True)) != subnet:
        raise DemoError(
            f"existing Docker network {NETWORK} uses {observed}, expected {subnet}; refusing implicit replacement"
        )


def _ensure_volumes() -> None:
    existing = set(_docker("volume", "ls", "--format", "{{.Name}}", capture=True).stdout.splitlines())
    for volume in VOLUMES.values():
        if volume not in existing:
            _docker("volume", "create", volume, capture=True)


def _container_inspect() -> dict[str, Any] | None:
    result = _docker("inspect", CONTAINER, capture=True, check=False)
    if result.returncode != 0:
        return None
    payload = json.loads(result.stdout)
    if not isinstance(payload, list) or len(payload) != 1 or not isinstance(payload[0], dict):
        raise DemoError("Docker returned invalid container inspection data")
    return payload[0]


def _start_container(repo: Path, ppu_ip: str, subnet: str) -> None:
    _docker_preflight()
    _ensure_network(subnet)
    _ensure_volumes()
    current = _container_inspect()
    if current is not None:
        networks = ((current.get("NetworkSettings") or {}).get("Networks") or {})
        current_ip = ((networks.get(NETWORK) or {}).get("IPAddress"))
        if current_ip != ppu_ip:
            raise DemoError(
                f"existing {CONTAINER} has private IP {current_ip!r}, expected {ppu_ip}; refusing implicit replacement"
            )
        bindings = ((current.get("HostConfig") or {}).get("PortBindings")) or {}
        if bindings:
            raise DemoError("existing z2like-demo QEMU container publishes host ports; fail closed")
        if not ((current.get("State") or {}).get("Running")):
            _docker("start", CONTAINER)
        return

    scripts = repo / "scripts"
    argv = [
        "run",
        "-d",
        "--name",
        CONTAINER,
        "--restart",
        "unless-stopped",
        "--platform",
        "linux/arm/v7",
        "--network",
        NETWORK,
        "--ip",
        ppu_ip,
        "--env",
        f"{TARGET_MARKER}=1",
        "--volume",
        f"{scripts}:/sim:ro",
        "--volume",
        f"{VOLUMES['product']}:/opt/plasma",
        "--volume",
        f"{VOLUMES['config']}:/etc/plasma",
        "--volume",
        f"{VOLUMES['bootstrap']}:/var/lib/plasma-bootstrap",
        "--volume",
        f"{VOLUMES['runtime']}:/var/lib/plasma",
        "--volume",
        f"{VOLUMES['logs']}:/var/log/plasma",
        ARM_IMAGE,
        "python3",
        "/sim/z2like-demo-qemu-target.py",
    ]
    _docker(*argv, capture=True)


def _request_json(
    url: str,
    *,
    method: str = "GET",
    body: Mapping[str, Any] | None = None,
    timeout_s: float = 3.0,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(dict(body)).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(request, timeout=timeout_s) as response:
            raw = response.read()
            status = int(response.status)
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        status = int(exc.code)
    except (OSError, urllib.error.URLError) as exc:
        raise DemoError(f"request failed for {url}: {exc}") from exc
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DemoError(f"non-JSON response from {url}: HTTP {status}") from exc
    if not isinstance(payload, dict):
        raise DemoError(f"non-object JSON response from {url}: HTTP {status}")
    return status, payload


def _wait_json(url: str, predicate, timeout_s: float = 30.0) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_s
    last = "no response"
    while time.monotonic() < deadline:
        try:
            status, payload = _request_json(url, timeout_s=2.0)
            if status == 200 and predicate(payload):
                return payload
            last = f"HTTP {status}: {payload!r}"
        except DemoError as exc:
            last = str(exc)
        time.sleep(0.2)
    raise DemoError(f"readiness deadline exceeded for {url}: {last}")


def _wait_http(url: str, timeout_s: float = 30.0) -> None:
    deadline = time.monotonic() + timeout_s
    last = "no response"
    while time.monotonic() < deadline:
        request = urllib.request.Request(url, method="GET")
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        try:
            with opener.open(request, timeout=2.0) as response:
                if 200 <= int(response.status) < 400:
                    return
                last = f"HTTP {response.status}"
        except (OSError, urllib.error.URLError) as exc:
            last = str(exc)
        time.sleep(0.2)
    raise DemoError(f"HTTP readiness deadline exceeded for {url}: {last}")


def _xdg_paths() -> dict[str, Path]:
    home = Path.home()
    config_home = Path(os.environ.get("XDG_CONFIG_HOME", home / ".config")).expanduser().resolve()
    state_home = Path(os.environ.get("XDG_STATE_HOME", home / ".local/state")).expanduser().resolve()
    data_home = Path(os.environ.get("XDG_DATA_HOME", home / ".local/share")).expanduser().resolve()
    return {
        "config_home": config_home,
        "state_home": state_home,
        "data_home": data_home,
        "scenario_config": config_home / "plasma/z2like-demo",
        "scenario_state": state_home / "plasma/z2like-demo",
        "control_station_current": data_home / "plasma/local-control-station/current",
        "unit_dir": config_home / "systemd/user",
    }


def _require_control_station_runtime(paths: Mapping[str, Path]) -> tuple[Path, Path, Path]:
    current = paths["control_station_current"]
    if not current.is_symlink():
        raise DemoError(
            "local-control-station runtime is not installed; deploy the current merged Control Station before z2like-demo"
        )
    release = current.resolve(strict=True)
    python = release / "venv/bin/python"
    web_server = release / "web/server.js"
    if not python.is_file() or not os.access(python, os.X_OK) or not web_server.is_file():
        raise DemoError(f"local-control-station active release is incomplete: {release}")
    probe = _run(
        [str(python), "-c", "import plasma_manager.bootstrap_server"],
        capture=True,
        check=False,
        timeout=10,
    )
    if probe.returncode != 0:
        raise DemoError(
            "active local-control-station release predates Bootstrap Manager composition; redeploy current main first"
        )
    node = Path(_require_command("node"))
    return python, web_server, node


def _write_manager_config(paths: Mapping[str, Path], ppu_ip: str) -> Path:
    config_root = paths["scenario_config"]
    state_root = paths["scenario_state"]
    config_root.mkdir(parents=True, exist_ok=True)
    state_root.mkdir(parents=True, exist_ok=True)
    manager_config = config_root / "manager.yaml"
    observation_db = state_root / "manager-observations.sqlite3"
    registry_state = state_root / "manager-registry.json"
    text = (
        "manager:\n"
        '  host: "127.0.0.1"\n'
        f"  port: {MANAGER_PORT}\n"
        "  request_timeout_s: 10.0\n"
        "  poll_interval_s: 1.0\n"
        f"  observation_db_path: {json.dumps(str(observation_db))}\n"
        f"  registry_state_path: {json.dumps(str(registry_state))}\n"
        "ppus: []\n"
    )
    manager_config.write_text(text, encoding="utf-8")
    manager_config.chmod(0o600)
    return manager_config


def _write_user_units(
    paths: Mapping[str, Path],
    *,
    python: Path,
    web_server: Path,
    node: Path,
    manager_config: Path,
    alias: str,
) -> tuple[Path, Path]:
    unit_dir = paths["unit_dir"]
    state_root = paths["scenario_state"]
    unit_dir.mkdir(parents=True, exist_ok=True)
    manager_unit = unit_dir / "plasma-z2like-demo-manager.service"
    console_unit = unit_dir / "plasma-z2like-demo-console.service"
    manager_unit.write_text(
        "\n".join(
            [
                UNIT_MARKER,
                "[Unit]",
                "Description=Plasma z2like-demo Manager",
                "After=network-online.target",
                "Wants=network-online.target",
                "",
                "[Service]",
                "Type=simple",
                f"WorkingDirectory={state_root}",
                "Environment=PYTHONUNBUFFERED=1",
                f"ExecStart={python} -m plasma_manager.bootstrap_server --config {manager_config}",
                "Restart=on-failure",
                "RestartSec=3",
                "NoNewPrivileges=true",
                "PrivateTmp=true",
                "",
                "[Install]",
                "WantedBy=default.target",
                "",
            ]
        ),
        encoding="utf-8",
    )
    console_unit.write_text(
        "\n".join(
            [
                UNIT_MARKER,
                "[Unit]",
                "Description=Plasma z2like-demo Console/BFF",
                "After=network-online.target plasma-z2like-demo-manager.service",
                "Wants=network-online.target plasma-z2like-demo-manager.service",
                "",
                "[Service]",
                "Type=simple",
                f"WorkingDirectory={web_server.parent}",
                "Environment=HOST=127.0.0.1",
                f"Environment=PORT={CONSOLE_PORT}",
                "Environment=PLASMA_FLEET_UI_ENABLED=1",
                "Environment=PLASMA_CONTROL_STATION_MODE=managed",
                f"Environment=PLASMA_MANAGER_API_URL=http://127.0.0.1:{MANAGER_PORT}",
                f"Environment=PLASMA_MANAGER_PPU_ALIAS={alias}",
                f"ExecStart={node} {web_server}",
                "Restart=on-failure",
                "RestartSec=3",
                "NoNewPrivileges=true",
                "PrivateTmp=true",
                "",
                "[Install]",
                "WantedBy=default.target",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return manager_unit, console_unit


def _systemctl_user(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return _run(["systemctl", "--user", *args], capture=True, check=check, timeout=30)


def _ensure_registry(alias: str, ppu_ip: str) -> None:
    manager = f"http://127.0.0.1:{MANAGER_PORT}"
    status, payload = _request_json(f"{manager}/api/registry")
    if status != 200:
        raise DemoError(f"Manager registry read failed: HTTP {status} {payload!r}")
    ppus = payload.get("ppus")
    if not isinstance(ppus, list):
        raise DemoError("Manager registry response omitted ppus list")
    matches = [entry for entry in ppus if isinstance(entry, dict) and entry.get("alias") == alias]
    endpoint = f"http://{ppu_ip}:{GATEWAY_PORT}"
    if not matches:
        status, created = _request_json(
            f"{manager}/api/registry",
            method="POST",
            body={"alias": alias, "endpoint": endpoint},
        )
        if status != 201:
            raise DemoError(f"cannot register QEMU PPU: HTTP {status} {created!r}")
        return
    if len(matches) != 1 or matches[0].get("endpoint") != endpoint:
        raise DemoError(
            "persisted z2like-demo registry alias does not match the canonical QEMU endpoint; refusing implicit mutation"
        )


def _configure_control_station(alias: str, ppu_ip: str) -> None:
    _require_command("systemctl")
    paths = _xdg_paths()
    python, web_server, node = _require_control_station_runtime(paths)
    manager_config = _write_manager_config(paths, ppu_ip)
    manager_unit, console_unit = _write_user_units(
        paths,
        python=python,
        web_server=web_server,
        node=node,
        manager_config=manager_config,
        alias=alias,
    )
    _systemctl_user("daemon-reload")
    _systemctl_user("enable", "plasma-z2like-demo-manager.service", "plasma-z2like-demo-console.service")
    _systemctl_user("restart", "plasma-z2like-demo-manager.service")
    _wait_json(
        f"http://127.0.0.1:{MANAGER_PORT}/api/health/live",
        lambda payload: payload.get("ok") is True,
    )
    _ensure_registry(alias, ppu_ip)
    _systemctl_user("restart", "plasma-z2like-demo-console.service")
    _wait_http(f"http://127.0.0.1:{CONSOLE_PORT}/")
    for unit in (manager_unit, console_unit):
        first = unit.read_text(encoding="utf-8").splitlines()[0]
        if first != UNIT_MARKER:
            raise DemoError(f"z2like-demo unit ownership marker is missing: {unit}")


def _verify(alias: str, ppu_ip: str) -> dict[str, Any]:
    current = _container_inspect()
    if current is None or not ((current.get("State") or {}).get("Running")):
        raise DemoError("z2like-demo QEMU container is not running")
    bindings = ((current.get("HostConfig") or {}).get("PortBindings")) or {}
    if bindings:
        raise DemoError("z2like-demo QEMU target must not publish host ports")
    machine = _docker("exec", CONTAINER, "uname", "-m", capture=True).stdout.strip().lower()
    if machine not in {"armv7", "armv7l"}:
        raise DemoError(f"QEMU target is not executing as ARMv7: {machine}")
    bootstrap = _wait_json(
        f"http://{ppu_ip}:{BOOTSTRAP_PORT}/v1/status",
        lambda payload: payload.get("bootstrap", {}).get("state") == "bootstrap_ready",
    )
    manager = f"http://127.0.0.1:{MANAGER_PORT}"
    _wait_json(f"{manager}/api/health/live", lambda payload: payload.get("ok") is True)
    status, registry = _request_json(f"{manager}/api/registry")
    if status != 200:
        raise DemoError(f"Manager registry read failed: HTTP {status}")
    expected_endpoint = f"http://{ppu_ip}:{GATEWAY_PORT}"
    matches = [
        item
        for item in registry.get("ppus", [])
        if isinstance(item, dict) and item.get("alias") == alias and item.get("endpoint") == expected_endpoint
    ]
    if len(matches) != 1:
        raise DemoError("z2like-demo Manager registry is not bound to the canonical QEMU PPU")
    _wait_http(f"http://127.0.0.1:{CONSOLE_PORT}/")
    runtime = bootstrap.get("runtime") if isinstance(bootstrap.get("runtime"), dict) else {}
    runtime_state = runtime.get("state")
    if runtime_state == "runtime_active":
        _wait_json(
            f"http://{ppu_ip}:{GATEWAY_PORT}/api/health/ready",
            lambda payload: payload.get("ok") is True
            and payload.get("gateway") == "alive"
            and payload.get("execution") == "ready",
        )
    elif runtime_state != "runtime_absent":
        raise DemoError(f"QEMU Bootstrap reports unsafe runtime state: {runtime_state!r}")
    return {
        "result": "PASS",
        "simulation_environment": "SWPC",
        "canonical_backend": "QEMU ARMv7 simulated Z2",
        "architecture": machine,
        "ppu_alias": alias,
        "gateway_endpoint": expected_endpoint,
        "bootstrap_endpoint": f"http://{ppu_ip}:{BOOTSTRAP_PORT}",
        "runtime_state": runtime_state,
        "console_origin": f"http://127.0.0.1:{CONSOLE_PORT}",
        "manager_origin": manager,
        "host_ports_published_by_qemu": False,
        "engineering_surrogate": "swpc-z2like remains separate",
        "not_claimed": [
            "PYNQ-Z2 hardware",
            "Plasma-owned Python installation",
            "systemd/DAC on Z2",
            "real Z2 reboot persistence",
            "PS-to-PL",
            "Site electrical I/O",
            "target power",
            "real IC programming",
        ],
    }


def _status(alias: str, ppu_ip: str) -> int:
    current = _container_inspect()
    running = bool(current and ((current.get("State") or {}).get("Running")))
    print(f"Simulation environment: SWPC")
    print(f"Scenario:               z2like-demo")
    print(f"Canonical PPU backend:  QEMU ARMv7 simulated Z2")
    print(f"Container:              {CONTAINER} ({'running' if running else 'stopped/not-created'})")
    print(f"PPU alias:              {alias}")
    print(f"Private Gateway:        http://{ppu_ip}:{GATEWAY_PORT}")
    print(f"Private Bootstrap:      http://{ppu_ip}:{BOOTSTRAP_PORT}")
    print(f"Console origin:         http://127.0.0.1:{CONSOLE_PORT}")
    print(f"Manager origin:         http://127.0.0.1:{MANAGER_PORT}")
    print("swpc-z2like:            engineering surrogate only")
    return 0 if running else 1


def _token() -> int:
    current = _container_inspect()
    if current is None or not ((current.get("State") or {}).get("Running")):
        raise DemoError("z2like-demo QEMU container is not running")
    result = _docker(
        "exec",
        CONTAINER,
        "cat",
        "/var/lib/plasma-bootstrap/control-token",
        capture=True,
    )
    token = result.stdout.strip()
    if not 32 <= len(token) <= 256 or any(ch.isspace() for ch in token):
        raise DemoError("Bootstrap pairing token in the QEMU target is invalid")
    print(token)
    return 0


def _down() -> int:
    # Preserve all durable QEMU/Manager state.  This is a stop, not a reset.
    for unit in ("plasma-z2like-demo-console.service", "plasma-z2like-demo-manager.service"):
        _systemctl_user("stop", unit, check=False)
    current = _container_inspect()
    if current is not None and ((current.get("State") or {}).get("Running")):
        _docker("stop", CONTAINER, timeout=30)
    print("z2like-demo stopped; persistent volumes, registry, credentials and units were preserved")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SWPC canonical z2like-demo QEMU ARMv7 scenario")
    parser.add_argument(
        "--subnet",
        default=os.environ.get("PLASMA_Z2LIKE_DEMO_SUBNET", DEFAULT_SUBNET),
        help=f"private Docker subnet (default {DEFAULT_SUBNET})",
    )
    parser.add_argument(
        "--ppu-ip",
        default=os.environ.get("PLASMA_Z2LIKE_DEMO_PPU_IP", DEFAULT_PPU_IP),
        help=f"private QEMU PPU IPv4 (default {DEFAULT_PPU_IP})",
    )
    parser.add_argument(
        "--alias",
        default=os.environ.get("PLASMA_Z2LIKE_DEMO_PPU_ALIAS", DEFAULT_ALIAS),
        help=f"Manager PPU alias (default {DEFAULT_ALIAS})",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("up", "configure-control-station", "activate", "verify", "status", "token", "down"):
        sub.add_parser(command)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        subnet, ppu_ip = _validate_topology(args.subnet, args.ppu_ip)
        alias = args.alias.strip()
        if not alias or len(alias) > 128 or "/" in alias or "\\" in alias:
            raise DemoError("PPU alias must be 1-128 characters without path separators")
        repo = _repo_root()
        if args.command in {"up", "activate"}:
            _require_clean_committed_source(repo)
            _start_container(repo, ppu_ip, subnet)
            _wait_json(
                f"http://{ppu_ip}:{BOOTSTRAP_PORT}/v1/health",
                lambda payload: payload.get("ok") is True
                and payload.get("service") == "plasma-ppu-bootstrap",
            )
        if args.command in {"configure-control-station", "activate"}:
            _configure_control_station(alias, ppu_ip)
        if args.command == "activate":
            print(json.dumps(_verify(alias, ppu_ip), indent=2, sort_keys=True))
            print(
                "Cloudflare boundary: route the operator-managed z2like-demo hostname only to "
                f"http://127.0.0.1:{CONSOLE_PORT}; never expose QEMU :18080/:18081 directly"
            )
            return 0
        if args.command == "verify":
            print(json.dumps(_verify(alias, ppu_ip), indent=2, sort_keys=True))
            return 0
        if args.command == "status":
            return _status(alias, ppu_ip)
        if args.command == "token":
            return _token()
        if args.command == "down":
            return _down()
        if args.command == "up":
            print(f"QEMU ARMv7 target ready; private Bootstrap=http://{ppu_ip}:{BOOTSTRAP_PORT}")
            return 0
        if args.command == "configure-control-station":
            print(f"z2like-demo Control Station ready at http://127.0.0.1:{CONSOLE_PORT}")
            return 0
        raise AssertionError("unreachable command")
    except (DemoError, OSError, subprocess.SubprocessError, json.JSONDecodeError) as exc:
        print(f"z2like-demo-qemu: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

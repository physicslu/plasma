"""Built-in Mock PPU: one product launcher for the Mock PPU stack.

A Mock PPU is the SAME three-process PPU as a Z2 (D1): the Plasma Runtime
with Mock Sites, the real PPU Bootstrap service (enrollment, B1/B2/B3, the
G13 controller admission socket) and the real Plasma Gateway. The Manager
reaches it through the same PPU boundary as a Physical PPU; nothing here is
a Manager, Scheduler or Batch engine, and the Mock Driver stays inside the
Runtime.

``serve`` provisions a private device root (stable identity across
restarts), starts the three processes, registers and enrolls the PPU with
the Manager through its existing registry and ticket-enrollment routes, and
supervises them. It needs no Git checkout: only this installed package and
the PPU control-plane scripts (``--control-plane``).
"""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import signal
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

import yaml

from . import mock_resources

DEFAULT_ALIAS = "mock-ppu-01"
DEFAULT_SITES = 8
# A dedicated loopback address: the Manager reaches a PPU Bootstrap at the
# fixed ``<gateway host>:18081``, so a Mock PPU never shares a host with a
# PPU (or the Control Station's own loopback services).
DEFAULT_HOST = "127.0.80.1"
DEFAULT_GATEWAY_PORT = 18080
DEFAULT_SERVER_PORT = 18082
BOOTSTRAP_PORT = 18081

# The built-in Mock Programming Route (committed under data/opf/
# programming-routes). A real ICPN so the Catalog IC selection can name it;
# its Mock Driver ABI maps to Site interface "mock", so it never qualifies on
# a physical Site, and the Manager resolves it only for a Mock Batch.
ROUTE_ICPN = "STM32F103C8T6"
FLASH_BASE = 0x08000000
FLASH_SIZE = 1024 * 1024
ERASE_GRANULARITY = 1024
MOCK_RELEASE_SHA = "0" * 39 + "1"
B3_INSTALL_POLICY = {
    "schema": "plasma.ppu.b3-install-policy.v2",
    "mode": "development",
    "modes": ["activate", "stage_only"],
    "actions": ["install", "verify"],
}
MAX_UNIX_SOCKET_PATH = 107
ENROLLMENT_LABEL = "built-in-mock-ppu"


class MockPPUError(RuntimeError):
    pass


class EnrollmentTicketRejected(MockPPUError):
    """The PPU refused the armed ticket (e.g. its window expired). The ticket
    is discarded and the launcher exits, so a restart arms a fresh one."""


def route_document() -> dict[str, Any]:
    """The built-in Mock Route file document (single source of its bytes)."""
    return mock_resources.mock_route_document(
        icpn=ROUTE_ICPN, flash_base=FLASH_BASE, flash_size=FLASH_SIZE,
        erase_granularity=ERASE_GRANULARITY)


@dataclass(frozen=True)
class MockPPUSpec:
    root: Path
    control_plane: Path
    alias: str = DEFAULT_ALIAS
    sites: int = DEFAULT_SITES
    host: str = DEFAULT_HOST
    gateway_port: int = DEFAULT_GATEWAY_PORT
    server_port: int = DEFAULT_SERVER_PORT
    ppu_id: str | None = None
    gateway_args: tuple[str, ...] = field(default=())
    #: Where the Runtime control and G13 admission sockets live (AF_UNIX
    #: paths are short): the systemd RuntimeDirectory, else the device root.
    socket_dir: Path | None = None

    @property
    def device_id(self) -> str:
        return self.ppu_id or self.alias

    @property
    def gateway_url(self) -> str:
        return f"http://{self.host}:{self.gateway_port}"

    @property
    def bootstrap_url(self) -> str:
        return f"http://{self.host}:{BOOTSTRAP_PORT}"

    def paths(self) -> dict[str, Path]:
        root = self.root
        sockets = self.socket_dir or root
        paths = {
            "root": root,
            "config": root / "ppu.yaml",
            "product": root / "product",
            "state": root / "state",
            "runtime_dir": sockets / "rt",
            "runtime_socket": sockets / "rt" / "control.sock",
            "admission_socket": sockets / "adm.sock",
            "machine_id": root / "machine-id",
            "package_target": root / "ppu-package-target.json",
            "install_policy": root / "ppu-bundle-install-policy.json",
            "ticket": root / "enrollment-ticket",
            "lock": root / "launcher.lock",
            "output": root / f"{self.device_id}-output",
        }
        for key in ("runtime_socket", "admission_socket"):
            if len(str(paths[key])) > MAX_UNIX_SOCKET_PATH:
                raise MockPPUError(f"Unix socket path too long for AF_UNIX: {paths[key]}")
        return paths


def _write_private_json(path: Path, payload: Mapping[str, Any]) -> None:
    partial = path.with_name(path.name + ".part")
    fd = os.open(partial, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, sort_keys=True) + "\n")
    os.replace(partial, path)


def runtime_config(spec: MockPPUSpec) -> dict[str, Any]:
    work = spec.root
    sites = [
        {
            "id": site_id, "enabled": True, "interface": "mock", "target": ROUTE_ICPN,
            "operation_timeout_s": 30.0, "max_retries": 0, "retry_backoff_s": 0.01,
            "mock": {"flash_base": FLASH_BASE, "flash_size": FLASH_SIZE,
                     "erase_granularity": ERASE_GRANULARITY, "default_delay_s": 0.01,
                     "progress_steps": 2},
        }
        for site_id in range(1, spec.sites + 1)
    ]
    return {
        "ppu": {"id": spec.device_id, "facility_id": "mock-facility", "model": "MOCK-PPU",
                "display_name": spec.device_id},
        "server": {
            "host": spec.host, "port": spec.server_port,
            "max_supported_sites": spec.sites, "max_concurrent_jobs": spec.sites,
            "max_queue_depth_per_site": 4,
            "output_root": str(work / f"{spec.device_id}-output"),
            "log_root": str(work / f"{spec.device_id}-logs"),
            "max_metadata_bytes": 65536, "max_map_bytes": 1048576,
            "max_binary_bytes": 67108864,
        },
        "sites": sites,
    }


def provision(spec: MockPPUSpec) -> dict[str, Path]:
    """The files a factory provisions on a PPU, under the Mock's private root.

    Idempotent: the machine identity and Bootstrap state survive restarts, so
    the Mock PPU keeps one device identity and its Manager enrollment.
    """
    if not 1 <= spec.sites <= 64:
        raise MockPPUError("a Mock PPU has 1 to 64 Sites")
    paths = spec.paths()
    paths["root"].mkdir(mode=0o700, parents=True, exist_ok=True)
    paths["root"].chmod(0o700)
    paths["runtime_dir"].mkdir(mode=0o700, parents=True, exist_ok=True)
    paths["runtime_dir"].chmod(0o700)
    paths["config"].write_text(yaml.safe_dump(runtime_config(spec), sort_keys=False),
                               encoding="utf-8")
    if not paths["machine_id"].is_file():
        paths["machine_id"].write_text(os.urandom(16).hex() + "\n", encoding="utf-8")
    # Owner-provisioned target identity: platform "mock" is what classifies
    # this device as a Mock PPU for the Manager (M2) and what alone permits
    # its self-armed Engineering enrollment ticket.
    _write_private_json(paths["package_target"], mock_resources.MOCK_PLATFORM)
    _write_private_json(paths["install_policy"], B3_INSTALL_POLICY)
    release = paths["product"] / "releases" / f"0.2.1-{MOCK_RELEASE_SHA[:12]}"
    release.mkdir(parents=True, exist_ok=True)
    (release / "release.json").write_text(json.dumps({
        "role": "ppu", "target": "linux-armv7l", "product_version": "0.2.1",
        "git_sha": MOCK_RELEASE_SHA}) + "\n", encoding="utf-8")
    current = paths["product"] / "current"
    if not current.is_symlink():
        current.symlink_to(release)
    for stale in (paths["runtime_socket"], paths["admission_socket"]):
        if stale.is_socket():
            stale.unlink()
    return paths


def runtime_command(spec: MockPPUSpec) -> list[str]:
    paths = spec.paths()
    return [
        sys.executable, "-m", "plasma_server.runtime_server",
        "--config", str(paths["config"]),
        "--runtime-control-socket", str(paths["runtime_socket"]),
        "--mock-asset-set-product-root", str(paths["product"]),
        "--mock-asset-set-control-plane", str(spec.control_plane),
    ]


def bootstrap_command(spec: MockPPUSpec) -> list[str]:
    paths, plane = spec.paths(), spec.control_plane
    return [
        sys.executable, str(plane / "ppu-bootstrap-service.py"),
        "--product-root", str(paths["product"]),
        "--state-root", str(paths["state"]),
        "--machine-id", str(paths["machine_id"]),
        "--package-target-file", str(paths["package_target"]),
        "--bundle-install-policy", str(paths["install_policy"]),
        "--deployment-engine-script", str(plane / "ppu-bootstrap-deployment.py"),
        "--z2-installer-script", str(plane / "ppu-z2-installer.py"),
        "--button-profile", str(paths["root"] / "no-button-profile.json"),
        "--admission-socket", str(paths["admission_socket"]),
        "--seal-dir", str(paths["root"] / "seals"),
        # U10 D2: B3 borrows the Job-admission lease from THIS Mock Runtime.
        "--runtime-control-socket", str(paths["runtime_socket"]),
        "--reload-fence", str(paths["root"] / "mmio.lock"),
        "--site-recovery-script", str(paths["root"] / "absent-site-recovery.py"),
        "--gateway-port", str(spec.gateway_port),
        "serve", "--host", spec.host, "--port", str(BOOTSTRAP_PORT),
        "--mock-enrollment-ticket-file", str(paths["ticket"]),
    ]


def gateway_command(spec: MockPPUSpec) -> list[str]:
    paths = spec.paths()
    # Read downloads are served from the same Job output directory the
    # Runtime writes. Every write is bound to the PPU controller (G13).
    return [
        sys.executable, "-m", "plasma_web.gateway_phase3",
        "--host", spec.host, "--port", str(spec.gateway_port),
        "--plasma-host", spec.host, "--plasma-port", str(spec.server_port),
        "--output-root", str(paths["output"]),
        "--ppu-config", str(paths["config"]),
        "--controller-admission-socket", str(paths["admission_socket"]),
        *spec.gateway_args,
    ]


# -- HTTP ----------------------------------------------------------------

def _request(method: str, url: str, body: Mapping[str, Any] | None = None, *,
             timeout: float = 10.0) -> tuple[int, dict[str, Any]]:
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    try:
        with urlopen(Request(url, data=data, method=method, headers=headers),
                     timeout=timeout) as response:
            payload = json.load(response)
            status = int(response.status)
    except HTTPError as exc:
        try:
            payload = json.loads(exc.read() or b"{}")
        except ValueError:
            payload = {}
        status = int(exc.code)
    return status, payload if isinstance(payload, dict) else {}


def _wait(predicate: Callable[[], bool], *, label: str, timeout_s: float,
          alive: Callable[[], None] = lambda: None) -> None:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        alive()
        try:
            if predicate():
                return
        except (URLError, OSError, ValueError):
            pass
        time.sleep(0.1)
    raise MockPPUError(f"timeout waiting for {label}")


def gateway_ready(spec: MockPPUSpec) -> bool:
    status, payload = _request("GET", f"{spec.gateway_url}/api/health/ready", timeout=3.0)
    return status == 200 and payload.get("ok") is True and payload.get("execution") == "ready"


# -- Manager registration (existing registry + ticket enrollment routes) ---

def enrollment_state(spec: MockPPUSpec, manager_url: str) -> dict[str, Any]:
    alias = quote(spec.alias, safe="")
    status, payload = _request("GET", f"{manager_url}/api/registry/{alias}/bootstrap",
                               timeout=15.0)
    if status != 200:
        return {}
    pairing = payload.get("pairing")
    return pairing if isinstance(pairing, dict) else {}


def register_with_manager(spec: MockPPUSpec, manager_url: str) -> str:
    """Register, commission and enroll this Mock PPU; idempotent.

    Returns ``ENROLLED`` when the Manager holds a credential proven by this
    device, ``ALREADY_ENROLLED`` when nothing had to change. Refuses an alias
    the Manager already maps to another endpoint (a Physical PPU keeps it).
    """
    manager_url = manager_url.rstrip("/")
    status, registry = _request("GET", f"{manager_url}/api/registry")
    if status != 200:
        raise MockPPUError(f"Manager registry unavailable: HTTP {status}")
    entries = registry.get("registry", registry).get("ppus") or []
    entry = next((e for e in entries if isinstance(e, dict) and e.get("alias") == spec.alias),
                 None)
    if entry is None:
        status, payload = _request("POST", f"{manager_url}/api/registry",
                                   {"alias": spec.alias, "endpoint": spec.gateway_url})
        if status != 201:
            raise MockPPUError(f"Manager refused the Mock PPU registration: HTTP {status} "
                               f"{payload.get('error')}")
        entry = payload.get("entry") or {}
    elif entry.get("endpoint", "").rstrip("/") != spec.gateway_url:
        raise MockPPUError(f"Manager alias {spec.alias} belongs to another endpoint; "
                           "refusing to take it over")
    alias = quote(spec.alias, safe="")
    if entry.get("lifecycle") != "commissioned":
        status, payload = _request("PATCH", f"{manager_url}/api/registry/{alias}",
                                   {"lifecycle": "commissioned"})
        if status != 200:
            raise MockPPUError(f"Manager refused to commission the Mock PPU: HTTP {status} "
                               f"{payload.get('error')}")
    pairing = enrollment_state(spec, manager_url)
    if pairing.get("paired") and pairing.get("device_authenticated"):
        return "ALREADY_ENROLLED"
    ticket_path = spec.paths()["ticket"]
    if not ticket_path.is_file():
        raise MockPPUError("Mock PPU is enrolled to another controller, or no enrollment "
                           "ticket is armed; reset the Mock PPU root to re-enroll")
    ticket = ticket_path.read_text(encoding="utf-8").strip()
    status, payload = _request(
        "POST", f"{manager_url}/api/registry/{alias}/bootstrap/enrollment",
        {"entry": "ticket", "ticket": ticket, "label": ENROLLMENT_LABEL}, timeout=60.0)
    if status == 409 and payload.get("ok") is False:   # the PPU refused the claim
        ticket_path.unlink(missing_ok=True)
        raise EnrollmentTicketRejected(f"Mock PPU refused its enrollment ticket: {payload.get('state')}")
    if status != 200 or payload.get("ok") is not True:
        raise MockPPUError(f"Mock PPU enrollment failed: HTTP {status} {payload.get('state')}")
    ticket_path.unlink(missing_ok=True)
    return "ENROLLED"


# -- process supervision -----------------------------------------------------

class Stack:
    """The three Mock PPU processes, started in dependency order.

    One launcher owns a device root at a time (an exclusive lock held for its
    whole life), so a second start can never re-provision, unlink the sockets
    of, or double-register a running Mock PPU.
    """

    def __init__(self, spec: MockPPUSpec, *, log_dir: Path | None = None) -> None:
        self.spec = spec
        self.log_dir = log_dir
        self.processes: list[tuple[str, subprocess.Popen[bytes]]] = []
        self._lock_fd: int | None = None

    def _acquire_root(self) -> None:
        root = self.spec.root
        root.mkdir(mode=0o700, parents=True, exist_ok=True)
        fd = os.open(self.spec.paths()["lock"], os.O_RDWR | os.O_CREAT | os.O_NOFOLLOW, 0o600)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            os.close(fd)
            raise MockPPUError(f"another launcher already runs this Mock PPU ({root})") from None
        self._lock_fd = fd

    def _spawn(self, name: str, command: list[str]) -> None:
        output: Any = None
        if self.log_dir is not None:
            self.log_dir.mkdir(parents=True, exist_ok=True)
            output = (self.log_dir / f"{self.spec.alias}-{name}.log").open("ab")
        env = dict(os.environ, PYTHONUNBUFFERED="1")
        process = subprocess.Popen(command, env=env, stdout=output,
                                   stderr=subprocess.STDOUT if output else None,
                                   start_new_session=True)
        if output is not None:
            output.close()
        self.processes.append((name, process))
        print(f"[mock-ppu] {self.spec.alias} {name} pid={process.pid}", flush=True)

    def assert_alive(self) -> None:
        dead = [(name, p.returncode) for name, p in self.processes if p.poll() is not None]
        if dead:
            raise MockPPUError(f"Mock PPU process exited: {dead}")

    def start(self, *, timeout_s: float = 60.0) -> None:
        self._acquire_root()
        paths = provision(self.spec)
        self._spawn("runtime", runtime_command(self.spec))
        # The Runtime control socket exists before the Bootstrap starts, so
        # the controller enrolls in NORMAL (not RECOVERY_ONLY) mode.
        _wait(paths["runtime_socket"].exists, label="Runtime control socket",
              timeout_s=timeout_s, alive=self.assert_alive)
        self._spawn("bootstrap", bootstrap_command(self.spec))
        _wait(paths["admission_socket"].exists, label="Bootstrap admission socket",
              timeout_s=timeout_s, alive=self.assert_alive)
        self._spawn("gateway", gateway_command(self.spec))
        _wait(lambda: gateway_ready(self.spec), label="Gateway ready",
              timeout_s=timeout_s, alive=self.assert_alive)

    def stop(self, timeout_s: float = 10.0) -> None:
        for _name, process in reversed(self.processes):
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        deadline = time.monotonic() + timeout_s
        for _name, process in reversed(self.processes):
            while process.poll() is None and time.monotonic() < deadline:
                time.sleep(0.05)
            if process.poll() is None:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                process.wait()
        self.processes.clear()
        if self._lock_fd is not None:
            os.close(self._lock_fd)
            self._lock_fd = None


def serve(spec: MockPPUSpec, manager_url: str | None, *, log_dir: Path | None = None,
          register_timeout_s: float | None = None) -> int:
    stopping = False

    def request_stop(_signum: int, _frame: object) -> None:
        nonlocal stopping
        stopping = True

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)
    stack = Stack(spec, log_dir=log_dir)
    try:
        stack.start()
        print(f"[mock-ppu] {spec.alias} ready: {spec.sites} Sites at {spec.gateway_url}",
              flush=True)
        registered = manager_url is None
        deadline = (None if register_timeout_s is None
                    else time.monotonic() + register_timeout_s)
        last_error = ""
        while not stopping:
            stack.assert_alive()
            if not registered:
                try:
                    result = register_with_manager(spec, manager_url)
                except EnrollmentTicketRejected:
                    raise
                except (MockPPUError, URLError, OSError) as exc:
                    if str(exc) != last_error:
                        print(f"[mock-ppu] {spec.alias} registration pending: {exc}",
                              flush=True)
                        last_error = str(exc)
                    if deadline is not None and time.monotonic() > deadline:
                        raise MockPPUError(f"registration did not complete: {exc}") from exc
                else:
                    registered = True
                    print(f"[mock-ppu] {spec.alias} Manager registration: {result}", flush=True)
            time.sleep(0.5 if registered else 2.0)
        return 0
    except MockPPUError as exc:
        print(f"[mock-ppu] {spec.alias} FAILED: {exc}", file=sys.stderr, flush=True)
        return 1
    finally:
        stack.stop()
        print(f"[mock-ppu] {spec.alias} stopped", flush=True)


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m plasma_server.mock_ppu",
                                     description="Built-in Mock PPU")
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("serve", help="provision, start, register and supervise one Mock PPU")
    run.add_argument("--root", type=Path, required=True, help="private Mock PPU device root")
    run.add_argument("--control-plane", type=Path, required=True,
                     help="directory holding the PPU Bootstrap control-plane scripts")
    run.add_argument("--alias", default=DEFAULT_ALIAS)
    run.add_argument("--ppu-id", default=None)
    run.add_argument("--sites", type=int, default=DEFAULT_SITES)
    run.add_argument("--host", default=DEFAULT_HOST)
    run.add_argument("--gateway-port", type=int, default=DEFAULT_GATEWAY_PORT)
    run.add_argument("--server-port", type=int, default=DEFAULT_SERVER_PORT)
    run.add_argument("--manager-url", default=None,
                     help="register and enroll with this Manager (omit: no registration)")
    run.add_argument("--register-timeout-s", type=float, default=None)
    run.add_argument("--socket-dir", type=Path, default=None,
                     help="private directory for the AF_UNIX sockets (default: --root)")
    run.add_argument("--log-dir", type=Path, default=None)
    run.add_argument("--gateway-arg", action="append", default=[],
                     help="extra Gateway argument (repeatable)")
    route = sub.add_parser("route", help="print the built-in Mock Route document")
    route.set_defaults(command="route")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    if args.command == "route":
        print(json.dumps(route_document(), indent=2, sort_keys=True))
        return 0
    spec = MockPPUSpec(
        root=args.root.resolve(), control_plane=args.control_plane.resolve(),
        alias=args.alias, sites=args.sites, host=args.host,
        gateway_port=args.gateway_port, server_port=args.server_port,
        ppu_id=args.ppu_id, gateway_args=tuple(args.gateway_arg),
        socket_dir=None if args.socket_dir is None else args.socket_dir.resolve())
    return serve(spec, args.manager_url, log_dir=args.log_dir,
                 register_timeout_s=args.register_timeout_s)


if __name__ == "__main__":
    raise SystemExit(main())

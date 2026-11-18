"""Shared Host-only lab for the LOM-P2A-2 P0 Runtime readiness / reconciliation tests.

Real Bootstrap HTTP service (controller engine + admission Unix socket), a
Gateway composed with the real ``ControllerWriteAdmissionMixin`` in front of the
real Phase 3 route predicates (health + PS loopback echo handlers only), the real
Manager coordinator / ``PPUHttpClient`` signer, and a Runtime execution-lease
socket. Only 127.0.0.1 and temporary directories are used.
"""
from __future__ import annotations

import importlib.util
import json
import os
import socketserver
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from http.server import ThreadingHTTPServer
from pathlib import Path
from typing import Any

from plasma_manager.bootstrap import BootstrapCredentialStore, BootstrapHttpClient
from plasma_manager.client import PPUHttpClient
from plasma_manager.config import PPURegistryEntry
from plasma_manager.registry import PPURegistryStore
from plasma_manager.verified_bootstrap import VerifiedManagerBootstrapCoordinator
from plasma_web import gateway_phase3
from plasma_web.controller_admission import ControllerWriteAdmissionMixin

ROOT = Path(__file__).resolve().parents[3]
LOOPBACK = "/api/engineering/diagnostics/loopback"
RELEASE_ID = "0.2.1-7e90f95bceb6"
ARTIFACT_SHA = "6f2506a6814df6f27d3dcf6735ff715d6597ce8b763e104509694cceefda9a92"
API_TX = "370e51bc99fa43329e974ee43a8fd319"


def load_script(name: str, file_name: str):
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file_name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


service = load_script("lom_p0_lab_service", "ppu-bootstrap-service.py")
bootstrap_base = load_script("lom_p0_lab_base", "ppu-bootstrap.py")


class GatewayRoutes(gateway_phase3.Phase3RouteHandler):
    """Real Phase 3 predicates; health and PS loopback echo stand in for the Runtime."""

    ready: dict[str, Any] = {"gateway": "alive", "execution": "ready"}
    loopbacks: list[dict[str, Any]] = []
    corrupt_echo = False

    def log_message(self, fmt: str, *args: object) -> None:  # quiet
        pass

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/api/health/ready":
            self._json(200, dict(type(self).ready))
            return
        self._json(404, {"ok": False, "error": {"code": "not_found"}})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length", "0"))
        raw = self._raw_body() if length else b""
        if self.path != LOOPBACK:
            self._json(202, {"ok": True})
            return
        body = json.loads(raw)
        type(self).loopbacks.append(body)
        rx = "00000000" if type(self).corrupt_echo else body["tx_crc32"]
        self._json(200, {
            "ok": True, "diagnostic_protocol_version": "1",
            "loopback": {"endpoint": "ps", "source": "ps", "test_id": body["test_id"],
                         "sequence": body["sequence"], "transform": "echo",
                         "pattern": body["pattern"], "payload_length": body["payload_length"],
                         "tx_crc32": body["tx_crc32"], "rx_crc32": rx},
            "payload_base64": body["payload_base64"],
        })


class G13Gateway(ControllerWriteAdmissionMixin, GatewayRoutes):
    pass


class HostLabGateway(ControllerWriteAdmissionMixin, GatewayRoutes):
    """An unauthenticated host-lab Gateway: must never pass a Z2 readiness check."""


class _LeaseHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        self.rfile.readline(65536)
        busy = self.server.busy  # type: ignore[attr-defined]
        self.wfile.write(json.dumps({"ok": True, "result": {"busy": busy}}).encode() + b"\n")


class LeaseServer(socketserver.ThreadingMixIn, socketserver.UnixStreamServer):
    daemon_threads = True
    busy = False


@dataclass
class Lab:
    tmp: Path
    paths: Any
    ppu: Any = None
    gateway: Any = None
    lease: Any = None
    threads: list[threading.Thread] = field(default_factory=list)

    # -- PPU state ------------------------------------------------------------
    def seed_runtime_failure(self, *, activated_ago_s: float = 30.0) -> dict[str, Any]:
        """The exact on-device shape of the 2026-11-09 Z2 failure."""
        product, state = self.paths.product_root, self.paths.state_root
        release = product / "releases" / RELEASE_ID
        release.mkdir(parents=True, exist_ok=True)
        (product / "releases" / "0.2.1-a1b1c6f3b142").mkdir(parents=True, exist_ok=True)
        current = product / "current"
        if current.is_symlink() or current.exists():
            current.unlink()
        current.symlink_to(release)
        (product / "install").mkdir(parents=True, exist_ok=True)
        (product / "install" / "last-install.json").write_text(json.dumps({
            "result": "PASS", "release_id": RELEASE_ID, "archive_sha256": ARTIFACT_SHA,
            "gateway_host": "127.0.0.1", "current": str(current)}), encoding="utf-8")
        state.mkdir(parents=True, exist_ok=True)
        journal = {
            "schema_version": 1, "transaction_id": str(uuid.uuid4()), "sequence": 8,
            "state": "runtime_active", "kind": "ppu-runtime", "api_transaction_id": API_TX,
            "release_id": RELEASE_ID, "artifact_sha256": ARTIFACT_SHA,
            "previous_release": str(product / "releases" / "0.2.1-a1b1c6f3b142"),
            "started_at_epoch_s": time.time() - activated_ago_s - 20,
            "updated_at_epoch_s": time.time() - activated_ago_s,
        }
        self.write_private(state / "deployment.json", journal)
        record = {
            "schema_version": 1, "transaction_id": API_TX, "upload_id": "6b820ce1488449dfa75311bad5b11f85",
            "state": "recovery_required", "error_code": "coordinator_result_unreconciled",
            "error": "deployment engine failed with exit 2: ... curl: (22) ... 401 ... "
                     "Z2 local PS loopback request failed",
            "result": None, "started_at_epoch_s": journal["started_at_epoch_s"],
            "updated_at_epoch_s": journal["updated_at_epoch_s"] + 5,
        }
        self.write_private(state / "deployment-api.json", record)
        return journal

    @staticmethod
    def write_private(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.chmod(path, 0o600)

    def journal(self) -> dict[str, Any]:
        return json.loads((self.paths.state_root / "deployment.json").read_text())

    def api_record(self) -> dict[str, Any]:
        return json.loads((self.paths.state_root / "deployment-api.json").read_text())

    def state_bytes(self) -> dict[str, bytes]:
        out = {}
        for name in ("deployment.json", "deployment-api.json"):
            out[name] = (self.paths.state_root / name).read_bytes()
        root = self.paths.state_root / "deployment-reconciliations"
        out["reconciliations"] = b"".join(sorted(p.read_bytes() for p in root.glob("*"))) if root.exists() else b""
        return out

    # -- services -------------------------------------------------------------
    def start_ppu(self) -> Any:
        self.ppu = service.BootstrapHTTPServer(("127.0.0.1", 0), paths=self.paths,
                                               base_module=bootstrap_base)
        self.ppu.start_controller_services()
        thread = threading.Thread(target=self.ppu.serve_forever, daemon=True)
        thread.start()
        self.threads.append(thread)
        return self.ppu

    def stop_ppu(self) -> None:
        if self.ppu is not None:
            self.ppu.shutdown()
            self.ppu.server_close()
            self.ppu = None

    def restart_ppu(self) -> Any:
        self.stop_ppu()
        return self.start_ppu()

    def manager(self, name: str):
        registry = PPURegistryStore(
            (PPURegistryEntry(endpoint=f"http://127.0.0.1:{self.gateway.server_port}", alias="z2"),),
            self.tmp / f"{name}-registry.json")
        store = BootstrapCredentialStore(self.tmp / f"{name}-bootstrap-credentials.json")
        lab = self

        def factory(_endpoint, timeout_s):
            return BootstrapHttpClient(f"http://127.0.0.1:{lab.ppu.server_port}", timeout_s)

        return store, VerifiedManagerBootstrapCoordinator(registry, store, 5.0, client_factory=factory)

    def enroll(self, coordinator, label: str = "cs") -> dict[str, Any]:
        ticket = self.ppu.engine.engineering_arm(self.ppu.controller_module.boot_clock(), authorized=True)
        result = coordinator.enrollment("z2", {"entry": "ticket", "ticket": ticket, "label": label})
        assert result["ok"] is True, result
        return result

    def gateway_client(self, coordinator) -> PPUHttpClient:
        client = PPUHttpClient(f"http://127.0.0.1:{self.gateway.server_port}", 5.0)
        client.write_signer = coordinator.gateway_signer("z2")
        return client

    def gateway_url(self) -> str:
        return f"http://127.0.0.1:{self.gateway.server_port}"

    def bootstrap_url(self) -> str:
        return f"http://127.0.0.1:{self.ppu.server_port}"


def make_lab(tmp_path: Path, *, gateway_cls=G13Gateway, host_lab: bool = False) -> Lab:
    machine_id = tmp_path / "machine-id"
    machine_id.write_text("0123456789abcdef0123456789abcdef\n", encoding="utf-8")
    lease_path = tmp_path / "control.sock"
    lease = LeaseServer(str(lease_path), _LeaseHandler)
    lease.busy = False
    GatewayRoutes.ready = {"gateway": "alive", "execution": "ready"}
    GatewayRoutes.loopbacks = []
    GatewayRoutes.corrupt_echo = False
    gateway_cls.configure_controller_admission(
        socket_path=None if host_lab else tmp_path / "adm.sock",
        host_lab_unauthenticated_writes=host_lab)
    gateway = ThreadingHTTPServer(("127.0.0.1", 0), gateway_cls)
    paths = service.ServicePaths(
        product_root=tmp_path / "product", state_root=tmp_path / "state",
        machine_id_path=machine_id,
        bootstrap_script=ROOT / "scripts" / "ppu-bootstrap.py",
        kit_tool=ROOT / "scripts" / "ppu-bootstrap-kit.py",
        admission_socket=tmp_path / "adm.sock",
        seal_dir=tmp_path / "seals", runtime_control_socket=lease_path,
        reload_fence=tmp_path / "mmio.lock", button_profile=tmp_path / "no-profile.json",
        site_recovery_script=tmp_path / "absent-recovery.py",
        gateway_port=gateway.server_port,
    )
    lab = Lab(tmp=tmp_path, paths=paths, gateway=gateway, lease=lease)
    for server in (lease, gateway):
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        lab.threads.append(thread)
    return lab


def close_lab(lab: Lab) -> None:
    lab.stop_ppu()
    for server in (lab.gateway, lab.lease):
        server.shutdown()
        server.server_close()
    for cls in (G13Gateway, HostLabGateway):
        cls.controller_admission_socket = None
        cls.host_lab_unauthenticated_writes = False

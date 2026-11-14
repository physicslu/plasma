"""LOM-P2A-2 G13 + enrollment, end to end on loopback (Host-only).

Real Bootstrap HTTP service (controller engine, enrollment endpoints, admission
Unix socket), a Gateway handler composed with the real ``ControllerWriteAdmission
Mixin`` in front of the real Phase 3 route predicates, and the real Manager
coordinator / ``PPUHttpClient`` signer. No Z2, FPGA, DUT, GPIO or network
beyond 127.0.0.1.
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import re
import sys
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from plasma_manager import bootstrap_request_auth as manager_auth
from plasma_manager.bootstrap import (
    BootstrapCredentialError,
    BootstrapCredentialStore,
    ControllerReplacedError,
)
from plasma_manager.client import PPUHttpClient
from plasma_manager.config import PPURegistryEntry
from plasma_manager.registry import PPURegistryStore
from plasma_manager.server import _MANAGED_POST_PATTERNS
from plasma_manager.verified_bootstrap import VerifiedManagerBootstrapCoordinator
from plasma_web import gateway_phase3
from plasma_web.controller_admission import ControllerWriteAdmissionMixin

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / file_name)
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


service = _load("lom_p2a2_g13_service", "ppu-bootstrap-service.py")
bootstrap_base = _load("lom_p2a2_g13_base", "ppu-bootstrap.py")
JOB = {"site_id": 2, "operation": "flash_cycle"}


class _Routes(gateway_phase3.Phase3RouteHandler):
    """Real Phase 3 route predicates; dispatch replaced by a recorder."""

    recorded: list[tuple[str, bytes]] = []
    hold_jobs = threading.Event()
    release_jobs = threading.Event()
    job_entered = threading.Event()

    def do_POST(self) -> None:  # noqa: N802
        path = self.path
        raw = self._raw_body() if int(self.headers.get("Content-Length", "0")) else b""
        if path == "/api/jobs" and self.hold_jobs.is_set():
            self.job_entered.set()
            self.release_jobs.wait(5)
        type(self).recorded.append((path, raw))
        self._json(202, {"ok": True, "job": {"job_id": f"job-{len(self.recorded)}"}})


class _Gateway(ControllerWriteAdmissionMixin, _Routes):
    pass


@pytest.fixture
def lab(tmp_path: Path):
    machine_id = tmp_path / "machine-id"
    machine_id.write_text("0123456789abcdef0123456789abcdef\n", encoding="utf-8")
    paths = service.ServicePaths(
        product_root=tmp_path / "product", state_root=tmp_path / "state",
        machine_id_path=machine_id,
        bootstrap_script=ROOT / "scripts" / "ppu-bootstrap.py",
        kit_tool=ROOT / "scripts" / "ppu-bootstrap-kit.py",
        admission_socket=tmp_path / "adm.sock",
        seal_dir=tmp_path / "seals", runtime_control_socket=tmp_path / "control.sock",
        reload_fence=tmp_path / "mmio.lock", button_profile=tmp_path / "no-profile.json",
        site_recovery_script=tmp_path / "absent-recovery.py",
    )
    ppu = service.BootstrapHTTPServer(("127.0.0.1", 0), paths=paths, base_module=bootstrap_base)
    ppu.start_controller_services()
    _Routes.recorded = []
    _Routes.hold_jobs.clear()
    _Routes.release_jobs.clear()
    _Routes.job_entered.clear()
    _Gateway.configure_controller_admission(socket_path=paths.admission_socket,
                                            host_lab_unauthenticated_writes=False)
    gateway = ThreadingHTTPServer(("127.0.0.1", 0), _Gateway)
    threads = [threading.Thread(target=s.serve_forever, daemon=True) for s in (ppu, gateway)]
    [t.start() for t in threads]
    try:
        yield ppu, gateway, paths, tmp_path
    finally:
        for server in (gateway, ppu):
            server.shutdown()
            server.server_close()
        _Gateway.controller_admission_socket = None


def _manager(tmp_path: Path, ppu, gateway, name: str):
    registry = PPURegistryStore(
        (PPURegistryEntry(endpoint=f"http://127.0.0.1:{gateway.server_port}", alias="z2"),),
        tmp_path / f"{name}-registry.json")
    store = BootstrapCredentialStore(tmp_path / f"{name}-bootstrap-credentials.json")
    from plasma_manager.bootstrap import BootstrapHttpClient

    def factory(_endpoint, timeout_s):
        return BootstrapHttpClient(f"http://127.0.0.1:{ppu.server_port}", timeout_s)

    return store, VerifiedManagerBootstrapCoordinator(registry, store, 5.0, client_factory=factory)


def _ticket(ppu) -> str:
    controller = ppu.controller_module
    return ppu.engine.engineering_arm(controller.boot_clock(), authorized=True)


def _gateway_client(coordinator, gateway) -> PPUHttpClient:
    client = PPUHttpClient(f"http://127.0.0.1:{gateway.server_port}", 5.0)
    client.write_signer = coordinator.gateway_signer("z2")
    return client


def _post(client, path, body=JOB):
    return client.relay("POST", path, headers={"Content-Type": "application/json"},
                        body=json.dumps(body).encode(), timeout_s=10.0, max_response_bytes=65536)


def _raw(gateway, method, path, body=None, headers=None):
    conn = HTTPConnection("127.0.0.1", gateway.server_port, timeout=10)
    conn.request(method, path, body=body, headers=headers or {})
    response = conn.getresponse()
    payload = response.read()
    conn.close()
    is_json = (response.getheader("Content-Type") or "").startswith("application/json")
    return response.status, json.loads(payload) if payload and is_json else None


# --- enrollment through the real Manager and Bootstrap HTTP -----------------------

def test_engineering_ticket_enrollment_then_signed_gateway_write(lab):
    ppu, gateway, _paths, tmp_path = lab
    store, coordinator = _manager(tmp_path, ppu, gateway, "a")
    result = coordinator.enrollment("z2", {"entry": "ticket", "ticket": _ticket(ppu), "label": "cs-a"})
    assert result["ok"] and result["state"] == "ENROLLED"
    assert (result["controller_generation"], result["enrollment_source"]) == (1, "engineering-cli")
    assert result["pairing"]["device_authenticated"] is True
    record = store.record_for("z2")
    assert record.generation == 1 and record.controller_id
    status, headers, body = _post(_gateway_client(coordinator, gateway), "/api/jobs")
    assert status == 202 and json.loads(body)["ok"] is True
    assert manager_auth.RESPONSE_HEADER in headers                       # proven by the PPU
    assert _Routes.recorded == [("/api/jobs", json.dumps(JOB).encode())]


def test_button_enrollment_binds_the_requesting_manager(lab):
    ppu, gateway, _paths, tmp_path = lab
    ppu.engine.button_enabled = True
    _store, coordinator = _manager(tmp_path, ppu, gateway, "b")
    started = coordinator.enrollment("z2", {"entry": "button"})
    assert started["state"] == "AWAITING_BUTTON"
    early = coordinator.enrollment("z2", {"entry": "button", "step": "claim"})
    assert early["ok"] is False and early["state"] == "ENROLLMENT_NOT_ARMED"
    _rival_store, rival = _manager(tmp_path, ppu, gateway, "rival")
    contended = rival.enrollment("z2", {"entry": "button"})
    assert contended["ok"] is False and contended["state"] == "ENROLLMENT_CONTENDED"
    assert ppu.engine.button_pressed(ppu.controller_module.boot_clock()) == "BUTTON_PRESS_REFUSED_CONTENDED"
    # A clean window: a single request, then the physical press.
    ppu.engine._button = {"requests": {}, "deadline": None, "contended": False}
    coordinator.enrollment("z2", {"entry": "button"})
    assert ppu.engine.button_pressed(ppu.controller_module.boot_clock()) == "ENROLLMENT_ARMED:ps-gpio-button"
    with pytest.raises(BootstrapCredentialError, match="not bound to this Control Station"):
        rival._button_keys["z2"] = coordinator._button_keys["z2"][:1] + ("0" * 64,) + coordinator._button_keys["z2"][2:]
        rival.enrollment("z2", {"entry": "button", "step": "claim"})
    claimed = coordinator.enrollment("z2", {"entry": "button", "step": "claim"})
    assert claimed["state"] == "ENROLLED" and claimed["enrollment_source"] == "ps-gpio-button"


# --- G13 negatives -------------------------------------------------------------------

def test_unsigned_wrong_or_unclassified_writes_fail_closed_before_dispatch(lab):
    ppu, gateway, _paths, tmp_path = lab
    store, coordinator = _manager(tmp_path, ppu, gateway, "a")
    coordinator.enrollment("z2", {"entry": "ticket", "ticket": _ticket(ppu)})
    status, payload = _raw(gateway, "POST", "/api/jobs", json.dumps(JOB).encode(),
                           {"Content-Type": "application/json"})
    assert status == 401 and payload["error"]["code"] == "CONTROLLER_UNAUTHENTICATED"
    assert payload["error"]["controller_generation"] == 1
    status, payload = _raw(gateway, "POST", "/api/shell", b"{}", {"Content-Type": "application/json"})
    assert status == 403 and payload["error"]["code"] == "CONTROLLER_OPERATION_UNCLASSIFIED"
    status, payload = _raw(gateway, "PUT", "/api/jobs", b"{}")
    assert status == 501                                             # no other mutating method
    good = store.record_for("z2")
    store.set("z2", good.device_id, "w" * 64, generation=good.generation)
    status, _headers, _body = _post(_gateway_client(coordinator, gateway), "/api/jobs")
    assert status == 401
    assert _Routes.recorded == []


def test_takeover_revokes_the_old_controller_and_manager_stops_without_retry(lab):
    ppu, gateway, _paths, tmp_path = lab
    store_a, manager_a = _manager(tmp_path, ppu, gateway, "a")
    manager_a.enrollment("z2", {"entry": "ticket", "ticket": _ticket(ppu)})
    old = store_a.record_for("z2")
    _store_b, manager_b = _manager(tmp_path, ppu, gateway, "b")
    taken = manager_b.enrollment("z2", {"entry": "ticket", "ticket": _ticket(ppu), "label": "cs-b"})
    assert taken["controller_generation"] == 2
    with pytest.raises(ControllerReplacedError):
        _post(_gateway_client(manager_a, gateway), "/api/jobs")       # stops before sending
    # Even a request that skips the Manager's generation check is revoked by the PPU.
    status, _headers, raw = _gateway_client(manager_a, gateway)._raw_relay(
        "GET", "/api/auth/challenge", headers={}, body=None, timeout_s=5, max_response_bytes=4096)
    challenge = json.loads(raw)
    header, _ctx = manager_auth.sign_request(
        credential=old.token, method="POST", path="/api/jobs", body=json.dumps(JOB).encode(),
        device_id=old.device_id, nonce=challenge["nonce"])
    status, payload = _raw(gateway, "POST", "/api/jobs", json.dumps(JOB).encode(),
                           {"Authorization": header, "Content-Type": "application/json"})
    assert status == 401 and payload["error"]["controller_generation"] == 2
    status, _h, _b = _post(_gateway_client(manager_b, gateway), "/api/jobs")
    assert status == 202 and len(_Routes.recorded) == 1


def test_recovery_only_controller_cannot_write_until_explicit_recovery(lab):
    ppu, gateway, paths, tmp_path = lab
    _store_a, manager_a = _manager(tmp_path, ppu, gateway, "a")
    manager_a.enrollment("z2", {"entry": "ticket", "ticket": _ticket(ppu)})
    paths.seal_dir.mkdir()
    marker = paths.seal_dir / "site2.sealed"
    marker.write_text('{"site": 2, "reason": "OUTCOME_UNKNOWN_SITE_SEALED"}')
    _store_b, manager_b = _manager(tmp_path, ppu, gateway, "b")
    taken = manager_b.enrollment("z2", {"entry": "ticket", "ticket": _ticket(ppu)})
    assert taken["controller_mode"] == "RECOVERY_ONLY" and taken["recovery_blockers"] == ["site2.sealed"]
    assert marker.exists()                                          # takeover preserved the seal
    status, _h, body = _post(_gateway_client(manager_b, gateway), "/api/jobs")
    assert status == 403 and json.loads(body)["error"]["code"] == "CONTROLLER_RECOVERY_ONLY"
    with pytest.raises(ValueError):
        manager_b.recovery_action("z2", {"action": "recovery.complete"})
    status, blocked = manager_b.recovery_action("z2", {"action": "recovery.complete",
                                                       "explicit_request": True})
    assert status == 409 and blocked["error"] == "RECOVERY_BLOCKED"
    status, recover = manager_b.recovery_action("z2", {"action": "site.recover", "site": 2,
                                                       "explicit_request": True})
    assert status == 200 and recover["result"]["result"] == "NOT_AVAILABLE"
    marker.unlink()                    # stands in for the Embedded seal procedure (root, on PPU)
    status, done = manager_b.recovery_action("z2", {"action": "recovery.complete",
                                                    "explicit_request": True})
    assert status == 200 and done["result"] == {"mode": "NORMAL"}
    status, _h, _b = _post(_gateway_client(manager_b, gateway), "/api/jobs")
    assert status == 202


def test_no_takeover_commits_while_a_gateway_write_is_being_admitted(lab):
    ppu, gateway, _paths, tmp_path = lab
    _store_a, manager_a = _manager(tmp_path, ppu, gateway, "a")
    manager_a.enrollment("z2", {"entry": "ticket", "ticket": _ticket(ppu)})
    ppu.engine.fence_wait_s = 0.3
    _Routes.hold_jobs.set()
    results: list[int] = []
    writer = threading.Thread(target=lambda: results.append(
        _post(_gateway_client(manager_a, gateway), "/api/jobs")[0]))
    writer.start()
    assert _Routes.job_entered.wait(5)
    assert ppu.engine.fence.holders() == 1          # the admission holds the fence
    _store_b, manager_b = _manager(tmp_path, ppu, gateway, "b")
    ticket = _ticket(ppu)
    deferred = manager_b.enrollment("z2", {"entry": "ticket", "ticket": ticket})
    assert deferred["ok"] is False and deferred["state"] == "TAKEOVER_DEFERRED_ACTIVE_OPERATION"
    assert deferred["detail"] == ["write-admission-in-progress"]
    _Routes.release_jobs.set()
    writer.join(5)
    assert results == [202]
    taken = manager_b.enrollment("z2", {"entry": "ticket", "ticket": ticket})
    assert taken["controller_generation"] == 2


def test_admission_unavailable_fails_closed(lab, tmp_path):
    ppu, gateway, paths, _tmp = lab
    _store, coordinator = _manager(tmp_path, ppu, gateway, "a")
    coordinator.enrollment("z2", {"entry": "ticket", "ticket": _ticket(ppu)})
    _Gateway.controller_admission_socket = tmp_path / "missing.sock"
    status, payload = _raw(gateway, "POST", "/api/jobs", json.dumps(JOB).encode(),
                           {"Content-Type": "application/json"})
    assert status == 403 or status == 503
    assert _Routes.recorded == []


# --- inventory -------------------------------------------------------------------------

def test_every_manager_forwarded_post_route_is_classified():
    handler = _Gateway.__new__(_Gateway)
    samples = {
        r"^/api/settings/gateway$": "/api/settings/gateway",
        r"^/api/settings/ppu-network$": "/api/settings/ppu-network",
        r"^/api/settings/sites/activation$": "/api/settings/sites/activation",
        r"^/api/settings/sites/[1-9][0-9]*$": "/api/settings/sites/2",
        r"^/api/mock/runtime$": "/api/mock/runtime",
        r"^/api/engineering/diagnostics/loopback$": "/api/engineering/diagnostics/loopback",
        r"^/api/engineering/diagnostics/openocd-control-plane$":
            "/api/engineering/diagnostics/openocd-control-plane",
        r"^/api/engineering/session$": "/api/engineering/session",
        r"^/api/jobs$": "/api/jobs",
    }
    expected = {
        "/api/settings/gateway": "ppu.settings.write", "/api/settings/ppu-network": "ppu.settings.write",
        "/api/settings/sites/activation": "site.activation", "/api/settings/sites/2": "site.settings.write",
        "/api/mock/runtime": "ppu.settings.write", "/api/jobs": "site.job.submit",
        "/api/jobs/job-1/cancel": "site.job.cancel",
        "/api/settings/ppu-network/activation": "ppu.settings.write",
        "/api/settings/ppu-network/activation/act-1/commit": "ppu.settings.write",
        "/api/engineering/targets/f/p/api/jobs": "engineering.write",
        "/api/batches": None,                     # not implemented by the PPU Gateway: refused
        "/api/anything-else": None,
    }
    for path, operation in expected.items():
        assert handler.controller_operation(path) == operation, path
    for pattern in _MANAGED_POST_PATTERNS:
        sample = samples.get(pattern.pattern)
        if sample is not None:
            assert handler.controller_operation(sample) is not None, pattern.pattern
    for cls in gateway_phase3.Phase3PlasmaWebHandler.__mro__:
        assert not {"do_PUT", "do_DELETE", "do_PATCH"} & set(vars(cls)), cls


def test_deployed_gateway_requires_an_explicit_admission_mode():
    with pytest.raises(RuntimeError, match="exactly one"):
        gateway_phase3.Phase3PlasmaWebHandler.configure_controller_admission(
            socket_path=None, host_lab_unauthenticated_writes=False)
    assert gateway_phase3.Phase3PlasmaWebHandler.host_lab_unauthenticated_writes is False
    assert gateway_phase3.Phase3PlasmaWebHandler.controller_admission_socket is None
    assert ControllerWriteAdmissionMixin in gateway_phase3.Phase3PlasmaWebHandler.__mro__
    assert gateway_phase3.Phase3PlasmaWebHandler.__mro__.index(ControllerWriteAdmissionMixin) == 1
    source = inspect.getsource(gateway_phase3._parser)
    assert "--controller-admission-socket" in source and "--host-lab-unauthenticated-writes" in source
    core = (ROOT / "scripts/ppu-z2-installer.py").read_text()
    assert re.search(r"--controller-admission-socket \{CONTROLLER_ADMISSION_SOCKET\}", core)


# --- Manager credential store v2 migration -------------------------------------------------

def test_manager_v1_credentials_migrate_in_place_to_generation_1(tmp_path):
    path = tmp_path / "bootstrap-credentials.json"
    path.write_text(json.dumps({"schema_version": 1, "credentials": {"z2": {
        "device_id": "ppu-device-0123456789abcdef01234567", "token": "t" * 40,
        "updated_at": "2026-11-09T08:31:00+00:00"}}}))
    path.chmod(0o600)
    store = BootstrapCredentialStore(path)
    record = store.record_for("z2")
    assert (record.generation, record.controller_id, record.token) == (1, None, "t" * 40)
    on_disk = json.loads(path.read_text())
    assert on_disk["schema_version"] == 2
    assert on_disk["credentials"]["z2"]["generation"] == 1
    assert path.stat().st_mode & 0o777 == 0o600


def test_wrong_or_unarmed_enrollment_never_persists_a_credential(lab):
    ppu, gateway, _paths, tmp_path = lab
    store, coordinator = _manager(tmp_path, ppu, gateway, "a")
    not_armed = coordinator.enrollment("z2", {"entry": "ticket", "ticket": "a" * 64})
    assert not_armed["ok"] is False and not_armed["state"] == "ENROLLMENT_NOT_ARMED"
    _ticket(ppu)
    wrong = coordinator.enrollment("z2", {"entry": "ticket", "ticket": "b" * 64})
    assert wrong["ok"] is False and wrong["state"] == "ENROLLMENT_PROOF_INVALID"
    assert store.paired("z2") is False and ppu.engine.controller() is None
    with pytest.raises(ValueError):
        coordinator.enrollment("z2", {"entry": "ticket", "ticket": "NOT-HEX"})


def test_unenrolled_manager_write_is_refused_by_the_ppu_not_silently_accepted(lab):
    ppu, gateway, _paths, tmp_path = lab
    _store, coordinator = _manager(tmp_path, ppu, gateway, "a")
    status, _headers, body = _post(_gateway_client(coordinator, gateway), "/api/jobs")
    assert status == 503 and json.loads(body)["error"]["code"] == "CONTROLLER_NOT_ENROLLED"
    _owner_store, owner = _manager(tmp_path, ppu, gateway, "owner")
    owner.enrollment("z2", {"entry": "ticket", "ticket": _ticket(ppu)})
    status, _headers, body = _post(_gateway_client(coordinator, gateway), "/api/jobs")
    assert status == 401 and json.loads(body)["error"]["code"] == "CONTROLLER_UNAUTHENTICATED"
    assert _Routes.recorded == []

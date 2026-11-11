"""Host-only HTTP routing for Manager Bundle programming (stub workflow)."""
from __future__ import annotations

import json
import threading
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from plasma_manager.bootstrap_server import BootstrapPlasmaManagerHandler
from plasma_manager.config import ManagerConfig
from plasma_manager.programming import ProgrammingError
from plasma_manager.registry import PPURegistryStore
from plasma_manager.server import PPUOperationGate

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_manager_bootstrap_rest import FakeBootstrapCoordinator, FakePoller  # noqa: E402

RUN_ID = "d" * 32


class StubWorkflow:
    def __init__(self):
        self.calls: list[tuple] = []

    def list_routes(self):
        self.calls.append(("routes",))
        return {"ok": True, "routes": [{"route_id": "r"}]}

    def plan(self, alias, body):
        self.calls.append(("plan", alias, dict(body)))
        if body.get("icpn") == "missing":
            raise ProgrammingError(422, "programming_route_not_found", "no route")
        return {"ok": True, "plan": {"plan_id": "e" * 32}}

    def start(self, alias, body):
        self.calls.append(("start", alias, dict(body)))
        return {"ok": True, "run": {"run_id": RUN_ID}}

    def run_status(self, alias, run_id):
        self.calls.append(("run", alias, run_id))
        return {"ok": True, "run": {"run_id": run_id, "outcome": None}}

    def read_output(self, alias, run_id):
        self.calls.append(("output", alias, run_id))
        if run_id != RUN_ID:
            raise ProgrammingError(409, "read_output_unavailable", "no output")
        return b"\x00\x01READ", {"filename": "read-IC-0x08000000-6.bin", "sha256": "a" * 64}

    def acknowledge(self, alias, run_id, body):
        self.calls.append(("ack", alias, run_id, dict(body)))
        return {"ok": True, "run": {"run_id": run_id, "acknowledged": True}}


@pytest.fixture
def manager(tmp_path: Path):
    registry = PPURegistryStore((), tmp_path / "registry.json")
    registry.add(alias="z2", endpoint="http://192.168.2.99:18080")
    names = ("config", "registry_store", "poller", "bootstrap_coordinator",
             "operation_gate", "programming_workflow")
    previous = {n: getattr(BootstrapPlasmaManagerHandler, n) for n in names}
    workflow = StubWorkflow()
    poller = FakePoller()
    coordinator = FakeBootstrapCoordinator()
    BootstrapPlasmaManagerHandler.config = ManagerConfig(registry_state_path=tmp_path / "registry.json")
    BootstrapPlasmaManagerHandler.registry_store = registry
    BootstrapPlasmaManagerHandler.poller = poller
    BootstrapPlasmaManagerHandler.bootstrap_coordinator = coordinator
    BootstrapPlasmaManagerHandler.operation_gate = PPUOperationGate()
    BootstrapPlasmaManagerHandler.programming_workflow = workflow
    server = ThreadingHTTPServer(("127.0.0.1", 0), BootstrapPlasmaManagerHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def call(method, path, body=None):
        conn = HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        raw = None if body is None else json.dumps(body).encode()
        conn.request(method, path, body=raw,
                     headers={"Content-Type": "application/json"} if raw else {})
        response = conn.getresponse()
        payload = json.loads(response.read() or b"{}")
        conn.close()
        return response.status, payload

    try:
        yield call, workflow, poller
    finally:
        server.shutdown()
        server.server_close()
        for name, value in previous.items():
            setattr(BootstrapPlasmaManagerHandler, name, value)


BASE = "/api/registry/z2/bootstrap/programming"


def test_routes_plan_run_status_and_ack_are_wired(manager):
    call, workflow, _poller = manager
    assert call("GET", f"{BASE}/routes")[0] == 200
    status, payload = call("POST", f"{BASE}/plans", {"icpn": "X", "site_id": 2, "firmware_base64": "AA=="})
    assert status == 200 and payload["plan"]["plan_id"] == "e" * 32
    status, payload = call("POST", f"{BASE}/runs", {"plan_id": "e" * 32, "confirm": "PROGRAM"})
    assert status == 202 and payload["run"]["run_id"] == RUN_ID
    assert call("GET", f"{BASE}/runs/{RUN_ID}")[0] == 200
    status, _ = call("POST", f"{BASE}/runs/{RUN_ID}/acknowledge", {"acknowledge": "OUTCOME_UNKNOWN_RECONCILED"})
    assert status == 200
    assert [c[0] for c in workflow.calls] == ["routes", "plan", "start", "run", "ack"]


def test_workflow_errors_keep_their_status_and_code(manager):
    call, _workflow, _poller = manager
    status, payload = call("POST", f"{BASE}/plans", {"icpn": "missing", "site_id": 2, "firmware_base64": "AA=="})
    assert status == 422 and payload["error"]["code"] == "programming_route_not_found"


def test_run_requires_platform_idle_gate(manager):
    call, workflow, poller = manager
    poller.active = True
    status, payload = call("POST", f"{BASE}/runs", {"plan_id": "e" * 32, "confirm": "PROGRAM"})
    assert status == 409 and payload["error"]["code"] == "ppu_busy"
    assert not any(c[0] == "start" for c in workflow.calls)


@pytest.mark.parametrize("method, path", [
    ("GET", f"{BASE}/runs/not-a-run-id"),
    ("GET", f"{BASE}/plans"),
    ("POST", f"{BASE}/runs/{RUN_ID}/retry"),
])
def test_unlisted_programming_paths_are_not_allowlisted(manager, method, path):
    call, workflow, _poller = manager
    status, payload = call(method, path, {} if method == "POST" else None)
    assert status == 404 and payload["error"]["code"] == "bootstrap_route_not_allowed"
    assert workflow.calls == []


def test_read_output_is_a_binary_download_with_its_sha256(manager):
    call, workflow, _poller = manager
    status, payload = call("GET", f"{BASE}/runs/{'e' * 32}/output")
    assert status == 409 and payload["error"]["code"] == "read_output_unavailable"
    import urllib.request
    server = next(c.cell_contents for c in call.__closure__
                  if isinstance(c.cell_contents, ThreadingHTTPServer))
    with urllib.request.urlopen(
            f"http://127.0.0.1:{server.server_address[1]}{BASE}/runs/{RUN_ID}/output") as response:
        assert response.status == 200 and response.read() == b"\x00\x01READ"
        assert response.headers["Content-Type"] == "application/octet-stream"
        assert response.headers["X-Plasma-Read-Sha256"] == "a" * 64
        assert response.headers["Content-Disposition"] == \
            'attachment; filename="read-IC-0x08000000-6.bin"'
        assert response.headers["Cache-Control"] == "no-store"
    assert ("output", "z2", RUN_ID) in workflow.calls

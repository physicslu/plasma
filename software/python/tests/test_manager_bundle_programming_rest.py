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

    def issue_batch_start(self, body):
        self.calls.append(("issue", dict(body)))
        return {"ok": True, "start": {"start_id": RUN_ID, "kind": "batch",
                                      "ppu_alias": None}}

    def void_start(self, start_id, body):
        self.calls.append(("void", start_id, dict(body)))
        if body != {"void": "VOID_UNSTARTED_START"}:
            raise ProgrammingError(400, "invalid_request", "void requires void=VOID_UNSTARTED_START")
        return {"ok": True, "reconciliation": {"start_id": start_id, "state": "NOT_ACCEPTED"}}


class StubBatches:
    def __init__(self):
        self.calls: list[tuple] = []

    def reconcile_start(self, start_id):
        self.calls.append(("reconcile", start_id))
        return {"ok": True, "reconciliation": {"start_id": start_id, "state": "OUTCOME_UNKNOWN"}}

    # The canonical resource: no alias, because the Batch is not owned by a PPU.
    def start_batch(self, body):
        self.calls.append(("start_batch", dict(body)))
        return {"ok": True, "batch": {"batch_id": RUN_ID, "outcome": None}}

    def status_batch(self, batch_id):
        self.calls.append(("status_batch", batch_id))
        return {"ok": True, "batch": {"batch_id": batch_id, "outcome": "PARTIAL"}}

    def request_stop_batch(self, batch_id, body):
        self.calls.append(("stop_batch", batch_id, dict(body)))
        if body != {"stop": "STOP_QUEUING"}:
            raise ProgrammingError(400, "invalid_request", "stop requires stop=STOP_QUEUING")
        return {"ok": True, "batch": {"batch_id": batch_id, "stop_requested": True}}


@pytest.fixture
def manager(tmp_path: Path):
    registry = PPURegistryStore((), tmp_path / "registry.json")
    registry.add(alias="z2", endpoint="http://192.168.2.99:18080")
    names = ("config", "registry_store", "poller", "bootstrap_coordinator",
             "operation_gate", "programming_workflow", "programming_batches")
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
    BootstrapPlasmaManagerHandler.programming_batches = StubBatches()
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
        yield call, workflow, poller, BootstrapPlasmaManagerHandler.programming_batches
    finally:
        server.shutdown()
        server.server_close()
        for name, value in previous.items():
            setattr(BootstrapPlasmaManagerHandler, name, value)


BASE = "/api/registry/z2/bootstrap/programming"


def test_routes_plan_run_status_and_ack_are_wired(manager):
    call, workflow, _poller, _batches = manager
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
    call, _workflow, _poller, _batches = manager
    status, payload = call("POST", f"{BASE}/plans", {"icpn": "missing", "site_id": 2, "firmware_base64": "AA=="})
    assert status == 422 and payload["error"]["code"] == "programming_route_not_found"


def test_run_requires_platform_idle_gate(manager):
    call, workflow, poller, _batches = manager
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
    call, workflow, _poller, _batches = manager
    status, payload = call(method, path, {} if method == "POST" else None)
    assert status == 404 and payload["error"]["code"] == "bootstrap_route_not_allowed"
    assert workflow.calls == []


def test_read_output_is_a_binary_download_with_its_sha256(manager):
    call, workflow, _poller, _batches = manager
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


def test_the_alias_scoped_batch_and_start_routes_are_retired(manager):
    call, workflow, _poller, batches = manager
    # A Console tab loaded before the upgrade still asks for these. 410 is a
    # definite refusal that names the current resource; 5.3 reads a 4xx as a
    # refusal, so nothing is ever recorded as an unknown outcome.
    for method, path, body in (
            ("POST", f"{BASE}/batches", {"icpn": "X", "site_id": 2, "operations": ["erase"]}),
            ("GET", f"{BASE}/batches/{RUN_ID}", None),
            ("POST", f"{BASE}/batches/{RUN_ID}/stop", {"stop": "STOP_QUEUING"}),
            ("POST", f"{BASE}/starts", {"kind": "batch"}),
            ("GET", f"{BASE}/starts/{RUN_ID}", None),
            ("POST", f"{BASE}/starts/{RUN_ID}/void", {"void": "VOID_UNSTARTED_START"})):
        status, payload = call(method, path, body) if body is not None else call(method, path)
        assert status == 410, (method, path, status)
        assert payload["error"]["code"] == "programming_route_retired"
        assert "/api/programming/batches" in payload["error"]["message"]
    # Nothing reached the engine: no Batch was started, read or stopped.
    assert workflow.calls == [] and batches.calls == []
    # No cancel / abort route exists for a submitted Job.
    for path in (f"{BASE}/batches/{RUN_ID}/cancel", f"{BASE}/batches/{RUN_ID}/abort",
                 f"{BASE}/runs/{RUN_ID}/cancel"):
        assert call("POST", path, {"x": 1})[0] == 404


CANONICAL = "/api/programming/batches"
CANONICAL_STARTS = "/api/programming/starts"


def test_the_canonical_start_resource_is_not_under_a_ppu(manager):
    call, workflow, _poller, batches = manager
    status, payload = call("POST", CANONICAL_STARTS, {"kind": "batch"})
    assert status == 200 and payload["start"]["start_id"] == RUN_ID
    assert payload["start"]["ppu_alias"] is None
    status, payload = call("GET", f"{CANONICAL_STARTS}/{RUN_ID}")
    assert status == 200 and payload["reconciliation"]["state"] == "OUTCOME_UNKNOWN"
    status, payload = call("POST", f"{CANONICAL_STARTS}/{RUN_ID}/void",
                           {"void": "VOID_UNSTARTED_START"})
    assert status == 200 and payload["reconciliation"]["state"] == "NOT_ACCEPTED"
    assert call("POST", f"{CANONICAL_STARTS}/{RUN_ID}/void", {"void": "x"})[0] == 400
    # No alias reached the workflow: issuing and voiding name no PPU at all.
    assert [c[0] for c in workflow.calls] == ["issue", "void", "void"]
    assert workflow.calls[0] == ("issue", {"kind": "batch"})
    assert batches.calls == [("reconcile", RUN_ID)]


def test_canonical_reconciliation_is_a_get_only_and_takes_a_strict_start_id(manager):
    call, workflow, _poller, batches = manager
    for path in (f"{CANONICAL_STARTS}/not-an-id", f"{CANONICAL_STARTS}/{'D' * 32}"):
        assert call("GET", path)[0] in (400, 404, 405)
    # A POST to the reconciliation path is never a query and changes nothing.
    assert call("POST", f"{CANONICAL_STARTS}/{RUN_ID}", {})[0] in (400, 404, 405)
    assert workflow.calls == [] and batches.calls == []


def test_the_canonical_batch_resource_is_not_under_a_ppu(manager):
    call, _workflow, _poller, batches = manager
    targets = [{"ppu_alias": "z2", "site_ids": [2, 3]},
               {"ppu_alias": "z2b", "site_ids": [2]}]
    status, payload = call("POST", CANONICAL, {"icpn": "X", "targets": targets,
                                               "operations": ["erase", "program", "verify"]})
    assert status == 202 and payload["batch"]["batch_id"] == RUN_ID
    status, payload = call("GET", f"{CANONICAL}/{RUN_ID}")
    assert status == 200 and payload["batch"]["outcome"] == "PARTIAL"
    status, payload = call("POST", f"{CANONICAL}/{RUN_ID}/stop", {"stop": "STOP_QUEUING"})
    assert status == 200 and payload["batch"]["stop_requested"] is True
    assert [c[0] for c in batches.calls] == ["start_batch", "status_batch", "stop_batch"]
    # No alias reached the coordinator: the Target Set carries them all.
    assert batches.calls[0][1]["targets"] == targets


def test_the_canonical_resource_keeps_coordinator_errors(manager):
    call, _workflow, _poller, _batches = manager
    status, payload = call("POST", f"{CANONICAL}/{RUN_ID}/stop", {"stop": "now"})
    assert status == 400 and payload["error"]["code"] == "invalid_request"


def test_an_unknown_canonical_batch_path_is_not_claimed(manager):
    call, _workflow, _poller, batches = manager
    # Only a 32-hex batch id is a Batch; anything else falls through to the
    # ordinary Manager routes rather than being answered by this resource.
    assert call("GET", "/api/programming/batches/not-a-batch")[0] == 404
    assert batches.calls == []

"""Diagnostic GAP reproducer for pinned b074bd3, NOT acceptance tests.

Run with PYTHONPATH=software/python python -m pytest -q -s <this file>.
WP01_REQUIRE_CONTRACT=1 applies the required global-domain/admission oracles
instead of the observed broken behavior and must fail on the pinned source.
No sockets, secrets, services or hardware are used. Credentials are synthetic.
"""
import json
import os
from types import SimpleNamespace

import pytest

from plasma_manager.bootstrap import BootstrapCredentialStore, ManagerBootstrapCoordinator
from plasma_manager.bootstrap_server import BootstrapPlasmaManagerHandler
from plasma_manager.poller import FleetPoller
from tests.test_programming_batch_targets import one, rig, with_start

REQUIRE = os.environ.get("WP01_REQUIRE_CONTRACT") == "1"
DEVICE = "ppu-device-0000000000000001"


def handler_for(workflow, coordinator):
    class Handler(BootstrapPlasmaManagerHandler):
        registry_store = workflow.registry
        bootstrap_coordinator = coordinator
        poller = FleetPoller(SimpleNamespace(fleet_snapshot=lambda: {"ppus": []}), 1)
    Handler.poller.refresh()  # local synthetic source; never polls a PPU
    return Handler


def response(batches, body):
    handler = object.__new__(BootstrapPlasmaManagerHandler)
    result = []
    handler._read_json_object = lambda: body
    handler._batches = lambda: batches
    handler._json = lambda status, payload: result.append((int(status), payload))
    assert handler._canonical_programming_post("/api/programming/batches")
    return result[0]


@pytest.mark.parametrize("stage", ["platform", "site"])
def test_manager_service_identity_is_reported_as_local(tmp_path, monkeypatch, stage):
    batches, workflow, _gateways, _ = rig(tmp_path)
    credentials = BootstrapCredentialStore(tmp_path / "synthetic-credentials.json")
    credentials.set("z2", DEVICE, "synthetic-test-credential-" + "x" * 32)
    coordinator = ManagerBootstrapCoordinator(workflow.registry, credentials, 1)
    handler = handler_for(workflow, coordinator)
    workflow.coordinator = coordinator
    for key in ("ORIGIN", "CLIENT_ID", "CLIENT_SECRET"):
        monkeypatch.delenv("PLASMA_MANAGER_CF_ACCESS_" + key, raising=False)
    monkeypatch.setenv("PLASMA_MANAGER_CF_ACCESS_ORIGIN", "https://example.invalid")
    # No identity or secret is supplied: this is Manager deployment state,
    # explicitly documented as distinct from PPU state in client.py.
    from plasma_manager import client
    remote = []
    def no_network(*args, **kwargs):
        remote.append(True)
        raise AssertionError("probe must not open a socket")
    monkeypatch.setattr(client._DIRECT_HTTP, "open", no_network)
    verdict = (handler.platform_gate_reason("z2") if stage == "platform"
               else workflow.target_block("z2", 2))
    print(json.dumps({"stage": stage, "verdict": verdict, "network_calls": len(remote)}))
    assert not remote
    assert verdict[0] == ("SHARED_CONTROL_FAILURE" if REQUIRE else "TARGET_STATE_UNAVAILABLE")


def test_ambiguous_shared_credential_read_is_reported_as_local(tmp_path, monkeypatch):
    _batches, workflow, _gateways, _ = rig(tmp_path)
    credentials = BootstrapCredentialStore(None)
    class Client:
        def status(self):
            return 200, {"bootstrap": {"state": "bootstrap_ready"},
                         "identity": {"device_id": DEVICE},
                         "runtime": {"state": "runtime_absent"}}
    coordinator = ManagerBootstrapCoordinator(
        workflow.registry, credentials, 1, client_factory=lambda *_: Client())
    handler = handler_for(workflow, coordinator)
    def broken_store(_alias):
        raise RuntimeError("synthetic shared credential store judgement unavailable")
    monkeypatch.setattr(credentials, "public_state", broken_store)
    verdict = handler.platform_gate_reason("z2")
    print(json.dumps({"stage": "shared_credential_read", "verdict": verdict}))
    assert verdict[0] == ("SHARED_CONTROL_FAILURE" if REQUIRE else "TARGET_STATE_UNAVAILABLE")


def test_stopped_poller_not_detected_by_platform_gate(tmp_path):
    _batches, workflow, _gateways, _ = rig(tmp_path)
    class Client:
        def status(self):
            return 200, {"bootstrap": {"state": "bootstrap_ready"},
                         "identity": {"device_id": DEVICE},
                         "runtime": {"state": "runtime_absent"}}
    coordinator = ManagerBootstrapCoordinator(
        workflow.registry, BootstrapCredentialStore(None), 1,
        client_factory=lambda *_: Client())
    handler = handler_for(workflow, coordinator)
    handler.poller.stop()
    assert handler.poller._thread is None
    verdict = handler.platform_gate_reason("z2")
    print(json.dumps({"stage": "stopped_poller", "verdict": verdict}))
    if REQUIRE:
        assert verdict is not None and verdict[0] == "SHARED_CONTROL_FAILURE"
    else:
        assert verdict is None


def test_real_missing_shared_control_consumes_start_before_refusal(tmp_path):
    class Handler(BootstrapPlasmaManagerHandler):
        registry_store = None
        poller = None
        bootstrap_coordinator = None
    batches, workflow, gateways, _ = rig(tmp_path, platform_gate=Handler.platform_gate_reason)
    body = with_start(workflow, [one("z2", 2)])
    before = (tmp_path / "batches.json").read_bytes()
    status, payload = response(batches, body)
    state = workflow._starts[body["start_id"]]["state"]
    reconciliation = batches.reconcile_start(body["start_id"])["reconciliation"]["state"]
    unchanged = (tmp_path / "batches.json").read_bytes() == before
    print(json.dumps({"stage": "missing_shared_control", "http": status,
                      "start_state": state, "reconciliation": reconciliation,
                      "batch_journal_unchanged": unchanged, "posts": len(gateways["z2"].posts)}))
    assert not gateways["z2"].posts
    if REQUIRE:
        assert status == 503
        assert state == "ISSUED" and unchanged
        assert reconciliation == "ACCEPTANCE_PENDING"
        workflow.require_batch_start(body["start_id"])
    else:
        assert status == 202
        assert state == "CONSUMED" and not unchanged
        assert reconciliation == "TERMINAL_CONFIRMED"
        assert payload["batch"]["failure_domain"] == "SHARED_CONTROL_FAILURE"

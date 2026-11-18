"""LOM-P2A-2 P0 work 2: controlled close of ONE ``coordinator_result_unreconciled``
Runtime transaction whose activation actually succeeded (Host-only).

Every negative must leave the API record, the Coordinator journal and the
reconciliation directory byte-identical. The original error is preserved; the
runner result is never fabricated.
"""
from __future__ import annotations

import base64
import fcntl
import json
import os
import time
from pathlib import Path

import pytest

from . import lom_p0_lab
from .lom_p0_lab import API_TX, ARTIFACT_SHA, LOOPBACK, RELEASE_ID, GatewayRoutes, close_lab, make_lab

service = lom_p0_lab.service


@pytest.fixture
def lab(tmp_path: Path):
    lab = make_lab(tmp_path)
    lab.start_ppu()
    store, coordinator = lab.manager("cs")
    lab.enroll(coordinator)                 # controller NORMAL before the failure (as on Z2)
    journal = lab.seed_runtime_failure()
    lab.coordinator, lab.store, lab.journal0 = coordinator, store, journal
    try:
        yield lab
    finally:
        close_lab(lab)


def _expected(lab, **override):
    expected = {"coordinator_transaction_id": lab.journal0["transaction_id"],
                "release_id": RELEASE_ID, "artifact_sha256": ARTIFACT_SHA}
    expected.update(override)
    return expected


def _reconcile(lab, *, tx=API_TX, **override):
    return lab.coordinator.reconcile_runtime_deployment(
        "z2", {"transaction_id": tx, "expected": _expected(lab, **override), "explicit_request": True},
        lab.gateway_client(lab.coordinator))


def _direct(lab, body):
    """Signed Bootstrap call with an arbitrary body (bypasses the Manager's own loopback)."""
    _n, _r, client, _p, device_id, token = lab.coordinator._authenticated("z2")
    return client._json("POST", "/v1/deployment/reconcile", credential=token,
                        device_id=device_id, body=body, timeout_s=30.0)


def _signed_loopback_body(lab) -> bytes:
    body = {"endpoint": "ps", "test_id": "probe", "sequence": 7, "pattern": "zero", "seed": "",
            "payload_length": 1, "payload_base64": "AA==", "tx_crc32": "d202ef8d", "timeout_ms": 5000}
    status, _h, raw = lab.gateway_client(lab.coordinator).relay(
        "POST", LOOPBACK, headers={"Content-Type": "application/json"},
        body=json.dumps(body).encode(), timeout_s=10, max_response_bytes=65536)
    assert status == 200
    return raw


def _request(lab, raw: bytes, **expected) -> dict:
    return {"action": "runtime.activation.reconcile", "transaction_id": API_TX,
            "expected": _expected(lab, **expected),
            "ps_loopback": {"target": LOOPBACK, "response_base64": base64.b64encode(raw).decode()},
            "explicit_request": True}


def _denied(lab, result, code):
    status, payload = result
    assert status == 409, payload
    assert payload["ok"] is False and payload["code"] == code, payload


# --- positive ------------------------------------------------------------------------

def test_reconcile_closes_exactly_the_failed_runtime_transaction(lab):
    original = lab.api_record()
    journal_bytes = (lab.paths.state_root / "deployment.json").read_bytes()
    assert lab.ppu.engine.probe.unknown_outcomes() == ["bootstrap-deployment:" + API_TX]
    status, payload = _reconcile(lab)
    assert status == 200 and payload["ok"] is True, payload
    record = lab.api_record()
    assert record["state"] == "reconciled"
    # The original failure is preserved verbatim; no runner success is fabricated.
    for key in ("transaction_id", "upload_id", "error_code", "error", "result", "started_at_epoch_s"):
        assert record[key] == original[key]
    assert record["result"] is None
    summary = record["reconciliation"]
    assert summary["decision"] == "CONFIRMED_EXECUTED_VERIFIED"
    assert summary["coordinator_transaction_id"] == lab.journal0["transaction_id"]
    assert summary["release_id"] == RELEASE_ID and summary["controller_generation"] == 1
    evidence_path = lab.paths.state_root / "deployment-reconciliations" / f"{API_TX}.json"
    assert oct(evidence_path.stat().st_mode & 0o777) == "0o600"
    evidence = json.loads(evidence_path.read_text())
    assert evidence["original_api_record"] == original
    assert evidence["coordinator"]["state"] == "runtime_active"
    assert evidence["verified"]["ps_loopback"]["status"] == 200
    assert evidence["verified"]["gateway"]["challenge_controller_generation"] == 1
    assert "credential" not in json.dumps(evidence)
    # Coordinator journal untouched; the transaction no longer blocks.
    assert (lab.paths.state_root / "deployment.json").read_bytes() == journal_bytes
    assert lab.ppu.engine.probe.unknown_outcomes() == []
    assert lab.coordinator.status("z2")["bootstrap"]["deployment"]["state"] == "reconciled"
    # Exactly once: the same transaction cannot be closed again.
    _denied(lab, _reconcile(lab), "RECONCILE_STATE_NOT_ELIGIBLE")


def test_reconcile_is_a_recovery_action_documented_in_the_spec():
    controller = service._controller_module()
    assert "deployment.reconcile" in controller.RECOVERY_ACTIONS
    spec = (lom_p0_lab.ROOT / "docs/development/opf-local-owner-mode-p2a0-enrollment-spec.md").read_text()
    assert "`deployment.reconcile`" in spec


# --- identity / state negatives: nothing written ----------------------------------------

@pytest.mark.parametrize("override, code", [
    ({"release_id": "0.2.1-a1b1c6f3b142"}, "RECONCILE_COORDINATOR_IDENTITY_MISMATCH"),
    ({"artifact_sha256": "0" * 64}, "RECONCILE_COORDINATOR_IDENTITY_MISMATCH"),
    ({"coordinator_transaction_id": "00000000-0000-4000-8000-000000000000"},
     "RECONCILE_COORDINATOR_IDENTITY_MISMATCH"),
])
def test_wrong_expected_identity_is_refused(lab, override, code):
    before = lab.state_bytes()
    _denied(lab, _reconcile(lab, **override), code)
    assert lab.state_bytes() == before


def test_wrong_transaction_is_refused(lab):
    before = lab.state_bytes()
    _denied(lab, _reconcile(lab, tx="0" * 32), "RECONCILE_TRANSACTION_MISMATCH")
    assert lab.state_bytes() == before


@pytest.mark.parametrize("mutate, code", [
    (lambda j, r: j.update(api_transaction_id="f" * 32), "RECONCILE_COORDINATOR_TRANSACTION_MISMATCH"),
    (lambda j, r: j.update(state="activating"), "RECONCILE_COORDINATOR_NOT_RUNTIME_ACTIVE"),
    (lambda j, r: j.update(kind="bundle"), "RECONCILE_COORDINATOR_NOT_RUNTIME_ACTIVE"),
    (lambda j, r: r.update(error_code="interrupted_service_restart"), "RECONCILE_STATE_NOT_ELIGIBLE"),
    (lambda j, r: r.update(state="failed"), "RECONCILE_STATE_NOT_ELIGIBLE"),
])
def test_inconsistent_ppu_state_is_refused(lab, mutate, code):
    journal, record = lab.journal(), lab.api_record()
    mutate(journal, record)
    lab.write_private(lab.paths.state_root / "deployment.json", journal)
    lab.write_private(lab.paths.state_root / "deployment-api.json", record)
    before = lab.state_bytes()
    _denied(lab, _reconcile(lab), code)
    assert lab.state_bytes() == before


def test_current_release_or_install_evidence_mismatch_is_refused(lab):
    current = lab.paths.product_root / "current"
    current.unlink()
    current.symlink_to(lab.paths.product_root / "releases" / "0.2.1-a1b1c6f3b142")
    _denied(lab, _reconcile(lab), "RECONCILE_CURRENT_RELEASE_MISMATCH")
    current.unlink()
    current.symlink_to(lab.paths.product_root / "releases" / RELEASE_ID)
    evidence = lab.paths.product_root / "install" / "last-install.json"
    data = json.loads(evidence.read_text())
    evidence.write_text(json.dumps({**data, "archive_sha256": "1" * 64}))
    before = lab.state_bytes()
    _denied(lab, _reconcile(lab), "RECONCILE_INSTALL_EVIDENCE_MISMATCH")
    assert lab.state_bytes() == before


# --- service / safety negatives ---------------------------------------------------------

def test_gateway_not_ready_is_refused(lab):
    GatewayRoutes.ready = {"gateway": "alive", "execution": "blocked"}
    _denied(lab, _reconcile(lab), "RECONCILE_GATEWAY_NOT_READY")


def test_active_site_job_lease_is_refused(lab):
    lab.lease.busy = True
    before = lab.state_bytes()
    _denied(lab, _reconcile(lab), "RECONCILE_ACTIVE_OPERATION")
    assert lab.state_bytes() == before


def test_sealed_site_is_refused(lab):
    lab.paths.seal_dir.mkdir()
    (lab.paths.seal_dir / "site2.sealed").write_text("{}")
    _denied(lab, _reconcile(lab), "RECONCILE_SITE_SEALED")


def test_coordinator_lock_held_by_another_transaction_is_refused(lab):
    with (lab.paths.state_root / "deployment.lock").open("a+b") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            # The flock is per open file description: a second open in-process conflicts.
            _denied(lab, _reconcile(lab), "RECONCILE_COORDINATOR_ACTIVE")
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def test_state_change_during_checks_is_refused(lab, monkeypatch):
    real = service._gateway_get

    def racing(host, port, path, timeout_s=5.0):
        if path == "/api/auth/challenge":
            record = lab.api_record()
            record["updated_at_epoch_s"] += 1          # another writer touched the record
            lab.write_private(lab.paths.state_root / "deployment-api.json", record)
        return real(host, port, path, timeout_s)

    monkeypatch.setattr(service, "_gateway_get", racing)
    _denied(lab, _reconcile(lab), "RECONCILE_STATE_CHANGED")
    assert lab.api_record()["state"] == "recovery_required"
    assert not (lab.paths.state_root / "deployment-reconciliations" / f"{API_TX}.json").exists()


# --- PS loopback proof negatives --------------------------------------------------------

def test_loopback_response_never_admitted_by_the_ppu_is_refused(lab):
    forged = json.dumps({"ok": True, "loopback": {"endpoint": "ps", "source": "ps",
                                                  "tx_crc32": "d202ef8d", "rx_crc32": "d202ef8d"}}).encode()
    _denied(lab, _direct(lab, _request(lab, forged)), "RECONCILE_LOOPBACK_NOT_ADMITTED")


def test_loopback_from_before_the_activation_is_refused(lab):
    raw = _signed_loopback_body(lab)
    journal = lab.journal()
    journal["updated_at_epoch_s"] = time.time() + 1          # activation newer than the proof
    lab.write_private(lab.paths.state_root / "deployment.json", journal)
    _denied(lab, _direct(lab, _request(lab, raw)), "RECONCILE_LOOPBACK_NOT_ADMITTED")


def test_failed_loopback_is_refused(lab):
    GatewayRoutes.corrupt_echo = True
    _denied(lab, _reconcile(lab), "RECONCILE_LOOPBACK_NOT_PASS")


def test_one_loopback_proof_cannot_be_replayed(lab):
    raw = _signed_loopback_body(lab)
    status, _payload = _direct(lab, _request(lab, raw))
    assert status == 200
    # A second PPU-side use of the consumed receipt is impossible even if the state allowed it.
    assert lab.ppu.engine.find_gateway_receipt(
        method="POST", target=LOOPBACK, status=200,
        body_sha256=__import__("hashlib").sha256(raw).hexdigest(), generation=1,
        not_before_epoch_s=0, max_age_s=300) is None


# --- authorization negatives ------------------------------------------------------------

def test_unsigned_or_revoked_reconcile_requests_are_refused(lab):
    from http.client import HTTPConnection
    conn = HTTPConnection("127.0.0.1", lab.ppu.server_port, timeout=10)
    conn.request("POST", "/v1/deployment/reconcile", body=b"{}", headers={"Content-Type": "application/json"})
    assert conn.getresponse().status == 401
    conn.close()
    _store_b, manager_b = lab.manager("rival")
    # A takeover while recovery_required commits RECOVERY_ONLY and revokes the old controller.
    taken = lab.enroll(manager_b, "rival")
    assert taken["controller_mode"] == "RECOVERY_ONLY"
    from plasma_manager.bootstrap import ControllerReplacedError
    with pytest.raises(ControllerReplacedError):
        _reconcile(lab)
    assert lab.api_record()["state"] == "recovery_required"


def test_recovery_only_controller_fails_closed_without_writing(lab):
    """Residual (documented): a RECOVERY_ONLY controller cannot produce the
    G13-admitted loopback proof, so reconciliation fails closed."""
    _store_b, manager_b = lab.manager("rival")
    lab.enroll(manager_b, "rival")
    before = lab.state_bytes()
    status, payload = manager_b.reconcile_runtime_deployment(
        "z2", {"transaction_id": API_TX, "expected": _expected(lab), "explicit_request": True},
        lab.gateway_client(manager_b))
    assert status == 403 and payload["error"] == "reconcile_loopback_refused"
    assert lab.state_bytes() == before


# --- crash / restart ----------------------------------------------------------------

def test_crash_after_evidence_record_then_restart_completes_with_the_same_record(lab):
    lab.ppu.reconcile_crash_at = "reconcile.after_evidence_record"
    with pytest.raises(Exception):
        _reconcile(lab)
    evidence_path = lab.paths.state_root / "deployment-reconciliations" / f"{API_TX}.json"
    first = evidence_path.read_bytes()
    assert lab.api_record()["state"] == "recovery_required"         # not yet closed
    lab.restart_ppu()
    assert lab.api_record()["state"] == "recovery_required"         # restart changes nothing
    status, payload = _reconcile(lab)
    assert status == 200, payload
    assert evidence_path.read_bytes() == first                      # append-only, never rewritten
    assert lab.api_record()["state"] == "reconciled"


def test_crash_after_api_record_then_restart_stays_reconciled(lab):
    lab.ppu.reconcile_crash_at = "reconcile.after_api_record"
    with pytest.raises(Exception):
        _reconcile(lab)
    lab.restart_ppu()
    record = lab.api_record()
    assert record["state"] == "reconciled" and record["error_code"] == "coordinator_result_unreconciled"
    assert lab.ppu.engine.probe.unknown_outcomes() == []
    _denied(lab, _reconcile(lab), "RECONCILE_STATE_NOT_ELIGIBLE")


def test_conflicting_existing_evidence_record_is_never_overwritten(lab):
    root = lab.paths.state_root / "deployment-reconciliations"
    root.mkdir(mode=0o700)
    lab.write_private(root / f"{API_TX}.json", {"api_transaction_id": API_TX,
                                                "original_api_record_sha256": "0" * 64})
    before = lab.state_bytes()
    _denied(lab, _reconcile(lab), "RECONCILE_EVIDENCE_RECORD_CONFLICT")
    assert lab.state_bytes() == before


def test_request_shape_is_strict(lab):
    raw = _signed_loopback_body(lab)
    for mutate in (lambda b: b.pop("explicit_request"), lambda b: b.update(explicit_request=False),
                   lambda b: b.update(action="other"), lambda b: b.update(extra=1),
                   lambda b: b["ps_loopback"].update(target="/api/jobs")):
        body = _request(lab, raw)
        mutate(body)
        status, payload = _direct(lab, body)
        assert status == 409 and payload["error"] == "deployment_reconciliation_denied"
    assert lab.api_record()["state"] == "recovery_required"
    assert os.listdir(lab.paths.state_root).count("deployment-reconciliations") == 0

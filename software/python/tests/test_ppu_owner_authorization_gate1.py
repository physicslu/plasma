"""Owner Operation Authorization: user-programmable Bundles (Host-only).

An authenticated, paired owner may admit / install their own Bundle without
any per-Bundle SHA256 allowlist. Each stage needs a fresh authorization bound
to device, exact archive SHA256, transaction and action. No Z2, FPGA or DUT.
"""
from __future__ import annotations

import importlib.util
import json
import sys
import threading
import time
from pathlib import Path

import pytest

from .ppu_owner_authorization_fixture import (
    OWNER_TOKEN, admit_body, authorize, device_id, install_body, owner,
)
from .test_ppu_bundle_v3_packages_contract import bundle_v3
from .test_ppu_bundle_v3_smoke_execution_gate1 import build_smoke
from .test_ppu_fpga_static_qualification_gate1 import _b3_server, _commit, bootstrap
from .test_ppu_package_receive_admission_pr1 import TOKEN, loopback  # noqa: F401
from .bootstrap_request_auth_fixture import signed_call
from .ppu_controller_fixture import clear_controller

ROOT = Path(__file__).resolve().parents[3]
# Load the Manager issuer by path: the factory Bootstrap CI job installs only
# pytest, and the issuer module is dependency-free by design.
_spec = importlib.util.spec_from_file_location(
    "plasma_manager_owner_authorization_cross",
    ROOT / "software" / "python" / "plasma_manager" / "owner_authorization.py",
)
manager_owner = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = manager_owner
_spec.loader.exec_module(manager_owner)

SHA = "b" * 64
TX = "c" * 32
DEV = "ppu-device-" + "d" * 24


# --- Contract unit -----------------------------------------------------------

def test_issue_verify_roundtrip_summary_has_no_secret_or_mac():
    auth = owner.issue(credential=OWNER_TOKEN, action=owner.ADMIT, device_id=DEV,
                       subject_sha256=SHA, transaction_id=TX)
    summary = owner.verify(auth, credential=OWNER_TOKEN, action=owner.ADMIT,
                           device_id=DEV, subject_sha256=SHA, transaction_id=TX)
    assert summary["status"] == "OWNER_AUTHORIZED"
    assert summary["method"] == "paired-console-operation-hmac-sha256"
    assert "mac" not in summary and OWNER_TOKEN not in json.dumps(summary)
    assert len(summary["authorization_sha256"]) == 64


def test_manager_issuer_is_byte_identical_to_ppu_contract():
    for action in (owner.ADMIT, owner.INSTALL, owner.ACTIVATE,
                   owner.ACTIVATE_FPGA_LOAD):
        ppu = owner.issue(credential=OWNER_TOKEN, action=action, device_id=DEV,
                          subject_sha256=SHA, transaction_id=TX)
        mgr = manager_owner.issue_bundle_operation(
            credential=OWNER_TOKEN, action=action, device_id=DEV,
            subject_sha256=SHA, transaction_id=TX)
        assert mgr == ppu
    assert manager_owner.SCHEMA == owner.SCHEMA
    assert manager_owner.KEY_CONTEXT == owner.KEY_CONTEXT
    # Manager never issues Runtime execute authority (Stage C not wired).
    with pytest.raises(manager_owner.OwnerAuthorizationError):
        manager_owner.issue_bundle_operation(
            credential=OWNER_TOKEN, action="asset.execute", device_id=DEV,
            subject_sha256=SHA, transaction_id=TX)


@pytest.mark.parametrize("field,value,code", [
    ("mac", "0" * 64, "OWNER_AUTHORIZATION_INVALID"),          # forged MAC
    ("subject_sha256", "e" * 64, "OWNER_AUTHORIZATION_INVALID"),  # tampered claim
    ("action", "bundle.install", "OWNER_AUTHORIZATION_INVALID"),
    ("action", "root.shell", "OWNER_AUTHORIZATION_ACTION_DENIED"),  # unknown action
    ("schema", "plasma.ppu.bundle-authority.v2", "OWNER_AUTHORIZATION_REQUIRED"),
    ("extra", True, "OWNER_AUTHORIZATION_REQUIRED"),
    ("package_identity_sha256", "f" * 64, "OWNER_AUTHORIZATION_FIELDS_INVALID"),
])
def test_forged_or_tampered_authorization_denied(field, value, code):
    auth = owner.issue(credential=OWNER_TOKEN, action=owner.ADMIT, device_id=DEV,
                       subject_sha256=SHA, transaction_id=TX)
    auth[field] = value
    with pytest.raises(owner.OwnerAuthorizationDenied, match=code):
        owner.verify(auth, credential=OWNER_TOKEN, action=owner.ADMIT,
                     device_id=DEV, subject_sha256=SHA, transaction_id=TX)


@pytest.mark.parametrize("expected,code", [
    ({"credential": "a-different-paired-credential-" + "r" * 8}, "OWNER_AUTHORIZATION_INVALID"),
    ({"device_id": "ppu-device-" + "e" * 24}, "OWNER_AUTHORIZATION_DEVICE_MISMATCH"),
    ({"subject_sha256": "e" * 64}, "OWNER_AUTHORIZATION_SUBJECT_MISMATCH"),
    ({"transaction_id": "e" * 32}, "OWNER_AUTHORIZATION_TRANSACTION_MISMATCH"),
    ({"action": owner.INSTALL}, "OWNER_AUTHORIZATION_ACTION_MISMATCH"),
    ({"credential": "short"}, "OWNER_AUTHORIZATION_CREDENTIAL_UNAVAILABLE"),
])
def test_authorization_is_bound_to_device_bytes_transaction_and_action(expected, code):
    auth = owner.issue(credential=OWNER_TOKEN, action=owner.ADMIT, device_id=DEV,
                       subject_sha256=SHA, transaction_id=TX)
    args = dict(credential=OWNER_TOKEN, action=owner.ADMIT, device_id=DEV,
                subject_sha256=SHA, transaction_id=TX)
    args.update(expected)
    with pytest.raises(owner.OwnerAuthorizationDenied, match=code):
        owner.verify(auth, **args)


def test_retired_allowlist_contract_is_gone():
    service_src = (ROOT / "scripts" / "ppu-bootstrap-service.py").read_text()
    assert not (ROOT / "scripts" / "ppu_bundle_authority.py").exists()
    for name in ("ppu-bootstrap-service.py", "ppu_asset_execution.py",
                 "ppu_unified_deployment.py", "ppu-bootstrap-deployment.py",
                 "ppu_deploy_api.py", "ppu_owner_authorization.py"):
        text = (ROOT / "scripts" / name).read_text()
        assert "approved_bundle_sha256" not in text, name
        assert "ppu-bundle-authority.json" not in text, name
        assert "LOCAL_APPROVED" not in text, name
    assert "bundle_authority_policy" not in service_src
    assert not hasattr(bootstrap.ServicePaths(), "bundle_authority_policy")


# --- Real HTTP B1/B2 -----------------------------------------------------------

def _raw_post(api, body, *, token=TOKEN):
    raw_body = json.dumps(body).encode()
    if token is None:
        status, raw, _headers = api._transport(
            "POST", "/v1/deployments", raw_body, {"Content-Type": "application/json"})
    else:
        status, raw = signed_call(api._transport, "POST", "/v1/deployments", raw_body,
                                  credential=token)
    return status, raw.decode()


def test_owner_admits_two_unlisted_user_bundles_without_device_preapproval(loopback, tmp_path):
    api, paths, server = loopback
    digests = []
    for index in range(2):
        archive, digest = bundle_v3(tmp_path / f"user-{index}", parts=[(
            f"user-tool-{index}", "python", [], {"python/tool.py": f"# {index}".encode()})])
        upload_id = api.upload(archive.read_bytes())
        status, raw = _raw_post(api, admit_body(paths, "bundle", upload_id))
        assert status == 200, raw
        record = json.loads(raw)["deployment"]
        assert record["result"]["owner_authorized"] is True
        plan = record["result"]["plan"]
        assert plan["owner_authorization"]["subject_sha256"] == digest
        assert plan["owner_authorization"]["transaction_id"] == upload_id
        assert plan["execution_permitted"] is False
        digests.append(digest)
    assert digests[0] != digests[1]
    # B1/B2 never install or execute anything.
    assert server.deployment_thread is None
    assert not paths.product_root.exists()
    assert not paths.coordinator_journal.exists()


@pytest.mark.parametrize("token", [None, "w" * 48])
def test_unauthenticated_request_rejected_before_admission(loopback, tmp_path, token):
    api, paths, _server = loopback
    archive, _ = bundle_v3(tmp_path)
    upload_id = api.upload(archive.read_bytes())
    status, _raw = _raw_post(api, admit_body(paths, "bundle", upload_id), token=token)
    assert status == 401
    assert not paths.deployment_record.exists()


@pytest.mark.parametrize("overrides,code", [
    ({"device": "ppu-device-" + "e" * 24}, "OWNER_AUTHORIZATION_DEVICE_MISMATCH"),
    ({"token": "attacker-guessed-credential-" + "k" * 12}, "OWNER_AUTHORIZATION_INVALID"),
])
def test_b2_wrong_device_or_forged_authorization_denied(loopback, tmp_path, overrides, code):
    api, paths, _server = loopback
    archive, _ = bundle_v3(tmp_path)
    upload_id = api.upload(archive.read_bytes())
    status, raw = _raw_post(api, admit_body(paths, "bundle", upload_id, **overrides))
    assert status == 409 and code in raw
    assert not paths.deployment_record.exists()


def test_b2_owner_chose_different_bytes_than_uploaded_is_denied(loopback, tmp_path):
    api, paths, _server = loopback
    archive, digest = bundle_v3(tmp_path)
    upload_id = api.upload(archive.read_bytes())
    body = {"kind": "bundle", "upload_id": upload_id,
            "authorization": authorize(paths, owner.ADMIT, "e" * 64, upload_id)}
    status, raw = _raw_post(api, body)
    assert status == 409 and "OWNER_AUTHORIZATION_SUBJECT_MISMATCH" in raw
    # Same authorization replayed against another upload also fails.
    other, _ = bundle_v3(tmp_path / "other", parts=[("x", "python", [], {"python/x.py": b"#"})])
    other_id = api.upload(other.read_bytes())
    replay = {"kind": "bundle", "upload_id": other_id,
              "authorization": authorize(paths, owner.ADMIT, digest, upload_id)}
    status, raw = _raw_post(api, replay)
    assert status == 409 and "OWNER_AUTHORIZATION_SUBJECT_MISMATCH" in raw
    assert not paths.deployment_record.exists()


@pytest.mark.parametrize("action", [owner.INSTALL, owner.ACTIVATE,
                                     owner.ACTIVATE_FPGA_LOAD])
def test_b2_rejects_authorization_for_another_stage(loopback, tmp_path, action):
    api, paths, _server = loopback
    archive, digest = bundle_v3(tmp_path)
    upload_id = api.upload(archive.read_bytes())
    body = {"kind": "bundle", "upload_id": upload_id,
            "authorization": authorize(paths, action, digest, upload_id)}
    status, raw = _raw_post(api, body)
    assert status == 409 and "OWNER_AUTHORIZATION_ACTION_MISMATCH" in raw


def test_b2_wrong_target_still_denied_for_authorized_owner(loopback, tmp_path):
    api, paths, _server = loopback
    archive, _ = bundle_v3(tmp_path, mutate=lambda m: m["target"].__setitem__(
        "board", "unknown-board"))
    upload_id = api.upload(archive.read_bytes())
    status, raw = _raw_post(api, admit_body(paths, "bundle", upload_id))
    assert status == 409 and "BUNDLE_MANIFEST_CONTENT_DENIED" in raw
    assert not paths.deployment_record.exists()


# --- B3 -------------------------------------------------------------------------

def _admitted(tmp_path):
    srv, paths, calls = _b3_server(tmp_path)
    archive, _digest = build_smoke(tmp_path / "bundle")
    upload_id = _commit(paths, archive.read_bytes())
    b2 = srv.start_deployment(admit_body(paths, "bundle", upload_id))
    assert b2["state"] == "admitted"
    return srv, paths, calls, b2


def test_b3_owner_install_binds_current_admission_and_records_receipt(tmp_path):
    srv, paths, calls, b2 = _admitted(tmp_path)
    record = srv.start_deployment(install_body(paths, b2, fpga_load=False))
    srv.deployment_thread.join(timeout=10)
    assert len(calls) == 1 and calls[0][2]["fpga_load"] is False
    assert record["admission_transaction_id"] == b2["transaction_id"]
    receipt = record["owner_authorization"]
    assert receipt["action"] == "bundle.install"
    assert receipt["transaction_id"] == b2["transaction_id"]
    assert receipt["subject_sha256"] == b2["result"]["plan"]["archive_sha256"]
    assert receipt["device_id"] == device_id(paths)


@pytest.mark.parametrize("mutate,code", [
    (lambda b: b.pop("authorization"), "B3_INSTALL_REQUEST_FIELDS_DENIED"),
    (lambda b: b["authorization"].__setitem__("mac", "0" * 64), "OWNER_AUTHORIZATION_INVALID"),
])
def test_b3_without_or_with_forged_authorization_denied(tmp_path, mutate, code):
    srv, paths, calls, b2 = _admitted(tmp_path)
    body = install_body(paths, b2, fpga_load=False)
    mutate(body)
    with pytest.raises(bootstrap.BootstrapServiceError, match=code):
        srv.start_deployment(body)
    assert calls == [] and srv.deployment_thread is None


def test_b3_stage_authorization_cannot_activate_and_activation_cannot_stage(tmp_path):
    srv, paths, calls, b2 = _admitted(tmp_path)
    staged = install_body(paths, b2, fpga_load=False, mode="stage_only")
    with pytest.raises(bootstrap.BootstrapServiceError, match="ACTION_MISMATCH"):
        srv.start_deployment({**staged, "mode": "activate"})
    activating = install_body(paths, b2, fpga_load=False, mode="activate")
    with pytest.raises(bootstrap.BootstrapServiceError, match="ACTION_MISMATCH"):
        srv.start_deployment({**activating, "mode": "stage_only"})
    assert calls == [] and srv.deployment_thread is None


def test_b3_wrong_device_and_changed_bundle_sha_denied(tmp_path):
    srv, paths, calls, b2 = _admitted(tmp_path)
    with pytest.raises(bootstrap.BootstrapServiceError, match="DEVICE_MISMATCH"):
        srv.start_deployment(install_body(paths, b2, fpga_load=False,
                                          device="ppu-device-" + "e" * 24))
    body = install_body(paths, b2, fpga_load=False)
    body["authorization"] = authorize(paths, owner.INSTALL, "e" * 64, b2["transaction_id"])
    with pytest.raises(bootstrap.BootstrapServiceError, match="SUBJECT_MISMATCH"):
        srv.start_deployment(body)
    assert calls == []


def test_b3_content_changed_after_b2_denied(tmp_path):
    srv, paths, calls, b2 = _admitted(tmp_path)
    committed = bootstrap._upload_paths(paths, b2["upload_id"]).committed
    committed.chmod(0o600)
    committed.write_bytes(committed.read_bytes() + b"tampered")
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_UPLOADED_ARCHIVE_CHANGED"):
        srv.start_deployment(install_body(paths, b2, fpga_load=False))
    assert calls == []


def test_b3_target_changed_after_b2_denied(tmp_path):
    srv, paths, calls, b2 = _admitted(tmp_path)
    target = json.loads(paths.package_target_file.read_text())
    paths.package_target_file.write_text(json.dumps(dict(target, board="other-board")))
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_ADMISSION_NOT_QUALIFIED"):
        srv.start_deployment(install_body(paths, b2, fpga_load=False))
    assert calls == []


def test_b3_stale_transaction_after_new_b2_and_expired_admission_denied(tmp_path):
    srv, paths, calls, first = _admitted(tmp_path)
    stale = install_body(paths, first, fpga_load=False)
    # A new B2 for the same upload supersedes the first admission.
    second = srv.start_deployment(admit_body(paths, "bundle", first["upload_id"]))
    assert second["transaction_id"] != first["transaction_id"]
    with pytest.raises(bootstrap.BootstrapServiceError, match="TRANSACTION_MISMATCH"):
        srv.start_deployment(stale)
    # The device-clock admission window elapsed.
    record = json.loads(paths.deployment_record.read_text())
    record["started_at_epoch_s"] = time.time() - bootstrap.B2_ADMISSION_TTL_S - 5
    paths.deployment_record.write_text(json.dumps(record))
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_B2_ADMISSION_EXPIRED"):
        srv.start_deployment(install_body(paths, second, fpga_load=False))
    assert calls == []


def test_b3_replay_after_success_and_running_job_denied(tmp_path):
    srv, paths, calls, b2 = _admitted(tmp_path)
    gate = threading.Event()
    srv.bundle_install_runner = lambda *args: gate.wait(10) and calls.append(args) or {}
    body = install_body(paths, b2, fpga_load=False)
    srv.start_deployment(body)
    try:
        # A Bootstrap deployment Job is running: neither B2 nor B3 may start.
        with pytest.raises(bootstrap.BootstrapServiceError, match="B3_DEPLOYMENT_ALREADY_RUNNING"):
            srv.start_deployment(install_body(paths, b2, fpga_load=False))
        with pytest.raises(bootstrap.BootstrapServiceError, match="already running"):
            srv.start_deployment(admit_body(paths, "bundle", b2["upload_id"]))
    finally:
        gate.set()
        srv.deployment_thread.join(timeout=10)
    # The one-shot authorization cannot be replayed: B2 is no longer current.
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_MATCHING_B2_ADMISSION_REQUIRED"):
        srv.start_deployment(body)
    assert len(calls) == 1


def test_b3_unapproved_package_actions_or_fpga_widening_denied(tmp_path):
    srv, paths, calls = _b3_server(tmp_path)
    # Bundle requesting activate/rollback Root actions is admitted-for-review
    # only; B3 never performs actions outside the factory install policy.
    archive, _ = build_smoke(tmp_path / "bundle")
    from .test_ppu_bundle_v3_packages_contract import bundle_v3 as build
    wide, _ = build(tmp_path / "wide", parts=[("tool", "python", [], {"python/t.py": b"#"})])
    upload_id = _commit(paths, wide.read_bytes())
    b2 = srv.start_deployment(admit_body(paths, "bundle", upload_id))
    assert b2["result"]["plan"]["requested_actions"] != ["install", "verify"]
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_ADMISSION_NOT_QUALIFIED"):
        srv.start_deployment(install_body(paths, b2, fpga_load=False))
    # Install-only owner authorization cannot be widened to an FPGA load.
    upload_id = _commit(paths, archive.read_bytes())
    b2 = srv.start_deployment(admit_body(paths, "bundle", upload_id))
    widened = dict(install_body(paths, b2, fpga_load=False),
                   mode="activate", fpga_load=True)
    with pytest.raises(bootstrap.BootstrapServiceError, match="ACTION_MISMATCH"):
        srv.start_deployment(widened)
    assert calls == []


def test_b2_and_b3_require_the_device_identity_and_credential(tmp_path):
    srv, paths, calls, b2 = _admitted(tmp_path)
    body = install_body(paths, b2, fpga_load=False)
    machine = paths.machine_id_path.read_text()
    paths.machine_id_path.write_text("not-hex\n")
    with pytest.raises(bootstrap.BootstrapServiceError,
                       match="OWNER_AUTHORIZATION_DEVICE_IDENTITY_UNAVAILABLE"):
        srv.start_deployment(body)
    paths.machine_id_path.write_text(machine)
    clear_controller(paths.state_root)
    with pytest.raises(bootstrap.BootstrapServiceError, match="CONTROLLER_NOT_ENROLLED"):
        srv.start_deployment(body)
    assert calls == []

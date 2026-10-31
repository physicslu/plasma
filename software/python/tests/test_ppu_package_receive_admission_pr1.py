"""PR 1: real HTTP upload, generic manifest admission and no execution."""
from __future__ import annotations

import hashlib
import http.client
import json
import threading
from pathlib import Path
from types import SimpleNamespace

import pytest

from .test_ppu_generic_package_host_only_gate1 import load, package, SAMPLES, TARGET

service = load("ppu_package_receive_service_pr1", "ppu-bootstrap-service.py")
client = load("ppu_package_receive_client_pr1", "ppu_deploy_api.py")
TOKEN = "t" * 48


@pytest.fixture
def loopback(tmp_path: Path):
    state = tmp_path / "state"
    target_file = tmp_path / "target.json"
    target_file.write_text(json.dumps(TARGET), encoding="utf-8")
    target_file.chmod(0o600)
    paths = service.ServicePaths(
        state_root=state, product_root=tmp_path / "product-untouched",
        package_target_file=target_file,
    )
    service.provision_token(paths.token_file, token=TOKEN)
    server = service.BootstrapHTTPServer(
        ("127.0.0.1", 0), paths=paths, base_module=SimpleNamespace(),
        deployment_runner=lambda *_: pytest.fail("unexpected deployment runner"),
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    def transport(method, path, data, headers):
        connection = http.client.HTTPConnection("127.0.0.1", server.server_address[1], timeout=5)
        try:
            connection.request(method, path, body=data, headers=headers)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    api = client.BootstrapAPIClient(
        "https://ppu.host-only.invalid:18081", TOKEN, transport=transport,
    )
    try:
        yield api, paths, server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(5)


@pytest.mark.parametrize("name,kind,files", SAMPLES)
def test_real_http_accepts_manifest_actions_without_install(loopback, tmp_path, name, kind, files):
    # Reuse the same HTTP upload and admission path; only the ZIP contract changes.
    from .test_ppu_bundle_v3_packages_contract import bundle_v3

    api, paths, server = loopback
    package_files = {
        filename.removeprefix("payload/"): data for filename, data in files.items()
    }
    archive, digest = bundle_v3(
        tmp_path, parts=[(name, kind, [], package_files)]
    )
    upload_id = api.upload(archive.read_bytes())
    submission = api.submit(kind="bundle", upload_id=upload_id)
    assert submission.state == "admitted"
    receipt = api.deployment_state(submission.transaction_id)
    result = receipt["result"]
    plan = result["plan"]
    assert result["stage"] == "package_admission_only"
    assert result["install_qualified"] is False
    assert plan["archive_sha256"] == digest
    assert plan["kind"] == "bundle"
    assert plan["bundle_schema"] == "plasma.ppu.bundle.v3"
    assert len(plan["packages"]) == 1
    assert plan["packages"][0]["id"] == name
    assert plan["packages"][0]["kind"] == kind
    assert plan["requested_actions"] == ["install", "verify", "activate", "rollback"]
    assert plan["execution_permitted"] is False
    assert plan["target"] == TARGET
    assert len(plan["files"]) == len(files)
    assert server.deployment_thread is None
    assert not paths.product_root.exists()
    assert not paths.coordinator_journal.exists()
    persisted = service._deployment_api_record(paths)
    assert persisted["transaction_id"] == submission.transaction_id
    assert persisted["result"]["plan"] == plan


@pytest.mark.parametrize("alterations,error", [
    ({"actions": ["shell", "verify"]}, "PACKAGE_ACTIONS_DENIED"),
    ({"actions": ["verify", "verify"]}, "PACKAGE_ACTIONS_DENIED"),
    ({"actions": ["install", {"shell": "rm"}]}, "PACKAGE_ACTIONS_DENIED"),
    ({"target": {**TARGET, "board": "unknown-board"}}, "PACKAGE_MANIFEST_CONTENT_DENIED"),
    ({"source_commit": "not-a-sha"}, "PACKAGE_MANIFEST_CONTENT_DENIED"),
    ({"files": [{"path": "payload/python/fake.py", "sha256": "0"*64,
                 "size": 3, "executable": False}]}, "PACKAGE_MEMBER_MISSING"),
])
def test_real_http_rejects_bad_manifest_without_side_effects(
    loopback, tmp_path, alterations, error,
):
    api, paths, server = loopback
    archive, _ = package(
        tmp_path, "wordport", "python", {"payload/python/wordport.py": b"print('test')"},
        alterations=alterations,
    )
    upload_id = api.upload(archive.read_bytes())
    with pytest.raises(client.DeploymentAPIError, match="API_HTTP_REJECTED:409"):
        api.submit(kind="python", upload_id=upload_id)
    assert not paths.deployment_record.exists()
    assert not paths.coordinator_journal.exists()
    assert not paths.product_root.exists()
    assert server.deployment_thread is None


def test_real_http_wrong_kind_or_spoofed_authority_denied(loopback, tmp_path):
    api, paths, _ = loopback
    archive, _ = package(tmp_path, "wordport", "python",
                         {"payload/python/wordport.py": b"# fixture"})
    upload_id = api.upload(archive.read_bytes())
    with pytest.raises(client.DeploymentAPIError, match="API_HTTP_REJECTED:409"):
        api.submit(kind="native-c", upload_id=upload_id)
    with pytest.raises(client.DeploymentAPIError, match="API_GENERIC_CALLER_AUTHORITY_DENIED"):
        api.submit(kind="python", upload_id=upload_id, ppu_id="spoof")
    assert not paths.deployment_record.exists()


def test_target_profile_missing_or_untrusted_fails_closed(loopback, tmp_path):
    api, paths, _ = loopback
    archive, _ = package(tmp_path, "wordport", "python",
                         {"payload/python/wordport.py": b"# fixture"})
    upload_id = api.upload(archive.read_bytes())
    paths.package_target_file.chmod(0o644)
    with pytest.raises(client.DeploymentAPIError, match="API_HTTP_REJECTED:409"):
        api.submit(kind="python", upload_id=upload_id)
    paths.package_target_file.unlink()
    with pytest.raises(client.DeploymentAPIError, match="API_HTTP_REJECTED:409"):
        api.submit(kind="python", upload_id=upload_id)
    assert not paths.deployment_record.exists()


def test_archive_changed_after_upload_commit_fails_closed(loopback, tmp_path):
    api, paths, _ = loopback
    archive, _ = package(tmp_path, "wordport", "python",
                         {"payload/python/wordport.py": b"# fixture"})
    upload_id = api.upload(archive.read_bytes())
    destination = service._upload_paths(paths, upload_id).committed
    destination.chmod(0o600)
    destination.write_bytes(b"corrupted-after-commit")
    with pytest.raises(client.DeploymentAPIError, match="API_HTTP_REJECTED:409"):
        api.submit(kind="python", upload_id=upload_id)
    assert not paths.deployment_record.exists()


def test_retired_v1_manifest_rejected_after_unchanged_upload(loopback, tmp_path):
    """Legacy content may be transported, but must fail at Admission."""
    api, paths, server = loopback
    archive, _ = package(tmp_path, "wordport", "python",
                         {"payload/python/wordport.py": b"# legacy"})
    uid = api.upload(archive.read_bytes())
    assert uid
    with pytest.raises(client.DeploymentAPIError, match="API_HTTP_REJECTED:409"):
        api.submit(kind="python", upload_id=uid)
    assert not paths.deployment_record.exists()
    assert not paths.product_root.exists()
    assert server.deployment_thread is None


def test_generic_requires_control_token(loopback, tmp_path):
    api, paths, _ = loopback
    archive, _ = package(tmp_path, "wordport", "python",
                         {"payload/python/wordport.py": b"# fixture"})
    bad = client.BootstrapAPIClient(api._base_url if hasattr(api, "_base_url") else
                                   "https://ppu.host-only.invalid:18081",
                                   "x" * 48, transport=api._transport)
    with pytest.raises(client.DeploymentAPIError, match="API_HTTP_REJECTED:401"):
        bad.upload(archive.read_bytes())
    assert not paths.deployment_record.exists()


@pytest.mark.parametrize("malformed_kind", [[], ["python"], {}, {"kind": "python"}])
def test_http_unhashable_kind_is_rejected_without_losing_service(loopback, tmp_path, malformed_kind):
    # Keep the HTTP negative cases; use the canonical v3 positive control.
    from .test_ppu_bundle_v3_packages_contract import bundle_v3

    api, paths, server = loopback
    archive, _ = bundle_v3(
        tmp_path, parts=[("wordport", "python", [], {"python/wordport.py": b"# valid"})]
    )
    upload_id = api.upload(archive.read_bytes())
    with pytest.raises(client.DeploymentAPIError, match="API_HTTP_REJECTED:409"):
        api._call("POST", "/v1/deployments", {"kind": malformed_kind, "upload_id": upload_id})
    assert not paths.deployment_record.exists()
    assert server.deployment_thread is None
    valid = api.submit(kind="bundle", upload_id=upload_id)
    assert valid.state == "admitted"


def test_client_rejects_admission_without_a_nonexecuting_plan():
    transaction_id = "a" * 32
    upload_id = "b" * 32

    def fake_transport(method, path, data, headers):
        # A compromised or buggy server may claim "admitted" without a plan.
        receipt = {
            "transaction_id": transaction_id, "state": "admitted",
            "upload_id": upload_id, "result": {
                "result": "PASS", "stage": "package_admission_only",
                "install_qualified": False,
                "plan": {"kind": "python", "execution_permitted": True},
            },
        }
        if path in ("/v1/deployments", "/v1/deployment"):
            return 200, json.dumps({"ok": True, "deployment": receipt}).encode()
        raise AssertionError(path)

    api = client.BootstrapAPIClient(
        "https://ppu.host-only.invalid:18081", TOKEN, transport=fake_transport,
    )
    with pytest.raises(client.DeploymentOutcomeUnknown, match="API_ADMISSION_RECEIPT_UNKNOWN"):
        api.submit(kind="python", upload_id=upload_id)
    with pytest.raises(client.DeploymentOutcomeUnknown, match="API_ADMISSION_EVIDENCE_MISSING"):
        api.deployment_state(transaction_id)


def test_client_rejects_incorrect_kind_in_admission_receipt():
    transaction_id = "a" * 32
    upload_id = "b" * 32

    def fake_transport(method, path, data, headers):
        receipt = {
            "transaction_id": transaction_id, "state": "admitted",
            "upload_id": upload_id, "result": {
                "result": "PASS", "stage": "package_admission_only",
                "install_qualified": False,
                "plan": {
                    "kind": "fpga-image", "execution_permitted": False,
                    "archive_sha256": "f" * 64, "files": [],
                    "requested_actions": [],
                },
            },
        }
        return 200, json.dumps({"ok": True, "deployment": receipt}).encode()

    api = client.BootstrapAPIClient(
        "https://ppu.host-only.invalid:18081", TOKEN, transport=fake_transport,
    )
    with pytest.raises(client.DeploymentOutcomeUnknown, match="API_ADMISSION_RECEIPT_UNKNOWN"):
        api.submit(kind="python", upload_id=upload_id)

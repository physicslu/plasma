from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
BASE_SCRIPT = ROOT / "scripts" / "ppu-bootstrap.py"
SERVICE_SCRIPT = ROOT / "scripts" / "ppu-bootstrap-service.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base = _load(BASE_SCRIPT, "test_ppu_bootstrap_service_base")
service = _load(SERVICE_SCRIPT, "test_ppu_bootstrap_service")


def _paths(tmp_path: Path):
    machine = tmp_path / "etc" / "machine-id"
    machine.parent.mkdir(parents=True)
    machine.write_text("0123456789abcdef0123456789abcdef\n", encoding="utf-8")
    kit_tool = tmp_path / "bootstrap" / "ppu-bootstrap-kit.py"
    kit_tool.parent.mkdir(parents=True)
    kit_tool.write_text("# kit tool\n", encoding="utf-8")
    return service.ServicePaths(
        product_root=tmp_path / "opt" / "plasma",
        state_root=tmp_path / "var" / "lib" / "plasma-bootstrap",
        machine_id_path=machine,
        bootstrap_script=BASE_SCRIPT,
        kit_tool=kit_tool,
    )


def _request(url: str, *, method="GET", body=None, token=None):
    data = None if body is None else json.dumps(body).encode("utf-8")
    headers = {"Accept": "application/json"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read().decode("utf-8"))


def _server(tmp_path: Path, *, runner=None):
    paths = _paths(tmp_path)
    server = service.BootstrapHTTPServer(
        ("127.0.0.1", 0),
        paths=paths,
        base_module=base,
        deployment_runner=runner or service.run_deployment_subprocess,
    )
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    return paths, server, thread, f"http://{host}:{port}"


def _stop(server, thread):
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def _committed_upload(paths, content=b"kit"):
    created = service.create_upload(paths, size=len(content), sha256=hashlib.sha256(content).hexdigest())
    upload_id = created["upload_id"]
    service.append_chunk(
        paths,
        upload_id,
        offset=0,
        data_base64=base64.b64encode(content).decode(),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    service.commit_upload(paths, upload_id)
    return upload_id


def _deployment_body(upload_id: str):
    return {
        "upload_id": upload_id,
        "gateway_host": "192.168.2.99",
        "ppu_id": "ppu-01",
        "facility_id": "lab",
        "display_name": "PPU 01",
    }


def _write_api_record(paths, *, upload_id: str, state: str, mode=0o600):
    record = {
        "schema_version": 1,
        "transaction_id": "tx-old",
        "state": state,
        "upload_id": upload_id,
        "started_at_epoch_s": 10.0,
        "updated_at_epoch_s": 11.0,
        "error_code": None,
        "error": None,
        "result": None,
    }
    service._atomic_json(paths.deployment_record, record)
    paths.deployment_record.chmod(mode)
    return record


def test_token_provisioning_is_local_and_mode_0600(tmp_path: Path):
    token_file = tmp_path / "state" / "control-token"
    token = service.provision_token(token_file, token="x" * 40)
    assert token == "x" * 40
    assert token_file.read_text(encoding="utf-8").strip() == token
    assert token_file.stat().st_mode & 0o777 == 0o600
    with pytest.raises(service.BootstrapServiceError, match="already exists"):
        service.provision_token(token_file, token="y" * 40)
    assert service.provision_token(token_file, rotate=True, token="z" * 40) == "z" * 40


def test_mutations_fail_closed_without_or_with_wrong_token(tmp_path: Path):
    paths, server, thread, base_url = _server(tmp_path)
    try:
        status, payload = _request(
            f"{base_url}/v1/uploads",
            method="POST",
            body={"size": 3, "sha256": hashlib.sha256(b"abc").hexdigest()},
        )
        assert status == 503
        assert payload["error"] == "control_not_provisioned"

        service.provision_token(paths.token_file, token="t" * 40)
        status, payload = _request(
            f"{base_url}/v1/uploads",
            method="POST",
            token="w" * 40,
            body={"size": 3, "sha256": hashlib.sha256(b"abc").hexdigest()},
        )
        assert status == 401
        assert payload["error"] == "unauthorized"
    finally:
        _stop(server, thread)


def test_chunked_upload_enforces_offset_chunk_hash_and_whole_hash(tmp_path: Path):
    paths, server, thread, base_url = _server(tmp_path)
    token = service.provision_token(paths.token_file, token="t" * 40)
    content = b"abcdef"
    try:
        status, payload = _request(
            f"{base_url}/v1/uploads",
            method="POST",
            token=token,
            body={"size": len(content), "sha256": hashlib.sha256(content).hexdigest()},
        )
        assert status == 201
        upload_id = payload["upload"]["upload_id"]

        chunk = content[:3]
        status, payload = _request(
            f"{base_url}/v1/uploads/{upload_id}/chunks",
            method="POST",
            token=token,
            body={
                "offset": 1,
                "data_base64": base64.b64encode(chunk).decode(),
                "sha256": hashlib.sha256(chunk).hexdigest(),
            },
        )
        assert status == 409
        assert "offset" in payload["message"]

        status, _ = _request(
            f"{base_url}/v1/uploads/{upload_id}/chunks",
            method="POST",
            token=token,
            body={
                "offset": 0,
                "data_base64": base64.b64encode(chunk).decode(),
                "sha256": "0" * 64,
            },
        )
        assert status == 409

        for offset, part in ((0, content[:3]), (3, content[3:])):
            status, payload = _request(
                f"{base_url}/v1/uploads/{upload_id}/chunks",
                method="POST",
                token=token,
                body={
                    "offset": offset,
                    "data_base64": base64.b64encode(part).decode(),
                    "sha256": hashlib.sha256(part).hexdigest(),
                },
            )
            assert status == 200
            assert payload["upload"]["received_bytes"] == offset + len(part)

        status, payload = _request(
            f"{base_url}/v1/uploads/{upload_id}/commit",
            method="POST",
            token=token,
            body={"action": "commit"},
        )
        assert status == 200
        assert payload["upload"]["state"] == "committed"
        uploaded = service._upload_paths(paths, upload_id)
        assert uploaded.committed.read_bytes() == content
        assert not uploaded.partial.exists()
        assert uploaded.sidecar.is_file()
    finally:
        _stop(server, thread)


def test_commit_rejects_wrong_complete_digest(tmp_path: Path):
    paths = _paths(tmp_path)
    content = b"abc"
    upload = service.create_upload(paths, size=3, sha256="0" * 64)
    uid = upload["upload_id"]
    service.append_chunk(
        paths,
        uid,
        offset=0,
        data_base64=base64.b64encode(content).decode(),
        sha256=hashlib.sha256(content).hexdigest(),
    )
    with pytest.raises(service.BootstrapServiceError, match="complete upload"):
        service.commit_upload(paths, uid)
    files = service._upload_paths(paths, uid)
    assert files.partial.is_file()
    assert not files.committed.exists()


def test_status_exposes_reserved_fpga_boundary_and_security_state(tmp_path: Path):
    paths, server, thread, base_url = _server(tmp_path)
    try:
        status, payload = _request(f"{base_url}/v1/status")
        assert status == 200
        assert payload["capabilities"]["fpga_update"] is False
        assert payload["capabilities"]["runtime_deployment"] is False
        assert payload["fpga"]["pl_compatibility"] == "not_managed"
        assert payload["security"] == {
            "control_token_provisioned": False,
            "transport_confidentiality": "not_qualified",
            "publisher_authenticity": "not_qualified",
        }

        service.provision_token(paths.token_file, token="t" * 40)
        status, payload = _request(f"{base_url}/v1/status")
        assert status == 200
        assert payload["capabilities"]["runtime_deployment"] is True
        assert payload["capabilities"]["fpga_update"] is False
    finally:
        _stop(server, thread)


def test_deployment_is_async_single_flight_and_pollable(tmp_path: Path):
    started = threading.Event()
    release = threading.Event()

    def fake_runner(paths, upload_id, request):
        started.set()
        assert release.wait(timeout=2)
        return {"result": "PASS", "kit_release_id": "1.2.3-aaaaaaaaaaaa"}

    paths, server, thread, base_url = _server(tmp_path, runner=fake_runner)
    token = service.provision_token(paths.token_file, token="t" * 40)
    content = b"kit"
    try:
        _, created = _request(
            f"{base_url}/v1/uploads",
            method="POST",
            token=token,
            body={"size": 3, "sha256": hashlib.sha256(content).hexdigest()},
        )
        uid = created["upload"]["upload_id"]
        _request(
            f"{base_url}/v1/uploads/{uid}/chunks",
            method="POST",
            token=token,
            body={
                "offset": 0,
                "data_base64": base64.b64encode(content).decode(),
                "sha256": hashlib.sha256(content).hexdigest(),
            },
        )
        _request(
            f"{base_url}/v1/uploads/{uid}/commit",
            method="POST",
            token=token,
            body={"action": "commit"},
        )
        request = _deployment_body(uid)
        status, payload = _request(
            f"{base_url}/v1/deployments",
            method="POST",
            token=token,
            body=request,
        )
        assert status == 202
        assert payload["deployment"]["state"] in {"queued", "running"}
        assert started.wait(timeout=1)

        status, payload = _request(
            f"{base_url}/v1/deployments",
            method="POST",
            token=token,
            body=request,
        )
        assert status == 409
        assert "already running" in payload["message"]

        release.set()
        deadline = time.time() + 2
        final = None
        while time.time() < deadline:
            _, polled = _request(f"{base_url}/v1/deployment")
            final = polled["deployment"]
            if final and final["state"] == "succeeded":
                break
            time.sleep(0.02)
        assert final is not None
        assert final["state"] == "succeeded"
        assert final["result"]["result"] == "PASS"
    finally:
        release.set()
        _stop(server, thread)


def test_restart_promotes_inflight_api_record_to_recovery_required(tmp_path: Path):
    paths = _paths(tmp_path)
    upload_id = _committed_upload(paths)
    _write_api_record(paths, upload_id=upload_id, state="running")

    server = service.BootstrapHTTPServer(
        ("127.0.0.1", 0),
        paths=paths,
        base_module=base,
        deployment_runner=lambda *_args: {"result": "PASS"},
    )
    try:
        recovered = service._deployment_api_record(paths)
        assert recovered is not None
        assert recovered["transaction_id"] == "tx-old"
        assert recovered["upload_id"] == upload_id
        assert recovered["state"] == "recovery_required"
        assert recovered["error_code"] == "interrupted_service_restart"
        assert "running" in recovered["error"]
        assert recovered["result"] is None
        assert paths.deployment_record.stat().st_mode & 0o077 == 0
    finally:
        server.server_close()


def test_restart_recovery_blocks_new_deployment_without_overwriting_evidence(tmp_path: Path):
    paths = _paths(tmp_path)
    upload_id = _committed_upload(paths)
    _write_api_record(paths, upload_id=upload_id, state="queued")
    server = service.BootstrapHTTPServer(
        ("127.0.0.1", 0),
        paths=paths,
        base_module=base,
        deployment_runner=lambda *_args: {"result": "PASS"},
    )
    try:
        before = paths.deployment_record.read_text(encoding="utf-8")
        with pytest.raises(service.BootstrapServiceError, match="requires explicit recovery"):
            server.start_deployment(_deployment_body(upload_id))
        after = paths.deployment_record.read_text(encoding="utf-8")
        assert after == before
        record = json.loads(after)
        assert record["state"] == "recovery_required"
        assert record["transaction_id"] == "tx-old"
    finally:
        server.server_close()


def test_invalid_or_overpermissive_api_record_prevents_service_start(tmp_path: Path):
    paths = _paths(tmp_path)
    upload_id = "a" * 32
    _write_api_record(paths, upload_id=upload_id, state="succeeded", mode=0o644)
    with pytest.raises(service.BootstrapServiceError, match="permissions are too broad"):
        service.BootstrapHTTPServer(("127.0.0.1", 0), paths=paths, base_module=base)

    paths.deployment_record.chmod(0o600)
    paths.deployment_record.write_text("not-json\n", encoding="utf-8")
    with pytest.raises(service.BootstrapServiceError, match="cannot read bootstrap state"):
        service.BootstrapHTTPServer(("127.0.0.1", 0), paths=paths, base_module=base)

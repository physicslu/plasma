"""Host-only SWPC Bootstrap HTTPS client with real existing upload validators.

All transport calls are replaced by FakeBootstrapTransport; no network, SSH,
Linux privilege, FPGA or DUT activity is possible in this suite.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]


def load(name: str, file_name: str):
    spec = importlib.util.spec_from_file_location(name, REPO / "scripts" / file_name)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


client = load("ppu_deploy_api_host", "ppu_deploy_api.py")
server = load("ppu_bootstrap_api_host", "ppu-bootstrap-service.py")
TOKEN = "a" * 48


class FakeBootstrapTransport:
    def __init__(self, tmp_path: Path):
        self.paths = server.ServicePaths(state_root=tmp_path / "bootstrap")
        self.calls: list[tuple[str, str, object]] = []
        self.upload_id: str | None = None
        self.transaction_id = "e" * 32
        self.state = "queued"
        self.expected_evidence: dict | None = None
        self.override: dict[str, object] = {}

    def __call__(self, method: str, path: str, raw: bytes | None, headers):
        assert headers["Authorization"] == "Bearer " + TOKEN
        assert method in ("POST", "GET")
        body = json.loads(raw) if raw is not None else None
        self.calls.append((method, path, body))
        if path in self.override:
            return self.override[path]
        if method == "POST" and path == "/v1/uploads":
            item = server.create_upload(self.paths, size=body["size"], sha256=body["sha256"])
            self.upload_id = item["upload_id"]
            return 201, json.dumps({"ok": True, "upload": item}).encode()
        if method == "POST" and path.endswith("/chunks"):
            receipt = server.append_chunk(
                self.paths, self.upload_id,
                offset=body["offset"],
                data_base64=body["data_base64"],
                sha256=body["sha256"],
            )
            return 200, json.dumps({"ok": True, "upload": receipt}).encode()
        if method == "POST" and path.endswith("/commit"):
            receipt = server.commit_upload(self.paths, self.upload_id)
            return 200, json.dumps({"ok": True, "upload": receipt}).encode()
        if method == "POST" and path == "/v1/deployments":
            request = server._deployment_request(body)
            assert request["upload_id"] == self.upload_id
            receipt = {
                "transaction_id": self.transaction_id,
                "state": self.state,
                "upload_id": self.upload_id,
                "result": None,
            }
            return 202, json.dumps({"ok": True, "deployment": receipt}).encode()
        if method == "GET" and path == "/v1/deployment":
            return 200, json.dumps({"ok": True, "deployment": {
                "transaction_id": self.transaction_id,
                "state": self.state,
                "result": self.expected_evidence,
            }}).encode()
        if method == "GET" and path == "/v1/status":
            return 200, b'{"ok":true,"runtime":{"state":"runtime_active"}}'
        raise AssertionError(f"Unexpected fake request: {method} {path}")


def make(tmp_path: Path):
    fake = FakeBootstrapTransport(tmp_path)
    return client.BootstrapAPIClient("https://ppu.example.test:18081", TOKEN, transport=fake), fake


def test_chunked_https_upload_integrates_with_existing_bootstrap_validators(tmp_path: Path):
    api, fake = make(tmp_path)
    artifact = b"full-size-runtime-archive" * 50_000  # > 1 MiB and crosses chunk boundary
    upload_id = api.upload(artifact)
    assert upload_id == fake.upload_id
    assert fake.calls[0][1] == "/v1/uploads"
    assert len([x for x in fake.calls if x[1].endswith("/chunks")]) == 2
    assert fake.calls[-1][1] == f"/v1/uploads/{upload_id}/commit"
    stored = fake.paths.uploads_root / f"{upload_id}.bin"
    # Bootstrap's real _upload_paths uses canonical object names; inspect receipt.
    committed = server._upload_paths(fake.paths, upload_id)
    assert committed.committed.read_bytes() == artifact
    assert hashlib.sha256(committed.committed.read_bytes()).hexdigest() == hashlib.sha256(artifact).hexdigest()
    assert committed.meta.is_file()


def test_ps_runtime_submission_and_status_without_ssh(tmp_path: Path):
    api, fake = make(tmp_path)
    uploaded = api.upload(b"host-only-synthetic-runtime")
    start = api.submit(
        kind="ppu-runtime", upload_id=uploaded,
        gateway_host="10.20.30.40", ppu_id="z2-01",
        facility_id="lab", display_name="PPU Z2",
    )
    assert start.transaction_id == fake.transaction_id
    assert start.state == "queued"
    assert api.deployment_state(start.transaction_id)["state"] == "queued"
    fake.state = "running"
    assert api.deployment_state(start.transaction_id)["state"] == "running"
    fake.state = "succeeded"
    fake.expected_evidence = {"result": "PASS"}
    assert api.deployment_state(start.transaction_id)["state"] == "succeeded"
    assert api.status()["runtime"]["state"] == "runtime_active"
    assert not any("ssh" in url for _, url, _ in fake.calls)


@pytest.mark.parametrize("kind", ["engineering-module", "fpga-image", "root-shell"])
def test_unqualified_deployment_denied_before_any_network(kind: str, tmp_path: Path):
    api, fake = make(tmp_path)
    with pytest.raises(client.DeploymentAPIError, match="NOT_QUALIFIED|DENIED"):
        api.submit(
            kind=kind, module="wordport", upload_id="a"*32,
            gateway_host="10.20.30.40", ppu_id="ppu-01",
            facility_id="lab", display_name="PPU",
        )
    assert fake.calls == []


@pytest.mark.parametrize("url", [
    "http://ppu.example.test:18081",
    "http://127.0.0.1:18081",
    "https://user:password@ppu.example.test",
    "https://ppu.example.test/prefix",
    "https://ppu.example.test?redirect=x",
    "https://ppu.example.test#fragment",
    "ftp://ppu.example.test",
    "https://ppu.example.test:0",
    "",
])
def test_client_requires_https_without_embedded_credentials(url: str):
    with pytest.raises(client.DeploymentAPIError, match="HTTPS|PORT"):
        client.BootstrapAPIClient(url, TOKEN, transport=lambda *_: (200, b'{"ok":true}'))


@pytest.mark.parametrize("bad", ["", "a", "bad\nvalue", "\x00" * 48])
def test_client_rejects_bad_credentials(bad: str):
    with pytest.raises(client.DeploymentAPIError, match="BEARER"):
        client.BootstrapAPIClient("https://ppu.example.test", bad, transport=lambda *_: (200, b'{"ok":true}'))


def test_malformed_progress_is_unknown_not_success(tmp_path: Path):
    api, fake = make(tmp_path)
    payload = b"demo"
    upload_id = "a"*32
    fake.override["/v1/uploads"] = (201, json.dumps({
        "ok": True, "upload": {"upload_id": upload_id},
    }).encode())
    fake.override[f"/v1/uploads/{upload_id}/chunks"] = (
        200, json.dumps({"ok": True, "upload": {
            "upload_id": upload_id, "received_bytes": 1,
        }}).encode()
    )
    with pytest.raises(client.DeploymentOutcomeUnknown, match="PROGRESS_UNKNOWN"):
        api.upload(payload)
    assert len(fake.calls) == 2


def test_missing_committed_digest_is_unknown(tmp_path: Path):
    api, fake = make(tmp_path)
    upload_id = "a"*32
    fake.override["/v1/uploads"] = (201, json.dumps({
        "ok": True, "upload": {"upload_id": upload_id},
    }).encode())
    fake.override[f"/v1/uploads/{upload_id}/chunks"] = (
        200, json.dumps({"ok": True, "upload": {
            "upload_id": upload_id, "received_bytes": 4,
        }}).encode()
    )
    fake.override[f"/v1/uploads/{upload_id}/commit"] = (
        200, json.dumps({"ok": True, "upload": {
            "upload_id": upload_id, "state": "committed", "sha256": "f"*64,
        }}).encode()
    )
    with pytest.raises(client.DeploymentOutcomeUnknown, match="COMMIT_UNKNOWN"):
        api.upload(b"demo")


@pytest.mark.parametrize("state", ["succeeded", "recovery_required", "failed"])
def test_terminal_state_requires_real_positive_receipt(tmp_path: Path, state: str):
    api, fake = make(tmp_path)
    fake.state = state
    if state == "succeeded":
        with pytest.raises(client.DeploymentOutcomeUnknown, match="SUCCESS_EVIDENCE"):
            api.deployment_state(fake.transaction_id)
        fake.expected_evidence = {"result": "PASS"}
    assert api.deployment_state(fake.transaction_id)["state"] == state


def test_unknown_transaction_mismatch_is_never_auto_retried(tmp_path: Path):
    api, fake = make(tmp_path)
    with pytest.raises(client.DeploymentOutcomeUnknown, match="STATE_UNKNOWN"):
        api.deployment_state("f"*32)
    assert len(fake.calls) == 1


def test_oversize_response_and_error_codes_fail_closed(tmp_path: Path):
    api, fake = make(tmp_path)
    fake.override["/v1/status"] = (200, b"x" * (2*1024*1024 + 1))
    with pytest.raises(client.DeploymentAPIError, match="SIZE"):
        api.status()
    fake.override["/v1/status"] = (409, b'{"ok":false,"message":"do not leak"}')
    with pytest.raises(client.DeploymentAPIError, match="API_HTTP_REJECTED:409") as exc:
        api.status()
    assert "do not leak" not in str(exc.value)


def test_transport_uncertain_does_not_retry_or_resubmit(tmp_path: Path):
    calls = []
    def broken(method, path, payload, headers):
        calls.append(path)
        raise TimeoutError("simulated outage after Z2 possibly accepted the request")
    api = client.BootstrapAPIClient("https://ppu.example.test", TOKEN, transport=broken)
    with pytest.raises(client.DeploymentOutcomeUnknown):
        api.submit(
            kind="ppu-runtime", upload_id="a"*32,
            gateway_host="10.20.30.40", ppu_id="ppu-01",
            facility_id="lab", display_name="PPU",
        )
    assert calls == ["/v1/deployments"]


def test_no_production_ssh_cutover_or_hidden_root_calls():
    code = (REPO / "scripts" / "ppu_deploy_api.py").read_text()
    import ast
    tree = ast.parse(code)
    imports = {
        alias.name for node in ast.walk(tree)
        if isinstance(node, ast.Import) for alias in node.names
    } | {
        node.module for node in ast.walk(tree)
        if isinstance(node, ast.ImportFrom)
    }
    assert "subprocess" not in imports and "os" not in imports
    assert "password_ssh_z2" not in code
    assert "sudo " not in code and "os.geteuid" not in code
    existing = (REPO / "scripts" / "ppu_deploy.py").read_text()
    assert "password_ssh_z2" in existing  # remains until separately qualified migration
    server_source = (REPO / "scripts" / "ppu-bootstrap-service.py").read_text()
    assert "ENGINEERING_INSTALL_NOT_QUALIFIED" in server_source

def test_swpc_cli_requires_private_local_token_file(tmp_path: Path):
    swpc = load("ppu_deploy_api_cli_token_gate1", "ppu_deploy.py")
    token = tmp_path / "bootstrap-token"
    token.write_text(TOKEN + "\n", encoding="ascii")
    token.chmod(0o644)
    with pytest.raises(swpc.DeploymentError, match="API_TOKEN_FILE_UNSAFE"):
        swpc.api_status(api_url="https://ppu.example.test:18081", token_file=token)
    token.chmod(0o600)
    alias = tmp_path / "bootstrap-token-link"
    alias.symlink_to(token)
    with pytest.raises(swpc.DeploymentError, match="API_TOKEN_FILE_UNAVAILABLE"):
        swpc.api_status(api_url="https://ppu.example.test:18081", token_file=alias)


def test_swpc_cli_api_status_requires_explicit_url_and_token(capsys):
    swpc = load("ppu_deploy_api_cli_args_gate1", "ppu_deploy.py")
    with pytest.raises(SystemExit) as exc:
        swpc.main(["api-status"])
    assert exc.value.code == 2
    assert "requires --api-url and --token-file" in capsys.readouterr().err

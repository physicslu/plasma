"""Host-only positive and negative acceptance for Path 2 physical B1/B2 CLI.

The actual physical script is never called with network. All HTTP is local
loopback using the existing Bootstrap/Admission test fixture.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
from pathlib import Path
import stat
import sys
import zipfile

import pytest

from .test_ppu_package_receive_admission_pr1 import loopback, client  # noqa: F401
from .test_ppu_generic_package_host_only_gate1 import load, SOURCE, TARGET

import importlib.util

_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = _ROOT / "scripts/ppu_path2_hardware_baseline.py"
spec = importlib.util.spec_from_file_location("ppu_path2_hardware_baseline_gate1", SCRIPT)
assert spec is not None and spec.loader is not None
baseline = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = baseline
spec.loader.exec_module(baseline)
DEVICE = "ppu-device-0123456789abcdef"


class PinnedLoopback:
    def __init__(self, actual_api, *, device_id=DEVICE, recovering=False):
        self._api = actual_api
        self.device_id = device_id
        self.recovering = recovering

    def status(self):
        return {
            "bootstrap": {"state": "bootstrap_ready", "version": "baseline-test-only"},
            "identity": {"device_id": self.device_id},
            "runtime": {"state": "runtime_active"},
            "deployment": {"state": "recovery_required"} if self.recovering else None,
        }

    def __getattr__(self, key):
        return getattr(self._api, key)


def test_archive_bytes_are_deterministic_and_never_executable():
    v1 = baseline.sample_v1(SOURCE, TARGET)
    assert v1 == baseline.sample_v1(SOURCE, TARGET)
    assert baseline.sample_v2(SOURCE, TARGET) == baseline.sample_v2(SOURCE, TARGET)
    for artifact in (v1, baseline.sample_v2(SOURCE, TARGET)):
        with zipfile.ZipFile(io.BytesIO(artifact)) as zipdata:
            manifest = json.loads(zipdata.read("manifest.json"))
            assert manifest["source_commit"] == SOURCE
            assert manifest["target"] == TARGET
            assert all(not data["executable"] for c in manifest.get("components", [])
                       for data in c["files"])
            assert not manifest.get("actions")
            assert all(not info.is_dir() for info in zipdata.infolist())


def test_real_loopback_upload_and_bundle_admission_are_independent(loopback):
    api, paths, server = loopback
    result = baseline.run(
        PinnedLoopback(api), client,
        source_sha=SOURCE, target=TARGET, expected_device_id=DEVICE,
    )
    assert result["b1"]["status"] == "PASS"
    assert result["b1"]["negative_chunk_sha256"] == "REJECTED"
    assert result["b1"]["archive_sha256"] == hashlib.sha256(
        baseline.sample_v1(SOURCE, TARGET)).hexdigest()
    assert result["b2_v1"]["status"] == "PASS"
    assert result["b2_v1"]["negatives"] == {
        "wrong_file_sha256": "REJECTED", "wrong_target": "REJECTED",
    }
    assert result["b2_v2"]["status"] == "PASS"
    assert result["baseline_qualification"] == "B1_B2_V1_V2_PASS"
    assert result["b3_install"] == "NOT_RUN"
    assert result["b4_activation_rollback"] == "NOT_RUN"
    assert result["fpga"] == result["dut"] == "NOT_RUN"
    assert server.deployment_thread is None
    assert not paths.product_root.exists()
    assert not paths.coordinator_journal.exists()


def test_wrong_pinned_identity_stops_before_first_write(loopback):
    api, paths, _ = loopback
    result = baseline.run(PinnedLoopback(api, device_id="ppu-device-other"), client,
                          source_sha=SOURCE, target=TARGET, expected_device_id=DEVICE)
    assert result["b1"] == {"status": "BLOCKED", "code": "PINNED_DEVICE_IDENTITY_MISMATCH"}
    assert result["b2_v1"]["status"] == result["b2_v2"]["status"] == "NOT_RUN"
    assert not paths.uploads_root.exists()


def test_recovery_required_stops_before_first_write(loopback):
    api, paths, _ = loopback
    result = baseline.run(PinnedLoopback(api, recovering=True), client,
                          source_sha=SOURCE, target=TARGET, expected_device_id=DEVICE)
    assert result["b1"]["status"] == "BLOCKED"
    assert not paths.uploads_root.exists()


def test_b1_pass_does_not_automatically_claim_b2_when_verifier_missing(loopback):
    api, paths, _ = loopback

    class AdmissionMissing(PinnedLoopback):
        def submit(self, *, kind, upload_id):
            raise client.DeploymentAPIError("API_HTTP_REJECTED:409")

    result = baseline.run(AdmissionMissing(api), client, source_sha=SOURCE,
                          target=TARGET, expected_device_id=DEVICE)
    assert result["b1"]["status"] == "PASS"
    assert result["b2_v1"]["status"] == "BLOCKED"
    assert result["b2_v2"]["status"] == "NOT_QUALIFIED"
    assert result["baseline_qualification"] == "B1_PASS_PARTIAL"
    assert not paths.product_root.exists()


def test_negative_chunk_hash_is_rejected_without_mutating_upload_state(loopback):
    api, paths, server = loopback
    data = baseline.sample_v1(SOURCE, TARGET)
    proof = baseline.b1_upload(api, client, data)
    assert proof["status"] == "PASS"
    assert proof["bytes_received"] == len(data)
    assert proof["negative_chunk_sha256"] == "REJECTED"
    meta = json.loads((paths.uploads_root / (proof["upload_id"] + ".json")).read_text())
    assert meta["state"] == "committed" and meta["received_bytes"] == len(data)


def test_wrong_target_and_wrong_member_hash_rejected_without_execution(loopback):
    api, paths, server = loopback
    failures = baseline.b2_negative(api, client, SOURCE, TARGET)
    assert all(v == "REJECTED" for v in failures.values())
    assert server.deployment_thread is None
    assert not paths.product_root.exists()


def test_bad_host_allowlist_denies_before_socket(monkeypatch):
    monkeypatch.setenv(baseline.HOST_ENV, "192.168.2.98")
    with pytest.raises(baseline.BaselineError, match="PPU_ALLOWED_IP_PIN"):
        baseline._private_ipv4("192.168.2.99")
    monkeypatch.setenv(baseline.HOST_ENV, "127.0.0.1")
    with pytest.raises(baseline.BaselineError, match="PPU_PRIVATE_LAN_ONLY"):
        baseline._private_ipv4("127.0.0.1")
    with pytest.raises(baseline.BaselineError, match="PPU_IP_LITERAL_REQUIRED"):
        baseline._private_ipv4("evil.example")


def test_manager_alias_and_port_are_strictly_allowlisted():
    with pytest.raises(baseline.BaselineError, match="MANAGER_ALIAS_INVALID"):
        baseline.ManagerAdmissionClient(alias="../../escape", port=18280, client_module=client)
    with pytest.raises(baseline.BaselineError, match="MANAGER_LOOPBACK_PORT_DENIED"):
        baseline.ManagerAdmissionClient(alias="z2", port=18380, client_module=client)


def test_no_unsafe_installer_or_device_operation_source_contract():
    body = SCRIPT.read_text(encoding="utf-8")
    assert "scope" not in body or "guarded-hardware" in body
    assert '"/v1/deployments"' in body or "b2_admission" in body
    assert "ssh" not in body.lower().replace("no ssh", "").replace("invokes ssh", "")
    assert 'kind="ppu-runtime"' not in body
    assert "sudo " not in body
    assert "fpga_manager" not in body
    assert "systemctl" not in body


def test_read_only_physical_probe_reports_version_but_not_installer_or_b1(monkeypatch):
    monkeypatch.delenv(baseline.HOST_ENV, raising=False)
    seen = []
    responses = {
        "/v1/health": {"ok": True, "service": "plasma-ppu-bootstrap", "api_version": "1"},
        "/v1/status": {
            "bootstrap": {"state": "bootstrap_ready", "version": "1.0", "api_version": "1"},
            "identity": {"device_id": DEVICE},
            "runtime": {"state": "runtime_active"},
        },
    }
    def reader(path):
        seen.append(path)
        return responses[path]

    result = baseline.probe_status("192.168.2.99", read_get=reader)
    assert seen == ["/v1/health", "/v1/status"]
    assert result["device_id_observed"] == DEVICE
    assert result["bootstrap_version_observed"] == "1.0"
    assert result["installed_verifier_source_sha"] == "NOT_ATTESTED"
    assert result["b1"] == result["b2_v2"] == "NOT_RUN"
    assert result["install"] == result["fpga"] == result["dut"] == "NOT_RUN"


def test_probe_denies_spoofed_identity_and_unknown_host(monkeypatch):
    monkeypatch.delenv(baseline.HOST_ENV, raising=False)
    assert baseline._private_ipv4("192.168.2.99") == "192.168.2.99"
    with pytest.raises(baseline.BaselineError, match="PPU_ALLOWED_IP_PIN"):
        baseline._private_ipv4("192.168.2.98")
    with pytest.raises(baseline.BaselineError, match="PPU_PROBE_IDENTITY_INVALID"):
        baseline.probe_status("192.168.2.99", read_get=lambda p: {
            "/v1/health": {"service": "plasma-ppu-bootstrap"},
            "/v1/status": {
                "bootstrap": {"state": "bootstrap_ready"},
                "identity": {"device_id": "fake-device"},
                "runtime": {"state": "runtime_active"},
            },
        }[p])


def test_path2_missing_manager_is_explicit_not_run_without_network(monkeypatch, capsys):
    monkeypatch.setattr(baseline, "_git_head", lambda: SOURCE)
    monkeypatch.delenv(baseline.HOST_ENV, raising=False)

    def unavailable(*args, **kwargs):
        raise baseline.BaselineError("MANAGER_REGISTRY_UNAVAILABLE")
    monkeypatch.setattr(baseline.ManagerAdmissionClient, "preflight", unavailable)
    result = baseline.main([
        "--host", "192.168.2.99", "--device-id", DEVICE,
        "--source-sha", SOURCE, "--platform", TARGET["platform"],
        "--board", TARGET["board"], "--fpga-part", TARGET["fpga_part"],
    ])
    assert result == 69
    out = capsys.readouterr().out
    assert "MANAGER_REGISTRY_UNAVAILABLE" in out
    assert '"result":"NOT_RUN"' in out
    assert "BEARER" not in out


def test_manager_transport_rewrites_upload_routes_and_omits_token(monkeypatch):
    seen = []
    responses = [
        (200, {"ok": True, "bootstrap": {
            "bootstrap": {"state": "bootstrap_ready"},
            "identity": {"device_id": DEVICE}},
            "pairing": {"paired": True, "device_match": True, "device_id": DEVICE},
            "ppu_alias": "z2",
            "bootstrap_endpoint_policy": "z2-ps-same-host:18081"}),
        (201, {"ok": True, "upload": {"upload_id": "a" * 32}}),
        (200, {"ok": True, "upload": {"upload_id": "a" * 32, "state": "committed"}}),
        (200, {"ok": True, "deployment": {"state": "admitted"}}),
    ]
    class Response:
        def __init__(self, status, data):
            self.status, self.data = status, json.dumps(data).encode()
        def read(self, limit):
            return self.data
    class Conn:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("127.0.0.1", 18280)
        def request(self, method, path, body=None, headers=None):
            seen.append((method, path, json.loads(body) if body else None, headers))
        def getresponse(self):
            status, data = responses.pop(0)
            return Response(status, data)
        def close(self):
            pass
    monkeypatch.setattr(baseline.http.client, "HTTPConnection", Conn)
    api = baseline.ManagerAdmissionClient(alias="z2", port=18280, client_module=client)
    assert api.status()["identity"]["device_id"] == DEVICE
    assert api._call("POST", "/v1/uploads", {"size": 1, "sha256": "0" * 64})["ok"]
    assert api._call("POST", "/v1/uploads/" + "a" * 32 + "/commit", {})["ok"]
    assert api._call("POST", "/v1/deployments", {"kind": "bundle", "upload_id": "a" * 32})["ok"]
    assert [p for _, p, _, _ in seen] == [
        "/api/registry/z2/bootstrap", "/api/registry/z2/bootstrap/uploads",
        "/api/registry/z2/bootstrap/uploads/" + "a" * 32 + "/commit",
        "/api/registry/z2/bootstrap/deployments",
    ]
    assert seen[2][2] == {"action": "commit"}
    assert all("Authorization" not in (h or {}) for _, _, _, h in seen)


def test_manager_registry_identity_and_pairing_are_mandatory(monkeypatch):
    registry = {"ok": True, "ppus": [{"alias": "z2", "endpoint": "http://192.168.2.99:18080"}]}
    status = {"bootstrap": {"state": "bootstrap_ready"},
              "identity": {"device_id": DEVICE}, "runtime": {"state": "runtime_active"}}
    state = {"status": status, "paired": True, "device_match": True}
    class Response:
        status = 200
        def read(self, size):
            return json.dumps(registry).encode()
    class Conn:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("127.0.0.1", 18280)
        def request(self, *args, **kwargs):
            pass
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(baseline.http.client, "HTTPConnection", Conn)
    api = baseline.ManagerAdmissionClient(alias="z2", port=18280, client_module=client)
    def fake_status():
        api._last_pairing = {"paired": state["paired"], "device_match": state["device_match"],
                             "device_id": DEVICE}
        return state["status"]
    monkeypatch.setattr(api, "status", fake_status)
    assert api.preflight(DEVICE, expected_host="192.168.2.99")["identity"]["device_id"] == DEVICE
    state["paired"] = False
    with pytest.raises(baseline.BaselineError, match="MANAGER_BOOTSTRAP_NOT_PAIRED"):
        api.preflight(DEVICE, expected_host="192.168.2.99")
    state["paired"] = True
    state["device_match"] = False
    with pytest.raises(baseline.BaselineError, match="MANAGER_PAIRING_DEVICE_MISMATCH"):
        api.preflight(DEVICE, expected_host="192.168.2.99")
    state["device_match"] = True
    registry["ppus"][0]["endpoint"] = "http://172.30.77.2:18080"
    with pytest.raises(baseline.BaselineError, match="MANAGER_PHYSICAL_TARGET_NOT_ENROLLED"):
        api.preflight(DEVICE, expected_host="192.168.2.99")



def test_readonly_manager_inventory_is_bounded_and_does_not_provision(monkeypatch):
    calls = []
    data = {
        18180: {"ok": True, "ppus": [
            {"alias": "qemu-ppu", "endpoint": "http://172.30.77.2:18080"},
        ]},
        18280: {"ok": True, "ppus": [
            {"alias": "prod-z2", "endpoint": "http://192.168.2.99:18080"},
            {"alias": "another-ppu", "endpoint": "http://192.168.2.100:18080"},
        ]},
    }
    class Response:
        status = 200
        def __init__(self, port):
            self.port = port
        def read(self, limit):
            return json.dumps(data[self.port]).encode()
    class Conn:
        def __init__(self, host, port, timeout):
            assert host == "127.0.0.1"
            assert port in (18180, 18280)
            self.port = port
        def request(self, method, path, **kwargs):
            calls.append((self.port, method, path))
        def getresponse(self):
            return Response(self.port)
        def close(self):
            pass
    monkeypatch.setattr(baseline.http.client, "HTTPConnection", Conn)
    monkeypatch.delenv(baseline.HOST_ENV, raising=False)
    report = baseline.probe_manager_registries("192.168.2.99")
    assert report["managers"] == [
        {"port": 18180, "status": "NO_PHYSICAL_TARGET", "real_z2_aliases": []},
        {"port": 18280, "status": "MATCH", "real_z2_aliases": ["prod-z2"]},
    ]
    assert calls == [
        (18180, "GET", "/api/registry"), (18280, "GET", "/api/registry"),
    ]
    assert report["b1"] == report["b2_v2"] == report["install"] == "NOT_RUN"


def test_manager_idle_gate_409_cannot_fake_invalid_package_rejection(monkeypatch):
    class Reply:
        status = 409
        def read(self, limit):
            return json.dumps({"ok": False, "error": {
                "code": "ppu_idle_state_unproven",
                "message": "runtime idle state unavailable",
            }}).encode()
    class Conn:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("127.0.0.1", 18280)
        def request(self, method, path, body=None, headers=None):
            pass
        def getresponse(self):
            return Reply()
        def close(self):
            pass
    monkeypatch.setattr(baseline.http.client, "HTTPConnection", Conn)
    api = baseline.ManagerAdmissionClient(alias="z2", port=18280,
                                          client_module=client)
    with pytest.raises(baseline.BaselineError, match="NEGATIVE_REJECTION_CAUSE_UNPROVEN"):
        baseline._expect_http_rejection(
            api, "POST", "/v1/deployments",
            {"kind": "python", "upload_id": "a" * 32},
            client.DeploymentAPIError,
            expected_reason="PACKAGE_FILE_SHA256_MISMATCH",
        )


def test_manager_exact_ppu_content_denial_proves_negative_case(monkeypatch):
    class Reply:
        status = 409
        def read(self, limit):
            return json.dumps({"ok": False,
                "error": "bootstrap_request_rejected",
                "message": "PACKAGE_FILE_SHA256_MISMATCH"}).encode()
    class Conn:
        def __init__(self, host, port, timeout):
            pass
        def request(self, method, path, body=None, headers=None):
            pass
        def getresponse(self):
            return Reply()
        def close(self):
            pass
    monkeypatch.setattr(baseline.http.client, "HTTPConnection", Conn)
    api = baseline.ManagerAdmissionClient(alias="z2", port=18280,
                                          client_module=client)
    baseline._expect_http_rejection(
        api, "POST", "/v1/deployments",
        {"kind": "python", "upload_id": "a" * 32},
        client.DeploymentAPIError,
        expected_reason="PACKAGE_FILE_SHA256_MISMATCH",
    )


def test_owner_enrollment_creates_only_pending_real_z2_registry(monkeypatch):
    monkeypatch.delenv(baseline.HOST_ENV, raising=False)
    responses = [
        (200, {"ok": True, "mutable": True, "ppus": [
            {"alias": "qemu", "endpoint": "http://172.30.77.2:18080"}]}),
        (201, {"ok": True, "entry": {
            "alias": "z2", "endpoint": "http://192.168.2.99:18080",
            "lifecycle": "pending"}}),
        (200, {"ok": True, "mutable": True, "ppus": [
            {"alias": "z2", "endpoint": "http://192.168.2.99:18080"}]}),
    ]
    requests = []
    class Response:
        def __init__(self, code, body):
            self.status, self.raw = code, json.dumps(body).encode()
        def read(self, limit):
            return self.raw
    class Conn:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("127.0.0.1", 18280)
        def request(self, method, path, body=None, headers=None):
            requests.append((method, path, json.loads(body) if body else None, headers))
        def getresponse(self):
            return Response(*responses.pop(0))
        def close(self):
            pass
    report = baseline.enroll_manager_real_z2(
        "192.168.2.99", DEVICE,
        probe=lambda host: {"device_id_observed": DEVICE},
        connection_factory=Conn,
    )
    assert report["registration"] == "REGISTERED_PENDING"
    assert report["pairing"] == "NOT_VERIFIED"
    assert report["b1"] == report["b2_v1"] == report["b2_v2"] == "NOT_RUN"
    assert [(method, path) for method, path, _, _ in requests] == [
        ("GET", "/api/registry"), ("POST", "/api/registry"),
        ("GET", "/api/registry"),
    ]
    assert requests[1][2] == {
        "alias": "z2", "endpoint": "http://192.168.2.99:18080"}
    assert all("Authorization" not in h for _, _, _, h in requests)


def test_owner_enrollment_never_writes_if_physical_identity_not_matching():
    def never(*args, **kwargs):
        raise AssertionError("Manager operation must not happen")
    with pytest.raises(baseline.BaselineError, match="ENROLL_REAL_DEVICE_ID_MISMATCH"):
        baseline.enroll_manager_real_z2(
            "192.168.2.99", DEVICE,
            probe=lambda host: {"device_id_observed": "ppu-device-deadbeefdeadbeef"},
            connection_factory=never,
        )


def test_owner_enrollment_fails_closed_on_duplicate_alias_and_immutable_registry():
    def simulate(first):
        class Response:
            status = 200
            def read(self, limit):
                return json.dumps(first).encode()
        class Conn:
            def __init__(self, host, port, timeout):
                pass
            def request(self, method, path, body=None, headers=None):
                assert method == "GET"
            def getresponse(self):
                return Response()
            def close(self):
                pass
        return Conn
    for obj, error in [
        ({"ok": True, "mutable": False, "ppus": []},
         "ENROLL_REGISTRY_NOT_MUTABLE"),
        ({"ok": True, "mutable": True, "ppus": [
            {"alias": "z2", "endpoint": "http://172.30.77.2:18080"}]},
         "ENROLL_ALIAS_CONFLICT"),
        ({"ok": True, "mutable": True, "ppus": [
            {"alias": "qemu", "endpoint": "http://192.168.2.99:18080"}]},
         "ENROLL_ENDPOINT_ALREADY_OWNED"),
    ]:
        with pytest.raises(baseline.BaselineError, match=error):
            baseline.enroll_manager_real_z2(
                "192.168.2.99", DEVICE,
                probe=lambda host: {"device_id_observed": DEVICE},
                connection_factory=simulate(obj),
            )


def test_owner_enrollment_never_accepts_arbitrary_alias_or_port():
    with pytest.raises(baseline.BaselineError, match="ENROLL_FIXED_MANAGER_ALIAS_AND_PORT_REQUIRED"):
        baseline.enroll_manager_real_z2(
            "192.168.2.99", DEVICE, alias="qemu",
            probe=lambda host: {"device_id_observed": DEVICE})


def test_swpc_inspection_reports_only_sanitized_fixed_files(tmp_path):
    conf = tmp_path / ".config/plasma/local-control-station"
    units = tmp_path / ".config/systemd/user"
    state = tmp_path / ".local/state/plasma/local-control-station"
    current = tmp_path / ".local/share/plasma/local-control-station/current"
    for p in [conf, units, state, current]:
        p.mkdir(parents=True)
    cfg = conf / "manager.yaml"
    cfg.write_text("manager:\n  host: 127.0.0.1\n  port: 18280\nppus: []\n")
    unit = units / "plasma-local-manager.service"
    unit.write_text("[Service]\nExecStart=" + str(current) +
                    "/venv/bin/python -m plasma_manager.server --config " + str(cfg) + "\n")
    secret = state / "bootstrap-credentials.json"
    secret.write_text("SENSITIVE_CONTENT_MUST_NOT_LEAK")
    secret.chmod(0o600)
    class Show:
        returncode = 0
        stdout = "LoadState=loaded\nActiveState=active\nMainPID=12345\n"
    report = baseline.inspect_swpc_manager_runtime(home=tmp_path, systemctl=lambda: Show())
    assert report["manager_entrypoint"] == "GENERIC_MANAGER"
    assert report["manager_service_state"] == "active"
    assert report["registry_state_configured"] is False
    assert report["bootstrap_credential_file"]["exists"] is True
    assert "SENSITIVE_CONTENT_MUST_NOT_LEAK" not in json.dumps(report)
    assert "12345" not in json.dumps(report)
    assert report["b1"] == "NOT_RUN"


def test_existing_enrolled_ssh_token_retrieval_is_memory_only_and_not_logged(monkeypatch):
    import base64
    monkeypatch.delenv(baseline.HOST_ENV, raising=False)
    private = "existing-secret-material-" + "P" * 43
    calls = []
    class Worker:
        @staticmethod
        def z2_login_credentials(home):
            return ({"ssh_host": "192.168.2.99", "ssh_username": "xilinx",
                     "ssh_password": "never-show", "sudo_password": "never-show"},
                    home / ".config/plasma/z2-login-known_hosts")
        @staticmethod
        def password_ssh_z2(cmd, credentials, known_hosts, *, timeout):
            calls.append((cmd, timeout))
            return (0, "PLASMA_BOOTSTRAP_MATERIAL:" +
                    base64.b64encode(private.encode()).decode())
    token = baseline._existing_bootstrap_token_via_z2_ssh("192.168.2.99", helper=Worker)
    assert token == private
    assert token not in repr(calls)
    assert calls[0][0][:3] == ["python3", "-I", "-c"]
    assert "control-token" in calls[0][0][3]


def test_direct_ssh_denies_host_drift_and_secret_access_failure(monkeypatch):
    monkeypatch.delenv(baseline.HOST_ENV, raising=False)
    class HostDrift:
        @staticmethod
        def z2_login_credentials(home):
            return ({"ssh_host": "192.168.2.100"}, home)
    with pytest.raises(baseline.BaselineError, match="SSH_HOST_NOT_APPROVED_TARGET"):
        baseline._existing_bootstrap_token_via_z2_ssh("192.168.2.99", helper=HostDrift)
    class MissingToken:
        @staticmethod
        def z2_login_credentials(home):
            return ({"ssh_host": "192.168.2.99"}, home)
        @staticmethod
        def password_ssh_z2(*args, **kwargs):
            return 77, "root-readable error secret can be here"
    with pytest.raises(baseline.BaselineError, match="TOKEN_ACCESS_DENIED") as exc:
        baseline._existing_bootstrap_token_via_z2_ssh("192.168.2.99", helper=MissingToken)
    assert "root-readable error" not in str(exc.value)


def test_physical_direct_bootstrap_uses_only_z2_http_and_rejects_wrong_hash(monkeypatch):
    monkeypatch.delenv(baseline.HOST_ENV, raising=False)
    calls = []
    class Response:
        def __init__(self, status, data):
            self.status = status
            self._data = data
        def read(self, n):
            return self._data
    class Conn:
        def __init__(self, host, port, timeout):
            assert (host, port) == ("192.168.2.99", 18081)
        def request(self, method, path, body=None, headers=None):
            calls.append((method, path, headers, body))
        def getresponse(self):
            return Response(409, json.dumps({
                "ok": False, "error": "bootstrap_request_rejected",
                "message": "chunk SHA-256 mismatch",
            }).encode())
        def close(self):
            pass
    api = baseline.DirectSSHAuthenticatedBootstrap(
        "192.168.2.99", module=client, token="x" * 48,
        connection_factory=Conn)
    baseline._expect_http_rejection(
        api, "POST", "/v1/uploads/" + "a" * 32 + "/chunks",
        {"offset": 0, "data_base64": "AA==", "sha256": "0" * 64},
        client.DeploymentAPIError, expected_reason="CHUNK_SHA256_MISMATCH")
    assert len(calls) == 1
    assert calls[0][1].endswith("/chunks")
    assert calls[0][2]["Authorization"] == "Bearer " + "x" * 48
    with pytest.raises(baseline.BaselineError, match="ROUTE_DENIED"):
        api._call("POST", "/v1/installer", {"execute": True})

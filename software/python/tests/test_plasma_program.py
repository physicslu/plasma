"""Host-only API contract for transport-independent Bundle programming CLI."""
from __future__ import annotations

import json
from pathlib import Path
import sys

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import plasma_program as program  # noqa: E402
import bluepill_bundle_v3_firmware_build as bluepill  # noqa: E402

RUNTIME = "c" * 40
DEVICE = "ppu-device-" + "1" * 24
HOST = "192.168.2.99"
JOB = "job-20261107-110001-abcdef12"


def selection():
    return program.Selection(
        b"TEST_ARCHIVE", "a" * 64, "bluepill-cdc-fw-v01",
        "b" * 64, 4, "profile", "provider", "STM32F103C8T6", 2)


class Client:
    _token = "c" * 64          # enrolled controller credential used to sign the Job

    def __init__(self, active="a" * 64, runtime=RUNTIME):
        self.active = active
        self.runtime = runtime
        self.events = []

    def status(self):
        self.events.append("status")
        return {"identity": {"device_id": DEVICE},
                "bootstrap": {"state": "bootstrap_ready"},
                "runtime": {"state": "runtime_active", "git_sha": self.runtime},
                "deployment": {"state": "succeeded"}}

    def assets_status(self):
        self.events.append("assets")
        return {"state": "ACTIVE", "asset_set_sha256": self.active}

    def reconcile_bundle_assets(self, archive, *, fpga_load):
        self.events.append("B1_B2_B3")
        assert archive == b"TEST_ARCHIVE"
        assert fpga_load is False
        return {"result": "B3_INSTALL_QUEUED",
                "asset_set_sha256": "a" * 64,
                "b3": {"transaction_id": "d" * 32}}

    def deployment_state(self, transaction):
        self.events.append("B3_STATUS")
        assert transaction == "d" * 32
        self.active = "a" * 64
        return {"state": "succeeded", "result": {"result": "PASS"}}


def patch_ready(monkeypatch):
    observations = []
    def fake(host, chosen):
        observations.append((host, chosen.site))
        return {"ppu_id": "z2-hil", "site": chosen.site, "site_idle": True}
    monkeypatch.setattr(program, "readiness", fake)
    return observations


def successful_job():
    chosen = selection()
    return {
        "job_id": JOB, "site_id": chosen.site, "operation": "flash_cycle",
        "state": "success",
        "result": {
            "state": "success", "image_sha256": chosen.firmware_sha,
            "image_size": chosen.firmware_size, "attempts": 1,
            "details": {"flash_cycle": {
                "result": "PASS", "readback_sha256": chosen.firmware_sha,
                "bytes_verified": chosen.firmware_size, "safe_off": True}},
        },
    }


def test_local_bundle_selects_firmware_from_canonical_v3(tmp_path):
    image = (ROOT / "docs/evidence/bluepill-z2-flash-2026-10-27"
             / "firmware/plasma-blue-pill-cdc.bin")
    output = tmp_path / "v01.zip"
    built = bluepill.build("v0.1", image, output)
    selected = program.read_bundle(
        output, site=2, package=None, image=image)
    assert selected.bundle_sha == built["archive_sha256"]
    assert selected.firmware_sha == built["firmware_sha256"]
    assert selected.profile == "stm32f103c8t6-site2"
    assert selected.provider == "openocd-platform-reference"
    assert selected.site == 2
    with pytest.raises(program.ProgramDenied, match="SITE_OR_TARGET_NOT_QUALIFIED"):
        program.read_bundle(output, site=3, package=None)
    with pytest.raises(program.ProgramDenied, match="FIRMWARE_PACKAGE_NOT_FOUND"):
        program.read_bundle(output, site=2, package="not-a-package")
    wrong = tmp_path / "wrong.bin"
    wrong.write_bytes(b"INCORRECT")
    with pytest.raises(program.ProgramDenied, match="EXTERNAL_IMAGE_NOT_IN_BUNDLE"):
        program.read_bundle(output, site=2, package=None, image=wrong)


def test_mutation_requires_approval_before_io(monkeypatch):
    client = Client()
    monkeypatch.setattr(program, "readiness", lambda *a: pytest.fail("No I/O"))
    for command in ("deploy", "flash", "run"):
        with pytest.raises(program.ProgramDenied, match="OWNER_APPROVAL_REQUIRED"):
            program.execute(command, selection(), host=HOST, device_id=DEVICE,
                            client=client, runtime_sha=RUNTIME)
    assert client.events == []


def test_diagnose_is_read_only(monkeypatch):
    observations = patch_ready(monkeypatch)
    client = Client()
    out = program.execute("diagnose", selection(), host=HOST,
                          device_id=DEVICE, client=client)
    assert out["status"] == "PASS" and out["mutations"] == "NOT_RUN"
    assert observations == [(HOST, 2)]
    assert "B1_B2_B3" not in client.events


def test_runtime_version_guard_blocks_before_deployment(monkeypatch):
    observations = patch_ready(monkeypatch)
    client = Client(runtime="0" * 40)
    with pytest.raises(program.ProgramDenied, match="RUNTIME_RELEASE_NOT_UPDATED"):
        program.execute("run", selection(), host=HOST, device_id=DEVICE,
                        client=client, runtime_sha=RUNTIME, approved_once=True)
    assert not observations and "B1_B2_B3" not in client.events


def test_flash_requires_matching_current_active_set(monkeypatch):
    patch_ready(monkeypatch)
    client = Client(active="e" * 64)
    monkeypatch.setattr(program, "post_once", lambda *_, **_kw: pytest.fail("No Job"))
    with pytest.raises(program.ProgramDenied, match="BUNDLE_NOT_CURRENTLY_ACTIVE"):
        program.execute("flash", selection(), host=HOST, device_id=DEVICE,
                        client=client, runtime_sha=RUNTIME, approved_once=True)


def test_run_deploys_once_then_submits_one_bundle_reference_job(monkeypatch):
    observations = patch_ready(monkeypatch)
    client = Client(active="e" * 64)
    submitted = []
    monkeypatch.setattr(program, "post_once",
                        lambda host, chosen, **_kw: submitted.append((host, chosen)) or JOB)
    monkeypatch.setattr(program, "poll_job", lambda host, job: successful_job())
    result = program.execute("run", selection(), host=HOST, device_id=DEVICE,
                             client=client, runtime_sha=RUNTIME, approved_once=True)
    assert result["status"] == "PASS"
    assert result["deployment"]["transaction_id"] == "d" * 32
    assert result["job"]["safe_off"] is True
    assert client.events.count("B1_B2_B3") == 1
    assert client.events.count("B3_STATUS") == 1
    assert len(submitted) == 1 and submitted[0][1].bundle_sha == "a" * 64
    assert len(observations) == 3


def test_already_active_does_not_reupload(monkeypatch):
    patch_ready(monkeypatch)
    client = Client()
    out = program.execute("deploy", selection(), host=HOST, device_id=DEVICE,
                          client=client, approved_once=True)
    assert out["deployment"]["result"] == "ALREADY_ACTIVE"
    assert "B1_B2_B3" not in client.events


def test_submitted_job_unknown_preserves_id_and_does_not_retry(monkeypatch):
    patch_ready(monkeypatch)
    client = Client()
    events = []
    monkeypatch.setattr(program, "post_once",
                        lambda *a, **_kw: events.append("POST") or JOB)
    def lost(*a):
        raise program.OutcomeUnknown("JOB_RESULT_UNKNOWN", JOB)
    monkeypatch.setattr(program, "poll_job", lost)
    out = program.execute("flash", selection(), host=HOST, device_id=DEVICE,
                          client=client, runtime_sha=RUNTIME, approved_once=True)
    assert out["status"] == "OUTCOME_UNKNOWN"
    assert out["job_id"] == JOB and out["submission_count"] == 1
    assert out["auto_retry"] == "DISABLED"
    assert events == ["POST"]


def test_failed_readback_or_safe_off_not_pass(monkeypatch):
    bad = successful_job()
    bad["result"]["details"]["flash_cycle"]["safe_off"] = False
    assert program.verify_job(bad, selection())["status"] == "FAIL_OR_INCOMPLETE"
    bad["result"]["details"]["flash_cycle"]["safe_off"] = True
    bad["result"]["details"]["flash_cycle"]["readback_sha256"] = "0" * 64
    assert program.verify_job(bad, selection())["status"] == "FAIL_OR_INCOMPLETE"


def test_job_http_payload_uses_reference_not_firmware(monkeypatch):
    """The Job is signed under the enrolled controller (LOM-P2A-2 G13)."""
    auth = program.ppu_deploy_api._request_auth_module()
    credential, device = "c" * 64, "ppu-device-0123456789abcdef01234567"
    observed, nonce = [], "5" * 32
    class Response:
        def __init__(self, status, raw, headers=None):
            self.status, self._raw, self._headers = status, raw, headers or {}
        def read(self, _max):
            return self._raw
        def getheader(self, name):
            return self._headers.get(name)
    class HTTP:
        def __init__(self, host, port, timeout):
            assert (host, port) == (HOST, 18080)
        def request(self, method, path, body=None, headers=None):
            self.method, self.path, self.body, self.headers = method, path, body, headers
        def getresponse(self):
            if self.method == "GET":
                assert self.path == "/api/auth/challenge"
                return Response(200, json.dumps({"ok": True, "schema": auth.SCHEMA,
                                                 "device_id": device, "nonce": nonce}).encode())
            assert (self.method, self.path) == ("POST", "/api/jobs")
            observed.append(json.loads(self.body))
            admitted = auth.admit_request_header(header=self.headers["Authorization"],
                                                 device_id=device, nonces=Nonces())
            context = auth.verify_request(credential=credential, admitted=admitted,
                                          method="POST", path="/api/jobs", body=self.body)
            raw = json.dumps({"job": {"job_id": JOB}}).encode()
            return Response(202, raw, {auth.RESPONSE_HEADER: auth.sign_response(
                credential=credential, context=context, status=202, body=raw)})
        def close(self):
            pass
    class Nonces:
        def consume(self, value):
            return value == nonce
    monkeypatch.setattr(program.http.client, "HTTPConnection", HTTP)
    assert program.post_once(HOST, selection(), credential=credential, device_id=device) == JOB
    assert len(observed) == 1
    body = observed[0]
    assert body["bundle_asset_sha256"] == "b" * 64
    assert body["asset_set_sha256"] == "a" * 64
    assert body["asset_package_id"] == "bluepill-cdc-fw-v01"
    assert "asset_base64" not in body and "asset_name" not in body


def test_existing_private_bootstrap_assets_read_only(monkeypatch):
    """New CLI reuses existing device-bound Bootstrap, not fake HTTPS."""
    import ppu_path2_hardware_baseline as enrolled
    from .bootstrap_request_auth_fixture import AuthenticatedFakePPU
    calls = []
    credential = "x" * 32

    def assets(method, path, raw, headers):
        assert (method, path) == ("GET", "/v1/assets")
        return 200, json.dumps({"ok": True, "assets": {
            "schema": "plasma.ppu.active-assets.v1",
            "state": "ACTIVE", "ready": False,
            "asset_set_sha256": "a" * 64}}).encode()

    ppu = AuthenticatedFakePPU(assets, credential=credential,
                               device_id="ppu-device-" + "0" * 24)

    class Connection:
        def __init__(self, host, port, timeout):
            assert (host, port) == (HOST, 18081)
        def request(self, method, path, body, headers):
            calls.append((method, path))
            self.result = ppu(method, path, body, headers)
        def getresponse(self):
            status, raw, headers = self.result
            class Response:
                def read(self, _limit):
                    return raw
                def getheaders(self):
                    return list(headers.items())
            response = Response()
            response.status = status
            return response
        def close(self):
            pass
    monkeypatch.setattr(enrolled.http.client, "HTTPConnection", Connection)
    client = program.open_bootstrap(HOST, credential)
    assert client.assets_status()["asset_set_sha256"] == "a" * 64
    # Credential never sent: one PPU challenge, then one MACed read.
    assert calls == [("GET", "/v1/auth/challenge"), ("GET", "/v1/assets")]
    assert ppu.authenticated_requests == 1


def test_runtime_deploy_refuses_untrusted_kit_before_device_io(monkeypatch):
    patch_ready(monkeypatch)
    client = Client()
    monkeypatch.delenv("PLASMA_Z2_KIT_ARTIFACT_PATH", raising=False)
    monkeypatch.delenv("PLASMA_Z2_KIT_SOURCE_SHA", raising=False)
    with pytest.raises(program.ProgramDenied, match="TRUSTED_RUNTIME_KIT_NOT_DELIVERED"):
        program.deploy_runtime_kit(
            client, selection(), host=HOST, device_id=DEVICE,
            runtime_sha="d" * 40, kit_sha256="e" * 64,
            ppu_id="z2-hil", facility_id="lab", display_name="Plasma Z2 PS")
    assert client.events == []


def test_runtime_deploy_one_bootstrap_transaction_never_programs(tmp_path, monkeypatch):
    import hashlib
    import ppu_deploy_api
    patch_ready(monkeypatch)
    archive = tmp_path / "verified-kit.tar.gz"
    data = b"simulated-source-verified-runtime-kit"
    archive.write_bytes(data)
    monkeypatch.setenv("PLASMA_Z2_KIT_ARTIFACT_PATH", str(archive))
    monkeypatch.setenv("PLASMA_Z2_KIT_SOURCE_SHA", "d" * 40)

    class RuntimeClient(Client):
        def upload(self, payload):
            self.events.append("upload")
            assert payload == data
            return "a" * 32
        def submit(self, **kwargs):
            self.events.append("submit")
            assert kwargs == {
                "kind": "ppu-runtime", "upload_id": "a" * 32,
                "gateway_host": HOST, "ppu_id": "z2-hil",
                "facility_id": "lab", "display_name": "Plasma Z2 PS",
            }
            return ppu_deploy_api.DeploymentSubmission("a" * 32, "d" * 32, "queued")
        def deployment_state(self, transaction):
            assert transaction == "d" * 32
            self.events.append("poll")
            self.runtime = "d" * 40
            return {"state": "succeeded", "result": {"result": "PASS"}}
        def status(self):
            return {**super().status(), "capabilities": {"runtime_deployment": True}}

    client = RuntimeClient()
    monkeypatch.setattr(program, "post_once",
                        lambda *args, **_kw: pytest.fail("DUT programming forbidden"))
    result = program.deploy_runtime_kit(
        client, selection(), host=HOST, device_id=DEVICE,
        runtime_sha="d" * 40, kit_sha256=hashlib.sha256(data).hexdigest(),
        ppu_id="z2-hil", facility_id="lab", display_name="Plasma Z2 PS")
    assert result["status"] == "PASS"
    assert result["transaction_id"] == "d" * 32
    assert result["flash"] == "NOT_RUN"
    assert client.events.count("submit") == 1
    assert client.events.count("poll") == 1


def test_runtime_deploy_rejects_wrong_sha_before_any_bootstrap_io(tmp_path, monkeypatch):
    archive = tmp_path / "mismatch.tar.gz"
    archive.write_bytes(b"not-matching")
    monkeypatch.setenv("PLASMA_Z2_KIT_ARTIFACT_PATH", str(archive))
    monkeypatch.setenv("PLASMA_Z2_KIT_SOURCE_SHA", "d" * 40)
    client = Client()
    with pytest.raises(program.ProgramDenied, match="RUNTIME_KIT_SHA256_MISMATCH"):
        program.deploy_runtime_kit(
            client, selection(), host=HOST, device_id=DEVICE,
            runtime_sha="d" * 40, kit_sha256="e" * 64,
            ppu_id="z2-hil", facility_id="lab", display_name="Plasma Z2 PS")
    assert client.events == []

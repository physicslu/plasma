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


def test_local_bundle_selects_firmware_from_canonical_v3(tmp_path):
    image = (ROOT / "docs/evidence/bluepill-z2-flash-2026-10-27"
             / "firmware/plasma-blue-pill-cdc.bin")
    output = tmp_path / "v01.zip"
    built = bluepill.build("v0.1", image, output)
    selected = program.read_bundle(
        output, site=2, package=None, image=image)
    assert selected.bundle_sha == built["archive_sha256"]
    assert selected.firmware_sha == built["firmware_sha256"]
    assert selected.profile == "stm32f103c8t6-site2-operations"
    assert selected.provider == "openocd-platform-reference"
    assert selected.site == 2
    # Bundle package selection is independent of physical Site identity.
    # Actual Site/interface readiness and Job Binding are checked by the
    # Manager/PPU before submitting a real hardware Job, not by this reader.
    other_site = program.read_bundle(output, site=3, package=None)
    assert other_site.site == 3
    assert other_site.bundle_sha == selected.bundle_sha
    assert other_site.firmware_sha == selected.firmware_sha
    with pytest.raises(program.ProgramDenied, match="FIRMWARE_PACKAGE_NOT_FOUND"):
        program.read_bundle(output, site=2, package="not-a-package")
    wrong = tmp_path / "wrong.bin"
    wrong.write_bytes(b"INCORRECT")
    with pytest.raises(program.ProgramDenied, match="EXTERNAL_IMAGE_NOT_IN_BUNDLE"):
        program.read_bundle(output, site=2, package=None, image=wrong)


def test_mutation_requires_approval_before_io(monkeypatch):
    client = Client()
    monkeypatch.setattr(program, "readiness", lambda *a: pytest.fail("No I/O"))
    with pytest.raises(program.ProgramDenied, match="OWNER_APPROVAL_REQUIRED"):
        program.execute("deploy", selection(), host=HOST, device_id=DEVICE, client=client)
    assert client.events == []


def test_direct_programming_job_commands_are_retired(monkeypatch):
    # U7: a Programming Job runs only under a Manager Batch Resource
    # Reservation (`plasmactl program`); this tool submits no Job at all.
    client = Client()
    monkeypatch.setattr(program, "readiness", lambda *a: pytest.fail("No I/O"))
    for command in ("flash", "run"):
        with pytest.raises(program.ProgramDenied, match="COMMAND_DENIED"):
            program.execute(command, selection(), host=HOST, device_id=DEVICE,
                            client=client, approved_once=True)
        with pytest.raises(SystemExit):
            program.main([command, "--bundle", "x", "--site", "2", "--host", HOST,
                          "--device-id", DEVICE])
    assert client.events == []
    assert not hasattr(program, "post_once")


def test_diagnose_is_read_only(monkeypatch):
    observations = patch_ready(monkeypatch)
    client = Client()
    out = program.execute("diagnose", selection(), host=HOST,
                          device_id=DEVICE, client=client)
    assert out["status"] == "PASS" and out["mutations"] == "NOT_RUN"
    assert observations == [(HOST, 2)]
    assert "B1_B2_B3" not in client.events


def test_already_active_does_not_reupload(monkeypatch):
    patch_ready(monkeypatch)
    client = Client()
    out = program.execute("deploy", selection(), host=HOST, device_id=DEVICE,
                          client=client, approved_once=True)
    assert out["deployment"]["result"] == "ALREADY_ACTIVE"
    assert "B1_B2_B3" not in client.events


def test_existing_private_bootstrap_assets_read_only(monkeypatch):
    """New CLI reuses existing device-bound Bootstrap, not fake HTTPS."""
    import ppu_bootstrap_transport as enrolled
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

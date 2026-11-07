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
    monkeypatch.setattr(program, "post_once", lambda *_: pytest.fail("No Job"))
    with pytest.raises(program.ProgramDenied, match="BUNDLE_NOT_CURRENTLY_ACTIVE"):
        program.execute("flash", selection(), host=HOST, device_id=DEVICE,
                        client=client, runtime_sha=RUNTIME, approved_once=True)


def test_run_deploys_once_then_submits_one_bundle_reference_job(monkeypatch):
    observations = patch_ready(monkeypatch)
    client = Client(active="e" * 64)
    submitted = []
    monkeypatch.setattr(program, "post_once",
                        lambda host, chosen: submitted.append((host, chosen)) or JOB)
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
                        lambda *a: events.append("POST") or JOB)
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
    observed = []
    class Response:
        status = 202
        def read(self, _max):
            return json.dumps({"job": {"job_id": JOB}}).encode()
    class HTTP:
        def __init__(self, host, port, timeout):
            assert (host, port) == (HOST, 18080)
        def request(self, method, path, body, headers):
            assert (method, path) == ("POST", "/api/jobs")
            observed.append(json.loads(body))
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(program.http.client, "HTTPConnection", HTTP)
    assert program.post_once(HOST, selection()) == JOB
    assert len(observed) == 1
    body = observed[0]
    assert body["bundle_asset_sha256"] == "b" * 64
    assert body["asset_set_sha256"] == "a" * 64
    assert body["asset_package_id"] == "bluepill-cdc-fw-v01"
    assert "asset_base64" not in body and "asset_name" not in body


def test_existing_private_bootstrap_assets_read_only(monkeypatch):
    """New CLI reuses existing device-bound Bootstrap, not fake HTTPS."""
    import ppu_path2_hardware_baseline as enrolled
    calls = []
    class Response:
        status = 200
        def read(self, _limit):
            return json.dumps({"ok": True, "assets": {
                "schema": "plasma.ppu.active-assets.v1",
                "state": "ACTIVE", "ready": False,
                "asset_set_sha256": "a" * 64}}).encode()
    class Connection:
        def __init__(self, host, port, timeout):
            assert (host, port) == (HOST, 18081)
        def request(self, method, path, body, headers):
            calls.append((method, path))
            assert headers["Authorization"] == "Bearer " + "x" * 32
        def getresponse(self):
            return Response()
        def close(self):
            pass
    monkeypatch.setattr(enrolled.http.client, "HTTPConnection", Connection)
    client = program.open_bootstrap(HOST, "x" * 32)
    assert client.assets_status()["asset_set_sha256"] == "a" * 64
    assert calls == [("GET", "/v1/assets")]

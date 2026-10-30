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
        baseline._commissioning_transport("192.168.2.99")
    monkeypatch.setenv(baseline.HOST_ENV, "127.0.0.1")
    with pytest.raises(baseline.BaselineError, match="PPU_PRIVATE_LAN_ONLY"):
        baseline._commissioning_transport("127.0.0.1")
    with pytest.raises(baseline.BaselineError, match="PPU_IP_LITERAL_REQUIRED"):
        baseline._commissioning_transport("evil.example")


def test_token_file_must_be_private_owner_file(tmp_path):
    good = tmp_path / "token"
    good.write_text("t" * 48)
    good.chmod(0o600)
    assert baseline._token_from_private_file(good) == "t" * 48
    good.chmod(0o644)
    with pytest.raises(baseline.BaselineError, match="PRIVATE_TOKEN_FILE_UNSAFE"):
        baseline._token_from_private_file(good)
    symlink = tmp_path / "token-link"
    symlink.symlink_to(good)
    with pytest.raises(baseline.BaselineError, match="PRIVATE_TOKEN_FILE_DENIED"):
        baseline._token_from_private_file(symlink)


def test_no_unsafe_installer_or_device_operation_source_contract():
    body = SCRIPT.read_text(encoding="utf-8")
    assert "scope" not in body or "guarded-hardware" in body
    assert '"/v1/deployments"' in body or "b2_admission" in body
    assert "ssh" not in body.lower().replace("no ssh", "").replace("invokes ssh", "")
    assert 'kind="ppu-runtime"' not in body
    assert "sudo " not in body
    assert "fpga_manager" not in body
    assert "systemctl" not in body

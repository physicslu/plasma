"""Host-only regression of the retained Site 2 read-only Active Set observer.

The retired Gen7 B3 deploy path must not be imported, required, or invoked.
No test reads SWPC credentials, connects to Z2, or performs hardware I/O.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace
import sys

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT

sys.path.insert(0, str(ROOT / "scripts"))
import plasma_site2_active_readonly_path2 as active  # noqa: E402

HOST = "192.168.2.99"
SHA = "a" * 40
ASSET = "b" * 64


def observed(state="ACTIVE", opf_static="PASS", asset_sha=ASSET):
    return {"state": state, "opf_static": opf_static,
            "asset_set_sha256": asset_sha,
            "generation": 8 if state == "ACTIVE" else None}


class FakeSSH:
    def __init__(self, *, paired=HOST, rc=0, transcript=None):
        self.paired = paired
        self.rc = rc
        self.transcript = transcript
        self.commands = []

    def z2_login_credentials(self, home):
        return {"ssh_host": self.paired}, Path("/tmp/test-pinned-public-key")

    def password_ssh_z2(self, command, credentials, hosts, timeout):
        self.commands.append((command, timeout))
        if self.transcript is None:
            receipt = base64.b64encode(json.dumps(observed()).encode()).decode()
            return self.rc, active.MARKER + receipt
        return self.rc, self.transcript


@pytest.mark.parametrize("state,opf_static,asset_sha", [
    ("ACTIVE", "PASS", ASSET),
    ("ACTIVE", "FAIL", ASSET),
    ("EMPTY", "NOT_APPLICABLE", None),
])
def test_readonly_observation_accepts_exact_guarded_receipt(state, opf_static, asset_sha):
    data = observed(state, opf_static, asset_sha)
    marker = active.MARKER + base64.b64encode(json.dumps(data).encode()).decode()
    helper = FakeSSH(transcript=marker)
    assert active.observe_active(HOST, helper=helper) == data
    assert helper.commands == [(["python3", "-I", "-c", active.REMOTE_OBSERVE], 60)]
    assert "from ppu_asset_set import read_active" in active.REMOTE_OBSERVE
    assert "os.system" not in active.REMOTE_OBSERVE


@pytest.mark.parametrize("transcript", [
    "", active.MARKER + "%%%", active.MARKER + "e30=",
])
def test_bad_observation_receipt_fails_closed(transcript):
    helper = FakeSSH(transcript=transcript)
    with pytest.raises(active.ActiveObservationDenied,
                       match="ACTIVE_SET_RECEIPT_INVALID"):
        active.observe_active(HOST, helper=helper)


def test_readonly_observation_rejects_failed_ssh():
    helper = FakeSSH(rc=1)
    with pytest.raises(active.ActiveObservationDenied,
                       match="ACTIVE_SET_READ_ONLY_OBSERVATION_FAILED"):
        active.observe_active(HOST, helper=helper)


def test_mismatched_paired_host_refuses_ssh():
    helper = FakeSSH(paired="192.168.2.88")
    with pytest.raises(active.ActiveObservationDenied,
                       match="PAIRED_TARGET_MISMATCH"):
        active.observe_active(HOST, helper=helper)
    assert not helper.commands


def good_preflight():
    return {"readiness": "NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS",
            "blockers": [],
            "z2": {"engine": {
                "status": "VERIFIED", "abi": 5, "driver": "plasma_swd",
                "openocd_sha256_observed": active.BIN,
                "admission_sha256_observed": active.ADM}},
            "rest": {"active_job_count": 0, "activation_active": False,
                     "lease_busy": False, "site2_idle": True}}


def test_retained_path_reports_readonly_active_without_gen7_deploy(monkeypatch):
    calls = []
    monkeypatch.setattr(active.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=SHA + "\n"))
    helper = FakeSSH()
    preflight = SimpleNamespace(run=lambda host, sha, helper: (
        calls.append(("preflight", host, sha)) or good_preflight()))
    def observe(host, *, helper):
        calls.append(("active", host))
        return observed()
    result = active.run(SHA, helper=helper, preflight=preflight,
                        active_observer=observe)
    assert result["readiness"] == "PASS"
    assert result["asset_set_sha256"] == ASSET
    assert result["flash"] == result["bundle_deploy"] == "NOT_RUN"
    assert result["fpga_reload"] == result["engine_switch"] == "NOT_RUN"
    assert calls == [("preflight", HOST, SHA), ("active", HOST)]
    assert not hasattr(active, "deployer")


@pytest.mark.parametrize("mutation", [
    {"rest": {"active_job_count": 1}},
    {"rest": {"lease_busy": True}},
    {"z2": {"engine": {"abi": 4}}},
])
def test_blocked_site_safety_prevents_active_observation(monkeypatch, mutation):
    monkeypatch.setattr(active.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=SHA))
    snapshot = good_preflight()
    if "rest" in mutation:
        snapshot["rest"].update(mutation["rest"])
    else:
        snapshot["z2"]["engine"].update(mutation["z2"]["engine"])
    def deny_active(*args, **kwargs):
        pytest.fail("Active observer must not run on unsafe preflight")
    with pytest.raises(RuntimeError, match="SITE2_PREFLIGHT_NOT_READY"):
        active.run(SHA, helper=FakeSSH(),
                   preflight=SimpleNamespace(run=lambda *a, **kw: snapshot),
                   active_observer=deny_active)


@pytest.mark.parametrize("record", [
    observed("EMPTY", "NOT_APPLICABLE", None),
    observed("ACTIVE", "FAIL", ASSET),
    observed("ACTIVE", "PASS", "invalid"),
])
def test_active_contract_denied_before_claiming_readiness(monkeypatch, record):
    monkeypatch.setattr(active.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=SHA))
    with pytest.raises(RuntimeError,
                       match="ACTIVE_OPF_NOT_VERIFIED|ACTIVE_ASSET_SHA_INVALID"):
        active.run(SHA, helper=FakeSSH(),
                   preflight=SimpleNamespace(run=lambda *a, **kw: good_preflight()),
                   active_observer=lambda *a, **kw: record)


def test_source_sha_mismatch_fails_before_paired_credentials(monkeypatch):
    monkeypatch.setattr(active.subprocess, "run",
                        lambda *a, **k: SimpleNamespace(stdout=SHA))
    class NoCredentialAccess:
        def z2_login_credentials(self, home):
            pytest.fail("source mismatch must not inspect credential files")
    with pytest.raises(RuntimeError, match="SOURCE_SHA_MISMATCH"):
        active.run("c" * 40, helper=NoCredentialAccess())

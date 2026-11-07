"""Joint PR #1337 + #1338 Host-only Path 2 acceptance.

All Z2, Bootstrap, SSH, B3 and Doctor network calls are mocks. The joint
orchestrator never loads FPGA, starts OpenOCD or touches DUT in this suite.
"""
from __future__ import annotations

import base64
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT

import sys
sys.path.insert(0, str(ROOT / "scripts"))
import opf_site2_joint_acceptance as joint


HOST = "192.168.2.99"
NEW = "f" * 64


def test_deploy_then_revalidate_once_in_order(monkeypatch):
    actions = []
    snapshots = iter([
        {"state": "ACTIVE", "asset_set_sha256": joint.OLD,
         "opf_static": "FAIL"},
        {"state": "ACTIVE", "asset_set_sha256": NEW,
         "opf_static": "PASS"},
    ])
    def doctor():
        actions.append("doctor")
        return {"overall": "WARN"}, HOST
    def observe(host, *, helper):
        assert host == HOST
        actions.append("active")
        return next(snapshots)
    def deploy(host):
        assert host == HOST
        actions.append("deploy")
        return {"result": "PASS", "fpga_reload": "NOT_RUN",
                "new_asset_set_sha256": NEW, "b2_transaction_id": "b" * 32,
                "b3_transaction_id": "c" * 32, "b3_state": "succeeded"}
    monkeypatch.setattr(joint, "doctor_snapshot", doctor)
    monkeypatch.setattr(joint, "observe_active", observe)
    monkeypatch.setattr(joint.deployer, "_load", lambda *args: object())
    monkeypatch.setattr(joint.deployer, "run", deploy)
    result = joint.execute()
    assert result["result"] == "PASS"
    assert result["action"] == "B3_DEPLOYED_AND_VERIFIED"
    assert result["new_asset_set_sha256"] == NEW
    assert result["opf_static"] == "PASS"
    assert result["dut"] == result["fpga_reload"] == "NOT_RUN"
    assert actions == ["doctor", "active", "deploy", "doctor", "active"]


def test_already_active_skips_mutating_b1_b2_b3(monkeypatch):
    monkeypatch.setattr(joint, "doctor_snapshot",
                        lambda: ({"overall": "WARN"}, HOST))
    monkeypatch.setattr(joint, "observe_active",
                        lambda *a, **kw: {"state": "ACTIVE",
                                         "asset_set_sha256": NEW,
                                         "opf_static": "PASS"})
    monkeypatch.setattr(joint.deployer, "_load", lambda *a: object())
    def no_mutation(host):
        pytest.fail("No B1/B2/B3 allowed on already corrected Active Set")
    monkeypatch.setattr(joint.deployer, "run", no_mutation)
    result = joint.execute()
    assert result["action"] == "ALREADY_ACTIVE_NO_REDEPLOY"
    assert result["b3"] == "NOT_RUN_ALREADY_ACTIVE"


@pytest.mark.parametrize("observed", [
    {"state": "ACTIVE", "asset_set_sha256": "e" * 64,
     "opf_static": "FAIL"},
    {"state": "EMPTY", "asset_set_sha256": None,
     "opf_static": "NOT_APPLICABLE"},
])
def test_unexpected_active_identity_denies_all_writes(monkeypatch, observed):
    monkeypatch.setattr(joint, "doctor_snapshot",
                        lambda: ({"overall": "WARN"}, HOST))
    monkeypatch.setattr(joint, "observe_active", lambda *a, **kw: observed)
    monkeypatch.setattr(joint.deployer, "_load", lambda *a: object())
    monkeypatch.setattr(joint.deployer, "run",
                        lambda *a: pytest.fail("Unexpected deployment"))
    with pytest.raises(joint.JointDenied,
                       match="ACTIVE_SET_NOT_EXPECTED_GEN7_DO_NOT_DEPLOY"):
        joint.execute()


def test_post_b3_changed_identity_is_not_reported_as_success(monkeypatch):
    snapshots = iter([
        {"state": "ACTIVE", "asset_set_sha256": joint.OLD,
         "opf_static": "FAIL"},
        {"state": "ACTIVE", "asset_set_sha256": "e" * 64,
         "opf_static": "PASS"},
    ])
    events = []
    monkeypatch.setattr(joint, "doctor_snapshot",
                        lambda: ({"overall": "WARN"}, HOST))
    monkeypatch.setattr(joint, "observe_active",
                        lambda *a, **kw: next(snapshots))
    monkeypatch.setattr(joint.deployer, "_load", lambda *a: object())
    def deploy(host):
        events.append("deploy")
        return {"result": "PASS", "fpga_reload": "NOT_RUN",
                "new_asset_set_sha256": NEW}
    monkeypatch.setattr(joint.deployer, "run", deploy)
    with pytest.raises(joint.JointDenied, match="B3_POST_ACTIVE_OPF_MISMATCH"):
        joint.execute()
    assert events == ["deploy"]


def test_paired_doctor_uses_one_fixed_host_and_requires_real_remote_pass(monkeypatch):
    calls = []
    monkeypatch.setattr(joint.plasma_z2, "paired_host", lambda: HOST)
    def doct(args):
        calls.append((args.host, args.paired_host))
        return {"overall": "WARN", "checks": [
            {"check": name, "status": "PASS"} for name in (
                "tcp_18080", "tcp_18081", "bootstrap_health", "bootstrap_status",
            )] + [{
                "check": "deployment_guard", "status": "PASS",
                "bootstrap_state": "bootstrap_ready",
                "runtime_state": "runtime_active",
                "capabilities": {"bundle_v3_b3_install": True},
            }]}
    monkeypatch.setattr(joint.plasma_z2, "doctor", doct)
    doc, host = joint.doctor_snapshot()
    assert doc["overall"] == "WARN" and host == HOST
    assert calls == [(HOST, False)]


def test_doctor_missing_b3_capability_blocks_before_ssh(monkeypatch):
    monkeypatch.setattr(joint.plasma_z2, "paired_host", lambda: HOST)
    monkeypatch.setattr(joint.plasma_z2, "doctor", lambda args: {
        "overall": "WARN",
        "checks": [
            {"check": name, "status": "PASS"} for name in (
                "tcp_18080", "tcp_18081", "bootstrap_health", "bootstrap_status",
            )] + [{
                "check": "deployment_guard", "status": "PASS",
                "bootstrap_state": "bootstrap_ready",
                "runtime_state": "runtime_active",
                "capabilities": {"bundle_v3_b3_install": False},
            }],
    })
    with pytest.raises(joint.JointDenied,
                       match="BOOTSTRAP_B3_NOT_QUALIFIED"):
        joint.doctor_snapshot()


@pytest.mark.parametrize("state,opf", [
    ("ACTIVE", "PASS"), ("ACTIVE", "FAIL"), ("EMPTY", "NOT_APPLICABLE"),
])
def test_pinned_readonly_active_record_validation(state, opf, monkeypatch):
    data={"state":state,
          "asset_set_sha256": NEW if state=="ACTIVE" else None,
          "generation": 8 if state=="ACTIVE" else None,
          "opf_static":opf}
    encoded=base64.b64encode(json.dumps(data).encode()).decode()
    commands=[]
    class Helper:
        def z2_login_credentials(self, home):
            return {"ssh_host": HOST}, Path("/tmp/test-known")
        def password_ssh_z2(self, command, credentials, hosts, timeout):
            commands.append(command)
            return 0, joint.MARKER + encoded
    assert joint.observe_active(HOST,helper=Helper()) == data
    assert commands[0][:3] == ["python3", "-I", "-c"]


def test_host_mismatch_never_executes_ssh():
    class Helper:
        def z2_login_credentials(self, home):
            return {"ssh_host":"192.168.2.88"},Path("/tmp/test-known")
        def password_ssh_z2(self,*a,**kw):
            pytest.fail("SSH must be refused on host mismatch")
    with pytest.raises(joint.JointDenied,match="PAIRED_TARGET_MISMATCH"):
        joint.observe_active(HOST,helper=Helper())


def test_doctor_deploy_command_remains_refused(monkeypatch, capsys):
    monkeypatch.setattr(joint.plasma_z2, "fetch_status",
                        lambda *a,**kw:pytest.fail("Doctor deploy used network"))
    rc=joint.plasma_z2.main(["deploy","--json"])
    report=json.loads(capsys.readouterr().out)
    assert rc == 2 and report["reason"]=="DEPLOY_DISABLED_BY_DESIGN"


def test_joint_gate_source_has_both_independent_entrypoints():
    paths=[
        "scripts/plasma_z2.py",
        "scripts/opf_platform_bundle_v3_build.py",
        "scripts/opf_site2_path2_bundle_deploy.py",
        "scripts/opf_site2_joint_acceptance.py",
    ]
    for name in paths:
        assert (ROOT/name).is_file()

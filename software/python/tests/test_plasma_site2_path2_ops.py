"""Host-only safety contracts: Site2 Path2 deploy / diagnose / flash."""
from __future__ import annotations
import subprocess
import sys
import types
import pytest
from .test_ppu_bundle_v3_packages_contract import ROOT
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_site2_path2_ops as ops

SHA = "a"*40
ACTIVE = ops.ACCEPTED_ACTIVE_SHA

def pin(monkeypatch):
    monkeypatch.setattr(ops.subprocess, "run",
                        lambda *_a, **_kw: subprocess.CompletedProcess(
                            args=["git"], returncode=0, stdout=SHA+"\n"))

def good():
    return {"readiness":"PASS", "opf_static":"PASS", "asset_set_sha256":ACTIVE}

def test_diagnose_read_only(monkeypatch):
    pin(monkeypatch)
    monkeypatch.setitem(sys.modules, "plasma_site2_active_readonly_path2",
                        types.SimpleNamespace(run=lambda sha: good()))
    result=ops.run("diagnose",SHA)
    assert result["status"]=="PASS"
    assert all(result[k]=="NOT_RUN" for k in ("flash","bundle_deploy","fpga_reload"))

@pytest.mark.parametrize("operation",["deploy","flash"])
def test_mutation_requires_once_flag_before_io(monkeypatch,operation):
    monkeypatch.setattr(ops,"source_guard",
                        lambda sha: (_ for _ in ()).throw(AssertionError("No IO")))
    with pytest.raises(ops.OperationDenied,match="MUTATION_REQUIRES_APPROVED_ONCE"):
        ops.run(operation,SHA)

def test_source_pin_blocks_nonmatching_sha(monkeypatch):
    pin(monkeypatch)
    with pytest.raises(ops.OperationDenied,match="SOURCE_SHA_MISMATCH"):
        ops.run("flash","b"*40,approved_once=True)
    with pytest.raises(ops.OperationDenied,match="SOURCE_SHA_INVALID"):
        ops.run("deploy","invalid",approved_once=True)

def test_deploy_already_active_noop(monkeypatch):
    pin(monkeypatch)
    events=[]
    def deploy():
        events.append("deploy")
        return {"result":"PASS","action":"ALREADY_ACTIVE_NO_REDEPLOY",
                "asset_set_sha256":ACTIVE}
    def diagnose(sha):
        events.append("diagnose")
        return good()
    monkeypatch.setitem(sys.modules,"opf_site2_joint_acceptance",
                        types.SimpleNamespace(execute=deploy))
    monkeypatch.setitem(sys.modules,"plasma_site2_active_readonly_path2",
                        types.SimpleNamespace(run=diagnose))
    result=ops.run("deploy",SHA,approved_once=True)
    assert result["status"]=="PASS"
    assert result["action"]=="ALREADY_ACTIVE_NO_REDEPLOY"
    assert events==["deploy","diagnose"]

def test_deploy_bad_postcheck_never_resubmits(monkeypatch):
    pin(monkeypatch)
    events=[]
    def deploy():
        events.append("B3")
        return {"result":"PASS","action":"B3_DEPLOYED_AND_VERIFIED",
                "new_asset_set_sha256":ACTIVE}
    monkeypatch.setitem(sys.modules,"opf_site2_joint_acceptance",
                        types.SimpleNamespace(execute=deploy))
    monkeypatch.setitem(sys.modules,"plasma_site2_active_readonly_path2",
                        types.SimpleNamespace(run=lambda sha:{
                            "readiness":"PASS","asset_set_sha256":"0"*64}))
    with pytest.raises(ops.OperationDenied,match="DEPLOY_POST_CHECK_DENIED"):
        ops.run("deploy",SHA,approved_once=True)
    assert events==["B3"]

def test_flash_unknown_keeps_job_id_without_retry(monkeypatch):
    pin(monkeypatch)
    events=[]
    def flash(sha,asset):
        assert sha==SHA and asset==ACTIVE
        events.append("POST")
        return {"flash_result":"OUTCOME_UNKNOWN","job_id":"job-preserved",
                "submission_count":1}
    monkeypatch.setitem(sys.modules,"plasma_site2_single_flash_path2",
                        types.SimpleNamespace(execute=flash))
    result=ops.run("flash",SHA,approved_once=True)
    assert result["status"]=="FAILED_OR_OUTCOME_UNKNOWN"
    assert result["job"]["job_id"]=="job-preserved"
    assert result["auto_retry"]=="DISABLED"
    assert events==["POST"]

def test_flash_success_one_call(monkeypatch):
    pin(monkeypatch)
    events=[]
    def flash(sha,asset):
        events.append("POST")
        return {"flash_result":"PASS","submission_count":1,
                "readback_sha256":"e"*64,"safe_off":True}
    monkeypatch.setitem(sys.modules,"plasma_site2_single_flash_path2",
                        types.SimpleNamespace(execute=flash))
    result=ops.run("flash",SHA,approved_once=True)
    assert result["status"]=="PASS" and result["submission_count"]==1
    assert events==["POST"]

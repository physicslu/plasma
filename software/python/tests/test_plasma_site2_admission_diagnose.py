"""Host-only fail-closed contract checks for Site 2 Admission diagnostic."""
from __future__ import annotations
import importlib.util,json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from .test_ppu_bundle_v3_packages_contract import ROOT

spec=importlib.util.spec_from_file_location("plasma_site2_admission_diagnose",ROOT/"scripts/plasma_site2_admission_diagnose.py")
assert spec and spec.loader
SCRIPT=importlib.util.module_from_spec(spec);spec.loader.exec_module(SCRIPT)
SHA="a"*40;HOST="192.168.2.99"
def state():
    return {"readiness":"NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS",
            "z2":{"engine":{"status":"VERIFIED","abi":5,"driver":"plasma_swd"},
       "fpga":{"status":"IMAGE","boot_match":True,"manager_state":"operating"},
       "site2_seal":{"present":False},"site2_admission":{"present":False},
       "openocd_pids":[]},
       "rest":{"status":"OBSERVED","health_ready":True,
         "node_matches_status":True,"lease_busy":False,"active_job_count":0,
         "site2_idle":True}}
class Pre:
    def __init__(self,s):self.s=s
    def run(self,host,sha):
        assert (host,sha)==(HOST,SHA)
        return self.s
class Helper:
    def __init__(self,payload):self.calls=[];self.payload=payload
    def z2_login_credentials(self,home):
        self.calls.append("credential")
        return {"ssh_host":HOST},Path("/tmp/known-hosts")
    def password_ssh_z2(self,command,creds,known,timeout):
        self.calls.append(("ssh",command))
        return 0,SCRIPT.MARK+json.dumps(self.payload)+"\n"
def reply():
    return {"schema":"plasma.site2.admission-diagnostic.v1",
            "result":"DENIED","code":"RELEASE_NOT_ABI5_INDEPENDENT",
            "revoke":"NOT_NEEDED","record_present":False,
            "fpga_manager_state":"operating"}
def test_root_entry_diagnostic_is_source_pinned_and_releases_record():
    h=Helper(reply())
    with patch.object(SCRIPT.subprocess,"run",return_value=SimpleNamespace(stdout=SHA+"\n")):
        out=SCRIPT.run(HOST,SHA,preflight=Pre(state()),helper=h)
    assert out["observation"]["code"]=="RELEASE_NOT_ABI5_INDEPENDENT"
    assert out["flash"]=="NOT_RUN" and out["fpga_reload"]=="NOT_RUN"
    remote=h.calls[-1][1][3]
    assert h.calls[-1][1][:3]==["python3","-I","-c"]
    assert 'call("admit")' in remote and 'call("revoke")' in remote
    for forbidden in ['"flash_cycle"','"load_fpga"','"reset"','"erase"','"recover"','"stop"']:
        assert forbidden not in remote
@pytest.mark.parametrize("change",[
 ("openocd_pids",[543]),
 ("site2_admission",{"present":True}),
 ("site2_seal",{"present":True}),
])
def test_bad_ownership_cannot_reach_ssh(change):
    s=state();key,value=change;s["z2"][key]=value
    h=Helper(reply())
    with patch.object(SCRIPT.subprocess,"run",return_value=SimpleNamespace(stdout=SHA+"\n")):
        with pytest.raises(RuntimeError,match="DIAGNOSTIC_SAFETY_PRECONDITION_FAILED"):
            SCRIPT.run(HOST,SHA,preflight=Pre(s),helper=h)
    assert not h.calls
def test_source_sha_change_denied_before_ssh():
    h=Helper(reply())
    with patch.object(SCRIPT.subprocess,"run",return_value=SimpleNamespace(stdout=SHA+"\n")):
        with pytest.raises(RuntimeError,match="SOURCE_SHA_MISMATCH"):
            SCRIPT.run(HOST,"b"*40,preflight=Pre(state()),helper=h)
    assert not h.calls


def test_diagnostic_uses_active_root_worker_interpreter_not_system_python():
    remote=SCRIPT.REMOTE
    assert '["/bin/systemctl","show","--property=MainPID"' in remote
    assert '(Path("/proc")/pid/"exe").resolve(strict=True)' in remote
    assert 'native.is_relative_to("/opt/plasma/python")' in remote
    assert "info.st_uid!=0" in remote and "info.st_mode&0o022" in remote
    assert 'argv=[str(native),"-I","-B",str(adm)]' in remote
    assert 'argv=[sys.executable' not in remote
    assert 'call("admit")' in remote and 'call("revoke")' in remote


def test_cli_denied_admission_is_not_pass(monkeypatch, capsys):
    payload=SCRIPT.run
    try:
        monkeypatch.setattr(SCRIPT, "run", lambda *a: {
            "schema":"plasma.site2.path2-admission-diagnostic.v1",
            "observation":reply(), "flash":"NOT_RUN"})
        assert SCRIPT.main(["--host",HOST,"--source-sha",SHA])==1
        observed=json.loads(capsys.readouterr().out.split("=",1)[1])
        assert observed["observation"]["result"]=="DENIED"
        assert observed["flash"]=="NOT_RUN"
    finally:
        monkeypatch.setattr(SCRIPT,"run",payload)


def test_cli_admitted_requires_revoke_pass_and_no_record(monkeypatch,capsys):
    result=reply()
    result.update(result="ADMITTED",code="NOT_RECORDED",revoke="PASS")
    monkeypatch.setattr(SCRIPT, "run", lambda *a: {
        "schema":"plasma.site2.path2-admission-diagnostic.v1",
        "observation":result,"flash":"NOT_RUN"})
    assert SCRIPT.main(["--host",HOST,"--source-sha",SHA])==0
    capsys.readouterr()
    result["record_present"]=True
    assert SCRIPT.main(["--host",HOST,"--source-sha",SHA])==1

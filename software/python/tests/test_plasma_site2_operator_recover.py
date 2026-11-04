"""Host-only admission tests for owner-approved Site 2 operator recovery."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT

SPEC=importlib.util.spec_from_file_location(
    "plasma_site2_operator_recovery_tests",ROOT/"scripts/plasma_site2_operator_recover.py")
assert SPEC and SPEC.loader
SCRIPT=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SCRIPT)
SHA="a"*40
HOST="192.168.2.99"

def ready():
    return {
        "rest":{"status":"OBSERVED","health_ready":True,"node_matches_status":True,
            "lease_busy":False,"active_job_count":0,"activation_active":False,
            "site2_idle":True,"site2_enabled":True,"site2_interface":"openocd",
            "site2_target_matches":True},
        "z2":{
            "engine":{"status":"VERIFIED","abi":5,"driver":"plasma_swd"},
            "fpga":{"status":"IMAGE","boot_match":True},
            "site2_seal":{"present":True},
            "site2_admission":{"present":False},
            "openocd_pids":[],
            "services":{"plasma-site-worker":{"ActiveState":"active"},
                        "plasma-server":{"ActiveState":"active"}}
        },
    }

class Preflight:
    def __init__(self,receipt):self.receipt=receipt
    def run(self,host,sha):
        assert host==HOST and sha==SHA
        return self.receipt

class Helper:
    def __init__(self,receipt):self.receipt=receipt;self.calls=[]
    def z2_login_credentials(self,home):
        self.calls.append("credentials")
        return {"ssh_host":HOST},Path("/not-used")
    def password_ssh_z2(self,args,creds,hosts,timeout):
        self.calls.append(("ssh",args))
        return 0,SCRIPT.MARKER+json.dumps(self.receipt)+"\n"

def recovery(status="RECOVERY_ACCEPTED"):
    return {"schema":"plasma.site2.operator-recovery.v1",
      "status":status,"service_was_active":True,"service_restored":True,
      "recovery_result":"RECOVERED" if status=="RECOVERY_ACCEPTED" else "DENIED",
      "seal_present_before":True,"seal_present_after":status!="RECOVERY_ACCEPTED",
      "safe_off":"VERIFIED" if status=="RECOVERY_ACCEPTED" else "NOT_PROVEN",
      "evidence_path":"/var/lib/plasma-site-worker/recovery/example.json",
      "error":"NONE" if status=="RECOVERY_ACCEPTED" else "RECOVERY_PRECONDITION_OR_SAFE_OFF_DENIED"}

def invoke(preflight,receipt=None,source=SHA):
    helper=Helper(receipt or recovery())
    with patch.object(SCRIPT.subprocess,"run",return_value=SimpleNamespace(stdout=SHA+"\n")):
        output=SCRIPT.run(HOST,source,preflight=Preflight(preflight),helper=helper)
    return output,helper

def test_single_site_recovery_routes_only_protected_root_cli():
    out,h=invoke(ready())
    assert out["status"]=="RECOVERY_ACCEPTED"
    assert out["flash"]=="NOT_RUN" and out["fpga_reload"]=="NOT_RUN"
    assert out["runtime_deploy"]=="NOT_RUN"
    assert h.calls[-1][1][:3]==["python3","-I","-c"]
    remote=h.calls[-1][1][3]
    assert '"/bin/systemctl","stop",UNIT' in remote
    assert '"/bin/systemctl","start",UNIT' in remote
    assert '"recover","2","--operator","plasma-site2-owner"' in remote
    for banned in ["os.remove(", "unlink(", "rm -", '"erase"', '"flash_cycle"',
                   '"fpga-reload"', '"/dev/mem"', '"plasma-server.service"']:
        assert banned not in remote

@pytest.mark.parametrize(("key","value"),[
 ("openocd_pids",[222]),
 ("site2_admission",{"present":True}),
 ("engine",{"status":"MISMATCH","abi":5,"driver":"plasma_swd"}),
 ("fpga",{"status":"IMAGE","boot_match":False}),
])
def test_invalid_live_ownership_or_image_fails_before_ssh(key,value):
    p=ready()
    p["z2"][key]=value
    h=Helper(recovery())
    with patch.object(SCRIPT.subprocess,"run",return_value=SimpleNamespace(stdout=SHA+"\n")):
        with pytest.raises(RuntimeError,match="LIVE_RECOVERY_ADMISSION_DENIED"):
            SCRIPT.run(HOST,SHA,preflight=Preflight(p),helper=h)
    assert not h.calls

def test_busy_lease_denies_recovery_before_ssh():
    p=ready()
    p["rest"]["lease_busy"]=True
    h=Helper(recovery())
    with patch.object(SCRIPT.subprocess,"run",return_value=SimpleNamespace(stdout=SHA+"\n")):
        with pytest.raises(RuntimeError,match="LIVE_RECOVERY_ADMISSION_DENIED"):
            SCRIPT.run(HOST,SHA,preflight=Preflight(p),helper=h)
    assert not h.calls

def test_denied_root_recovery_does_not_claim_pass():
    out,_=invoke(ready(),recovery("BLOCKED"))
    assert out["status"]=="BLOCKED"
    assert out["hardware_safe_off"]=="NOT_PROVEN"

def test_exact_source_sha_required():
    h=Helper(recovery())
    with patch.object(SCRIPT.subprocess,"run",return_value=SimpleNamespace(stdout=SHA+"\n")):
        with pytest.raises(RuntimeError,match="SOURCE_SHA_MISMATCH"):
            SCRIPT.run(HOST,"b"*40,preflight=Preflight(ready()),helper=h)
    assert not h.calls

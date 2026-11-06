"""Host-only contract tests for the strictly read-only Site 2 Path 2 probe."""
from __future__ import annotations
import importlib.util
import json
import pathlib
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT

SCRIPT=ROOT/"scripts/plasma_site2_path2_preflight.py"
SPEC=importlib.util.spec_from_file_location("plasma_site2_readonly_contract",SCRIPT)
assert SPEC and SPEC.loader
PROBE=importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PROBE)
SHA="a"*40
HOST="192.168.2.99"

def observation():
    return {
      "schema":"plasma.site2.z2-observation.v1",
      "root_read_only_observer":True,
      "release":{"current":"0.2.1-abc","valid_target":True},
      "bootstrap_renderer":{"present":True},
      "services":{k:{"ActiveState":"active"} for k in
        ("plasma-server","plasma-site-worker","plasma-bootstrap")},
      "engine":{"status":"VERIFIED","abi":5,"driver":"plasma_swd"},
      "fpga":{"status":"IMAGE","manager_state":"operating","boot_match":True},
      "site2_seal":{"present":False},
      "site2_admission":{"present":False},
      "site_worker_control_socket":{"present":True,"socket":True,"root_owned":True,"mode":"0660"},
      "site_worker_transport_socket":{"present":True,"socket":True,"root_owned":True,"mode":"0660"},
      "runtime_control_socket":{"present":True,"socket":True,"root_owned":True,"mode":"0660"},
      "openocd_pids":[],
      "site_lock_owner":"NOT_VERIFIED_NO_LOCK_ACQUISITION",
      "site_hw_probe":"NOT_RUN","fpga_reload":"NOT_RUN",
      "flash":"NOT_RUN","recovery":"NOT_RUN",
    }

class Helper:
    def __init__(self,z,rc=0):
        self.z=z
        self.rc=rc
        self.calls=[]
    def z2_login_credentials(self,home):
        self.calls.append("credential")
        return {"ssh_host":HOST},pathlib.Path("/not-used/known_hosts")
    def password_ssh_z2(self,command,creds,hosts,timeout=60):
        self.calls.append(("ssh",command))
        return self.rc, PROBE.MARKER+json.dumps(self.z,sort_keys=True)+"\n"

class Baseline:
    def probe_status(self,host):
        assert host==HOST
        return {"device_id_observed":"ppu-device-"+"c"*24,
                "phase":"READ_ONLY_DEVICE_PROBE"}

def rest(_):
    return {"status":"OBSERVED","health_ready":True,
      "node_matches_status":True,"lease_busy":False,
      "active_job_count":0,"activation_active":False,
      "site2_enabled":True,"site2_interface":"openocd",
      "site2_target_matches":True,"site2_idle":True}

def run_with(z,host=HOST,rest_fn=rest):
    h=Helper(z)
    with patch.object(PROBE.subprocess,"run",return_value=SimpleNamespace(stdout=SHA+"\n")):
        receipt=PROBE.run(host,SHA,helper=h,baseline=Baseline(),rest=rest_fn)
    return receipt,h

def test_host_only_clean_observation_is_not_hil_pass():
    result,h=run_with(observation())
    assert result["status"]=="READ_ONLY_OBSERVED"
    assert result["readiness"]=="NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS"
    assert result["limits"]["site_lock"]=="NOT_VERIFIED"
    assert result["limits"]["flash"]=="NOT_RUN"
    assert result["z2"]["site_hw_probe"]=="NOT_RUN"
    assert h.calls[-1][1][:3]==["python3","-I","-c"]
    remote=h.calls[-1][1][3]
    assert "/bin/systemctl" in remote and '"show"' in remote
    for banned in ['"restart"','"stop"','"start"','"kill"','"erase"','"/dev/mem"',
                   '"write"', '"load"']:
        assert banned not in remote
    assert 'subprocess.run(["/bin/systemctl","show"' in remote
    assert 'subprocess.run(["/bin/systemctl","restart"' not in remote
    assert '"flash":"NOT_RUN"' in remote

@pytest.mark.parametrize(("field","value","blocker"),[
    ("site2_seal",{"present":True},"SITE2_SEALED"),
    ("site2_admission",{"present":True},"SITE2_ADMISSION_RECORD_PRESENT"),
    ("openocd_pids",[1234],"OPENOCD_PROCESS_PRESENT"),
    ("engine",{"status":"MISMATCH","abi":5,"driver":"plasma_swd"},"ENGINE_SELECTION_NOT_VERIFIED"),
    ("fpga",{"status":"IMAGE","manager_state":"operating","boot_match":False},
     "FPGA_IDENTITY_OR_BOOT_UNVERIFIED"),
])
def test_readonly_observation_cannot_claim_ready_on_hardware_blocker(field,value,blocker):
    z=observation()
    z[field]=value
    result,_=run_with(z)
    assert result["readiness"]=="BLOCKED_OR_UNVERIFIED"
    assert blocker in result["blockers"]

def test_rest_unavailable_is_not_reported_ready():
    result,_=run_with(observation(),rest_fn=lambda _host:{"status":"UNAVAILABLE"})
    assert "GATEWAY_STATUS_UNAVAILABLE" in result["blockers"]

def test_wrong_host_refused_without_ssh():
    h=Helper(observation())
    with patch.object(PROBE.subprocess,"run",return_value=SimpleNamespace(stdout=SHA+"\n")):
        with pytest.raises(RuntimeError,match="HOST_SCOPE_DENIED"):
            PROBE.run("8.8.8.8",SHA,helper=h,baseline=Baseline(),rest=rest)
    assert not h.calls

def test_mismatched_pinned_sha_refused_without_ssh():
    h=Helper(observation())
    with patch.object(PROBE.subprocess,"run",return_value=SimpleNamespace(stdout=SHA+"\n")):
        with pytest.raises(RuntimeError,match="SOURCE_SHA_MISMATCH"):
            PROBE.run(HOST,"b"*40,helper=h,baseline=Baseline(),rest=rest)
    assert not h.calls

def test_remote_receipt_claiming_flash_run_is_rejected():
    z=observation()
    z["flash"]="PASS"
    h=Helper(z)
    with patch.object(PROBE.subprocess,"run",return_value=SimpleNamespace(stdout=SHA+"\n")):
        with pytest.raises(RuntimeError,match="REMOTE_RECEIPT_INVALID"):
            PROBE.run(HOST,SHA,helper=h,baseline=Baseline(),rest=rest)

def test_runtime_private_socket_is_not_falsely_rejected():
    z=observation()
    z["runtime_control_socket"]={
        "present":True,"socket":True,"root_owned":False,
        "uid":999,"gid":999,"mode":"0600","writable_by_others":False}
    result,_=run_with(z)
    assert "SOCKET_PERMISSION_REVIEW_runtime_control_socket" not in result["blockers"]
    assert result["readiness"]=="NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS"


def test_runtime_socket_broad_permissions_are_rejected():
    z=observation()
    z["runtime_control_socket"]={
        "present":True,"socket":True,"root_owned":False,
        "uid":999,"gid":999,"mode":"0666","writable_by_others":True}
    result,_=run_with(z)
    assert "SOCKET_PERMISSION_REVIEW_runtime_control_socket" in result["blockers"]


def test_manager_sysfs_uses_bounded_read_not_virtual_stat_size():
    remote=PROBE.REMOTE
    assert 'ms=sysfs_text("/sys/class/fpga_manager/fpga0/state",128)' in remote
    assert 'stream.read(limit+1)' in remote
    assert 'ms=literal("/sys/class/fpga_manager/fpga0/state",128)' not in remote


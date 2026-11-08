"""Host-only negative safety gates for post-install Site2 C-3 Worker identity."""
from __future__ import annotations
import importlib.util
from pathlib import Path
import sys
from copy import deepcopy
import pytest
ROOT=Path(__file__).resolve().parents[3]
sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location("s2_postinstall_path2",ROOT/"scripts/plasma_s2_postinstall_site2_path2.py")
assert spec and spec.loader
m=importlib.util.module_from_spec(spec);sys.modules[spec.name]=m;spec.loader.exec_module(m)
def fixtures():
    snap={"status":"READ_ONLY_OBSERVED","readiness":"NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS","blockers":[],
        "z2":{"release":{"current":m.RELEASE},
              "engine":{"status":"VERIFIED","abi":5,"driver":"plasma_swd",
                        "openocd_sha256_observed":m.ENGINE_BIN,"admission_sha256_observed":m.ENGINE_ADM},
              "fpga":{"status":"IMAGE","boot_match":True,"manager_state":"operating","image_id":m.IMAGE,
                      "boot_id_sha12":"abc123","journal_sha256":"0"*64},
              "services":{"plasma-site-worker":{"MainPID":925,"ActiveState":"active"}},
              "site2_seal":{"present":False},"site2_admission":{"present":False},"openocd_pids":[]},
        "rest":{"site2_idle":True,"active_job_count":0,"lease_busy":False,"activation_active":False}}
    worker={"schema":"plasma.s2.worker-live.v1","state":"OBSERVED","file_sha256":m.WORKER_SHA256,
            "worker_pid":925,"worker_executable_verified":True,"worker_cmdline_verified":True,
            "process_started_after_file_install":True}
    status={"identity":{"device_id":m.DEVICE},"bootstrap":{"state":"bootstrap_ready"},
            "runtime":{"state":"runtime_active","git_sha":m.RUNTIME},
            "deployment":{"state":"succeeded"}}
    assets={"state":"ACTIVE","asset_set_sha256":m.BUNDLE_B}
    return snap,worker,status,assets
def test_source_and_live_code_accept_complete_evidence():
    assert m.validate(*fixtures())["status"]=="PASS"
@pytest.mark.parametrize("path,value",[
    (("z2","site2_seal","present"),True),
    (("z2","fpga","boot_match"),False),
    (("z2","engine","openocd_sha256_observed"),"0"*64),
    (("rest","active_job_count"),1),
    (("z2","services","plasma-site-worker","MainPID"),924),
])
def test_preflight_negative_changes_fail_closed(path,value):
    args=list(fixtures());n=args[0]
    for k in path[:-1]:n=n[k]
    n[path[-1]]=value
    with pytest.raises(RuntimeError):m.validate(*args)
@pytest.mark.parametrize("key,value",[
    ("state","UNVERIFIED"),("file_sha256","0"*64),
    ("worker_pid",927),("worker_cmdline_verified",False),
    ("process_started_after_file_install",False)])
def test_untrusted_live_worker_denied(key,value):
    args=list(fixtures());args[1][key]=value
    with pytest.raises(RuntimeError,match="WORKER_LIVE_SOURCE_NOT_ATTESTED"):
        m.validate(*args)
def test_wrong_runtime_or_active_bundle_denied():
    for index,path,value in [
        (2,("runtime","git_sha"),"0"*40),
        (2,("deployment","state"),"recovery_required"),
        (3,("asset_set_sha256",),"f"*64)]:
        args=list(fixtures());d=args[index]
        for k in path[:-1]:d=d[k]
        d[path[-1]]=value
        with pytest.raises(RuntimeError,match="RUNTIME_OR_ACTIVE_BUNDLE_MISMATCH"):
            m.validate(*args)

"""Host-only contract: one bounded Site 2 physical flash, no implicit retry.

No DUT, FPGA, SWD, Root privilege or network is accessed by these tests.
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest
from .test_ppu_bundle_v3_packages_contract import ROOT

sys.path.insert(0,str(ROOT/"scripts"))
import plasma_site2_single_flash_path2 as flow

SHA="a"*40
ACTIVE="b82ce5fd0725dacdd02a3805168e847b190841c95887ba2c567761a48024e393"
JOB_ID="job-20261107-140201-1234abcd"
HOST="192.168.2.99"


def observation(*_args,**_kwargs):
    return {
        "readiness":"NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS","blockers":[],
        "z2":{"site2_seal":{"present":False},
              "site2_admission":{"present":False},"openocd_pids":[]},
        "rest":{"site2_idle":True},
    }


def active(*_args,**_kwargs):
    return {"state":"ACTIVE","asset_set_sha256":ACTIVE,"opf_static":"PASS"}


def admitted(*_args,**_kwargs):
    return {"observation":{"result":"ADMITTED","code":"NOT_RECORDED",
                           "revoke":"PASS","record_present":False}}


def complete():
    return {"job_id":JOB_ID,"site_id":2,"operation":"flash_cycle",
            "state":"success","stage":"flash_cycle",
            "result":{"state":"success","site_id":2,"operation":"flash_cycle",
                "image_sha256":flow.IMAGE_SHA,"image_size":flow.IMAGE_BYTES,
                "attempts":1,
                "details":{"flash_cycle":{"result":"PASS","safe_off":True,
                   "readback_sha256":flow.IMAGE_SHA,
                   "bytes_verified":flow.IMAGE_BYTES,
                   "opf_provider_package":flow.PROVIDER,
                   "opf_profile_package":flow.PROFILE}}}}


def prepare(monkeypatch, *, root=admitted, preflight=observation,
            asset=active, wait=None):
    events=[]
    monkeypatch.setattr(flow,"current_source",lambda sha: events.append("source"))
    monkeypatch.setattr(flow,"paired_target",lambda:HOST)
    monkeypatch.setattr(flow,"firmware",lambda:b"X"*flow.IMAGE_BYTES)
    monkeypatch.setattr(flow.preflight,"run",lambda *a,**kw: (
        events.append("preflight") or preflight(*a,**kw)))
    monkeypatch.setattr(flow.joint,"observe_active",lambda *a,**kw: (
        events.append("asset") or asset(*a,**kw)))
    monkeypatch.setattr(flow.admission,"run",lambda *a,**kw: (
        events.append("admit_revoke") or root(*a,**kw)))
    def post(host, data):
        assert host==HOST and len(data)==flow.IMAGE_BYTES
        events.append("ONE_POST")
        return JOB_ID
    monkeypatch.setattr(flow,"submit_exactly_once",post)
    monkeypatch.setattr(flow,"wait_job",lambda *a,**kw: (
        events.append("poll") or (wait(*a,**kw) if wait is not None else complete())))
    return events


def test_one_post_only_after_root_admit_revoke_and_static_opf(monkeypatch):
    events=prepare(monkeypatch)
    result=flow.execute(SHA,ACTIVE)
    assert result["flash_result"]=="PASS"
    assert result["safe_off"] is True
    assert result["readback_sha256"]==flow.IMAGE_SHA
    assert result["submission_count"]==1
    assert events==["source","preflight","asset","admit_revoke",
                    "preflight","asset","ONE_POST","poll","preflight"]


@pytest.mark.parametrize("root",[
    lambda *a,**kw: {"observation":{"result":"DENIED",
       "code":"NATIVE_ARMV7_PYTHON_RUNTIME_REQUIRED",
       "revoke":"NOT_NEEDED","record_present":False}},
    lambda *a,**kw: {"observation":{"result":"ADMITTED",
       "code":"NOT_RECORDED","revoke":"FAIL","record_present":True}},
])
def test_no_post_on_root_admission_denial_or_unproven_cleanup(monkeypatch,root):
    events=prepare(monkeypatch,root=root)
    with pytest.raises(flow.FlashDenied,match="SITE2_ROOT_ADMISSION_DENIED"):
        flow.execute(SHA,ACTIVE)
    assert "ONE_POST" not in events


def test_no_post_on_unexpected_active_set(monkeypatch):
    events=prepare(monkeypatch,asset=lambda *a,**kw: {
        "state":"ACTIVE","asset_set_sha256":"c"*64,"opf_static":"PASS"})
    with pytest.raises(flow.FlashDenied,match="ACTIVE_OPF_SET_MISMATCH"):
        flow.execute(SHA,ACTIVE)
    assert "admit_revoke" not in events and "ONE_POST" not in events


def test_one_post_on_polling_uncertainty_preserves_job_id(monkeypatch):
    def uncertain(*a,**kw):
        raise flow.FlashDenied("GATEWAY_GET_DENIED")
    events=prepare(monkeypatch,wait=uncertain)
    result=flow.execute(SHA,ACTIVE)
    assert result["flash_result"]=="OUTCOME_UNKNOWN"
    assert result["job_id"]==JOB_ID
    assert result["submission_count"]==1
    assert events.count("ONE_POST")==1
    assert "fpga_reload" in result and result["fpga_reload"]=="NOT_RUN"


@pytest.mark.parametrize("mutate",[
    lambda job:job["result"]["details"]["flash_cycle"].update(safe_off=False),
    lambda job:job["result"]["details"]["flash_cycle"].update(readback_sha256="a"*64),
    lambda job:job["result"].update(attempts=2),
    lambda job:job["result"]["details"]["flash_cycle"].update(bytes_verified=0),
    lambda job:job.update(state="failed"),
])
def test_flash_job_pass_requires_exact_readback_safeoff_one_attempt(mutate):
    job=complete()
    mutate(job)
    assert flow.verify_job(job)["flash_result"]=="FAIL_OR_INCOMPLETE"


def test_image_provenance_is_exact_tracked_firmware():
    image=flow.firmware()
    assert len(image)==18768
    assert hashlib.sha256(image).hexdigest()==flow.IMAGE_SHA


def test_source_and_job_regex_fullmatch_contract():
    assert flow.JOB_RE.fullmatch(JOB_ID)
    assert flow.HEX40.fullmatch(SHA)
    assert flow.HEX64.fullmatch(ACTIVE)
    assert not flow.JOB_RE.fullmatch(JOB_ID+"EXTRA")
    assert not flow.HEX40.fullmatch(SHA+"a")

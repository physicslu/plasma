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
              "site2_admission":{"present":False},"openocd_pids":[],
              "engine":{"status":"VERIFIED","driver":"plasma_swd","abi":5,
                  "openocd_sha256_observed":"b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861",
                  "admission_sha256_observed":"3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"}},
        "rest":{"site2_idle":True},
    }


def active(*_args,**_kwargs):
    return {"state":"ACTIVE","asset_set_sha256":ACTIVE,"opf_static":"PASS"}


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


def prepare(monkeypatch, *, preflight=observation, asset=active, wait=None):
    events=[]
    monkeypatch.setattr(flow,"current_source",lambda sha: events.append("source"))
    monkeypatch.setattr(flow,"paired_target",lambda:HOST)
    monkeypatch.setattr(flow,"firmware",lambda:b"X"*flow.IMAGE_BYTES)
    monkeypatch.setattr(flow.preflight,"run",lambda *a,**kw: (
        events.append("preflight") or preflight(*a,**kw)))
    monkeypatch.setattr(flow.joint,"observe_active",lambda *a,**kw: (
        events.append("asset") or asset(*a,**kw)))
    def post(host, data):
        assert host==HOST and len(data)==flow.IMAGE_BYTES
        events.append("ONE_POST")
        return JOB_ID
    monkeypatch.setattr(flow,"submit_exactly_once",post)
    monkeypatch.setattr(flow,"wait_job",lambda *a,**kw: (
        events.append("poll") or (wait(*a,**kw) if wait is not None else complete())))
    return events


def test_one_post_after_previous_admit_revoke_and_opf_static(monkeypatch):
    events=prepare(monkeypatch)
    result=flow.execute(SHA,ACTIVE)
    assert result["flash_result"]=="PASS"
    assert result["safe_off"] is True
    assert result["readback_sha256"]==flow.IMAGE_SHA
    assert result["submission_count"]==1
    assert events==["source","preflight","asset",
                    "preflight","asset","ONE_POST","poll","preflight"]


@pytest.mark.parametrize("binary_sha,admission_sha",[
    ("0"*64,"3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"),
    ("b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861","0"*64),
])
def test_no_post_if_selected_engine_identity_changed(monkeypatch,binary_sha,admission_sha):
    def mismatch(*_args,**_kwargs):
        state=observation()
        state["z2"]["engine"]["openocd_sha256_observed"]=binary_sha
        state["z2"]["engine"]["admission_sha256_observed"]=admission_sha
        return state
    events=prepare(monkeypatch,preflight=mismatch)
    with pytest.raises(flow.FlashDenied,match="SITE2_ADMITTED_ENGINE_IDENTITY_CHANGED"):
        flow.execute(SHA,ACTIVE)
    assert "ONE_POST" not in events


def test_no_post_on_unexpected_active_set(monkeypatch):
    events=prepare(monkeypatch,asset=lambda *a,**kw: {
        "state":"ACTIVE","asset_set_sha256":"c"*64,"opf_static":"PASS"})
    with pytest.raises(flow.FlashDenied,match="ACTIVE_OPF_SET_MISMATCH"):
        flow.execute(SHA,ACTIVE)
    assert "ONE_POST" not in events


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


@pytest.mark.parametrize("response,expected", [
    ({"job": {"job_id": JOB_ID}}, JOB_ID),
    ({"job_id": JOB_ID}, "POST_JOB_ID_UNKNOWN_DO_NOT_RESUBMIT"),
    ({"job": {}}, "POST_JOB_ID_UNKNOWN_DO_NOT_RESUBMIT"),
])
def test_accepted_rest_post_requires_nested_gateway_job_id_and_never_retries(
    monkeypatch, response, expected
):
    import json
    requests=[]

    class Connection:
        def __init__(self, host, port, timeout):
            assert host==HOST and port==18080
        def request(self, method, path, body=None, headers=None):
            requests.append((method,path,body))
        def getresponse(self):
            class Reply:
                status=202
                def read(self, limit):
                    return json.dumps(response).encode("utf8")
            return Reply()
        def close(self):
            pass

    monkeypatch.setattr(flow.http.client,"HTTPConnection",Connection)
    if expected == JOB_ID:
        assert flow.submit_exactly_once(HOST,b"test") == JOB_ID
    else:
        with pytest.raises(flow.FlashDenied,match=expected):
            flow.submit_exactly_once(HOST,b"test")
    assert len(requests)==1
    assert requests[0][0:2]==("POST","/api/jobs")
    payload=json.loads(requests[0][2])
    assert payload["site_id"]==2
    assert payload["operation"]=="flash_cycle"
    assert payload["asset_sha256"]==flow.IMAGE_SHA
    assert payload["provider"]==flow.PROVIDER
    assert payload["profile"]==flow.PROFILE

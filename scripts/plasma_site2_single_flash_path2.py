#!/usr/bin/env python3
"""Path 2: exactly ONE authorized REST Site 2 flash_cycle and readback.

This is an acceptance entrypoint, not a product deployment flow. It reuses
the already selected Active Bundle, installed OpenOCD and enrolled SWPC target.
It does not deploy, activate, reload FPGA, switch Engine, restart services,
remove seals, auto-cancel or resubmit any uncertain Job. The Runtime's trusted
OPF/Root Worker remains the final execution authority.
"""
from __future__ import annotations

import base64
import hashlib
import http.client
import ipaddress
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import quote

import opf_site2_joint_acceptance as joint
import plasma_site2_path2_preflight as preflight
import plasma_wordport_program as pairing

ROOT = Path(__file__).resolve().parents[1]
IMAGE = ROOT / "docs/evidence/bluepill-z2-flash-2026-10-27/firmware/plasma-blue-pill-cdc.bin"
IMAGE_SHA = "8d3ffb02b80f779758829ff5c3727f5ade466652806d9124fa17c39fc48d841d"
IMAGE_BYTES = 18768
ICPN = "STM32F103C8T6"
SITE = 2
PROVIDER = "openocd-platform-reference"
PROFILE = "stm32f103c8t6-site2"
JOB_RE = re.compile(r"job-[0-9]{8}-[0-9]{6}-[0-9a-f]{8}\Z")
HEX40 = re.compile(r"[0-9a-f]{40}\Z")
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
TERMINAL = frozenset(("success","failed","error","cancelled","timeout","aborted"))
SCHEMA = "plasma.site2.path2-single-rest-flash.v1"


class FlashDenied(RuntimeError):
    pass


def require(ok: bool, reason: str) -> None:
    if not ok:
        raise FlashDenied(reason)


def current_source(expected: str) -> None:
    require(bool(HEX40.fullmatch(expected)), "SOURCE_SHA_INVALID")
    current = subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                             capture_output=True,text=True,check=True,
                             timeout=8).stdout.strip()
    require(current == expected, "SOURCE_SHA_MISMATCH")


def paired_target() -> str:
    creds, _known_hosts = pairing.z2_login_credentials(Path.home())
    host = creds.get("ssh_host")
    try:
        address = ipaddress.ip_address(host)
    except (ValueError, TypeError) as exc:
        raise FlashDenied("PAIRED_HOST_INVALID") from exc
    require(address.version==4 and address.is_private, "PAIRED_HOST_INVALID")
    return host


def firmware() -> bytes:
    require(IMAGE.is_file() and not IMAGE.is_symlink(), "FIRMWARE_NOT_TRACKED")
    data = IMAGE.read_bytes()
    require(len(data)==IMAGE_BYTES and hashlib.sha256(data).hexdigest()==IMAGE_SHA,
            "FIRMWARE_SHA256_MISMATCH")
    return data


def get_json(host: str, path: str) -> dict:
    conn = http.client.HTTPConnection(host,18080,timeout=10)
    try:
        conn.request("GET",path,headers={"Accept":"application/json"})
        res=conn.getresponse()
        data=res.read(65537)
        require(res.status==200 and len(data)<=65536, "GATEWAY_GET_DENIED")
        result=json.loads(data)
        require(type(result) is dict, "GATEWAY_GET_INVALID")
        return result
    finally:
        conn.close()


def submit_exactly_once(host: str, data: bytes) -> str:
    payload={
        "site_id":SITE,"operation":"flash_cycle","timeout_s":180.0,
        "target":ICPN,"provider":PROVIDER,"profile":PROFILE,
        "asset_name":IMAGE.name,"asset_type":"image","asset_format":"binary",
        "asset_size":len(data),"asset_sha256":IMAGE_SHA,
        "asset_base64":base64.b64encode(data).decode("ascii"),
    }
    raw=json.dumps(payload,sort_keys=True,separators=(",",":")).encode("utf-8")
    conn=http.client.HTTPConnection(host,18080,timeout=18)
    try:
        # Exactly one POST. Any transport/timeout ambiguity is NOT retryable.
        conn.request("POST","/api/jobs",body=raw,headers={
            "Content-Type":"application/json","Accept":"application/json"})
        response=conn.getresponse()
        body=response.read(65537)
        require(len(body)<=65536,"POST_RESPONSE_OVERSIZE_OUTCOME_UNKNOWN")
        try:
            parsed=json.loads(body)
        except (ValueError,UnicodeError) as exc:
            raise FlashDenied("POST_RESPONSE_INVALID_OUTCOME_UNKNOWN") from exc
        if response.status!=202:
            raise FlashDenied("GATEWAY_SUBMIT_HTTP_"+str(response.status))
        # The established REST Gateway start() envelope is {"job": {"job_id": ...}}.
        # A 202 POST may already be executing hardware, so fail without
        # resubmission if its exact Job ID cannot be recovered.
        job=parsed.get("job") if type(parsed) is dict else None
        require(type(job) is dict and type(job.get("job_id")) is str,
                "POST_JOB_ID_UNKNOWN_DO_NOT_RESUBMIT")
        job_id=job["job_id"]
        require(bool(JOB_RE.fullmatch(job_id)),"POST_JOB_ID_UNTRUSTED_DO_NOT_RESUBMIT")
        return job_id
    except (OSError,TimeoutError,http.client.HTTPException) as exc:
        raise FlashDenied("SUBMIT_OUTCOME_UNKNOWN_DO_NOT_RESUBMIT") from exc
    finally:
        conn.close()


def wait_job(host: str, job_id: str, *, interval_s=1.0, limit_s=240.0) -> dict:
    deadline=time.monotonic()+limit_s
    while True:
        snapshot=get_json(host,"/api/status?job="+quote(job_id,safe=""))
        job=snapshot.get("job")
        require(type(job) is dict and job.get("job_id")==job_id,
                "JOB_IDENTITY_MISMATCH_OUTCOME_UNKNOWN")
        state=job.get("state")
        if state in TERMINAL:
            return job
        require(state in ("queued","running"), "JOB_STATE_UNKNOWN_DO_NOT_RESUBMIT")
        if time.monotonic()>=deadline:
            raise FlashDenied("JOB_STILL_UNRESOLVED_DO_NOT_RESUBMIT")
        time.sleep(interval_s)


def verify_job(job: dict) -> dict:
    result=job.get("result")
    details=result.get("details",{}) if isinstance(result,dict) else {}
    flash=details.get("flash_cycle",{}) if isinstance(details,dict) else {}
    passed=(job.get("operation")=="flash_cycle"
            and job.get("site_id")==SITE
            and job.get("state")=="success"
            and isinstance(result,dict) and result.get("state")=="success"
            and result.get("site_id")==SITE
            and result.get("operation")=="flash_cycle"
            and result.get("image_sha256")==IMAGE_SHA
            and result.get("image_size")==IMAGE_BYTES
            and result.get("attempts")==1
            and isinstance(flash,dict) and flash.get("result")=="PASS"
            and flash.get("readback_sha256")==IMAGE_SHA
            and flash.get("bytes_verified")==IMAGE_BYTES
            and flash.get("safe_off") is True)
    error=result.get("error") if isinstance(result,dict) else None
    return {
        "flash_result":"PASS" if passed else "FAIL_OR_INCOMPLETE",
        "job_id":job.get("job_id"),"job_state":job.get("state"),
        "job_stage":job.get("stage"),"attempts":result.get("attempts") if isinstance(result,dict) else None,
        "image_sha256":IMAGE_SHA,"image_size":IMAGE_BYTES,
        "readback_sha256":flash.get("readback_sha256") if isinstance(flash,dict) else None,
        "bytes_verified":flash.get("bytes_verified") if isinstance(flash,dict) else None,
        "safe_off":flash.get("safe_off") if isinstance(flash,dict) else None,
        "opf_provider":flash.get("opf_provider_package") if isinstance(flash,dict) else None,
        "opf_profile":flash.get("opf_profile_package") if isinstance(flash,dict) else None,
        "error_code":error.get("error_code") if isinstance(error,dict) else None,
    }


def execute(source_sha: str, expected_active_sha: str) -> dict:
    current_source(source_sha)
    require(bool(HEX64.fullmatch(expected_active_sha)), "EXPECTED_ASSET_SHA_INVALID")
    host=paired_target()
    image=firmware()
    observation=preflight.run(host,source_sha,helper=pairing)
    require(observation.get("readiness")=="NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS"
            and observation.get("blockers")==[], "SITE2_PREFLIGHT_DENIED")
    active=joint.observe_active(host,helper=pairing)
    require(active.get("state")=="ACTIVE"
            and active.get("asset_set_sha256")==expected_active_sha
            and active.get("opf_static")=="PASS",
            "ACTIVE_OPF_SET_MISMATCH")

    # The owner-approved single Root admit/revoke diagnostic already PASSED
    # on the exact selected Engine: Path 2 Run #42354991188. Do not issue
    # another standalone admission: the real Job's C-3 Worker performs its own
    # mandatory Root Admission/ownership check under the Job lease.
    selected=observation.get("z2",{}).get("engine",{})
    require(selected.get("status")=="VERIFIED"
            and selected.get("driver")=="plasma_swd"
            and selected.get("abi")==5
            and selected.get("openocd_sha256_observed")
                =="b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
            and selected.get("admission_sha256_observed")
                =="3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b",
            "SITE2_ADMITTED_ENGINE_IDENTITY_CHANGED")
    # Recheck Site/Bundle immediately before the sole POST. No detached
    # second admission session can be left behind.
    renewed=preflight.run(host,source_sha,helper=pairing)
    require(renewed.get("readiness")=="NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS"
            and renewed.get("blockers")==[], "SITE2_CHANGED_AFTER_ADMISSION")
    stable=joint.observe_active(host,helper=pairing)
    require(stable.get("asset_set_sha256")==expected_active_sha
            and stable.get("opf_static")=="PASS" and stable.get("state")=="ACTIVE",
            "ACTIVE_SET_CHANGED_AFTER_ADMISSION")

    # The trusted PPU Runtime performs exact OPF Provider resolution and
    # Worker Identity before opening its one physical Site Job.
    job_id=submit_exactly_once(host,image)
    try:
        job=wait_job(host,job_id)
    except Exception as exc:
        # The POST was accepted: retain its ID even when later observations
        # are lost. Reconciliation is read-only; never submit a second Job.
        reason=str(exc) if isinstance(exc,FlashDenied) else type(exc).__name__
        return {"schema":SCHEMA,"source_sha":source_sha,
                "active_asset_set_sha256":expected_active_sha,
                "flash_result":"OUTCOME_UNKNOWN","job_id":job_id,
                "observation_error":reason,"submission_count":1,
                "root_admission":"GATE1_ADMIT_REVOKE_PASS_RUN_42354991188",
                "auto_retry":"DISABLED","fpga_reload":"NOT_RUN",
                "bundle_deploy":"NOT_RUN"}
    summary=verify_job(job)
    summary.update({"schema":SCHEMA,"source_sha":source_sha,
                    "active_asset_set_sha256":expected_active_sha,
                    "root_admission":"GATE1_ADMIT_REVOKE_PASS_RUN_42354991188",
                    "submission_count":1,"auto_retry":"DISABLED",
                    "fpga_reload":"NOT_RUN","bundle_deploy":"NOT_RUN"})
    # Observe final idle and no seal/admission; never recover automatically.
    try:
        post=preflight.run(host,source_sha,helper=pairing)
        summary["post_site2_seal"]=post.get("z2",{}).get("site2_seal",{}).get("present")
        summary["post_site2_admission_record"]=post.get("z2",{}).get("site2_admission",{}).get("present")
        summary["post_openocd_processes"]=len(post.get("z2",{}).get("openocd_pids",[]))
        summary["post_site2_idle"]=post.get("rest",{}).get("site2_idle")
        if (summary["post_site2_seal"] is not False
            or summary["post_site2_admission_record"] is not False
            or summary["post_openocd_processes"]!=0
            or summary["post_site2_idle"] is not True):
            summary["flash_result"]="FAIL_OR_INCOMPLETE"
    except Exception:
        summary["post_observation"]="UNKNOWN"
        summary["flash_result"]="FAIL_OR_INCOMPLETE"
    return summary


def main() -> int:
    import argparse
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--active-sha",required=True)
    args=parser.parse_args()
    result={"schema":SCHEMA,"flash_result":"NOT_RUN","submission_count":0,
            "fpga_reload":"NOT_RUN","bundle_deploy":"NOT_RUN"}
    try:
        result=execute(args.source_sha,args.active_sha)
        code=0 if result.get("flash_result")=="PASS" else 1
    except Exception as exc:
        code=69
        if isinstance(exc,FlashDenied):
            reason=str(exc)
        else:
            reason=type(exc).__name__
        maybe_submitted=any(word in reason for word in (
            "OUTCOME_UNKNOWN","DO_NOT_RESUBMIT","JOB_STILL_UNRESOLVED",
            "GATEWAY_GET_DENIED","JOB_IDENTITY_MISMATCH"))
        result.update({"flash_result":"NOT_RUN_OR_UNKNOWN","reason":reason,
                       "submission_count":"UNKNOWN" if maybe_submitted else 0,
                       "warning":"DO_NOT_RESUBMIT_WITHOUT_JOB_RECONCILIATION"})
    print("PLASMA_SITE2_SINGLE_FLASH="+json.dumps(result,sort_keys=True,
        separators=(",",":")))
    return code


if __name__=="__main__":
    raise SystemExit(main())

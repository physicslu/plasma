#!/usr/bin/env python3
"""Path 2 post-install S2 Worker live-code and Site2 admission read-only attestation.

Uses enrolled pinned Z2 SSH and existing Bootstrap status GET only.
Never changes services, hardware ownership, FPGA, Bundle or DUT.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

import plasma_site2_path2_preflight as preflight
import plasma_wordport_program as pairing
import ppu_path2_hardware_baseline as baseline

ROOT = Path(__file__).resolve().parents[1]
HOST = "192.168.2.99"
DEVICE = "ppu-device-7ed4b30913a9bf6101da5a7a"
RUNTIME = "37a7823d89973dd0f6656ed276a7a290eb033f98"
RELEASE = "0.2.1-37a7823d8997"
WORKER_SHA256 = "703d5756a9a0aa71a31cee26ee76a316f9dd70c59d97b0f8706bd0f7bfc75530"
BUNDLE_B = "387b9c8c08822a6d4edb8ac7904a71a6e3143b1714453a35778c372a7517764c"
ENGINE_BIN = "b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
ENGINE_ADM = "3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"
IMAGE = "z2-independent-swd-v5-d0add58c"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
MARKER = "PLASMA_S2_WORKER_LIVE="

REMOTE = r'''
import hashlib,json,os,pathlib,re,stat,subprocess
W=pathlib.Path("/opt/plasma/bootstrap/ppu_site_worker.py")
result={"schema":"plasma.s2.worker-live.v1","state":"UNVERIFIED"}
try:
    if os.geteuid()!=0: raise ValueError("ROOT_REQUIRED")
    st=W.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022 or not 0<st.st_size<=262144:
        raise ValueError("WORKER_SOURCE_UNTRUSTED")
    digest=hashlib.sha256(W.read_bytes()).hexdigest()
    unit=subprocess.run(
        ["/bin/systemctl","show","--no-pager",
         "--property=MainPID,ActiveState,SubState",
         "plasma-site-worker.service"],
        capture_output=True,text=True,timeout=8,check=True)
    fields=dict(line.split("=",1) for line in unit.stdout.splitlines() if "=" in line)
    pid=int(fields.get("MainPID","0"))
    if fields.get("ActiveState")!="active" or fields.get("SubState")!="running" or pid<2:
        raise ValueError("WORKER_SERVICE_NOT_RUNNING")
    proc=pathlib.Path("/proc")/str(pid)
    cmd=(proc/"cmdline").read_bytes().split(b"\x00")
    if (b"/opt/plasma/bootstrap/ppu_site_worker_service.py" not in cmd
        or b"-I" not in cmd or b"-B" not in cmd or b"-S" not in cmd):
        raise ValueError("WORKER_CMDLINE_UNEXPECTED")
    exe=str((proc/"exe").resolve(strict=True))
    if not exe.startswith("/opt/plasma/python/3.12.13/"):
        raise ValueError("WORKER_PYTHON_UNEXPECTED")
    raw=(proc/"stat").read_text()
    tail=raw[raw.rfind(") ")+2:].split()
    ticks=int(tail[19])
    hz=os.sysconf("SC_CLK_TCK")
    btime=next(int(x.split()[1]) for x in pathlib.Path("/proc/stat").read_text().splitlines() if x.startswith("btime "))
    process_start_epoch=btime+ticks/hz
    # ctime is the actual inode-content change time, independent of tar mtime.
    # Allow 1 s for /proc/stat btime truncation; never infer loaded code from on-disk SHA alone.
    after_install=(process_start_epoch+1.0>=st.st_ctime)
    result={"schema":"plasma.s2.worker-live.v1","state":"OBSERVED",
            "file_sha256":digest,"worker_pid":pid,
            "worker_executable_verified":True,"worker_cmdline_verified":True,
            "process_started_after_file_install":after_install,
            "process_start_epoch_seconds":round(process_start_epoch,3),
            "installed_file_ctime_seconds":round(st.st_ctime,3)}
except (OSError,ValueError,StopIteration,IndexError,KeyError,subprocess.SubprocessError):
    pass
print("PLASMA_S2_WORKER_LIVE="+json.dumps(result,sort_keys=True,separators=(",",":")))
'''


def validate(snapshot: dict, worker: dict, status: dict, assets: dict) -> dict:
    if snapshot.get("status")!="READ_ONLY_OBSERVED" or snapshot.get("readiness")!="NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS" or snapshot.get("blockers")!=[]:
        raise RuntimeError("SITE2_PREFLIGHT_BLOCKED")
    z=snapshot.get("z2",{})
    engine=z.get("engine",{})
    fpga=z.get("fpga",{})
    rest=snapshot.get("rest",{})
    services=z.get("services",{})
    if not (z.get("release",{}).get("current")==RELEASE
        and engine.get("status")=="VERIFIED" and engine.get("abi")==5
        and engine.get("driver")=="plasma_swd"
        and engine.get("openocd_sha256_observed")==ENGINE_BIN
        and engine.get("admission_sha256_observed")==ENGINE_ADM
        and fpga.get("status")=="IMAGE" and fpga.get("boot_match") is True
        and fpga.get("manager_state")=="operating" and fpga.get("image_id")==IMAGE
        and z.get("site2_seal",{}).get("present") is False
        and z.get("site2_admission",{}).get("present") is False
        and z.get("openocd_pids")==[]
        and rest.get("site2_idle") is True and rest.get("active_job_count")==0
        and rest.get("lease_busy") is False and rest.get("activation_active") is False):
        raise RuntimeError("SITE2_LIVE_IDENTITY_MISMATCH")
    wsvc=services.get("plasma-site-worker",{})
    if not (worker.get("schema")=="plasma.s2.worker-live.v1"
        and worker.get("state")=="OBSERVED"
        and worker.get("file_sha256")==WORKER_SHA256
        and type(worker.get("worker_pid")) is int and worker["worker_pid"]>=2
        and worker["worker_pid"]==wsvc.get("MainPID")
        and wsvc.get("ActiveState")=="active"
        and worker.get("worker_executable_verified") is True
        and worker.get("worker_cmdline_verified") is True
        and worker.get("process_started_after_file_install") is True):
        raise RuntimeError("WORKER_LIVE_SOURCE_NOT_ATTESTED")
    deployment=status.get("deployment",{})
    runtime=status.get("runtime",{})
    if not (status.get("identity",{}).get("device_id")==DEVICE
        and status.get("bootstrap",{}).get("state")=="bootstrap_ready"
        and runtime.get("state")=="runtime_active"
        and runtime.get("git_sha")==RUNTIME
        and isinstance(deployment,dict)
        and deployment.get("state") not in ("queued","running","recovery_required")
        and assets.get("state")=="ACTIVE"
        and assets.get("asset_set_sha256")==BUNDLE_B):
        raise RuntimeError("RUNTIME_OR_ACTIVE_BUNDLE_MISMATCH")
    return {"schema":"plasma.s2.postinstall-hil-preflight.v1","status":"PASS",
            "source_sha":RUNTIME,"installed_worker_sha256":WORKER_SHA256,
            "worker_pid":worker["worker_pid"],
            "worker_process_started_after_install":True,
            "fpga_image_id":IMAGE,"fpga_boot_id_sha12":fpga.get("boot_id_sha12"),
            "fpga_journal_sha256":fpga.get("journal_sha256"),
            "engine_openocd_sha256":ENGINE_BIN,"engine_admission_sha256":ENGINE_ADM,
            "active_bundle_sha256":BUNDLE_B,"site2_idle":True,"site2_sealed":False,
            "flash":"NOT_RUN","fpga_reload":"NOT_RUN","service_restart":"NOT_RUN"}


def run(source_sha: str) -> dict:
    head=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                        capture_output=True,text=True,check=True,timeout=8).stdout.strip()
    if not SHA40.fullmatch(source_sha) or source_sha!=head:
        raise RuntimeError("SOURCE_SHA_MISMATCH")
    creds,known_hosts=pairing.z2_login_credentials(Path.home())
    if creds.get("ssh_host")!=HOST:
        raise RuntimeError("ENROLLED_HOST_MISMATCH")
    snapshot=preflight.run(HOST,source_sha,helper=pairing)
    token=baseline._existing_bootstrap_token_via_z2_ssh(HOST,helper=pairing)
    client=baseline.DirectSSHAuthenticatedBootstrap(HOST,module=baseline._load_client(),token=token)
    status=client.status()
    assets=client._call("GET","/v1/assets",None).get("assets",{})
    rc,transcript=pairing.password_ssh_z2(["python3","-I","-c",REMOTE],creds,known_hosts,timeout=60)
    if rc!=0:raise RuntimeError("WORKER_OBSERVATION_DENIED")
    matches=re.findall(r"(?m)^PLASMA_S2_WORKER_LIVE=(\{[^\r\n]{1,4096}\})\s*$",transcript)
    if len(matches)!=1:raise RuntimeError("WORKER_RECEIPT_INVALID")
    worker=json.loads(matches[0])
    result=validate(snapshot,worker,status,assets)
    after=preflight.run(HOST,source_sha,helper=pairing)
    if (after.get("readiness")!="NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS"
        or after.get("blockers")!=[]
        or after.get("z2",{}).get("services",{}).get("plasma-site-worker",{}).get("MainPID")!=worker["worker_pid"]
        or after.get("z2",{}).get("fpga",{}).get("journal_sha256")!=snapshot["z2"]["fpga"].get("journal_sha256")
        or after.get("z2",{}).get("release",{}).get("current")!=RELEASE):
        raise RuntimeError("POST_ATTESTATION_STATE_CHANGED")
    return result


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args(argv)
    try:
        receipt=run(a.source_sha)
        rc=0
    except Exception as exc:
        permitted={"SOURCE_SHA_MISMATCH","ENROLLED_HOST_MISMATCH",
                   "SITE2_PREFLIGHT_BLOCKED","SITE2_LIVE_IDENTITY_MISMATCH",
                   "WORKER_LIVE_SOURCE_NOT_ATTESTED",
                   "RUNTIME_OR_ACTIVE_BUNDLE_MISMATCH",
                   "WORKER_OBSERVATION_DENIED","WORKER_RECEIPT_INVALID",
                   "POST_ATTESTATION_STATE_CHANGED"}
        reason=str(exc) if isinstance(exc,RuntimeError) and str(exc) in permitted else type(exc).__name__
        receipt={"schema":"plasma.s2.postinstall-hil-preflight.v1",
                 "status":"BLOCKED","reason":reason,
                 "flash":"NOT_RUN","service_restart":"NOT_RUN"}
        rc=69
    print("PLASMA_S2_POSTINSTALL="+json.dumps(receipt,sort_keys=True,separators=(",",":")))
    return rc
if __name__=="__main__":raise SystemExit(main())

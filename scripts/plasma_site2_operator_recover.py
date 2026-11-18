#!/usr/bin/env python3
"""Source-pinned one-shot Site 2 Operator Recovery via enrolled Path 2 SSH.

Owner-authorized recovery operation. This is NOT a seal-file delete, arbitrary
remote shell, FPGA download, driver replacement, or automatic flash retry.

Preflight the PPU's real Job lease and image/engine provenance first. Stop only
plasma-site-worker; invoke the ALREADY installed Root Operator Recovery which
rechecks ownership and verifies PS-local OpenOCD/ABI-v5 SAFE_OFF. Always restore
the worker service, even if recovery is denied. Never claim PASS without a
verifiable recovery receipt, absence of the seal and restored service.
"""
from __future__ import annotations
import argparse
import importlib.util
import ipaddress
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SHA40=re.compile(r"[0-9a-f]{40}\Z")
MARKER="PLASMA_SITE2_OPERATOR_RECOVERY="
REMOTE=r'''
import json,os,pathlib,stat,subprocess,sys,time
P=pathlib.Path
UNIT="plasma-site-worker.service"
RECOVERY=P("/opt/plasma/bootstrap/ppu_site_recovery.py")
# The protected G5 Admission requires the native ARMv7 CPython 3.12.13.
# Recovery invokes the Adapter's child admission with sys.executable.
NATIVE=P("/opt/plasma/python/3.12.13/bin/python3")
SEAL=P("/var/lib/plasma-site-worker/seals/site2.sealed")
def command(args,timeout=20):
    try:
        return subprocess.run(args,capture_output=True,text=True,
            stdin=subprocess.DEVNULL,timeout=timeout,
            env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin"})
    except (OSError,subprocess.SubprocessError):
        return None
def service_active():
    r=command(["/bin/systemctl","is-active",UNIT],6)
    return (r is not None and r.stdout.strip()=="active")
out={"schema":"plasma.site2.operator-recovery.v1","status":"NOT_RUN",
     "service_was_active":False,"service_restored":False,
     "recovery_result":"NOT_RUN","seal_present_before":False,
     "seal_present_after":False,"safe_off":"NOT_RUN",
     "evidence_path":"NOT_AVAILABLE","error":"NOT_RUN"}
try:
    if os.geteuid()!=0:raise RuntimeError("ROOT_REQUIRED")
    if not NATIVE.is_file():raise RuntimeError("NATIVE_ARMV7_PYTHON_MISSING")
    if not RECOVERY.is_file() or RECOVERY.is_symlink():raise RuntimeError("INSTALLED_RECOVERY_MISSING")
    st=RECOVERY.stat()
    if st.st_uid!=0 or st.st_mode&0o022:raise RuntimeError("RECOVERY_SCRIPT_NOT_TRUSTED")
    if not SEAL.is_file() or SEAL.is_symlink():raise RuntimeError("SITE2_SEAL_NOT_PRESENT_OR_UNTRUSTED")
    marker=json.loads(SEAL.read_text())
    if type(marker)!=dict or marker.get("site")!=2:
        raise RuntimeError("SITE2_SEAL_MALFORMED")
    out["seal_present_before"]=True
    if not service_active():raise RuntimeError("WORKER_NOT_ACTIVE")
    out["service_was_active"]=True
    # Recovery is the ONLY allowed operation that may move the persistent seal.
    # Do not remove it here. The installed operator code requires a stopped
    # Worker, no PPU job lease, no OpenOCD Owner and verified SAFE_OFF.
    stopped=command(["/bin/systemctl","stop",UNIT],20)
    if stopped is None or stopped.returncode!=0 or service_active():
        raise RuntimeError("WORKER_STOP_FAILED")
    result=command([str(NATIVE),str(RECOVERY),
                    "recover","2","--operator","plasma-site2-owner"],130)
    if result is None:raise RuntimeError("RECOVERY_TIMEOUT_OR_EXEC_ERROR")
    try:
        receipt=json.loads(result.stdout)
    except (ValueError,TypeError):
        raise RuntimeError("RECOVERY_RECEIPT_INVALID")
    if type(receipt)!=dict:
        raise RuntimeError("RECOVERY_RECEIPT_INVALID")
    out["recovery_result"]=receipt.get("result","DENIED")
    out["evidence_path"]=receipt.get("evidence","NOT_AVAILABLE")
    out["safe_off"]="VERIFIED" if (receipt.get("result")=="RECOVERED"
               and type(receipt.get("safe_off")) is dict
               and receipt["safe_off"].get("result")=="SAFE_OFF_VERIFIED"
               and receipt["safe_off"].get("openocd_rc")==0) else "NOT_PROVEN"
    out["status"]="RECOVERY_ACCEPTED" if (
        result.returncode==0 and out["recovery_result"]=="RECOVERED"
        and out["safe_off"]=="VERIFIED" and not SEAL.exists()) else "BLOCKED"
    out["error"]="NONE" if out["status"]=="RECOVERY_ACCEPTED" else "RECOVERY_PRECONDITION_OR_SAFE_OFF_DENIED"
except Exception as exc:
    out["status"]="BLOCKED"
    code=str(exc)
    allowed={"ROOT_REQUIRED","NATIVE_ARMV7_PYTHON_MISSING","INSTALLED_RECOVERY_MISSING","RECOVERY_SCRIPT_NOT_TRUSTED",
             "SITE2_SEAL_NOT_PRESENT_OR_UNTRUSTED","SITE2_SEAL_MALFORMED",
             "WORKER_NOT_ACTIVE","WORKER_STOP_FAILED","RECOVERY_TIMEOUT_OR_EXEC_ERROR",
             "RECOVERY_RECEIPT_INVALID"}
    out["error"]=code if code in allowed else type(exc).__name__
finally:
    # Restart is permitted only for the already-running worker service.
    # Never restart Runtime, Bootstrap, FPGA Manager or OpenOCD.
    if out["service_was_active"]:
        r=command(["/bin/systemctl","start",UNIT],25)
        out["service_restored"]=bool(r and r.returncode==0 and service_active())
    out["seal_present_after"]=SEAL.exists()
    if out["status"]=="RECOVERY_ACCEPTED" and (
        not out["service_restored"] or out["seal_present_after"]):
        out["status"]="BLOCKED"
        out["error"]="POST_RECOVERY_SERVICE_OR_SEAL_NOT_VERIFIED"
    print("PLASMA_SITE2_OPERATOR_RECOVERY="+json.dumps(
        out,sort_keys=True,separators=(",",":")))
'''
def load(path,name):
    s=importlib.util.spec_from_file_location(name,ROOT/path)
    if s is None or s.loader is None:raise RuntimeError("REVIEWED_SOURCE_MISSING")
    m=importlib.util.module_from_spec(s)
    sys.modules[s.name]=m
    s.loader.exec_module(m)
    return m

def run(host,sha,*,preflight=None,helper=None):
    current=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                           capture_output=True,text=True,timeout=6,check=True).stdout.strip()
    if not SHA40.fullmatch(sha) or current!=sha:
        raise RuntimeError("SOURCE_SHA_MISMATCH")
    addr=ipaddress.ip_address(host)
    if addr.version!=4 or not addr.is_private:raise RuntimeError("HOST_SCOPE_DENIED")
    if preflight is None:preflight=load("scripts/plasma_site2_path2_preflight.py","plasma_recovery_preflight")
    evidence=preflight.run(host,sha)
    z=evidence["z2"]
    rest=evidence["rest"]
    # EXACT real hardware and PPU idle observations are required.
    if not (rest.get("status")=="OBSERVED" and rest.get("health_ready") is True
        and rest.get("node_matches_status") is True
        and rest.get("lease_busy") is False and rest.get("active_job_count")==0
        and rest.get("activation_active") is False and rest.get("site2_idle") is True
        and rest.get("site2_enabled") is True and rest.get("site2_interface")=="openocd"
        and rest.get("site2_target_matches") is True
        and z["engine"].get("status")=="VERIFIED" and z["engine"].get("abi")==5
        and z["engine"].get("driver")=="plasma_swd"
        and z["fpga"].get("status")=="IMAGE" and z["fpga"].get("boot_match") is True
        and z["site2_seal"].get("present") is True
        and not z["site2_admission"].get("present")
        and not z["openocd_pids"]
        and z["services"].get("plasma-site-worker",{}).get("ActiveState")=="active"
        and z["services"].get("plasma-server",{}).get("ActiveState")=="active"):
        raise RuntimeError("LIVE_RECOVERY_ADMISSION_DENIED")
    if helper is None:helper=load("scripts/plasma_wordport_program.py","plasma_recovery_pinned_ssh")
    credentials,hosts=helper.z2_login_credentials(Path.home())
    if credentials.get("ssh_host")!=host:raise RuntimeError("ENROLLED_HOST_MISMATCH")
    code,log=helper.password_ssh_z2(["python3","-I","-c",REMOTE],
                                     credentials,hosts,timeout=220)
    if code!=0:raise RuntimeError("SSH_RECOVERY_CALL_FAILED")
    hits=re.findall(r"(?m)^PLASMA_SITE2_OPERATOR_RECOVERY=(\{[^\r\n]{1,4096}\})\s*$",log)
    if len(hits)!=1:raise RuntimeError("RECOVERY_RECEIPT_INVALID")
    receipt=json.loads(hits[0])
    required={"schema","status","service_was_active","service_restored",
              "recovery_result","seal_present_before","seal_present_after",
              "safe_off","evidence_path","error"}
    if (type(receipt)!=dict or set(receipt)!=required
        or receipt["schema"]!="plasma.site2.operator-recovery.v1"):
        raise RuntimeError("RECOVERY_RECEIPT_INVALID")
    # Root recovery evidence is NOT a proof of full DUT Flash.
    return {"schema":"plasma.site2.path2-operator-recovery.v1",
            "source_sha":sha,
            "status":receipt["status"],
            "recovery":receipt,
            "flash":"NOT_RUN","fpga_reload":"NOT_RUN",
            "runtime_deploy":"NOT_RUN","hardware_safe_off":receipt["safe_off"]}

def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args(argv)
    try:
        receipt=run(a.host,a.source_sha)
        rc=0 if receipt["status"]=="RECOVERY_ACCEPTED" else 1
    except Exception as exc:
        codes={"SOURCE_SHA_MISMATCH","HOST_SCOPE_DENIED","REVIEWED_SOURCE_MISSING",
               "LIVE_RECOVERY_ADMISSION_DENIED","ENROLLED_HOST_MISMATCH",
               "SSH_RECOVERY_CALL_FAILED","RECOVERY_RECEIPT_INVALID"}
        reason=str(exc) if isinstance(exc,RuntimeError) and str(exc) in codes else type(exc).__name__
        receipt={"schema":"plasma.site2.path2-operator-recovery.v1",
                 "status":"BLOCKED","reason":reason,"flash":"NOT_RUN"}
        rc=69
    print("PLASMA_SITE2_RECOVERY_GATE1="+json.dumps(receipt,sort_keys=True,separators=(",",":")))
    return rc
if __name__=="__main__":raise SystemExit(main())

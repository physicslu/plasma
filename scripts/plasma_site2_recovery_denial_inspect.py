#!/usr/bin/env python3
"""Read-only forensic inspection of the *single* approved Site 2 Recovery denial.

Never re-runs recovery, does not touch a Site Worker, OpenOCD or FPGA.
Only reads root-private evidence and returns a schema-limited reason matrix.
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
SHA40=re.compile("[0-9a-f]{40}\\Z")
MARK="PLASMA_SITE2_RECOVERY_DENIAL="
REMOTE=r'''
import json,os,pathlib,stat
p=pathlib.Path("/var/lib/plasma-site-worker/recovery/20261104T162024Z-site2-denied.json")
out={"schema":"plasma.site2.recovery-denial-inspect.v1","status":"UNREADABLE"}
try:
    st=p.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_size>65536:
        raise ValueError("EVIDENCE_UNTRUSTED")
    r=json.loads(p.read_text())
    if type(r)!=dict or r.get("schema")!="plasma.ppu.site-seal-recovery.v1":
        raise ValueError("EVIDENCE_SCHEMA_INVALID")
    def shaped(value):
        if type(value)!=dict:return {"status":"NOT_PRESENT"}
        selected=("seal_present","site_supported","worker_stopped",
                  "no_active_job","no_external_owner","preconditions",
                  "runtime_lease","owner_error")
        return {k:value[k] for k in selected if k in value and
                type(value[k]) in (str,int,bool) and
                len(str(value[k]))<=128}
    out={"schema":"plasma.site2.recovery-denial-inspect.v1",
         "status":"OBSERVED","result":r.get("result","UNVERIFIED"),
         "pre_checks":shaped(r.get("checks")),
         "post_checks":shaped(r.get("post_checks")),
         "safe_off_status":r.get("safe_off","NOT_ATTEMPTED") if type(r.get("safe_off")) is str else "STRUCTURED",
         "error_code":r.get("error","NOT_RECORDED") if type(r.get("error")) is str and len(r.get("error"))<=128 else "STRUCTURED_OR_MISSING",
         "evidence_schema":r["schema"],
         "seal_still_present":pathlib.Path("/var/lib/plasma-site-worker/seals/site2.sealed").exists(),
         "fpga_manager_exists":pathlib.Path("/sys/class/fpga_manager/fpga0/state").exists()}
except (OSError,ValueError,TypeError):
    out["status"]="EVIDENCE_UNREADABLE"
print("PLASMA_SITE2_RECOVERY_DENIAL="+json.dumps(out,sort_keys=True,separators=(",",":")))
'''
def load_helper():
    spec=importlib.util.spec_from_file_location(
        "plasma_site2_inspect_ssh",ROOT/"scripts/plasma_wordport_program.py")
    if spec is None or spec.loader is None:raise RuntimeError("REVIEWED_HELPER_MISSING")
    obj=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=obj
    spec.loader.exec_module(obj)
    return obj
def run(host,sha,*,helper=None):
    cur=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                       capture_output=True,text=True,check=True,timeout=6).stdout.strip()
    if not SHA40.fullmatch(sha) or sha!=cur:raise RuntimeError("SOURCE_SHA_MISMATCH")
    addr=ipaddress.ip_address(host)
    if addr.version!=4 or not addr.is_private:raise RuntimeError("HOST_SCOPE_DENIED")
    if helper is None:helper=load_helper()
    credentials,hosts=helper.z2_login_credentials(Path.home())
    if credentials.get("ssh_host")!=host:raise RuntimeError("ENROLLED_HOST_MISMATCH")
    rc,txt=helper.password_ssh_z2(["python3","-I","-c",REMOTE],
                                    credentials,hosts,timeout=55)
    if rc!=0:raise RuntimeError("SSH_FAILED")
    match=re.findall(r"(?m)^PLASMA_SITE2_RECOVERY_DENIAL=(\{[^\r\n]{1,4096}\})\s*$",txt)
    if len(match)!=1:raise RuntimeError("DENIAL_RECEIPT_INVALID")
    out=json.loads(match[0])
    if type(out)!=dict or out.get("schema")!="plasma.site2.recovery-denial-inspect.v1":
        raise RuntimeError("DENIAL_RECEIPT_INVALID")
    return out
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args(argv)
    try:out=run(a.host,a.source_sha);rc=0 if out.get("status")=="OBSERVED" else 1
    except Exception as exc:
        allowed={"SOURCE_SHA_MISMATCH","HOST_SCOPE_DENIED","ENROLLED_HOST_MISMATCH",
                 "SSH_FAILED","DENIAL_RECEIPT_INVALID","REVIEWED_HELPER_MISSING"}
        reason=str(exc) if isinstance(exc,RuntimeError) and str(exc) in allowed else type(exc).__name__
        out={"schema":"plasma.site2.recovery-denial-inspect.v1",
             "status":"BLOCKED","reason":reason};rc=69
    print("PLASMA_SITE2_RECOVERY_DENIAL="+json.dumps(out,sort_keys=True,separators=(",",":")))
    return rc
if __name__=="__main__":raise SystemExit(main())

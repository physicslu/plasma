#!/usr/bin/env python3
"""One-shot bounded Site 2 ABI-v5 Root admission diagnosis via Path 2.

Uses the Z2's EXISTING selected Engine and protected Site Admission entry.
On successful admission, immediately invoke its existing revoke entry; never
leave an admission record, never load FPGA, run OpenOCD, or Flash the DUT.
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
MARK="PLASMA_SITE2_ADMISSION_DIAGNOSTIC="
REMOTE=r'''
import json,os,pathlib,re,stat,subprocess,sys
from pathlib import Path
MARK="PLASMA_SWD_SITE_ADMISSION="
out={"schema":"plasma.site2.admission-diagnostic.v1","result":"NOT_RUN",
     "code":"NOT_RUN","revoke":"NOT_RUN","record_present":False,
     "fpga_manager_state":"NOT_VERIFIED"}
try:
    if os.geteuid()!=0:raise RuntimeError("ROOT_REQUIRED")
    manager=Path("/sys/class/fpga_manager/fpga0/state")
    try:
        observed=manager.read_text().strip()
        out["fpga_manager_state"]=observed if observed in ("operating","unknown","write","write init","write complete") else "UNEXPECTED"
    except OSError:
        out["fpga_manager_state"]="UNAVAILABLE"
    # Exact factory-installed Engine contract. No alternative binary/image.
    sys.path.insert(0,"/opt/plasma/bootstrap")
    import ppu_site_engine
    e=ppu_site_engine.load_engine()
    adm=e.openocd_root/"libexec/plasma_swd_site_admission.py"
    record=Path("/run/plasma-z2-swd05/swd-site2-admission")
    if record.exists():raise RuntimeError("EXISTING_ADMISSION_OWNER")
    argv=[sys.executable,"-I","-B",str(adm)]
    def call(action):
        return subprocess.run(argv+[action,"2"],capture_output=True,text=True,
                              timeout=100,stdin=subprocess.DEVNULL)
    try:
        attempt=call("admit")
        found=[x[len(MARK):] for x in attempt.stdout.splitlines()
               if x.startswith(MARK)]
        if len(found)!=1:
            out["result"]="INCOMPLETE"
            out["code"]="ADMISSION_RECEIPT_INVALID"
        else:
            payload=json.loads(found[0])
            code=str(payload.get("code","NOT_RECORDED"))[:160]
            out["code"]=code if re.fullmatch(r"[A-Za-z0-9_.:/+-]{1,160}",code) else "DENIAL_CODE_UNRECOGNIZED"
            out["result"]="ADMITTED" if attempt.returncode==0 and payload.get("result")=="SITE_ADMISSION_RECORD_ISSUED" else "DENIED"
    except (OSError,ValueError,subprocess.SubprocessError):
        out["result"]="INCOMPLETE";out["code"]="ADMISSION_EXECUTION_FAILED"
    finally:
        # Trusted revoke is the only supported way to remove an admission record.
        # If no record exists after a denied admission, no mutation is needed.
        if record.exists():
            try:
                revoke=call("revoke")
                out["revoke"]="PASS" if revoke.returncode==0 and not record.exists() else "FAIL"
            except (OSError,subprocess.SubprocessError):
                out["revoke"]="FAIL"
        else:
            out["revoke"]="NOT_NEEDED"
    out["record_present"]=record.exists()
    if out["record_present"] or out["revoke"]=="FAIL":
        out["result"]="UNKNOWN_OWNER_PRESERVED"
except Exception as e:
    out["result"]="BLOCKED"
    value=str(e)
    out["code"]=value if value in ("ROOT_REQUIRED","EXISTING_ADMISSION_OWNER") else type(e).__name__
print("PLASMA_SITE2_ADMISSION_DIAGNOSTIC="+json.dumps(out,sort_keys=True,separators=(",",":")))
'''
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    if spec is None or spec.loader is None:raise RuntimeError("REVIEWED_HELPER_UNAVAILABLE")
    m=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=m
    spec.loader.exec_module(m)
    return m
def run(host,sha,*,preflight=None,helper=None):
    cur=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                       capture_output=True,text=True,check=True,timeout=6).stdout.strip()
    if not SHA40.fullmatch(sha) or cur!=sha:raise RuntimeError("SOURCE_SHA_MISMATCH")
    address=ipaddress.ip_address(host)
    if address.version!=4 or not address.is_private:raise RuntimeError("HOST_SCOPE_DENIED")
    if preflight is None:preflight=load("scripts/plasma_site2_path2_preflight.py","plasma_admit_preflight")
    state=preflight.run(host,sha)
    z=state["z2"];rest=state["rest"]
    if not (state.get("readiness")=="NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS"
       and z["engine"].get("status")=="VERIFIED"
       and z["engine"].get("abi")==5 and z["engine"].get("driver")=="plasma_swd"
       and z["fpga"].get("status")=="IMAGE" and z["fpga"].get("boot_match") is True
       and z["fpga"].get("manager_state")=="operating"
       and z["site2_seal"].get("present") is False
       and z["site2_admission"].get("present") is False
       and not z["openocd_pids"]
       and rest.get("status")=="OBSERVED" and rest.get("health_ready") is True
       and rest.get("node_matches_status") is True
       and rest.get("lease_busy") is False and rest.get("active_job_count")==0
       and rest.get("site2_idle") is True):
        raise RuntimeError("DIAGNOSTIC_SAFETY_PRECONDITION_FAILED")
    if helper is None:helper=load("scripts/plasma_wordport_program.py","plasma_admit_ssh")
    creds,known=helper.z2_login_credentials(Path.home())
    if creds.get("ssh_host")!=host:raise RuntimeError("ENROLLED_HOST_MISMATCH")
    rc,out=helper.password_ssh_z2(["python3","-I","-c",REMOTE],
                                    creds,known,timeout=200)
    if rc!=0:raise RuntimeError("PINNED_SSH_FAILED")
    hits=re.findall(r"(?m)^PLASMA_SITE2_ADMISSION_DIAGNOSTIC=(\{[^\r\n]{1,4096}\})\s*$",out)
    if len(hits)!=1:raise RuntimeError("REMOTE_DIAGNOSTIC_RECEIPT_INVALID")
    data=json.loads(hits[0])
    fields={"schema","result","code","revoke","record_present","fpga_manager_state"}
    if type(data)!=dict or set(data)!=fields or data["schema"]!="plasma.site2.admission-diagnostic.v1":
        raise RuntimeError("REMOTE_DIAGNOSTIC_RECEIPT_INVALID")
    return {"schema":"plasma.site2.path2-admission-diagnostic.v1",
            "source_sha":sha,"observation":data,
            "physical_swd":"NOT_RUN","flash":"NOT_RUN",
            "fpga_reload":"NOT_RUN","recovery":"NOT_RUN"}
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    args=p.parse_args(argv)
    try:
        value=run(args.host,args.source_sha)
        rc=0 if value["observation"]["result"] in ("DENIED","ADMITTED") and not value["observation"]["record_present"] else 1
    except Exception as exc:
        allowed={"SOURCE_SHA_MISMATCH","HOST_SCOPE_DENIED","DIAGNOSTIC_SAFETY_PRECONDITION_FAILED",
                 "ENROLLED_HOST_MISMATCH","PINNED_SSH_FAILED","REMOTE_DIAGNOSTIC_RECEIPT_INVALID"}
        code=str(exc) if isinstance(exc,RuntimeError) and str(exc) in allowed else type(exc).__name__
        value={"schema":"plasma.site2.path2-admission-diagnostic.v1",
               "status":"BLOCKED","code":code,
               "physical_swd":"NOT_RUN","flash":"NOT_RUN","recovery":"NOT_RUN"}
        rc=69
    print("PLASMA_SITE2_ADMISSION_GATE1="+json.dumps(value,sort_keys=True,separators=(",",":")))
    return rc
if __name__=="__main__":raise SystemExit(main())

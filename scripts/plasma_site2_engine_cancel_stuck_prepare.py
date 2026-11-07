#!/usr/bin/env python3
"""Cancel exactly one authenticated orphan Site 2 Admission-only installer PID.

This does NOT repeat the interrupted install, change Engine selection, clean
temporary files, restart services, admit a Site, load FPGA or operate DUT.
Send one SIGTERM only if every independent identity/state check matches.
"""
from __future__ import annotations
import argparse
import ipaddress
import json
import re
import subprocess
from pathlib import Path
import plasma_site2_path2_preflight as preflight
import plasma_wordport_program as ssh

ROOT=Path(__file__).resolve().parents[1]
SHA40=re.compile(r"[0-9a-f]{40}\Z")
MARK="PLASMA_SITE2_CANCEL_STUCK_PREPARE="
REMOTE=r'''
import hashlib,json,os,re,signal,stat,sys,time
from pathlib import Path
PID=680
START=1794037223.17
BASE=Path("/opt/plasma/programming-engines/openocd")
OLD="0.12.0-5088db4c9154-plasma-swd-b8a7db670649"
NEW=OLD+"-3f5d5feca058"
EXPECTED_STAGE_MANIFEST="bab56f084b6d5af0fcedfdef7216bbe75ae1fb447d7d3794f347a3feefbc8982"
EXPECTED_BIN="b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
EXPECTED_OLD_ADM="1838d082222429083e3aca91290677d3873f5c681cac004a703b75f40d86c345"
out={"schema":"plasma.site2.cancel-stuck-prepare.v1","status":"BLOCKED",
     "target_pid":PID,"signal":"NOT_SENT","flash":"NOT_RUN",
     "fpga_reload":"NOT_RUN","bundle_deploy":"NOT_RUN",
     "engine_select":"NOT_RUN","stage_cleanup":"NOT_RUN"}
def need(ok,code):
    if not ok:raise ValueError(code)
def start_epoch(pid):
    raw=(Path("/proc")/str(pid)/"stat").read_text()
    ticks=int(raw.rsplit(")",1)[1].split()[19])
    boot=next(int(x.split()[1]) for x in Path("/proc/stat").read_text().splitlines()
              if x.startswith("btime "))
    return boot+ticks/os.sysconf("SC_CLK_TCK")
def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()
try:
    need(os.geteuid()==0,"ROOT_REQUIRED")
    need(Path("/sys/class/fpga_manager/fpga0/state").read_text().strip()=="operating",
         "FPGA_MANAGER_CHANGED")
    need(not Path("/var/lib/plasma-site-worker/seals/site2.sealed").exists() and
         not Path("/run/plasma-z2-swd05/swd-site2-admission").exists(),
         "SITE2_OWNER_PRESENT")
    sel=json.loads(Path("/etc/plasma/site-worker-engine.json").read_bytes())
    need(sel.get("openocd_root")==str(BASE/OLD) and
         sel.get("openocd_sha256")==EXPECTED_BIN and
         sel.get("admission_sha256")==EXPECTED_OLD_ADM,
         "SELECTION_DRIFT")
    need(not (BASE/NEW).exists(),"NEW_ENGINE_ALREADY_PUBLISHED")
    stage=BASE/("."+NEW+".tmp-"+str(PID))
    st=stage.lstat()
    need(stat.S_ISDIR(st.st_mode) and st.st_uid==0 and st.st_mode&0o022==0,
         "STAGING_IDENTITY_CHANGED")
    need(sha(stage/"plasma-engine.json")==EXPECTED_STAGE_MANIFEST,
         "STAGING_MANIFEST_CHANGED")
    proc=Path("/proc")/str(PID)
    need(proc.is_dir() and proc.stat().st_uid==0,"PID_NOT_PRESENT_OR_ROOT")
    need(abs(start_epoch(PID)-START)<0.01,"PID_START_IDENTITY_CHANGED")
    need(str((proc/"exe").resolve()).startswith("/opt/plasma/python/3.12.13/"),
         "PID_EXECUTABLE_CHANGED")
    cmd=(proc/"cmdline").read_bytes()[:131072]
    need(b"PLASMA_SITE2_ENGINE_MAINT=" in cmd and b"prepare\x00" in cmd,
         "PID_COMMAND_IDENTITY_CHANGED")
    need((proc/"comm").read_text().strip()=="python3","PID_COMM_CHANGED")
    # One precise signal, no process group or broad kill.
    os.kill(PID,signal.SIGTERM)
    out["signal"]="SIGTERM_SENT"
    time.sleep(0.3)
    try:
        still=proc.is_dir() and abs(start_epoch(PID)-START)<0.01
    except (FileNotFoundError,ProcessLookupError,OSError,ValueError):
        still=False
    out["status"]="SIGTERM_SENT_PROCESS_STILL_PRESENT" if still else "SIGTERM_SENT_PROCESS_EXITED"
except Exception as exc:
    out["code"]=str(exc) if isinstance(exc,ValueError) and re.fullmatch(
        "[A-Z0-9_]{3,100}",str(exc)) else type(exc).__name__
print("PLASMA_SITE2_CANCEL_STUCK_PREPARE="+json.dumps(out,sort_keys=True,separators=(",",":")))
sys.exit(0 if out["signal"]=="SIGTERM_SENT" else 1)
'''
def run(host,source_sha,*,baseline=None,helper=None):
    cur=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,check=True,
                       capture_output=True,text=True,timeout=6).stdout.strip()
    if not SHA40.fullmatch(source_sha) or cur!=source_sha:
        raise RuntimeError("SOURCE_SHA_MISMATCH")
    addr=ipaddress.ip_address(host)
    if addr.version!=4 or not addr.is_private:
        raise RuntimeError("HOST_SCOPE_DENIED")
    if baseline is None:baseline=preflight
    check=baseline.run(host,source_sha)
    if (check.get("readiness")!="NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS"
        or check.get("blockers")
        or check.get("z2",{}).get("engine",{}).get("openocd_sha256_observed")
           !="b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
        or check.get("z2",{}).get("site2_admission",{}).get("present")
        or check.get("z2",{}).get("site2_seal",{}).get("present")):
        raise RuntimeError("CANCEL_PREFLIGHT_BLOCKED")
    if helper is None:helper=ssh
    creds,known=helper.z2_login_credentials(Path.home())
    if creds.get("ssh_host")!=host:raise RuntimeError("ENROLLED_HOST_MISMATCH")
    code,stdout=helper.password_ssh_z2(
        ["/opt/plasma/python/3.12.13/bin/python3","-I","-B","-c",REMOTE],
        creds,known,timeout=80)
    hits=re.findall(r"(?m)^PLASMA_SITE2_CANCEL_STUCK_PREPARE=(\{[^\r\n]{1,4096}\})\s*$",stdout)
    if len(hits)!=1:raise RuntimeError("CANCEL_RECEIPT_UNKNOWN")
    data=json.loads(hits[0])
    if (code!=0 or type(data)!=dict or
        data.get("schema")!="plasma.site2.cancel-stuck-prepare.v1" or
        data.get("signal")!="SIGTERM_SENT" or
        data.get("engine_select")!="NOT_RUN" or
        data.get("stage_cleanup")!="NOT_RUN" or
        data.get("fpga_reload")!="NOT_RUN" or data.get("flash")!="NOT_RUN"):
        raise RuntimeError("CANCEL_RESULT_UNVERIFIED")
    return {"schema":"plasma.site2.path2-cancel-stuck-prepare.v1",
            "source_sha":source_sha,"observation":data}
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args(argv)
    try:out=run(a.host,a.source_sha);code=0
    except Exception as exc:
        allowed={"SOURCE_SHA_MISMATCH","HOST_SCOPE_DENIED","CANCEL_PREFLIGHT_BLOCKED",
                 "ENROLLED_HOST_MISMATCH","CANCEL_RECEIPT_UNKNOWN",
                 "CANCEL_RESULT_UNVERIFIED"}
        reason=str(exc) if isinstance(exc,RuntimeError) and str(exc) in allowed else type(exc).__name__
        out={"schema":"plasma.site2.path2-cancel-stuck-prepare.v1",
             "status":"BLOCKED_OR_UNKNOWN","reason":reason,
             "flash":"NOT_RUN","fpga_reload":"NOT_RUN","bundle_deploy":"NOT_RUN"}
        code=69
    print(MARK+json.dumps(out,sort_keys=True,separators=(",",":")))
    return code
if __name__=="__main__":raise SystemExit(main())

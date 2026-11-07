#!/usr/bin/env python3
"""Read-only Z2 selected/derived OpenOCD Engine inventory after ambiguous Prepare.

Never installs, selects, restarts, admits Site, touches FPGA MMIO or DUT.
Only resolves exact prior and new Admission SHA-pinned Engine identity.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
from pathlib import Path

import plasma_wordport_program as paired

ROOT=Path(__file__).resolve().parents[1]
SHA40=re.compile(r"[0-9a-f]{40}\Z")
MARK="PLASMA_SITE2_ENGINE_INVENTORY="
REMOTE=r'''
import hashlib,json,os,stat,subprocess
from pathlib import Path
BASE=Path("/opt/plasma/programming-engines/openocd")
OLD="0.12.0-5088db4c9154-plasma-swd-b8a7db670649"
NEW=OLD+"-3f5d5feca058"
EXPECTED_BIN="b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
OLD_ADM="1838d082222429083e3aca91290677d3873f5c681cac004a703b75f40d86c345"
NEW_ADM="3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"
def digest(p,max_bytes=33554432):
    try:
        if p.is_symlink() or not p.is_file() or p.stat().st_size>max_bytes:return "UNVERIFIED"
        h=hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda:f.read(1<<20),b""):h.update(chunk)
        return h.hexdigest()
    except OSError:return "UNVERIFIED"
def manifest(p):
    try:
        if p.is_symlink() or not p.is_file() or p.stat().st_size>16384:return {}
        data=json.loads(p.read_bytes())
        return data if type(data) is dict else {}
    except (OSError,ValueError,UnicodeError):return {}
def inspect(name):
    path=BASE/name
    if not path.exists():return {"status":"ABSENT"}
    if path.is_symlink() or not path.is_dir():return {"status":"UNTRUSTED"}
    try:
        st=path.stat()
        if st.st_uid!=0 or st.st_mode&0o022:return {"status":"UNTRUSTED"}
        x=manifest(path/"plasma-engine.json")
        bin_sha=digest(path/"bin/openocd")
        adm_sha=digest(path/"libexec/plasma_swd_site_admission.py",1048576)
        return {"status":"OBSERVED","openocd_sha256":bin_sha,
                "admission_sha256":adm_sha,
                "manifest_runtime_id_matches":x.get("runtime_id")==name,
                "manifest_binary_matches":x.get("openocd_sha256")==bin_sha,
                "manifest_admission_matches":x.get("admission_sha256")==adm_sha,
                "source_engine_runtime_id":x.get("source_engine_runtime_id"),
                "native_binary_expected":bin_sha==EXPECTED_BIN,
                "admission_expected":adm_sha==(OLD_ADM if name==OLD else NEW_ADM)}
    except OSError:return {"status":"UNVERIFIED"}
ret={"schema":"plasma.site2.engine-inventory.v1","status":"BLOCKED",
     "root_observer":os.geteuid()==0,"old_engine":inspect(OLD),"new_engine":inspect(NEW)}
try:
    rec=manifest(Path("/etc/plasma/site-worker-engine.json"))
    ret["selection"]=("OLD" if rec.get("openocd_root")==str(BASE/OLD) else
                      "NEW" if rec.get("openocd_root")==str(BASE/NEW) else "OTHER_OR_UNKNOWN")
    ret["selection_binary_sha256"]=rec.get("openocd_sha256")
    ret["selection_admission_sha256"]=rec.get("admission_sha256")
    stages=sorted(BASE.glob("."+NEW+".tmp-*"))
    ret["stage_temp_count"]=len(stages)
    ret["stages"]=[]
    for stage in stages[:3]:
        try:
            if stage.is_symlink() or not stage.is_dir():continue
            meta=stage.stat()
            suffix=stage.name.rsplit(".tmp-",1)[-1]
            pid=int(suffix) if suffix.isdigit() else 0
            comm_file=Path("/proc")/str(pid)/"comm"
            pid_alive=pid>1 and comm_file.is_file()
            comm=comm_file.read_text(errors="replace").strip() if pid_alive else "ABSENT"
            if comm not in ("python","python3","sudo","ABSENT"):comm="OTHER"
            ret["stages"].append({
                "directory_owner_uid":meta.st_uid,
                "mtime_ns":meta.st_mtime_ns,
                "pid_from_stage_name":pid,
                "pid_present":pid_alive,
                "pid_comm":comm,
                "partial_binary":(stage/"bin/openocd").is_file(),
                "partial_admission":(stage/"libexec/plasma_swd_site_admission.py").is_file(),
                "partial_manifest":(stage/"plasma-engine.json").is_file(),
                "partial_tcl":(stage/"share/openocd/scripts").is_dir(),
                "stage_binary_sha256":digest(stage/"bin/openocd"),
                "stage_admission_sha256":digest(
                    stage/"libexec/plasma_swd_site_admission.py",1048576),
                "stage_manifest_sha256":digest(stage/"plasma-engine.json",16384),
                "stage_manifest_mtime_ns":(
                    (stage/"plasma-engine.json").stat().st_mtime_ns
                    if (stage/"plasma-engine.json").is_file() else None),
                "pid_uid":(Path("/proc")/str(pid)).stat().st_uid
                          if pid_alive else None,
                "pid_executable":(
                    "PLASMA_NATIVE" if str((Path("/proc")/str(pid)/"exe").resolve()).startswith(
                        "/opt/plasma/python/3.12.13/") else "OTHER"
                    if pid_alive else "ABSENT"),
                "pid_start_epoch":(
                    (next(int(x.split()[1]) for x in
                          Path("/proc/stat").read_text().splitlines()
                          if x.startswith("btime "))+
                     int((Path("/proc")/str(pid)/"stat").read_text().rsplit(")",1)[1].split()[19])/
                     os.sysconf("SC_CLK_TCK")) if pid_alive else None),
                "pid_command_marker_matches":(
                    b"PLASMA_SITE2_ENGINE_MAINT=" in
                    (Path("/proc")/str(pid)/"cmdline").read_bytes()[:131072]
                    if pid_alive else False),
                "pid_mode_prepare":(
                    b"prepare\x00" in
                    (Path("/proc")/str(pid)/"cmdline").read_bytes()[:131072]
                    if pid_alive else False),
                "pid_state":(
                    (Path("/proc")/str(pid)/"stat").read_text().rsplit(")",1)[1].split()[0]
                    if pid_alive else None),
                "pid_cpu_ticks":(
                    sum(int((Path("/proc")/str(pid)/"stat").read_text()
                            .rsplit(")",1)[1].split()[i]) for i in (11,12))
                    if pid_alive else None),
            })
        except (OSError,ValueError):ret["stages"].append({"status":"UNVERIFIED"})
    mgr=Path("/sys/class/fpga_manager/fpga0/state").read_text().strip()
    ret["fpga_manager"]=mgr if mgr in ("operating","unknown","write","reset") else "UNVERIFIED"
    ret["site2_sealed"]=Path("/var/lib/plasma-site-worker/seals/site2.sealed").exists()
    ret["site2_admission_record"]=Path("/run/plasma-z2-swd05/swd-site2-admission").exists()
    ret["openocd_process_count"]=sum(
      (p/"comm").read_text(errors="replace").strip()=="openocd"
      for p in Path("/proc").iterdir() if p.name.isdigit() and (p/"comm").is_file())
    ret["status"]="READ_ONLY_OBSERVED"
except (OSError,ValueError):ret["status"]="UNVERIFIED"
print("PLASMA_SITE2_ENGINE_INVENTORY="+json.dumps(ret,sort_keys=True,separators=(",",":")))
'''
def run(host,source_sha,*,helper=None):
    cur=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,capture_output=True,text=True,
                       check=True,timeout=6).stdout.strip()
    if not SHA40.fullmatch(source_sha) or cur!=source_sha:
        raise RuntimeError("SOURCE_SHA_MISMATCH")
    addr=ipaddress.ip_address(host)
    if addr.version!=4 or not addr.is_private:raise RuntimeError("HOST_SCOPE_DENIED")
    if helper is None:helper=paired
    creds,known=helper.z2_login_credentials(Path.home())
    if creds.get("ssh_host")!=host:raise RuntimeError("ENROLLED_HOST_MISMATCH")
    code,stdout=helper.password_ssh_z2(
        ["/opt/plasma/python/3.12.13/bin/python3","-I","-B","-c",REMOTE],
        creds,known,timeout=80)
    if code!=0:raise RuntimeError("PINNED_SSH_INVENTORY_UNAVAILABLE")
    hits=re.findall(r"(?m)^PLASMA_SITE2_ENGINE_INVENTORY=(\{[^\r\n]{1,8192}\})\s*$",stdout)
    if len(hits)!=1:raise RuntimeError("INVENTORY_RECEIPT_INVALID")
    data=json.loads(hits[0])
    if (type(data)!=dict or data.get("schema")!="plasma.site2.engine-inventory.v1"
            or data.get("root_observer") is not True):
        raise RuntimeError("INVENTORY_RECEIPT_INVALID")
    return {"schema":"plasma.site2.path2-engine-inventory.v1","source_sha":source_sha,
            "observation":data,"flash":"NOT_RUN","fpga_reload":"NOT_RUN",
            "deployment":"NOT_RUN","service_restart":"NOT_RUN"}
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args(argv)
    try:
        result=run(a.host,a.source_sha)
        rc=0
    except Exception as exc:
        allowed={"SOURCE_SHA_MISMATCH","HOST_SCOPE_DENIED","ENROLLED_HOST_MISMATCH",
                 "PINNED_SSH_INVENTORY_UNAVAILABLE","INVENTORY_RECEIPT_INVALID"}
        reason=str(exc) if isinstance(exc,RuntimeError) and str(exc) in allowed else type(exc).__name__
        result={"schema":"plasma.site2.path2-engine-inventory.v1",
                "status":"BLOCKED","reason":reason,
                "flash":"NOT_RUN","fpga_reload":"NOT_RUN","deployment":"NOT_RUN"}
        rc=69
    print(MARK+json.dumps(result,sort_keys=True,separators=(",",":")))
    return rc
if __name__=="__main__":raise SystemExit(main())

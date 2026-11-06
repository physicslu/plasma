#!/usr/bin/env python3
"""PLASMA Path 2: bounded, source-pinned Z2 Site 2 READ-ONLY preflight.

Fixed HTTP GET + pinned SSH root-metadata reads. Never execute OpenOCD,
probe SWD, access MMIO, change services, clear seals, install or flash.
This is not authority to operate a DUT; successful observation != HIL PASS.
"""
from __future__ import annotations

import argparse
import http.client
import importlib.util
import ipaddress
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
MARKER = "PLASMA_SITE2_READONLY_Z2="
SCHEMA = "plasma.site2.path2-readonly-preflight.v1"

REMOTE = r'''
import hashlib, json, os, pathlib, re, stat, subprocess, time
P=pathlib.Path
SHA64=re.compile(r"[0-9a-f]{64}\Z")
NAME=re.compile(r"[A-Za-z0-9._-]{1,128}\Z")
def literal(path,limit=16384):
    try:
        p=P(path)
        s=p.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_size<0 or s.st_size>limit:
            return None
        return p.read_bytes()
    except (OSError,ValueError):
        return None
def safe_string(value):
    return value if isinstance(value,str) and len(value)<=128 and NAME.fullmatch(value) else "UNVERIFIED"
def sysfs_text(path,limit=128):
    # sysfs advertises a virtual size (e.g. 4096); bound ACTUAL read bytes.
    try:
        p=P(path)
        if not stat.S_ISREG(p.lstat().st_mode):return None
        with p.open("rb") as stream: raw=stream.read(limit+1)
        return raw if 0<len(raw)<=limit else None
    except (OSError,ValueError):
        return None
def metadata(path):
    try:
        info=P(path).lstat()
        return {"present":True,"regular":stat.S_ISREG(info.st_mode),
                "socket":stat.S_ISSOCK(info.st_mode),
                "symlink":stat.S_ISLNK(info.st_mode),
                "root_owned":info.st_uid==0,
                "uid":info.st_uid,"gid":info.st_gid,
                "mode":format(stat.S_IMODE(info.st_mode),"04o"),
                "writable_by_others":bool(info.st_mode&0o022)}
    except OSError:
        return {"present":False}
def service(name):
    try:
        r=subprocess.run(["/bin/systemctl","show","--no-pager",
            "--property=LoadState,ActiveState,SubState,MainPID",
            name],capture_output=True,text=True,timeout=6)
        if r.returncode: return {"state":"UNAVAILABLE"}
        f={}
        for line in r.stdout.splitlines():
            a,_,b=line.partition("=")
            if a in ("LoadState","ActiveState","SubState"): f[a]=safe_string(b)
            elif a=="MainPID" and b.isdigit(): f[a]=int(b)
        return f if set(f)=={"LoadState","ActiveState","SubState","MainPID"} else {"state":"INCOMPLETE"}
    except (OSError,subprocess.SubprocessError):
        return {"state":"UNAVAILABLE"}
def sha_of(path,max_size):
    try:
        p=P(path)
        s=p.lstat()
        if not stat.S_ISREG(s.st_mode) or s.st_size<1 or s.st_size>max_size:
            return "UNVERIFIED"
        h=hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda:f.read(1048576),b""): h.update(chunk)
        return h.hexdigest()
    except OSError:
        return "UNVERIFIED"
def engine():
    path="/etc/plasma/site-worker-engine.json"
    meta=metadata(path)
    out={"selection":meta,"status":"NOT_VERIFIED"}
    raw=literal(path,8192)
    if not raw or not meta.get("root_owned") or meta.get("writable_by_others"):
        return out
    try:
        data=json.loads(raw)
        expected={"schema","openocd_root","openocd_sha256","admission_sha256",
                  "adapter_driver","driver_abi","adapter_khz"}
        if set(data)!=expected or data["schema"]!="plasma.ppu.site-worker-engine.v1":
            return out
        root=P(data["openocd_root"])
        base=P("/opt/plasma/programming-engines/openocd")
        if root.parent!=base or not NAME.fullmatch(root.name):
            return out
        binary=root/"bin/openocd"
        admission=root/"libexec/plasma_swd_site_admission.py"
        if not all(isinstance(data[k],str) and SHA64.fullmatch(data[k]) for k in ("openocd_sha256","admission_sha256")):
            return out
        binary_actual=sha_of(binary,33554432)
        admission_actual=sha_of(admission,1048576)
        out.update({"status":"VERIFIED" if (binary_actual==data["openocd_sha256"]
                 and admission_actual==data["admission_sha256"] and
                 metadata(binary).get("root_owned") and not metadata(binary).get("writable_by_others")
                 and metadata(admission).get("root_owned") and not metadata(admission).get("writable_by_others")
                 and (root/"share/openocd/scripts").is_dir()) else "MISMATCH",
            "runtime_id":root.name,
            "driver":safe_string(data["adapter_driver"]),
            "abi":data["driver_abi"] if type(data["driver_abi"]) is int else "INVALID",
            "adapter_khz":data["adapter_khz"] if type(data["adapter_khz"]) is int else "INVALID",
            "openocd_sha256_observed":binary_actual,
            "openocd_sha256_selected":data["openocd_sha256"],
            "admission_sha256_observed":admission_actual,
            "admission_sha256_selected":data["admission_sha256"]})
    except (ValueError,KeyError,TypeError,OSError):
        return out
    return out
def fpga():
    raw=literal("/var/lib/plasma-privileged/fpga-deployment-state.json",16384)
    boot=literal("/proc/sys/kernel/random/boot_id",128)
    result={"journal":"UNAVAILABLE","manager_state":"UNAVAILABLE","boot_match":False}
    if boot: result["boot_id_sha12"]=hashlib.sha256(boot.strip()).hexdigest()[:12]
    ms=sysfs_text("/sys/class/fpga_manager/fpga0/state",128)
    if ms: result["manager_state"]=safe_string(ms.decode("ascii","replace").strip())
    if not raw: return result
    result["journal_sha256"]=hashlib.sha256(raw).hexdigest()
    try:
        j=json.loads(raw)
        if type(j)!=dict:return result
        result.update({"journal":"OBSERVED",
            "status":safe_string(j.get("status")),
            "image_id":safe_string(j.get("image_id")),
            "session_id":safe_string(j.get("session_id")),
            "firmware_sha256":j.get("firmware_sha256") if type(j.get("firmware_sha256")) is str and SHA64.fullmatch(j["firmware_sha256"]) else "UNVERIFIED",
            "boot_match": bool(boot and type(j.get("boot_id")) is str and j["boot_id"]==boot.decode().strip())})
    except (ValueError,UnicodeError):
        result["journal"]="INVALID"
    return result
def release():
    current=P("/opt/plasma/current")
    result={"current":"UNAVAILABLE","valid_target":False}
    try:
        if not current.is_symlink():return result
        target=current.resolve(strict=True)
        parent=P("/opt/plasma/releases").resolve(strict=True)
        if target.is_dir() and target.parent==parent and NAME.fullmatch(target.name):
            result={"current":target.name,"valid_target":True}
    except (OSError,RuntimeError):
        pass
    return result
def openocd_pids():
    found=[]
    try:
        for p in P("/proc").iterdir():
            if not p.name.isdigit():continue
            raw=literal(p/"comm",128)
            if raw and raw.strip()==b"openocd":
                found.append(int(p.name))
                if len(found)>=16:break
    except OSError: pass
    return sorted(found)
services={n:service(n+".service") for n in (
    "plasma-bootstrap","plasma-server","plasma-site-worker",
    "plasma-web","plasma-package-control")}
result={
 "schema":"plasma.site2.z2-observation.v1",
 "root_read_only_observer":os.geteuid()==0,
 "release":release(),
 "bootstrap_renderer":metadata("/opt/plasma/bootstrap/ppu_package_units.py"),
 "services":services,
 "engine":engine(),
 "fpga":fpga(),
 "site2_seal":metadata("/var/lib/plasma-site-worker/seals/site2.sealed"),
 "site2_admission":metadata("/run/plasma-z2-swd05/swd-site2-admission"),
 "site_worker_control_socket":metadata("/run/plasma-site-worker/control.sock"),
 "site_worker_transport_socket":metadata("/run/plasma-site-worker/transport.sock"),
 "runtime_control_socket":metadata("/run/plasma-server/control.sock"),
 "openocd_pids":openocd_pids(),
 "site_lock_owner":"NOT_VERIFIED_NO_LOCK_ACQUISITION",
 "site_hw_probe":"NOT_RUN",
 "fpga_reload":"NOT_RUN",
 "flash":"NOT_RUN",
 "recovery":"NOT_RUN",
}
print("PLASMA_SITE2_READONLY_Z2="+json.dumps(result,sort_keys=True,separators=(",",":")))
'''
def module(path: str, name: str):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    if spec is None or spec.loader is None: raise RuntimeError("REVIEWED_MODULE_MISSING")
    obj=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=obj
    spec.loader.exec_module(obj)
    return obj

def get_json(host: str,port: int,path: str) -> dict:
    conn=http.client.HTTPConnection(host,port,timeout=8)
    try:
        conn.request("GET",path,headers={"Accept":"application/json"})
        response=conn.getresponse()
        raw=response.read(65537)
        if response.status!=200 or len(raw)>65536: raise RuntimeError("HTTP_READ_DENIED")
        obj=json.loads(raw)
        if type(obj)!=dict: raise RuntimeError("HTTP_INVALID_JSON")
        return obj
    finally:
        conn.close()

def rest_observation(host: str) -> dict:
    try:
        ready=get_json(host,18080,"/api/health/ready")
        node=get_json(host,18080,"/api/node")
        status=get_json(host,18080,"/api/status?site=2")
        ident=node.get("ppu") if type(node.get("ppu")) is dict else {}
        ppu=status.get("ppu") if type(status.get("ppu")) is dict else {}
        lease=ppu.get("execution") if type(ppu.get("execution")) is dict else {}
        activation=ppu.get("runtime_activation") if type(ppu.get("runtime_activation")) is dict else {}
        sites=status.get("sites") if type(status.get("sites")) is list else []
        site=sites[0] if len(sites)==1 and type(sites[0]) is dict and sites[0].get("site_id")==2 else {}
        return {
            "status":"OBSERVED",
            "health_ready":ready.get("ok") is True and ready.get("execution")=="ready",
            "node_matches_status":bool(ident.get("ppu_id") and ident.get("ppu_id")==ppu.get("ppu_id")),
            "ppu_id":ident.get("ppu_id") if type(ident.get("ppu_id")) is str and re.fullmatch(r"[a-zA-Z0-9._-]{1,80}",ident["ppu_id"]) else "UNVERIFIED",
            "lease_busy":lease.get("busy"),
            "active_job_count":lease.get("active_job_count"),
            "activation_active":activation.get("active"),
            "site2_enabled":site.get("enabled"),
            "site2_interface":site.get("interface") if site.get("interface") in ("openocd","mock","none") else "UNVERIFIED",
            "site2_target_matches":site.get("target")=="STM32F103C8T6",
            "site2_idle":site.get("state")=="idle" and site.get("current_job_id") is None and site.get("queued_jobs")==0,
        }
    except (OSError,ValueError,TimeoutError,http.client.HTTPException,RuntimeError):
        return {"status":"UNAVAILABLE"}

def run(host: str,source_sha: str,*,helper=None,baseline=None,rest=None) -> dict:
    current=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                           capture_output=True,text=True,check=True,timeout=5).stdout.strip()
    if not SHA40.fullmatch(source_sha) or source_sha!=current:
        raise RuntimeError("SOURCE_SHA_MISMATCH")
    addr=ipaddress.ip_address(host)
    if addr.version!=4 or not addr.is_private:raise RuntimeError("HOST_SCOPE_DENIED")
    if baseline is None:baseline=module("scripts/ppu_path2_hardware_baseline.py","plasma_site2_baseline")
    bootstrap=baseline.probe_status(host)
    device=bootstrap.get("device_id_observed")
    if not isinstance(device,str) or not re.fullmatch(r"ppu-device-[0-9a-f]{16,64}",device):
        raise RuntimeError("BOOTSTRAP_IDENTITY_INVALID")
    if rest is None:rest=rest_observation
    rest_state=rest(host)
    if helper is None:helper=module("scripts/plasma_wordport_program.py","plasma_site2_enrolled_ssh")
    creds,known_hosts=helper.z2_login_credentials(Path.home())
    if creds.get("ssh_host")!=host:raise RuntimeError("ENROLLED_HOST_MISMATCH")
    rc,transcript=helper.password_ssh_z2(["python3","-I","-c",REMOTE],creds,known_hosts,timeout=60)
    if rc!=0:raise RuntimeError("PINNED_READONLY_SSH_DENIED")
    hits=re.findall(r"(?m)^PLASMA_SITE2_READONLY_Z2=(\{[^\r\n]{1,20000}\})\s*$",transcript)
    if len(hits)!=1:raise RuntimeError("REMOTE_RECEIPT_INVALID")
    z=json.loads(hits[0])
    expected={"schema","root_read_only_observer","release","bootstrap_renderer","services","engine","fpga","site2_seal",
              "site2_admission","site_worker_control_socket","site_worker_transport_socket",
              "runtime_control_socket","openocd_pids","site_lock_owner",
              "site_hw_probe","fpga_reload","flash","recovery"}
    if (type(z)!=dict or set(z)!=expected or
        z["schema"]!="plasma.site2.z2-observation.v1" or z["root_read_only_observer"] is not True or
        any(z[k]!="NOT_RUN" for k in ("site_hw_probe","fpga_reload","flash","recovery"))):
        raise RuntimeError("REMOTE_RECEIPT_INVALID")
    blockers=[]
    if z["engine"].get("status")!="VERIFIED": blockers.append("ENGINE_SELECTION_NOT_VERIFIED")
    if z["engine"].get("abi")!=5: blockers.append("ENGINE_DRIVER_ABI_NOT_V5")
    if z["engine"].get("driver")!="plasma_swd": blockers.append("ENGINE_DRIVER_NOT_PLASMA_SWD")
    if z["release"].get("valid_target") is not True: blockers.append("RUNTIME_RELEASE_UNVERIFIED")
    if z["bootstrap_renderer"].get("present") is not True: blockers.append("BOOTSTRAP_RENDERER_UNAVAILABLE")
    for entry in ("site_worker_control_socket","site_worker_transport_socket","runtime_control_socket"):
        if z[entry].get("socket") is not True:
            blockers.append("SOCKET_MISSING_"+entry)
        else:
            meta=z[entry]
            # Runtime's own control.sock is deliberately 0600, owned by
            # the unprivileged Runtime account (not by root). This is
            # observational readiness only, not authority to use the socket.
            runtime_private=(entry=="runtime_control_socket"
                and meta.get("mode")=="0600"
                and type(meta.get("uid")) is int and meta["uid"]>0
                and meta.get("writable_by_others") is False)
            root_control=(meta.get("root_owned") is True and
                meta.get("mode") in ("0660","0600","0640","0644"))
            if not (root_control or runtime_private):
                blockers.append("SOCKET_PERMISSION_REVIEW_"+entry)
    if z["fpga"].get("status")!="IMAGE" or not z["fpga"].get("boot_match"): blockers.append("FPGA_IDENTITY_OR_BOOT_UNVERIFIED")
    if z["fpga"].get("manager_state")!="operating":blockers.append("FPGA_MANAGER_NOT_OPERATING")
    if z["site2_seal"].get("present"): blockers.append("SITE2_SEALED")
    if z["site2_admission"].get("present"): blockers.append("SITE2_ADMISSION_RECORD_PRESENT")
    if z["openocd_pids"]: blockers.append("OPENOCD_PROCESS_PRESENT")
    for key in ("plasma-server","plasma-site-worker","plasma-bootstrap"):
        if z["services"].get(key,{}).get("ActiveState")!="active": blockers.append("SERVICE_NOT_ACTIVE_"+key)
    if rest_state.get("status")!="OBSERVED": blockers.append("GATEWAY_STATUS_UNAVAILABLE")
    elif not (rest_state.get("health_ready") and rest_state.get("node_matches_status")
              and rest_state.get("lease_busy") is False and rest_state.get("active_job_count")==0
              and rest_state.get("activation_active") is False
              and rest_state.get("site2_enabled") is True
              and rest_state.get("site2_interface")=="openocd"
              and rest_state.get("site2_target_matches") and rest_state.get("site2_idle")):
        blockers.append("REST_SITE2_NOT_IDLE_OR_ENABLED")
    return {"schema":SCHEMA,"status":"READ_ONLY_OBSERVED","source_sha":source_sha,
            "bootstrap":bootstrap,"rest":rest_state,"z2":z,
            "readiness":"NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS" if not blockers else "BLOCKED_OR_UNVERIFIED",
            "blockers":blockers,
            "limits":{"site_lock":"NOT_VERIFIED","physical_swd":"NOT_RUN",
                      "flash":"NOT_RUN","software_deployment":"NOT_RUN",
                      "service_restart":"NOT_RUN","fpga_reload":"NOT_RUN",
                      "recovery":"NOT_RUN"}}

def main(argv=None) -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args(argv)
    try:
        receipt=run(a.host,a.source_sha)
        code=0
    except Exception as exc:
        reason=str(exc) if isinstance(exc,RuntimeError) and str(exc) in {
            "SOURCE_SHA_MISMATCH","HOST_SCOPE_DENIED","BOOTSTRAP_IDENTITY_INVALID",
            "ENROLLED_HOST_MISMATCH","PINNED_READONLY_SSH_DENIED","REMOTE_RECEIPT_INVALID",
            "REVIEWED_MODULE_MISSING"} else type(exc).__name__
        receipt={"schema":SCHEMA,"status":"NOT_RUN_OR_BLOCKED","reason":reason,
                 "flash":"NOT_RUN","fpga_reload":"NOT_RUN","recovery":"NOT_RUN"}
        code=69
    print("PLASMA_SITE2_PATH2_PREFLIGHT="+json.dumps(receipt,sort_keys=True,separators=(",",":")))
    return code
if __name__=="__main__":raise SystemExit(main())

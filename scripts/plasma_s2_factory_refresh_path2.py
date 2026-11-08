#!/usr/bin/env python3
"""S2 one-shot source-pinned Factory Control Plane refresh on the enrolled Z2.

Path 2 development helper for #1350 S2 safety runtime precondition. Repackages the exact factory source files
from the reviewed accepted main checkout, transports a SHA256-checked private
archive over pinned owner SSH, and runs the EXISTING official
ppu-bootstrap-installer.py --refresh-only. It is not another installer and
does not install/submit a Runtime, restart services or operate DUT/FPGA.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.client
import importlib.util
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
SOURCE_COMMIT = "37a7823d89973dd0f6656ed276a7a290eb033f98"
EXPECTED_ASSET_BLOB = "4e13c51db6069a9b3a9701c8d70d5303aa16d6e9"
EXPECTED_WORKER_BLOB = "c068283afca432831ac22509bead598c9e2fe738"
DEVICE = "ppu-device-7ed4b30913a9bf6101da5a7a"
HOST = "192.168.2.99"
OLD = "0.2.1-2a5c09f62d07"
ACTIVE_B = "387b9c8c08822a6d4edb8ac7904a71a6e3143b1714453a35778c372a7517764c"
STAGE = "/var/lib/plasma-bootstrap/operator-recovery/factory-refresh-s2-37a7823d"
BUNDLE_ROOT = "plasma-ppu-bootstrap-0.1.0-" + SOURCE_COMMIT[:12]
PREFIX = "PLASMA_FACTORY_REFRESH="
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SCRIPT_NAMES = (
    "ppu-bootstrap.py", "ppu-bootstrap-service.py", "ppu-bootstrap-deployment.py",
    "ppu-bootstrap-kit.py", "ppu-bootstrap-installer.py", "ppu_unified_deployment.py",
    "ppu-z2-installer.py", "ppu-z2-installer-core.py", "ppu_asset_set.py",
    "ppu_owner_authorization.py", "ppu_asset_execution.py",
    "ppu_privileged_source.py", "ppu-privileged-source-install.py",
    "ppu_package_launcher.py", "ppu_package_entry.py", "ppu_package_unit_helper.py",
    "ppu_package_units.py", "ppu_package_action.py", "ppu_site_worker.py",
    "ppu_site_worker_service.py", "ppu_site_engine.py", "ppu_opf_reference_openocd.py",
    "ppu_opf_site_session.py", "ppu_provider_contract.py", "ppu_provider_options.py",
    "ppu_site_adapter_abi5.py", "ppu_site_recovery.py", "ppu_fpga_qualification.py",
    "ppu-bundle-install-policy.json",
)
EXTRA_FILES = (
    "pl/hil/fpga_image_root.py", "pl/hil/fpga_image_guard.py",
    "pl/hil/fpga_image_admission.py",
    "software/python/plasma_interfaces/__init__.py",
    "software/python/plasma_interfaces/linux_mmio.py",
    "z2/plasma-path2-root-entry",
)
ALL_FILES = tuple(sorted("scripts/" + p for p in (*SCRIPT_NAMES, *EXTRA_FILES)))
EXPECTED_ENGINE_BINARY = "b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
EXPECTED_ENGINE_ADMISSION = "3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"

REMOTE_COMMON = r'''
import hashlib,json,os,pathlib,stat
BASE=pathlib.Path("/var/lib/plasma-bootstrap")
API=BASE/"deployment-api.json"
COORD=BASE/"deployment.json"
CURRENT=pathlib.Path("/opt/plasma/current")
STAGE=pathlib.Path("__STAGE__")
OLD="0.2.1-2a5c09f62d07"
def fail(reason):
    print("PLASMA_FACTORY_STAGE="+json.dumps({"status":"BLOCKED","reason":reason}))
    raise SystemExit(69)
def journal(path):
    st=path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o077 or not 0<st.st_size<=1048576:
        fail("JOURNAL_OWNER_MODE_SIZE_INVALID")
    data=path.read_bytes()
    if len(data)>1048576: fail("JOURNAL_BOUNDS_INVALID")
    obj=json.loads(data)
    if type(obj) is not dict: fail("JOURNAL_INVALID")
    return obj,data
def guard():
    if os.geteuid()!=0: fail("ROOT_REQUIRED")
    api,api_bytes=journal(API)
    coord,coord_bytes=journal(COORD)
    if api.get("state") in ("queued","running","recovery_required"):
        fail("API_DEPLOYMENT_BUSY_OR_RECOVERY")
    if coord.get("state") in ("queued","running","recovery_required",
                             "installing","activating","verified"):
        fail("COORDINATOR_DEPLOYMENT_BUSY_OR_RECOVERY")
    if (not CURRENT.is_symlink() or CURRENT.resolve(strict=True)
        !=pathlib.Path("/opt/plasma/releases")/OLD):
        fail("ORIGINAL_RUNTIME_NOT_SELECTED")
    root=pathlib.Path("/opt/plasma/bootstrap")
    st=root.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:
        fail("FACTORY_ROOT_UNTRUSTED")
    st=(root/"ppu_asset_set.py").lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:
        fail("FACTORY_ASSET_SET_UNTRUSTED")
    return api_bytes,coord_bytes
'''
REMOTE_PREP = REMOTE_COMMON + r'''
guard()
parent=STAGE.parent
p=parent.lstat()
if not stat.S_ISDIR(p.st_mode) or p.st_uid!=0 or p.st_mode&0o077:
    fail("PRIVATE_RECOVERY_PARENT_INVALID")
try:
    STAGE.mkdir(mode=0o700)
except FileExistsError: fail("REFRESH_ALREADY_STAGED_NO_RETRY")
print("PLASMA_FACTORY_STAGE="+json.dumps({"status":"READY","stage":"CREATED"}))
'''
REMOTE_CHUNK = r'''
import base64,hashlib,json,os,pathlib,stat
p=pathlib.Path("__STAGE__")
st=p.lstat()
if not stat.S_ISDIR(st.st_mode) or st.st_uid!=0 or st.st_mode&0o077:
    raise SystemExit(69)
b=base64.b64decode("__BASE64__",validate=True)
if len(b)!=__SIZE__ or hashlib.sha256(b).hexdigest()!="__HASH__":
    raise SystemExit(69)
f=p/"__PART__"
fd=os.open(f,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
with os.fdopen(fd,"wb") as stream:
    stream.write(b);stream.flush();os.fsync(stream.fileno())
print("PLASMA_FACTORY_STAGE="+json.dumps({"status":"CHUNK_WRITTEN","part":"__PART__"}))
'''
REMOTE_APPLY = REMOTE_COMMON + r'''
import ast,io,importlib.util,subprocess,tarfile,shutil
before_api,before_coord=guard()
if STAGE.is_symlink() or not STAGE.is_dir():fail("STAGE_MISSING")
expected=__FILE_LIST__
parts=sorted(STAGE.glob("part-*.bin"))
if len(parts)!=__NCHUNKS__ or [p.name for p in parts]!=["part-%03d.bin"%i for i in range(__NCHUNKS__)]:
    fail("ARCHIVE_CHUNK_SET_MISMATCH")
body=b"".join(p.read_bytes() for p in parts)
if hashlib.sha256(body).hexdigest()!="__DIGEST__" or len(body)>2097152:
    fail("ARCHIVE_DIGEST_INVALID")
rootname="__BUNDLE_ROOT__"
package=STAGE/"source"/rootname
files={}
try:
    with tarfile.open(fileobj=io.BytesIO(body),mode="r:gz") as archive:
        members=archive.getmembers()
        if len(members)!=len(expected)+2:fail("FACTORY_MEMBER_COUNT_INVALID")
        for member in members:
            if (not member.isfile() or member.size<0 or member.size>1048576
                or not member.name.startswith(rootname+"/")):
                fail("FACTORY_TAR_MEMBER_DENIED")
            name=member.name[len(rootname)+1:]
            if name not in (*expected,"manifest.json","SHA256SUMS") or name in files:
                fail("FACTORY_FILE_SET_DENIED")
            files[name]=archive.extractfile(member).read()
except (OSError,tarfile.TarError,ValueError,TypeError):
    fail("FACTORY_ARCHIVE_INVALID")
if set(files)!=set(expected)|{"manifest.json","SHA256SUMS"}:
    fail("FACTORY_SOURCE_SET_INVALID")
manifest=json.loads(files["manifest.json"])
if (manifest.get("git_sha")!="37a7823d89973dd0f6656ed276a7a290eb033f98"
    or manifest.get("product")!="plasma-ppu-bootstrap"
    or manifest.get("runtime_included") is not False):
    fail("FACTORY_MANIFEST_IDENTITY_MISMATCH")
checks=files["SHA256SUMS"].decode("ascii").splitlines()
expected_checks=[hashlib.sha256(files[name]).hexdigest()+"  "+name for name in ["manifest.json",*sorted(expected)]]
if checks!=expected_checks:fail("FACTORY_FILE_HASHES_INVALID")
if (not any(isinstance(n,ast.FunctionDef) and n.name=="resolve_active_firmware"
            for n in ast.parse(files["scripts/ppu_asset_set.py"]).body)):
    fail("FACTORY_REQUIRED_RESOLVER_MISSING")
worker=files["scripts/ppu_site_worker.py"]
worker_blob=hashlib.sha1(b"blob "+str(len(worker)).encode()+b"\0"+worker).hexdigest()
if worker_blob!="c068283afca432831ac22509bead598c9e2fe738" or b"OPERATION_IN_PROGRESS" not in worker:
    fail("S2_WORKER_SOURCE_MISMATCH")
# Extract only exact regular allowlisted files. Avoid tarfile.extractall traversal.
for name,data in files.items():
    dst=package/name
    dst.parent.mkdir(parents=True,exist_ok=True)
    fd=os.open(dst,os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"wb") as stream:
        stream.write(data);stream.flush();os.fsync(stream.fileno())
# Retain existing Factory source files privately for a separately authorized recovery.
backup=STAGE/"factory-before"
backup.mkdir(mode=0o700)
installed=pathlib.Path("/opt/plasma/bootstrap")
for name in expected:
    relative=name[len("scripts/"):]
    dst=installed/relative
    if dst.exists() or dst.is_symlink():
        st=dst.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or st.st_mode&0o022:
            fail("EXISTING_FACTORY_FILE_UNTRUSTED")
        old=dst.read_bytes()
        if len(old)>1048576:fail("FACTORY_BACKUP_FILE_TOO_LARGE")
        target=backup/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(target,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"wb") as stream:
            stream.write(old);stream.flush();os.fsync(stream.fileno())
unit=pathlib.Path("/etc/systemd/system/plasma-bootstrap.service")
ust=unit.lstat()
if not stat.S_ISREG(ust.st_mode) or ust.st_uid!=0:
    fail("BOOTSTRAP_UNIT_UNTRUSTED")
unit_hash=hashlib.sha256(unit.read_bytes()).hexdigest()
# Only the canonical Factory Installer is authorized to replace installed scripts.
cmd=["/usr/bin/python3",str(package/"scripts/ppu-bootstrap-installer.py"),
     "--source-root",str(package/"scripts"),
     "--host","192.168.2.99","--refresh-only"]
try:
    result=subprocess.run(cmd,capture_output=True,text=True,timeout=120,check=False)
except (OSError,subprocess.TimeoutExpired):
    fail("OFFICIAL_FACTORY_INSTALLER_UNAVAILABLE_OR_TIMEOUT")
if result.returncode!=0:fail("OFFICIAL_FACTORY_REFRESH_FAILED_NO_AUTORETRY")
try:
    receipt=json.loads(result.stdout)
except (ValueError,TypeError):fail("FACTORY_RECEIPT_INVALID")
if receipt.get("result")!="PASS" or receipt.get("operation")!="refresh_only":
    fail("FACTORY_INSTALLER_NOT_PASS")
module_file=installed/"ppu_asset_set.py"
if hashlib.sha256(module_file.read_bytes()).hexdigest()!=hashlib.sha256(files["scripts/ppu_asset_set.py"]).hexdigest():
    fail("INSTALLED_RESOLVER_DIGEST_MISMATCH")
if hashlib.sha256((installed/"ppu_site_worker.py").read_bytes()).hexdigest()!=hashlib.sha256(worker).hexdigest():
    fail("INSTALLED_S2_WORKER_DIGEST_MISMATCH")
spec=importlib.util.spec_from_file_location("plasma_factory_resolver_attestation",module_file)
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
if not callable(getattr(mod,"resolve_active_firmware",None)):
    fail("INSTALLED_RESOLVER_NOT_CALLABLE")
after_api,after_coord=guard()
if before_api!=after_api or before_coord!=after_coord:
    fail("DEPLOYMENT_JOURNALS_CHANGED_DURING_REFRESH")
if unit_hash!=hashlib.sha256(unit.read_bytes()).hexdigest():
    fail("BOOTSTRAP_UNIT_CHANGED")
print("PLASMA_FACTORY_STAGE="+json.dumps({"status":"PASS","result":"REFRESH_ONLY",
      "factory_source_commit":"37a7823d89973dd0f6656ed276a7a290eb033f98",
      "resolver_source_sha256":hashlib.sha256(files["scripts/ppu_asset_set.py"]).hexdigest(),
      "worker_sha256":hashlib.sha256(worker).hexdigest(),
      "resolver_callable":True,"unit_changed":False,"service_restarted":False,
      "runtime_installed":False,"fpga":"NOT_RUN","dut":"NOT_RUN"}))
'''

def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT/path)
    if spec is None or spec.loader is None:
        raise RuntimeError("REVIEWED_HELPER_UNAVAILABLE")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

def get(host: str, path: str) -> dict:
    conn = http.client.HTTPConnection(host, 18080, timeout=12)
    try:
        conn.request("GET", path, headers={"Accept": "application/json"})
        resp = conn.getresponse()
        data = resp.read(65537)
        if resp.status != 200 or len(data) > 65536:
            raise RuntimeError("GATEWAY_READ_DENIED")
        obj = json.loads(data)
        if type(obj) is not dict:raise RuntimeError("GATEWAY_RESPONSE_INVALID")
        return obj
    finally:
        conn.close()

def require_site2_safe_observation(snapshot: object) -> dict:
    """Bounded, real read-only Z2 preflight; a zero exit alone is insufficient."""
    if not isinstance(snapshot, dict) or snapshot.get("readiness") != "NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS" or snapshot.get("blockers") != []:
        raise RuntimeError("SITE2_PHYSICAL_PRECHECK_BLOCKED")
    z = snapshot.get("z2", {})
    engine = z.get("engine", {})
    fpga = z.get("fpga", {})
    rest = snapshot.get("rest", {})
    release = z.get("release", {})
    if not (
        snapshot.get("status") == "READ_ONLY_OBSERVED"
        and release.get("current") == OLD
        and engine.get("status") == "VERIFIED"
        and engine.get("openocd_sha256_observed") == EXPECTED_ENGINE_BINARY
        and engine.get("admission_sha256_observed") == EXPECTED_ENGINE_ADMISSION
        and engine.get("driver") == "plasma_swd" and engine.get("abi") == 5
        and fpga.get("status") == "IMAGE" and fpga.get("boot_match") is True
        and fpga.get("manager_state") == "operating"
        and z.get("site2_seal", {}).get("present") is False
        and z.get("site2_admission", {}).get("present") is False
        and z.get("openocd_pids") == []
        and rest.get("active_job_count") == 0 and rest.get("lease_busy") is False
        and rest.get("activation_active") is False and rest.get("site2_idle") is True
    ):
        raise RuntimeError("SITE2_PHYSICAL_PRECHECK_BLOCKED")
    return {"fpga_image_id": fpga.get("image_id"),
            "fpga_boot_id_sha12": fpga.get("boot_id_sha12"),
            "engine_binary_sha256": EXPECTED_ENGINE_BINARY}


def make_archive() -> bytes:
    inputs={}
    for name in ALL_FILES:
        relative=name[len("scripts/"):]
        f=(ROOT/relative if relative.startswith(("pl/hil/","software/python/"))
           else ROOT/name)
        if f.is_symlink() or not f.is_file():
            raise RuntimeError("FACTORY_SOURCE_FILE_MISSING_OR_SYMLINK")
        inputs[name]=f.read_bytes()
    blob=subprocess.run(["git","hash-object","scripts/ppu_asset_set.py"],
                        cwd=ROOT,capture_output=True,text=True,timeout=5,check=True).stdout.strip()
    if blob!=EXPECTED_ASSET_BLOB:
        raise RuntimeError("FACTORY_ACCEPTED_RESOLVER_SOURCE_MISMATCH")
    worker_blob=subprocess.run(["git","hash-object","scripts/ppu_site_worker.py"],
                        cwd=ROOT,capture_output=True,text=True,timeout=5,check=True).stdout.strip()
    if worker_blob!=EXPECTED_WORKER_BLOB:
        raise RuntimeError("FACTORY_ACCEPTED_S2_WORKER_SOURCE_MISMATCH")
    manifest={
        "schema_version":1,"product":"plasma-ppu-bootstrap",
        "bootstrap_version":"0.1.0","git_sha":SOURCE_COMMIT,
        "python_min":"3.10","runtime_included":False,
        "control_token_included":False,"fpga_update":False,
        "publisher_authenticity":"not_qualified",
    }
    inputs["manifest.json"]=(json.dumps(manifest,indent=2,sort_keys=True)+"\n").encode()
    inputs["SHA256SUMS"]=("".join(
        hashlib.sha256(inputs[n]).hexdigest()+"  "+n+"\n"
        for n in ("manifest.json",*sorted(ALL_FILES)))).encode()
    buf=io.BytesIO()
    with tarfile.open(fileobj=buf,mode="w:gz") as archive:
        for name in sorted(inputs):
            data=inputs[name]
            info=tarfile.TarInfo(BUNDLE_ROOT+"/"+name)
            info.size=len(data)
            info.mode=0o600
            info.mtime=0
            archive.addfile(info,io.BytesIO(data))
    data=buf.getvalue()
    if not 0<len(data)<=2*1024*1024:
        raise RuntimeError("FACTORY_ARCHIVE_BOUNDS_INVALID")
    return data

def main() -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host",required=True)
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--approved-once",action="store_true")
    args=parser.parse_args()
    result={"schema":"plasma.factory-source-refresh.v1","status":"BLOCKED",
            "runtime_install":"NOT_RUN","fpga":"NOT_RUN","dut":"NOT_RUN"}
    try:
        head=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                            capture_output=True,text=True,timeout=5,check=True).stdout.strip()
        if not SHA40.fullmatch(args.source_sha) or head!=args.source_sha:
            raise RuntimeError("SOURCE_SHA_MISMATCH")
        if not args.approved_once:raise RuntimeError("OWNER_ONCE_APPROVAL_REQUIRED")
        if args.host!=HOST:raise RuntimeError("HOST_DENIED")
        baseline=load("scripts/ppu_path2_hardware_baseline.py","factory_refresh_baseline")
        if baseline.probe_status(HOST).get("device_id_observed")!=DEVICE:
            raise RuntimeError("DEVICE_ID_MISMATCH")
        ready=get(HOST,"/api/health/ready")
        node=get(HOST,"/api/node")
        status=get(HOST,"/api/status?site=2")
        ppu=status.get("ppu",{})
        execution=ppu.get("execution",{})
        activation=ppu.get("runtime_activation",{})
        sites=status.get("sites",[])
        site=sites[0] if type(sites) is list and len(sites)==1 else {}
        if not (ready.get("ok") is True and ready.get("execution")=="ready"
            and node.get("ppu",{}).get("ppu_id")=="z2-hil"
            and ppu.get("ppu_id")=="z2-hil"
            and execution.get("busy") is False
            and execution.get("active_job_count")==0
            and activation.get("active") is False
            and site.get("site_id")==2 and site.get("state")=="idle"
            and site.get("current_job_id") is None and site.get("queued_jobs")==0):
            raise RuntimeError("Z2_SITE2_NOT_IDLE")
        preflight=load("scripts/plasma_site2_path2_preflight.py","factory_s2_readonly")
        safety=require_site2_safe_observation(preflight.run(HOST,args.source_sha))
        token=baseline._existing_bootstrap_token_via_z2_ssh(HOST)
        client=baseline.DirectSSHAuthenticatedBootstrap(
            HOST,module=baseline._load_client(),token=token)
        observed=client.status()
        if (observed.get("identity",{}).get("device_id")!=DEVICE
            or observed.get("runtime",{}).get("state")!="runtime_active"
            or observed.get("runtime",{}).get("release_id")!=OLD
            or observed.get("deployment",{}).get("state") in ("queued","running","recovery_required")):
            raise RuntimeError("BOOTSTRAP_RECOVERY_OR_RUNTIME_MISMATCH")
        assets=client._call("GET","/v1/assets",None).get("assets",{})
        if (assets.get("state")!="ACTIVE" or assets.get("asset_set_sha256")!=ACTIVE_B):
            raise RuntimeError("ACTIVE_ASSET_SET_CHANGED")
        data=make_archive()
        digest=hashlib.sha256(data).hexdigest()
        chunks=[data[i:i+18000] for i in range(0,len(data),18000)]
        if len(chunks)>120:raise RuntimeError("FACTORY_ARCHIVE_CHUNK_LIMIT")
        helper=load("scripts/plasma_wordport_program.py","factory_refresh_ssh")
        creds,hosts=helper.z2_login_credentials(Path.home())
        if creds.get("ssh_host")!=HOST:
            raise RuntimeError("ENROLLED_HOST_MISMATCH")
        def remote(script, expected_status, timeout=90):
            code,text=helper.password_ssh_z2(["python3","-I","-B","-c",script],
                                              creds,hosts,timeout=timeout)
            rows=re.findall(r'(?m)^PLASMA_FACTORY_STAGE=(\{[^\r\n]{1,8192}\})\s*$',text)
            if len(rows)!=1:
                raise RuntimeError("FACTORY_REMOTE_RECEIPT_MISSING")
            row=json.loads(rows[0])
            if code!=0 or row.get("status")!=expected_status:
                raise RuntimeError("FACTORY_REMOTE_"+str(row.get("reason","FAILED")))
            return row
        remote(REMOTE_PREP.replace("__STAGE__",STAGE),"READY")
        for i,part in enumerate(chunks):
            script=(REMOTE_CHUNK.replace("__STAGE__",STAGE)
                   .replace("__BASE64__",base64.b64encode(part).decode())
                   .replace("__SIZE__",str(len(part)))
                   .replace("__HASH__",hashlib.sha256(part).hexdigest())
                   .replace("__PART__","part-%03d.bin"%i))
            remote(script,"CHUNK_WRITTEN")
        require_site2_safe_observation(preflight.run(HOST,args.source_sha))
        script=(REMOTE_APPLY.replace("__STAGE__",STAGE)
                .replace("__DIGEST__",digest)
                .replace("__NCHUNKS__",str(len(chunks)))
                .replace("__FILE_LIST__",repr(list(ALL_FILES)))
                .replace("__BUNDLE_ROOT__",BUNDLE_ROOT))
        final=remote(script,"PASS",timeout=240)
        after=client.status()
        if (after.get("deployment",{}).get("state") in ("queued","running","recovery_required")
            or after.get("runtime",{}).get("release_id")!=OLD
            or after.get("identity",{}).get("device_id")!=DEVICE):
            raise RuntimeError("FACTORY_POST_BOOTSTRAP_STATE_CHANGED")
        if final.get("worker_sha256") is None:
            raise RuntimeError("FACTORY_WORKER_DIGEST_NOT_REPORTED")
        after_assets=client._call("GET","/v1/assets",None).get("assets",{})
        if (after_assets.get("state")!="ACTIVE" or after_assets.get("asset_set_sha256")!=ACTIVE_B):
            raise RuntimeError("ACTIVE_ASSET_SET_CHANGED_DURING_REFRESH")
        result.update(status="PASS",factory=final.get("result"),
                      resolver_callable=final.get("resolver_callable",final.get("result")=="ALREADY_INSTALLED"),
                      factory_source_commit=SOURCE_COMMIT,
                      resolver_sha256=final.get("resolver_source_sha256"),
                      archive_sha256=digest,source_provenance="REPACKAGED_FROM_ACCEPTED_MAIN",
                      worker_sha256=final.get("worker_sha256"),
                      runtime_unchanged=True,active_bundle_unchanged=True,
                      bootstrap_journals_unchanged=True,service_restart="NOT_RUN",
                      fpga_image_id=safety["fpga_image_id"],
                      fpga_boot_id_sha12=safety["fpga_boot_id_sha12"])
        print(PREFIX+json.dumps(result,sort_keys=True))
        return 0
    except Exception as exc:
        allowed={"SOURCE_SHA_MISMATCH","OWNER_ONCE_APPROVAL_REQUIRED","HOST_DENIED",
                 "DEVICE_ID_MISMATCH","Z2_SITE2_NOT_IDLE",
                 "BOOTSTRAP_RECOVERY_OR_RUNTIME_MISMATCH","ACTIVE_ASSET_SET_CHANGED",
                 "SITE2_PHYSICAL_PRECHECK_BLOCKED",
                 "FACTORY_ACCEPTED_RESOLVER_SOURCE_MISMATCH",
                 "FACTORY_ACCEPTED_S2_WORKER_SOURCE_MISMATCH","FACTORY_ARCHIVE_BOUNDS_INVALID",
                 "FACTORY_ARCHIVE_CHUNK_LIMIT","ENROLLED_HOST_MISMATCH",
                 "FACTORY_REMOTE_RECEIPT_MISSING","FACTORY_POST_BOOTSTRAP_STATE_CHANGED"}
        reason=(str(exc) if isinstance(exc,RuntimeError)
                and (str(exc) in allowed or str(exc).startswith("FACTORY_REMOTE_"))
                else type(exc).__name__)
        result.update(reason=reason)
        print(PREFIX+json.dumps(result,sort_keys=True))
        return 69

if __name__=="__main__":
    raise SystemExit(main())

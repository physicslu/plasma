#!/usr/bin/env python3
"""One-shot Z2 Runtime rollback journal reconciliation plus libgpiod2 prerequisite.

Dev-only temporary PR; no install/deploy/flash/FPGA actions. The already
rolled-back Coordinator transaction must be PROVEN terminal before fixing the
Bootstrap API's independent recovery_required state.
"""
from __future__ import annotations
import argparse
import http.client
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[a-f0-9]{40}\Z")
DEVICE = "ppu-device-7ed4b30913a9bf6101da5a7a"
TX = "192d50fd295e4e9788b34b3ad4d7e83f"
OLD = "0.2.1-68536c66bb82"
NEW = "0.2.1-2a5c09f62d07"
ACTIVE_A = "71e9a044c7f45d0f6e608c2727961f6ada220b483225bd20b928bf06f289946a"
MARKER = "PLASMA_RUNTIME_ROLLBACK_RECOVER="

REMOTE = r'''
import ctypes,ctypes.util,hashlib,json,os,pathlib,shutil,stat,subprocess,time
BASE=pathlib.Path("/var/lib/plasma-bootstrap")
API=BASE/"deployment-api.json"
COORD=BASE/"deployment.json"
CURRENT=pathlib.Path("/opt/plasma/current")
TX="192d50fd295e4e9788b34b3ad4d7e83f"
OLD="0.2.1-68536c66bb82"
NEW="0.2.1-2a5c09f62d07"
RESULT={"schema":"plasma.runtime-rollback-recovery.v1",
        "status":"BLOCKED","api_record":"NOT_CHANGED","dependency":"NOT_RUN",
        "new_runtime_install":"NOT_RUN","fpga":"NOT_RUN","dut":"NOT_RUN"}
def fail(why):
    RESULT["reason"]=why
    print("PLASMA_RUNTIME_ROLLBACK_RECOVER="+json.dumps(RESULT,sort_keys=True,separators=(",",":")))
    raise SystemExit(69)
def bounded(path):
    try:
        st=path.lstat()
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=0
            or st.st_mode&0o077 or st.st_size<=0 or st.st_size>1048576):
            fail("JOURNAL_OWNER_MODE_OR_SIZE_INVALID")
        with path.open("rb") as f:data=f.read(1048577)
        if len(data)>1048576:fail("JOURNAL_TOO_LARGE")
        obj=json.loads(data)
        if type(obj) is not dict:fail("JOURNAL_OBJECT_INVALID")
        return obj,data
    except (OSError,ValueError,TypeError):
        fail("JOURNAL_READ_FAILED")
if os.geteuid()!=0:fail("ROOT_AUTHORITY_UNAVAILABLE")
api,original=bounded(API)
coordinator,coordinator_bytes=bounded(COORD)
if (api.get("transaction_id")!=TX or api.get("state")!="recovery_required"
    or api.get("error_code")!="coordinator_result_unreconciled"
    or api.get("result") is not None):
    fail("API_EXACT_ROLLBACK_STATE_MISMATCH")
if (coordinator.get("api_transaction_id")!=TX
    or coordinator.get("kind")!="ppu-runtime"
    or coordinator.get("state")!="rolled_back"
    or coordinator.get("error_code")!="activation_failed_rolled_back"
    or coordinator.get("release_id")!=NEW):
    fail("COORDINATOR_ROLLBACK_NOT_PROVEN")
error=api.get("error")
if type(error) is not str or "libgpiod" not in error.lower():
    fail("EXPECTED_LIBGPIOD_CAUSE_NOT_PROVEN")
try:
    if not CURRENT.is_symlink() or CURRENT.resolve(strict=True)!=pathlib.Path("/opt/plasma/releases")/OLD:
        fail("ORIGINAL_RUNTIME_NOT_SELECTED")
except OSError:fail("ACTIVE_RUNTIME_UNAVAILABLE")
if shutil.disk_usage("/").free < 2*1024**3:fail("DISK_SPACE_INSUFFICIENT")
try:
    info=pathlib.Path("/proc/meminfo").read_text()
    free=int(next(x.split()[1] for x in info.splitlines() if x.startswith("MemAvailable:")))
    if free<180*1024:fail("MEMORY_AVAILABILITY_LOW")
except (OSError,ValueError,StopIteration):fail("MEMORY_UNVERIFIED")
# Keep the Coordinator journal completely untouched. Back up only the exact
# API record as a root-private, fsynced file. Never read or copy token/state.
backups=BASE/"operator-recovery"
try:
    backups.mkdir(mode=0o700,exist_ok=True)
    bstat=backups.lstat()
    if not stat.S_ISDIR(bstat.st_mode) or bstat.st_uid!=0 or bstat.st_mode&0o077:
        fail("RECOVERY_DIRECTORY_NOT_PRIVATE")
    backup=backups/("deployment-api-"+TX+".json")
    fd=os.open(backup,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    try:
        with os.fdopen(fd,"wb") as f:
            f.write(original);f.flush();os.fsync(f.fileno())
    except BaseException:
        raise
except (OSError,FileExistsError):fail("RECOVERY_BACKUP_NOT_CREATED_OR_ALREADY_EXISTS")
updated=dict(api)
updated.update(state="failed",error_code="operator_reconciled_rolled_back",
               error="Coordinator terminal rolled_back and original Runtime verified",
               result=None,updated_at_epoch_s=time.time())
tmp=API.with_name(API.name+".operator-recovery-new")
try:
    fd=os.open(tmp,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,"w",encoding="utf-8") as f:
        json.dump(updated,f,indent=2,sort_keys=True)
        f.write("\n");f.flush();os.fsync(f.fileno())
    # Revalidate the original API and Coordinator bytes immediately before CAS.
    if API.read_bytes()!=original or COORD.read_bytes()!=coordinator_bytes:
        fail("JOURNAL_CHANGED_CONCURRENTLY")
    os.replace(tmp,API)
    fd=os.open(BASE,os.O_RDONLY|os.O_DIRECTORY)
    try:os.fsync(fd)
    finally:os.close(fd)
except OSError:fail("API_RECOVERY_WRITE_FAILED")
recovered,_=bounded(API)
if recovered.get("state")!="failed" or recovered.get("transaction_id")!=TX:
    fail("API_RECOVERY_READBACK_FAILED")
RESULT.update(api_record="RECONCILED_FAILED",coordinator_unchanged=True,
              previous_release=OLD,status="PARTIAL_PASS")
# Installation prerequisite is the documented OS library ONLY, not an OS upgrade.
def available():
    try:
        ctypes.CDLL("libgpiod.so.2")
        return True
    except OSError:return False
if not available():
    cmd=["apt-get","install","-y","--no-install-recommends","libgpiod2"]
    env={"PATH":"/usr/sbin:/usr/bin:/sbin:/bin","LANG":"C",
         "DEBIAN_FRONTEND":"noninteractive","APT_LISTCHANGES_FRONTEND":"none"}
    try:
        proc=subprocess.run(cmd,capture_output=True,text=True,timeout=240,check=False,env=env)
    except (OSError,subprocess.TimeoutExpired):fail("LIBGPIOD2_APT_UNAVAILABLE")
    if proc.returncode!=0:fail("LIBGPIOD2_APT_INSTALL_FAILED")
if not available():fail("LIBGPIOD_SO2_STILL_NOT_LOADABLE")
RESULT.update(status="PASS",dependency="LIBGPIOD_SO2_LOADABLE")
print("PLASMA_RUNTIME_ROLLBACK_RECOVER="+json.dumps(RESULT,sort_keys=True,separators=(",",":")))
'''

def loader(path: str, name: str):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    if spec is None or spec.loader is None:raise RuntimeError("REVIEWED_HELPER_UNAVAILABLE")
    module=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=module
    spec.loader.exec_module(module)
    return module

def get(host: str, path: str) -> dict:
    conn=http.client.HTTPConnection(host,18080,timeout=12)
    try:
        conn.request("GET",path,headers={"Accept":"application/json"})
        resp=conn.getresponse();content=resp.read(65537)
        if resp.status!=200 or len(content)>65536:raise RuntimeError("GATEWAY_READ_DENIED")
        obj=json.loads(content)
        if type(obj) is not dict:raise RuntimeError("GATEWAY_RESPONSE_INVALID")
        return obj
    finally:conn.close()

def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    p.add_argument("--approved-once",action="store_true")
    a=p.parse_args()
    try:
        head=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                            capture_output=True,text=True,timeout=5,check=True).stdout.strip()
        if not SHA.fullmatch(a.source_sha) or head!=a.source_sha:
            raise RuntimeError("SOURCE_SHA_PIN_MISMATCH")
        if not a.approved_once:raise RuntimeError("OWNER_ONCE_APPROVAL_REQUIRED")
        if a.host!="192.168.2.99" or ipaddress.ip_address(a.host).version!=4:
            raise RuntimeError("HOST_DENIED")
        common=loader("scripts/ppu_path2_hardware_baseline.py","runtime_recovery_common")
        probe=common.probe_status(a.host)
        if probe.get("device_id_observed")!=DEVICE:
            raise RuntimeError("DEVICE_ID_MISMATCH")
        ready=get(a.host,"/api/health/ready")
        node=get(a.host,"/api/node")
        status=get(a.host,"/api/status?site=2")
        ppu=status.get("ppu",{})
        exec_state=ppu.get("execution",{})
        activation=ppu.get("runtime_activation",{})
        sites=status.get("sites")
        site=sites[0] if type(sites) is list and len(sites)==1 else {}
        if not (ready.get("ok") is True and ready.get("execution")=="ready"
                and node.get("ppu",{}).get("ppu_id")=="z2-hil"
                and ppu.get("ppu_id")=="z2-hil"
                and exec_state.get("busy") is False
                and exec_state.get("active_job_count")==0
                and activation.get("active") is False
                and site.get("site_id")==2 and site.get("enabled") is True
                and site.get("state")=="idle" and site.get("current_job_id") is None
                and site.get("queued_jobs")==0):
            raise RuntimeError("SITE2_OR_RUNTIME_BUSY")
        token=common._existing_bootstrap_token_via_z2_ssh(a.host)
        client=common.DirectSSHAuthenticatedBootstrap(
            a.host,module=common._load_client(),token=token)
        bootstrap=client.status()
        if (bootstrap.get("identity",{}).get("device_id")!=DEVICE
                or bootstrap.get("runtime",{}).get("state")!="runtime_active"
                or bootstrap.get("runtime",{}).get("release_id")!=OLD):
            raise RuntimeError("BOOTSTRAP_RUNTIME_IDENTITY_MISMATCH")
        assets=client._call("GET","/v1/assets",None).get("assets",{})
        if (assets.get("state")!="ACTIVE"
                or assets.get("asset_set_sha256")!=ACTIVE_A):
            raise RuntimeError("ACTIVE_BUNDLE_A_CHANGED")
        helper=loader("scripts/plasma_wordport_program.py","runtime_recovery_ssh")
        creds,hosts=helper.z2_login_credentials(Path.home())
        if creds.get("ssh_host")!=a.host:
            raise RuntimeError("ENROLLED_HOST_MISMATCH")
        rc,text=helper.password_ssh_z2(["python3","-I","-B","-c",REMOTE],
                                       creds,hosts,timeout=360)
        marks=re.findall(r"(?m)^PLASMA_RUNTIME_ROLLBACK_RECOVER=(\{[^\r\n]{1,8192}\})\s*$",text)
        if len(marks)!=1:raise RuntimeError("RECOVERY_RECEIPT_MISSING")
        report=json.loads(marks[0])
        if rc!=0 or report.get("status")!="PASS":
            report["status"]="BLOCKED_OR_PARTIAL"
            print(MARKER+json.dumps(report,sort_keys=True))
            return 69
        # Verify API settled to failed, not recovery_required; no new POST.
        after=client.status()
        if (after.get("deployment",{}).get("state")!="failed"
                or after.get("runtime",{}).get("state")!="runtime_active"):
            raise RuntimeError("API_RECOVERY_NOT_VISIBLE")
        print(MARKER+json.dumps(report,sort_keys=True))
        return 0
    except Exception as exc:
        allowed={"SOURCE_SHA_PIN_MISMATCH","OWNER_ONCE_APPROVAL_REQUIRED","HOST_DENIED",
                 "DEVICE_ID_MISMATCH","SITE2_OR_RUNTIME_BUSY","BOOTSTRAP_RUNTIME_IDENTITY_MISMATCH",
                 "ACTIVE_BUNDLE_A_CHANGED","ENROLLED_HOST_MISMATCH","RECOVERY_RECEIPT_MISSING",
                 "API_RECOVERY_NOT_VISIBLE","GATEWAY_READ_DENIED","GATEWAY_RESPONSE_INVALID"}
        why=str(exc) if isinstance(exc,RuntimeError) and str(exc) in allowed else type(exc).__name__
        print(MARKER+json.dumps({"schema":"plasma.runtime-rollback-recovery.v1",
              "status":"BLOCKED_OR_UNKNOWN","reason":why,"new_runtime_install":"NOT_RUN",
              "dut":"NOT_RUN"},sort_keys=True))
        return 69

if __name__=="__main__":raise SystemExit(main())

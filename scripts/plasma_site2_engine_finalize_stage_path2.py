#!/usr/bin/env python3
"""One-shot owner-authorized recovery of a completed, interrupted Engine stage.

Atomic rename of ONLY the exact existing root-owned .tmp-680 stage into the
verified immutable new OpenOCD Engine directory. Never redo Prepare, replace
OpenOCD, touch Tcl, change Engine selection, restart services or operate DUT.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
from pathlib import Path

import plasma_site2_path2_preflight as preflight
import plasma_wordport_program as paired

ROOT=Path(__file__).resolve().parents[1]
SHA40=re.compile(r"[0-9a-f]{40}\Z")
MARK="PLASMA_SITE2_ENGINE_FINALIZE="
BIN="b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
OLD_ADM="1838d082222429083e3aca91290677d3873f5c681cac004a703b75f40d86c345"
NEW_ADM="3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"
REMOTE=r'''
import hashlib,json,os,re,stat,sys
from pathlib import Path

MARK="PLASMA_SITE2_ENGINE_FINALIZE="
BASE=Path("/opt/plasma/programming-engines/openocd")
OLD="0.12.0-5088db4c9154-plasma-swd-b8a7db670649"
NEW=OLD+"-3f5d5feca058"
STAGE=BASE/("."+NEW+".tmp-680")
TARGET=BASE/NEW
BIN="b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
OLD_ADM="1838d082222429083e3aca91290677d3873f5c681cac004a703b75f40d86c345"
NEW_ADM="3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"
STAGE_MANIFEST="bab56f084b6d5af0fcedfdef7216bbe75ae1fb447d7d3794f347a3feefbc8982"
result={"schema":"plasma.site2.engine-finalize.v1","status":"BLOCKED",
        "stage_published":False,"selection_changed":False,
        "service_restarted":False,"fpga_reload":"NOT_RUN",
        "bundle_deploy":"NOT_RUN","flash":"NOT_RUN","openocd_build":"NOT_RUN"}
def require(value,code):
    if not value:raise ValueError(code)
def sha(path):
    hasher=hashlib.sha256()
    with open(path,"rb") as stream:
        for block in iter(lambda:stream.read(1<<20),b""):hasher.update(block)
    return hasher.hexdigest()
def trust(p,directory):
    info=Path(p).lstat()
    require((stat.S_ISDIR(info.st_mode) if directory else stat.S_ISREG(info.st_mode))
            and info.st_uid==0 and info.st_mode&0o022==0,
            "STAGE_OR_ENGINE_SOURCE_UNTRUSTED")
def state():
    require(os.geteuid()==0,"ROOT_REQUIRED")
    require(Path("/sys/class/fpga_manager/fpga0/state").read_text().strip()=="operating",
            "FPGA_MANAGER_CHANGED")
    journal=Path("/var/lib/plasma-privileged/fpga-deployment-state.json")
    value=json.loads(journal.read_bytes())
    boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    require(value.get("status")=="IMAGE" and value.get("boot_id")==boot,
            "FPGA_JOURNAL_BOOT_CHANGED")
    require(not Path("/run/plasma-z2-swd05/swd-site2-admission").exists()
            and not Path("/var/lib/plasma-site-worker/seals/site2.sealed").exists(),
            "SITE2_ADMISSION_OR_SEAL_PRESENT")
    for p in Path("/proc").iterdir():
        if p.name.isdigit() and (p/"comm").is_file():
            try:
                require((p/"comm").read_text().strip()!="openocd",
                        "OPENOCD_PROCESS_PRESENT")
            except FileNotFoundError:pass
    return {"journal_sha256":sha(journal),"boot":boot,
            "release":str(Path("/opt/plasma/current").resolve(strict=True))}
try:
    before=state()
    require(not Path("/proc/680").exists(),"ORIGINAL_INSTALLER_PID_PRESENT")
    require(not os.path.lexists(TARGET),"NEW_ENGINE_ALREADY_PUBLISHED")
    trust(BASE,True)
    trust(BASE/OLD,True)
    trust(STAGE,True)
    sys.path.insert(0,"/opt/plasma/bootstrap")
    import ppu_asset_set,ppu_site_engine as engine
    with ppu_asset_set.held_runtime_asset_lease():
        require(state()==before,"SITE2_DEVICE_STATE_CHANGED")
        selected=engine.load_engine()
        require(selected.openocd_root==BASE/OLD and
                selected.openocd_sha256==BIN and
                selected.admission_sha256==OLD_ADM and
                selected.adapter_driver=="plasma_swd" and
                selected.driver_abi==5 and selected.adapter_khz==2000,
                "BASELINE_ENGINE_DRIFT")
        old_manifest=engine._manifest(BASE/OLD)
        require(old_manifest.get("openocd_source_sha")==
                "5088db4c9154ca833c6d558381074b33672e127a",
                "NATIVE_ENGINE_SOURCE_DRIFT")
        trust(STAGE/"plasma-engine.json",False)
        require(sha(STAGE/"plasma-engine.json")==STAGE_MANIFEST,
                "STAGE_MANIFEST_SHA_MISMATCH")
        # A staged directory deliberately has a .tmp-PID name; the public
        # _manifest() validator requires the *final* runtime directory name.
        # Verify raw staged content by pinned SHA, then inspect its identity.
        new_manifest=json.loads((STAGE/"plasma-engine.json").read_bytes())
        require(type(new_manifest) is dict and
                new_manifest.get("schema")==engine.MANIFEST_SCHEMA and
                new_manifest.get("runtime_id")==NEW and
                new_manifest.get("source_engine_runtime_id")==OLD and
                new_manifest.get("openocd_sha256")==BIN and
                new_manifest.get("admission_sha256")==NEW_ADM and
                new_manifest.get("adapter_khz")==2000 and
                new_manifest.get("admission_source_sha")==
                    "e270616bd05094ade5c80f322c76efa88f3f5225",
                "STAGE_ENGINE_MANIFEST_MISMATCH")
        require(new_manifest.get("source_engine_manifest_sha256")==
                sha(BASE/OLD/"plasma-engine.json"),
                "STAGE_SOURCE_MANIFEST_DRIFT")
        require(all(not f.is_symlink() for f in STAGE.rglob("*")),
                "STAGE_SYMLINK_DENIED")
        oldfiles=engine._tree(BASE/OLD)
        stagedfiles=engine._tree(STAGE)
        require(oldfiles.keys()==stagedfiles.keys(),
                "STAGE_FILE_SET_CHANGED")
        changes={key for key in oldfiles
                 if oldfiles[key]!=stagedfiles[key]}
        require(changes=={"plasma-engine.json",
                          "libexec/plasma_swd_site_admission.py"},
                "STAGE_CONTENT_DELTA_NOT_ADMISSION_ONLY")
        require(oldfiles.get("bin/openocd")==BIN and
                stagedfiles.get("bin/openocd")==BIN and
                stagedfiles.get("libexec/plasma_swd_site_admission.py")==NEW_ADM,
                "STAGE_NATIVE_OR_ADMISSION_SHA_MISMATCH")
        require(all(stagedfiles[k]==v for k,v in oldfiles.items()
                    if k.startswith("share/openocd/")),
                "STAGE_TCL_CONTENT_CHANGED")
        require(not os.path.lexists(TARGET),"NEW_ENGINE_PUBLISH_RACE")
        require(state()==before,"SITE2_DEVICE_STATE_CHANGED")
        os.replace(STAGE,TARGET)
        result["stage_published"]=True
        # No second attempt or rollback if post-publication verification fails:
        # the operator must re-observe the exact selected Engine and contents.
        engine.verify_installed(TARGET,openocd_sha256=BIN,
                                admission_sha256=NEW_ADM)
        require(engine.load_engine().openocd_root==BASE/OLD,
                "ENGINE_SELECTION_DRIFT_AFTER_PUBLISH")
        require(state()==before,"FPGA_OR_RUNTIME_CHANGED_AFTER_PUBLISH")
        result.update(status="FINALIZED_NOT_SELECTED",runtime_id=NEW,
                      previous_runtime_id=OLD,openocd_sha256=BIN,
                      admission_sha256=NEW_ADM,
                      fpga_journal_sha256=before["journal_sha256"])
except Exception as e:
    result["error_code"]=(str(e) if isinstance(e,ValueError) and
                          re.fullmatch(r"[A-Z0-9_]{3,100}",str(e))
                          else type(e).__name__)
print(MARK+json.dumps(result,sort_keys=True,separators=(",",":")))
sys.exit(0 if result["status"]=="FINALIZED_NOT_SELECTED" else 1)
'''
def run(host,source_sha,*,helper=None,baseline=None):
    cur=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,check=True,
                       capture_output=True,text=True,timeout=6).stdout.strip()
    if source_sha!=cur or not SHA40.fullmatch(source_sha):
        raise RuntimeError("SOURCE_SHA_MISMATCH")
    target=ipaddress.ip_address(host)
    if target.version!=4 or not target.is_private:
        raise RuntimeError("HOST_SCOPE_DENIED")
    if baseline is None:baseline=preflight
    check=baseline.run(host,source_sha)
    z=check.get("z2",{})
    eng=z.get("engine",{})
    rest=check.get("rest",{})
    if (check.get("readiness")!="NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS"
        or check.get("blockers")
        or eng.get("status")!="VERIFIED"
        or eng.get("openocd_sha256_observed")!=BIN
        or eng.get("admission_sha256_observed")!=OLD_ADM
        or eng.get("abi")!=5 or eng.get("driver")!="plasma_swd"
        or eng.get("adapter_khz")!=2000
        or z.get("fpga",{}).get("status")!="IMAGE"
        or z.get("fpga",{}).get("boot_match") is not True
        or z.get("fpga",{}).get("manager_state")!="operating"
        or z.get("openocd_pids")
        or z.get("site2_seal",{}).get("present") is not False
        or z.get("site2_admission",{}).get("present") is not False
        or rest.get("active_job_count")!=0
        or rest.get("lease_busy") is not False
        or rest.get("activation_active") is not False):
        raise RuntimeError("FINALIZE_PREFLIGHT_BLOCKED")
    if helper is None:helper=paired
    credentials,known=helper.z2_login_credentials(Path.home())
    if credentials.get("ssh_host")!=host:
        raise RuntimeError("ENROLLED_HOST_MISMATCH")
    rc,stdout=helper.password_ssh_z2(
        ["/opt/plasma/python/3.12.13/bin/python3","-I","-B","-c",REMOTE],
        credentials,known,timeout=300)
    found=re.findall(r"(?m)^PLASMA_SITE2_ENGINE_FINALIZE=(\{[^\r\n]{1,4096}\})\s*$",stdout)
    if len(found)!=1:
        raise RuntimeError("FINALIZE_RECEIPT_UNKNOWN")
    observed=json.loads(found[0])
    if (type(observed)!=dict or observed.get("schema")!="plasma.site2.engine-finalize.v1"
        or observed.get("flash")!="NOT_RUN"
        or observed.get("bundle_deploy")!="NOT_RUN"
        or observed.get("fpga_reload")!="NOT_RUN"
        or observed.get("openocd_build")!="NOT_RUN"
        or observed.get("selection_changed") is not False
        or observed.get("service_restarted") is not False):
        raise RuntimeError("FINALIZE_RECEIPT_INVALID")
    return {"schema":"plasma.site2.path2-engine-finalize.v1",
            "source_sha":source_sha,"exit_code":rc,"observation":observed}
def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host",required=True)
    parser.add_argument("--source-sha",required=True)
    args=parser.parse_args(argv)
    try:
        result=run(args.host,args.source_sha)
        valid=(result["exit_code"]==0 and
               result["observation"].get("status")=="FINALIZED_NOT_SELECTED")
        rc=0 if valid else 1
    except Exception as exc:
        allowed={"SOURCE_SHA_MISMATCH","HOST_SCOPE_DENIED",
                 "FINALIZE_PREFLIGHT_BLOCKED","ENROLLED_HOST_MISMATCH",
                 "FINALIZE_RECEIPT_UNKNOWN","FINALIZE_RECEIPT_INVALID"}
        reason=str(exc) if isinstance(exc,RuntimeError) and str(exc) in allowed else type(exc).__name__
        result={"schema":"plasma.site2.path2-engine-finalize.v1",
                "status":"BLOCKED_OR_UNKNOWN","reason":reason,
                "flash":"NOT_RUN","bundle_deploy":"NOT_RUN",
                "fpga_reload":"NOT_RUN","openocd_build":"NOT_RUN"}
        rc=69
    print(MARK+json.dumps(result,sort_keys=True,separators=(",",":")))
    return rc
if __name__=="__main__":
    raise SystemExit(main())

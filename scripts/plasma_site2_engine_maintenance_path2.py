#!/usr/bin/env python3
"""One-shot Site 2 Admission-only Engine maintenance on paired Z2 (Path 2).

Owner-authorized Gate 1: preserve the selected native OpenOCD executable, Tcl,
FPGA Image and Active Bundle. Never compile OpenOCD or deploy a Bundle. The
source-pinned PR installer is loaded in memory without changing Bootstrap.
"prepare" creates only a new immutable Engine directory; "switch" selects
and restarts the Site Worker under its existing Runtime Job gate.
Each mode is strictly one-shot: no retry, fallback, flash, or rollback.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import ipaddress
import json
import re
import subprocess
import zlib
from pathlib import Path

import plasma_site2_path2_preflight as preflight
import plasma_wordport_program as ssh

ROOT = Path(__file__).resolve().parents[1]
CI_ADMISSION_SHA256 = "3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"
CI_ADMISSION_SOURCE_SHA = "e270616bd05094ade5c80f322c76efa88f3f5225"
OLD_ADMISSION_SHA256 = "1838d082222429083e3aca91290677d3873f5c681cac004a703b75f40d86c345"
OLD_OPENOCD_SHA256 = "b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
SOURCE = "5088db4c9154ca833c6d558381074b33672e127a"
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
MARK = "PLASMA_SITE2_ENGINE_MAINT="

REMOTE = r'''
import base64,hashlib,io,json,os,re,stat,subprocess,sys,tarfile,tempfile,types,zlib
from pathlib import Path

MARK="PLASMA_SITE2_ENGINE_MAINT="
EXPECTED_BIN="b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
EXPECTED_OLD_ADM="1838d082222429083e3aca91290677d3873f5c681cac004a703b75f40d86c345"
EXPECTED_ADM="3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"
SOURCE="5088db4c9154ca833c6d558381074b33672e127a"
CI_SOURCE="e270616bd05094ade5c80f322c76efa88f3f5225"
result={"schema":"plasma.site2.engine-maint.v1","status":"BLOCKED",
        "mode":"UNKNOWN","flash":"NOT_RUN","fpga_reload":"NOT_RUN",
        "bundle_deploy":"NOT_RUN","openocd_build":"NOT_RUN"}
def require(ok,code):
    if not ok:raise ValueError(code)
def sha(path):
    h=hashlib.sha256()
    with open(path,"rb") as stream:
        for chunk in iter(lambda:stream.read(1024*1024),b""):h.update(chunk)
    return h.hexdigest()
def trust(path,dir=False):
    p=Path(path)
    x=p.lstat()
    require((stat.S_ISDIR(x.st_mode) if dir else stat.S_ISREG(x.st_mode))
            and x.st_uid==0 and x.st_mode&0o022==0,
            "MAINT_SOURCE_NOT_ROOT_OWNED")
def state():
    require(os.geteuid()==0,"ROOT_REQUIRED")
    require(Path("/sys/class/fpga_manager/fpga0/state").read_text().strip()=="operating",
            "FPGA_MANAGER_NOT_OPERATING")
    j=json.loads(Path("/var/lib/plasma-privileged/fpga-deployment-state.json").read_bytes())
    boot=Path("/proc/sys/kernel/random/boot_id").read_text().strip()
    require(j.get("status")=="IMAGE" and j.get("boot_id")==boot,
            "FPGA_JOURNAL_BOOT_MISMATCH")
    require(not Path("/run/plasma-z2-swd05/swd-site2-admission").exists(),
            "SITE2_ADMISSION_PRESENT")
    require(not Path("/var/lib/plasma-site-worker/seals/site2.sealed").exists(),
            "SITE2_SEAL_PRESENT")
    require(not any((p/"comm").read_text(errors="replace").strip()=="openocd"
          for p in Path("/proc").iterdir() if p.name.isdigit()
          and (p/"comm").is_file()),"OPENOCD_PROCESS_PRESENT")
    return {"boot_id":boot,"journal_sha256":sha("/var/lib/plasma-privileged/fpga-deployment-state.json"),
            "image_sha256":j.get("firmware_sha256"),
            "current_release":str(Path("/opt/plasma/current").resolve())}
def require_unchanged(before,after):
    require(before==after,"FPGA_OR_RELEASE_CHANGED")
def get_module(encoded,digest):
    raw=zlib.decompress(base64.b64decode(encoded))
    require(len(raw)<80000 and hashlib.sha256(raw).hexdigest()==digest,
            "REVIEWED_ENGINE_SOURCE_MISMATCH")
    m=types.ModuleType("plasma_reviewed_engine_maintenance")
    sys.modules[m.__name__]=m
    exec(compile(raw,"<source-pinned-ppu_site_engine.py>","exec"),m.__dict__)
    return m
def typed_json(out):
    print(MARK+json.dumps(out,sort_keys=True,separators=(",",":")))
try:
    mode=sys.argv[1]
    result["mode"]=mode
    require(mode in ("prepare","switch"),"MODE_DENIED")
    require(len(sys.argv)==5,"ARGUMENTS_INVALID")
    before=state()
    trust("/opt/plasma/bootstrap",dir=True)
    trust("/opt/plasma/bootstrap/ppu_asset_set.py")
    sys.path.insert(0,"/opt/plasma/bootstrap")
    import ppu_asset_set
    eng=get_module(sys.argv[2],sys.argv[3])
    source=eng.load_engine()
    require(source.openocd_sha256==EXPECTED_BIN and
            source.admission_sha256==EXPECTED_OLD_ADM and
            source.driver_abi==5 and source.adapter_driver=="plasma_swd" and
            source.adapter_khz==2000,"BASELINE_ENGINE_IDENTITY_CHANGED")
    old_root=source.openocd_root
    orig=eng._manifest(old_root)
    require(orig.get("openocd_source_sha")==SOURCE and
            orig.get("openocd_sha256")==EXPECTED_BIN,"BASELINE_PROVENANCE_MISMATCH")
    new_id=(f"{orig['openocd_version']}-{SOURCE[:12]}-plasma-swd-"
            f"{EXPECTED_BIN[:12]}-{EXPECTED_ADM[:12]}")
    require(eng.RUNTIME_ID.fullmatch(new_id) is not None,"RUNTIME_ID_INVALID")
    new_root=eng.ENGINE_BASE/new_id
    initial_root=old_root
    if mode=="prepare":
        # The source is independently tied to the successful CI candidate,
        # not derived from an untrusted installed Z2 file.
        admission=zlib.decompress(base64.b64decode(sys.argv[4]))
        require(len(admission)<100000 and
                hashlib.sha256(admission).hexdigest()==EXPECTED_ADM and
                b"DEVMEM_INDEPENDENT_IMAGES" not in admission,
                "CI_ADMISSION_SOURCE_MISMATCH")
        require(not new_root.exists() and not new_root.is_symlink(),
                "NEW_ENGINE_ALREADY_EXISTS")
        with ppu_asset_set.held_runtime_asset_lease():
            require_unchanged(before,state())
            with tempfile.TemporaryDirectory(prefix="plasma-site2-adm-") as scratch:
                directory=Path(scratch)
                artifact=directory/"admission-only.tar.gz"
                evidence={"schema":eng.CANDIDATE_SCHEMA,
                          "openocd_source_sha":SOURCE,
                          "plasma_source_sha":CI_SOURCE,
                          "site_admission_script_sha256":EXPECTED_ADM}
                with tarfile.open(artifact,"w:gz") as archive:
                    for name,data in (
                        (eng.ADMISSION_NAME,admission),
                        ("candidate-evidence.json",json.dumps(evidence,sort_keys=True).encode())
                    ):
                        item=tarfile.TarInfo(name)
                        item.size=len(data)
                        item.mode=0o644
                        archive.addfile(item,io.BytesIO(data))
                sidecar=Path(str(artifact)+".sha256")
                sidecar.write_text(sha(artifact)+"  "+artifact.name+"\n")
                out=eng.install_selected_admission(
                    artifact,expected_admission_sha256=EXPECTED_ADM,sidecar=sidecar)
                require(out.get("result")=="ADMISSION_INSTALLED_NOT_SELECTED" and
                        out.get("runtime_id")==new_id and
                        out.get("openocd_sha256")==EXPECTED_BIN,
                        "ENGINE_PREPARE_RECEIPT_INVALID")
                require(eng.load_engine().openocd_root==old_root,
                        "SELECTION_CHANGED_DURING_PREPARE")
                require(sha(new_root/"bin/openocd")==EXPECTED_BIN and
                        sha(new_root/"libexec"/eng.ADMISSION_NAME)==EXPECTED_ADM,
                        "PREPARED_ENGINE_SHA_INVALID")
                # Use the existing per-file tree SHA to prove the native Tcl
                # source/configuration bytes are identical.
                orig_files=eng._tree(old_root)
                new_files=eng._tree(new_root)
                require(orig_files.get("bin/openocd")==new_files.get("bin/openocd") and
                        all(new_files.get(k)==v for k,v in orig_files.items()
                            if k.startswith("share/openocd/")),
                        "NATIVE_ENGINE_CONTENT_CHANGED")
                require_unchanged(before,state())
        result.update(status="PREPARED_NOT_SELECTED",runtime_id=new_id,
                      original_runtime_id=old_root.name,
                      openocd_sha256=EXPECTED_BIN,admission_sha256=EXPECTED_ADM,
                      selection_changed=False,service_restarted=False,
                      fpga_journal_sha256=before["journal_sha256"])
    else:
        require(new_root.is_dir() and not new_root.is_symlink(),
                "PREPARED_ENGINE_NOT_INSTALLED")
        new_manifest=eng._manifest(new_root)
        require(new_manifest.get("source_engine_runtime_id")==old_root.name and
                new_manifest.get("openocd_sha256")==EXPECTED_BIN and
                new_manifest.get("admission_sha256")==EXPECTED_ADM,
                "PREPARED_ENGINE_PROVENANCE_MISMATCH")
        eng.verify_installed(new_root,openocd_sha256=EXPECTED_BIN,
                             admission_sha256=EXPECTED_ADM)
        orig_files=eng._tree(old_root)
        new_files=eng._tree(new_root)
        require(all(new_files.get(k)==v for k,v in orig_files.items()
                    if k.startswith("share/openocd/")),"TCL_MISMATCH")
        require_unchanged(before,state())
        def gate():
            return ppu_asset_set.held_runtime_asset_lease()
        selected=eng.select(new_id,restart=True,hold_gate=gate)
        chosen=eng.load_engine()
        require(chosen.openocd_root==new_root and
                chosen.openocd_sha256==EXPECTED_BIN and
                chosen.admission_sha256==EXPECTED_ADM,
                "ENGINE_SELECTION_POSTCHECK_FAILED")
        require_unchanged(before,state())
        service=subprocess.run(["systemctl","is-active","plasma-site-worker.service"],
                               capture_output=True,text=True,timeout=10)
        require(service.returncode==0 and service.stdout.strip()=="active",
                "SITE_WORKER_RESTART_HEALTH_FAILED")
        result.update(status="SELECTED",runtime_id=new_id,
                      original_runtime_id=old_root.name,
                      openocd_sha256=EXPECTED_BIN,admission_sha256=EXPECTED_ADM,
                      selection_changed=True,service_restarted=True,
                      fpga_journal_sha256=before["journal_sha256"])
except Exception as exc:
    # No auto-retry or rollback. An interruption after a selection may have
    # committed an unknown state; the operator must read the exact receipt.
    result["error_code"]=(str(exc) if isinstance(exc,ValueError) and
                          re.fullmatch("[A-Z0-9_]{3,100}",str(exc))
                          else type(exc).__name__)
typed_json(result)
sys.exit(0 if result["status"] in ("PREPARED_NOT_SELECTED","SELECTED") else 1)
'''

def run(host: str, source_sha: str, mode: str, *, baseline=None, helper=None):
    current = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                             check=True, capture_output=True, text=True, timeout=6).stdout.strip()
    if not SHA40.fullmatch(source_sha) or current != source_sha:
        raise RuntimeError("SOURCE_SHA_MISMATCH")
    if mode not in ("prepare", "switch"):
        raise RuntimeError("MODE_DENIED")
    ip = ipaddress.ip_address(host)
    if ip.version != 4 or not ip.is_private:
        raise RuntimeError("HOST_SCOPE_DENIED")
    if baseline is None:
        baseline = preflight
    check = baseline.run(host, source_sha)
    z = check.get("z2", {})
    if (check.get("readiness") != "NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS"
            or check.get("blockers") or z.get("engine", {}).get("status") != "VERIFIED"
            or z.get("engine", {}).get("openocd_sha256_observed") != OLD_OPENOCD_SHA256
            or z.get("engine", {}).get("admission_sha256_observed") != OLD_ADMISSION_SHA256
            or z.get("engine", {}).get("abi") != 5
            or z.get("engine", {}).get("adapter_khz") != 2000
            or z.get("fpga", {}).get("manager_state") != "operating"
            or z.get("openocd_pids") or z.get("site2_seal", {}).get("present")
            or z.get("site2_admission", {}).get("present")):
        raise RuntimeError("ENGINE_MAINT_PREFLIGHT_BLOCKED")
    # Source pinned to one PR; the admission content is separately pinned to
    # the successful ARMv7 CI candidate SHA (not an arbitrary Git SHA).
    engine_bytes = (ROOT / "scripts/ppu_site_engine.py").read_bytes()
    admission_bytes = (ROOT / "scripts/z2/plasma_swd_site_admission.py").read_bytes()
    if hashlib.sha256(admission_bytes).hexdigest() != CI_ADMISSION_SHA256:
        raise RuntimeError("CI_ADMISSION_SHA_MISMATCH")
    if b"DEVMEM_INDEPENDENT_IMAGES" in admission_bytes:
        raise RuntimeError("LEGACY_ADMISSION_SOURCE_DENIED")
    if len(engine_bytes) > 80000 or len(admission_bytes) > 100000:
        raise RuntimeError("SOURCE_SIZE_DENIED")
    if helper is None:
        helper = ssh
    creds, known = helper.z2_login_credentials(Path.home())
    if creds.get("ssh_host") != host:
        raise RuntimeError("ENROLLED_HOST_MISMATCH")
    command = [
        "/opt/plasma/python/3.12.13/bin/python3", "-I", "-B", "-c", REMOTE,
        mode,
        base64.b64encode(zlib.compress(engine_bytes, level=9)).decode(),
        hashlib.sha256(engine_bytes).hexdigest(),
        base64.b64encode(zlib.compress(admission_bytes, level=9)).decode(),
    ]
    rc, stdout = helper.password_ssh_z2(command, creds, known, timeout=300)
    found = re.findall(r"(?m)^PLASMA_SITE2_ENGINE_MAINT=(\{[^\r\n]{1,8000}\})\s*$", stdout)
    if len(found) != 1:
        raise RuntimeError("MAINTENANCE_RECEIPT_UNKNOWN")
    observed = json.loads(found[0])
    if (type(observed) is not dict or observed.get("schema") != "plasma.site2.engine-maint.v1"
            or observed.get("mode") != mode
            or observed.get("openocd_build") != "NOT_RUN"
            or observed.get("bundle_deploy") != "NOT_RUN"
            or observed.get("fpga_reload") != "NOT_RUN"
            or observed.get("flash") != "NOT_RUN"):
        raise RuntimeError("MAINTENANCE_RECEIPT_INVALID")
    return {"schema": "plasma.site2.path2-engine-maint.v1",
            "source_sha": source_sha, "phase": mode,
            "exit_code": rc, "observation": observed,
            "flash": "NOT_RUN", "fpga_reload": "NOT_RUN",
            "openocd_build": "NOT_RUN", "bundle_deploy": "NOT_RUN"}

def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host",required=True)
    parser.add_argument("--source-sha",required=True)
    parser.add_argument("--mode",choices=("prepare","switch"),required=True)
    args=parser.parse_args(argv)
    try:
        receipt=run(args.host,args.source_sha,args.mode)
        status=receipt["observation"].get("status")
        ok=receipt["exit_code"]==0 and status==(
            "PREPARED_NOT_SELECTED" if args.mode=="prepare" else "SELECTED")
        code=0 if ok else 1
    except Exception as exc:
        allowed={"SOURCE_SHA_MISMATCH","MODE_DENIED","HOST_SCOPE_DENIED",
                 "ENGINE_MAINT_PREFLIGHT_BLOCKED","CI_ADMISSION_SHA_MISMATCH",
                 "LEGACY_ADMISSION_SOURCE_DENIED","SOURCE_SIZE_DENIED",
                 "ENROLLED_HOST_MISMATCH","MAINTENANCE_RECEIPT_UNKNOWN",
                 "MAINTENANCE_RECEIPT_INVALID"}
        reason=str(exc) if isinstance(exc,RuntimeError) and str(exc) in allowed else type(exc).__name__
        receipt={"schema":"plasma.site2.path2-engine-maint.v1",
                 "phase":args.mode,"status":"BLOCKED_OR_UNKNOWN","reason":reason,
                 "flash":"NOT_RUN","fpga_reload":"NOT_RUN",
                 "bundle_deploy":"NOT_RUN","openocd_build":"NOT_RUN"}
        code=69
    print(MARK+json.dumps(receipt,sort_keys=True,separators=(",",":")))
    return code
if __name__=="__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read-only Z2 protected FPGA Root source identity audit via existing paired SSH.

Compares two fixed privileged Python source modules and their protected code
manifest against this source-pinned PR. Uses a separate native Python process
only to inspect module import identity; it never mutates Z2, starts/stops
services, admits a Site, invokes FPGA/MMIO or flashes DUT.
"""
from __future__ import annotations

import argparse
import hashlib
import ipaddress
import json
import re
import subprocess
from pathlib import Path

import plasma_wordport_program as paired

ROOT = Path(__file__).resolve().parents[1]
SHA40 = re.compile(r"[0-9a-f]{40}\Z")
SHA64 = re.compile(r"[0-9a-f]{64}\Z")
SCHEMA = "plasma.site2.root-module-audit.v1"
MARK = "PLASMA_SITE2_ROOT_MODULES="
FILES = (
    "pl/hil/fpga_image_root.py",
    "pl/hil/fpga_image_admission.py",
)

REMOTE = r'''
import hashlib,json,stat,subprocess
from pathlib import Path
root=Path("/opt/plasma/privileged/fpga-root")
files=("pl/hil/fpga_image_root.py","pl/hil/fpga_image_admission.py")
def bounded(root_path, max_size):
    p=Path(root_path)
    st=p.lstat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or
        st.st_mode&0o022 or st.st_size<1 or st.st_size>max_size):
        raise ValueError("SOURCE_UNTRUSTED")
    return p.read_bytes()
result={"schema":"plasma.site2.root-module-audit.v1",
        "observation":"BLOCKED","modules":{},
        "manifest":"UNVERIFIED","manifest_sha256":None}
try:
    manifest_raw=bounded(root/".plasma-privileged-code.json",16384)
    manifest=json.loads(manifest_raw)
    assert (type(manifest) is dict and
            manifest.get("schema")=="plasma.ppu.privileged-code.v1" and
            type(manifest.get("files")) is dict)
    result["manifest_sha256"]=hashlib.sha256(manifest_raw).hexdigest()
    result["manifest_mtime_ns"]=(root/".plasma-privileged-code.json").stat().st_mtime_ns
    result["manifest"]="PARSED"
    for name in files:
        raw=bounded(root/name,524288)
        digest=hashlib.sha256(raw).hexdigest()
        expected=manifest["files"].get(name)
        result["modules"][name]={
            "sha256":digest,
            "source_mtime_ns":(root/name).stat().st_mtime_ns,
            "manifest_sha256":expected if isinstance(expected,str) else None,
            "manifest_match":isinstance(expected,str) and digest==expected,
            "references_devmem_independent_images":b"DEVMEM_INDEPENDENT_IMAGES" in raw,
        }
    # Independently inspect the selected Engine's fixed admission entrypoint.
    # This entry is not part of the FPGA privileged-source file manifest.
    result["engine_entry"]={"status":"UNVERIFIED"}
    try:
        selection_raw=bounded("/etc/plasma/site-worker-engine.json",8192)
        selection=json.loads(selection_raw)
        engine_root=Path(selection["openocd_root"])
        if (selection.get("schema")!="plasma.ppu.site-worker-engine.v1"
            or engine_root.parent != Path(
                "/opt/plasma/programming-engines/openocd")
            or not engine_root.name.isascii()
            or not engine_root.name.replace("-","").replace("_","").isalnum()):
            raise ValueError("ENGINE_SELECTION_INVALID")
        entry=engine_root/"libexec/plasma_swd_site_admission.py"
        raw=bounded(entry,524288)
        digest=hashlib.sha256(raw).hexdigest()
        result["engine_entry"]={
            "status":"OBSERVED",
            "source_sha256":digest,
            "selected_sha256_matches":digest==selection.get("admission_sha256"),
            "references_removed_symbol":
                b"DEVMEM_INDEPENDENT_IMAGES" in raw,
            "source_mtime_ns":entry.stat().st_mtime_ns,
        }
    except Exception as exc:
        result["engine_entry"]={"status":"BLOCKED",
                                "error_type":type(exc).__name__}
    # Run a new isolated, native 3.12.13 process like the protected admission
    # entrypoint, but ONLY import pure Python modules and inspect code objects.
    # Do not invoke any Root functions, access FPGA/MMIO, create state or flash.
    native_code = """
import json,sys,types
from pathlib import Path
source=Path('/opt/plasma/privileged/fpga-root')
sys.path.insert(0,str(source))
from pl.hil import fpga_image_root as root, fpga_image_admission as admission
def any_symbol(code,symbol):
    return symbol in code.co_names or any(
        any_symbol(c,symbol) for c in code.co_consts
        if isinstance(c,types.CodeType))
def module_symbol(module,symbol):
    return any(any_symbol(value.__code__,symbol)
               for value in vars(module).values()
               if isinstance(value,types.FunctionType)
               and value.__module__==module.__name__)
out={
    'status':'OBSERVED',
    'root_loaded_from_protected_source':
      Path(root.__file__).resolve()==source/'pl/hil/fpga_image_root.py',
    'admission_loaded_from_protected_source':
      Path(admission.__file__).resolve()==source/'pl/hil/fpga_image_admission.py',
    'root_live_bytecode_uses_removed_symbol':
      module_symbol(root,'DEVMEM_INDEPENDENT_IMAGES'),
    'admission_has_removed_symbol':
      hasattr(admission,'DEVMEM_INDEPENDENT_IMAGES'),
    'root_cached_bytecode_exists':
      bool(root.__cached__ and Path(root.__cached__).exists()),
    'admission_cached_bytecode_exists':
      bool(admission.__cached__ and Path(admission.__cached__).exists()),
}
print(json.dumps(out,sort_keys=True,separators=(',',':')))
"""
    native_probe={"status":"BLOCKED"}
    try:
        worker=subprocess.run(
            ["/bin/systemctl","show","--property=MainPID","--value",
             "plasma-site-worker.service"],
            capture_output=True,text=True,timeout=6)
        pid=worker.stdout.strip()
        if worker.returncode!=0 or not pid.isdigit() or int(pid)<2:
            raise ValueError("NATIVE_WORKER_PID_UNAVAILABLE")
        native=(Path("/proc")/pid/"exe").resolve(strict=True)
        info=native.lstat()
        if (not native.is_relative_to("/opt/plasma/python/3.12.13")
            or not stat.S_ISREG(info.st_mode) or info.st_uid!=0
            or info.st_mode&0o022):
            raise ValueError("NATIVE_WORKER_EXECUTABLE_UNTRUSTED")
        probe=subprocess.run([str(native),"-I","-B","-c",native_code],
            capture_output=True,text=True,timeout=20)
        if probe.returncode:
            raise ValueError("NATIVE_IMPORT_INSPECTION_FAILED")
        native_probe=json.loads(probe.stdout)
        if (type(native_probe) is not dict or
            set(native_probe)!={
            "status","root_loaded_from_protected_source",
            "admission_loaded_from_protected_source",
            "root_live_bytecode_uses_removed_symbol",
            "admission_has_removed_symbol",
            "root_cached_bytecode_exists",
            "admission_cached_bytecode_exists"} or
            native_probe["status"]!="OBSERVED" or
            any(type(v) is not bool for k,v in native_probe.items()
                if k!="status")):
            raise ValueError("NATIVE_IMPORT_OBSERVATION_INVALID")
    except Exception as exc:
        native_probe={"status":"BLOCKED","error_type":type(exc).__name__}
    result["native_import"]=native_probe
    result["observation"]="OBSERVED"
except Exception as exc:
    # No source bytes or free-form device exception text leave the device.
    result["error_type"]=type(exc).__name__
print("PLASMA_SITE2_ROOT_MODULES="+json.dumps(result,sort_keys=True,separators=(",",":")))
'''


def run(source_sha: str, *, helper=paired) -> dict:
    if not SHA40.fullmatch(source_sha):
        raise ValueError("SOURCE_SHA_INVALID")
    current = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=ROOT,
        capture_output=True, text=True, check=True, timeout=8,
    ).stdout.strip()
    if current != source_sha:
        raise ValueError("SOURCE_SHA_MISMATCH")
    credentials, hosts = helper.z2_login_credentials(Path.home())
    address = ipaddress.ip_address(credentials.get("ssh_host"))
    if address.version != 4 or not address.is_private:
        raise ValueError("PAIRED_TARGET_INVALID")
    rc, output = helper.password_ssh_z2(
        ["python3", "-I", "-c", REMOTE], credentials, hosts, timeout=75,
    )
    if rc != 0:
        raise RuntimeError("READONLY_SSH_FAILED")
    found = re.findall(
        r"(?m)^PLASMA_SITE2_ROOT_MODULES=(\{[^\r\n]{1,4096}\})\s*$", output
    )
    if len(found) != 1:
        raise RuntimeError("OBSERVATION_RECEIPT_INVALID")
    observed = json.loads(found[0])
    if (type(observed) is not dict or observed.get("schema") != SCHEMA
            or observed.get("observation") != "OBSERVED"
            or observed.get("manifest") != "PARSED"
            or type(observed.get("modules")) is not dict
            or set(observed["modules"]) != set(FILES)):
        raise RuntimeError("ROOT_AUDIT_INCOMPLETE")
    result = {}
    for name in FILES:
        item = observed["modules"][name]
        if (type(item) is not dict
                or not isinstance(item.get("sha256"), str)
                or not SHA64.fullmatch(item["sha256"])
                or not isinstance(item.get("manifest_sha256"), str)
                or not SHA64.fullmatch(item["manifest_sha256"])
                or type(item.get("manifest_match")) is not bool
                or type(item.get("references_devmem_independent_images")) is not bool):
            raise RuntimeError("ROOT_MODULE_RECEIPT_INVALID")
        local_path = ROOT / name
        source_sha256 = hashlib.sha256(local_path.read_bytes()).hexdigest()
        result[name] = {
            "z2_sha256": item["sha256"],
            "git_sha256": source_sha256,
            "matches_git": item["sha256"] == source_sha256,
            "source_mtime_ns": item.get("source_mtime_ns"),
            "matches_installed_manifest": item["manifest_match"],
            "references_devmem_independent_images": item[
                "references_devmem_independent_images"
            ],
        }
    return {
        "schema": SCHEMA,
        "result": "OBSERVED",
        "source_sha": source_sha,
        "installed_manifest_sha256": observed["manifest_sha256"],
        "installed_manifest_mtime_ns": observed.get("manifest_mtime_ns"),
        "engine_entry": observed.get("engine_entry", {"status": "NOT_RUN"}),
        "modules": result,
        "native_import": observed.get("native_import", {"status": "NOT_RUN"}),
        "hardware": "NOT_RUN",
        "flash": "NOT_RUN",
        "deployment": "NOT_RUN",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-sha", required=True)
    args = parser.parse_args()
    try:
        output = run(args.source_sha)
        exit_code = 0
    except Exception as exc:
        output = {
            "schema": SCHEMA, "result": "BLOCKED",
            "error": str(exc) if isinstance(exc, (RuntimeError, ValueError))
            and str(exc) in {
                "SOURCE_SHA_INVALID", "SOURCE_SHA_MISMATCH",
                "PAIRED_TARGET_INVALID", "READONLY_SSH_FAILED",
                "OBSERVATION_RECEIPT_INVALID", "ROOT_AUDIT_INCOMPLETE",
                "ROOT_MODULE_RECEIPT_INVALID",
            } else type(exc).__name__,
            "hardware": "NOT_RUN", "flash": "NOT_RUN",
            "deployment": "NOT_RUN",
        }
        exit_code = 69
    print("PLASMA_SITE2_ROOT_MODULE_AUDIT=" + json.dumps(output, sort_keys=True))
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())

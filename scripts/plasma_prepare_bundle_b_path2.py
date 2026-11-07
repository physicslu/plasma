#!/usr/bin/env python3
"""Prepare exact historical Blue Pill v0.2 Bundle locally on SWPC (no DUT).

Reads the original 62,800-byte firmware once over the existing pinned Z2
SSH credential, verifies exact historical SHA, then REUSES the canonical
Bundle v3 builder already merged on main. No new Bundle format or installer.
"""
from __future__ import annotations
import argparse
import base64
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SHA=re.compile(r"[0-9a-f]{40}\Z")
EXPECTED_FW="e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c"
EXPECTED_BUNDLE="387b9c8c08822a6d4edb8ac7904a71a6e3143b1714453a35778c372a7517764c"
DEVICE="ppu-device-7ed4b30913a9bf6101da5a7a"
REMOTE=r'''
import base64,hashlib,pathlib,stat
p=pathlib.Path("/home/xilinx/plasma-bluepill-ab-20261028/plasma-blue-pill-cdc-v0.2.bin")
st=p.lstat()
if not stat.S_ISREG(st.st_mode) or st.st_size!=62800 or st.st_mode&0o002:
    raise SystemExit(69)
b=p.read_bytes()
if hashlib.sha256(b).hexdigest()!="e691ab23b835bfe0b4ec5e2ae6f8ddb913d84be502c4065e985c5ad2ba72682c":
    raise SystemExit(69)
print("PLASMA_VERIFIED_BLUEPILL_V02="+base64.b64encode(b).decode("ascii"))
'''
def module(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    if spec is None or spec.loader is None:raise RuntimeError("REVIEWED_HELPER_UNAVAILABLE")
    obj=importlib.util.module_from_spec(spec);sys.modules[spec.name]=obj
    spec.loader.exec_module(obj);return obj
def main()->int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    p.add_argument("--output",type=Path,required=True)
    a=p.parse_args()
    out={"schema":"plasma.bundle-v02-swpc-prep.v1","status":"NOT_RUN",
         "mutation_z2":"NOT_RUN","dut":"NOT_RUN"}
    try:
        cur=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                           capture_output=True,text=True,timeout=5,check=True).stdout.strip()
        if not SHA.fullmatch(a.source_sha) or cur!=a.source_sha:
            raise RuntimeError("SOURCE_SHA_MISMATCH")
        if a.host!="192.168.2.99" or ipaddress.ip_address(a.host).version!=4:
            raise RuntimeError("HOST_DENIED")
        if not a.output.is_absolute() or a.output.parent!=Path("/tmp") or a.output.is_symlink():
            raise RuntimeError("OUTPUT_DIRECTORY_DENIED")
        if a.output.exists():
            b=a.output.read_bytes()
            if hashlib.sha256(b).hexdigest()!=EXPECTED_BUNDLE:
                raise RuntimeError("EXISTING_OUTPUT_DIGEST_MISMATCH")
            out.update(status="PASS",bundle_sha256=EXPECTED_BUNDLE,result="ALREADY_PRESENT")
            print("PLASMA_BLUEPILL_BUNDLE_B="+json.dumps(out,sort_keys=True))
            return 0
        baseline=module("scripts/ppu_path2_hardware_baseline.py","bundle_b_identity")
        if baseline.probe_status(a.host).get("device_id_observed")!=DEVICE:
            raise RuntimeError("DEVICE_ID_MISMATCH")
        helper=module("scripts/plasma_wordport_program.py","bundle_b_ssh")
        creds,hosts=helper.z2_login_credentials(Path.home())
        if creds.get("ssh_host")!=a.host:raise RuntimeError("ENROLLED_HOST_MISMATCH")
        rc,txt=helper.password_ssh_z2(["python3","-I","-B","-c",REMOTE],
                                      creds,hosts,timeout=100)
        if rc!=0:raise RuntimeError("SOURCE_FIRMWARE_READ_DENIED")
        matches=re.findall(r"(?m)^PLASMA_VERIFIED_BLUEPILL_V02=([A-Za-z0-9+/=]{80000,100000})\s*$",txt)
        if len(matches)!=1:raise RuntimeError("REMOTE_FIRMWARE_RECEIPT_MISSING")
        fw=base64.b64decode(matches[0],validate=True)
        if len(fw)!=62800 or hashlib.sha256(fw).hexdigest()!=EXPECTED_FW:
            raise RuntimeError("FIRMWARE_SIZE_OR_DIGEST_MISMATCH")
        builder=module("scripts/bluepill_bundle_v3_firmware_build.py","bundle_b_canonical")
        fd,name=tempfile.mkstemp(prefix="plasma-b-v02-source-",suffix=".bin")
        temp=Path(name)
        try:
            with os.fdopen(fd,"wb") as file:
                file.write(fw)
                file.flush();os.fsync(file.fileno())
            built=builder.build("v0.2",temp,a.output)
        finally:temp.unlink(missing_ok=True)
        if built.get("archive_sha256")!=EXPECTED_BUNDLE:
            raise RuntimeError("CANONICAL_BUNDLE_SHA_MISMATCH")
        out.update(status="PASS",firmware_sha256=EXPECTED_FW,
                   bundle_sha256=EXPECTED_BUNDLE,firmware_size=62800,
                   output=str(a.output),result="HOST_ONLY_VERIFIED")
        print("PLASMA_BLUEPILL_BUNDLE_B="+json.dumps(out,sort_keys=True))
        return 0
    except Exception as exc:
        allow={"SOURCE_SHA_MISMATCH","HOST_DENIED","OUTPUT_DIRECTORY_DENIED",
               "EXISTING_OUTPUT_DIGEST_MISMATCH","DEVICE_ID_MISMATCH",
               "ENROLLED_HOST_MISMATCH","SOURCE_FIRMWARE_READ_DENIED",
               "REMOTE_FIRMWARE_RECEIPT_MISSING","FIRMWARE_SIZE_OR_DIGEST_MISMATCH",
               "CANONICAL_BUNDLE_SHA_MISMATCH"}
        why=str(exc) if isinstance(exc,RuntimeError) and str(exc) in allow else type(exc).__name__
        out.update(status="BLOCKED",reason=why)
        print("PLASMA_BLUEPILL_BUNDLE_B="+json.dumps(out,sort_keys=True))
        return 69
if __name__=="__main__":raise SystemExit(main())

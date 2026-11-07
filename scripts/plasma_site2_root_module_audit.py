#!/usr/bin/env python3
"""Read-only Z2 protected FPGA Root source identity audit via existing paired SSH.

Compares two fixed privileged Python source modules and their protected code
manifest against this source-pinned PR. Never imports device modules, mutates
Z2, starts/stops services, admits a Site, invokes FPGA/MMIO or flashes DUT.
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
import hashlib,json,stat
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
    result["manifest"]="PARSED"
    for name in files:
        raw=bounded(root/name,524288)
        digest=hashlib.sha256(raw).hexdigest()
        expected=manifest["files"].get(name)
        result["modules"][name]={
            "sha256":digest,
            "manifest_sha256":expected if isinstance(expected,str) else None,
            "manifest_match":isinstance(expected,str) and digest==expected,
            "references_devmem_independent_images":b"DEVMEM_INDEPENDENT_IMAGES" in raw,
        }
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
        "modules": result,
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

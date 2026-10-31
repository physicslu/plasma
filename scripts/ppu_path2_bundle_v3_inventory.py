#!/usr/bin/env python3
"""Read-only installed Bootstrap verifier capability inventory on enrolled Z2."""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REMOTE = r'''
import json, os, pathlib, subprocess
# Fixed read-only service unit lookup. Do not read env files, credentials or logs.
p = subprocess.run(["systemctl", "show", "plasma-ppu-bootstrap.service",
                    "--property=ExecStart,FragmentPath,ActiveState", "--no-pager"],
                   capture_output=True, text=True, timeout=8)
unit = {}
for line in p.stdout.splitlines():
    k, _, v = line.partition("=")
    if k == "ActiveState": unit["active"] = v if v in ("active","inactive","failed") else "unknown"
    if k == "FragmentPath": unit["unit_present"] = v.startswith("/")
    if k == "ExecStart":
        unit["entrypoint_is_python"] = "python" in v
        # Never print ExecStart: may contain secret argv.
paths = [
    "/usr/local/lib/plasma/ppu-bootstrap-deployment.py",
    "/opt/plasma/scripts/ppu-bootstrap-deployment.py",
    "/usr/local/bin/ppu-bootstrap-deployment.py",
    "/opt/plasma/ppu-bootstrap-deployment.py",
]
found = []
for name in paths:
    try:
        f = pathlib.Path(name)
        if not f.is_file() or f.is_symlink() or f.stat().st_size > 512000: continue
        data = f.read_bytes()
        found.append({"path_class":"candidate", "bundle_v3_literal": b"plasma.ppu.bundle.v3" in data,
                      "bundle_kind_literal": b'"bundle"' in data, "bytes":len(data)})
    except (OSError, UnicodeError):
        pass
print("PLASMA_Z2_BOOTSTRAP_INVENTORY_JSON="+json.dumps(
    {"service":unit,"candidate_files":found,"verifier":"NOT_ATTESTED" if not found else "SOURCE_LITERAL_ONLY"},
    sort_keys=True))
'''
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args()
    out={"schema":"plasma.ppu.z2-verifier-inventory.v1","status":"NOT_RUN","b2":"NOT_QUALIFIED"}
    try:
        actual=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True,timeout=5).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40}",a.source_sha) or actual!=a.source_sha:
            raise RuntimeError("SOURCE_SHA_MISMATCH")
        spec=importlib.util.spec_from_file_location("ppu_v3_inventory_common",ROOT/"scripts/ppu_path2_hardware_baseline.py")
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        module._private_ipv4(a.host)
        helper_spec=importlib.util.spec_from_file_location("ppu_v3_inventory_ssh",ROOT/"scripts/plasma_wordport_program.py")
        helper=importlib.util.module_from_spec(helper_spec)
        sys.modules[helper_spec.name]=helper
        helper_spec.loader.exec_module(helper)
        credentials,known_hosts=helper.z2_login_credentials(Path.home())
        if credentials.get("ssh_host")!=a.host: raise RuntimeError("SSH_HOST_PIN_MISMATCH")
        rc,raw=helper.password_ssh_z2(["python3","-I","-c",REMOTE],credentials,known_hosts,timeout=45)
        if rc!=0: raise RuntimeError("REMOTE_INVENTORY_UNAVAILABLE")
        matches=re.findall(r"PLASMA_Z2_BOOTSTRAP_INVENTORY_JSON=(\{[^\n]+\})",raw)
        if len(matches)!=1: raise RuntimeError("REMOTE_INVENTORY_UNAVAILABLE")
        inventory=json.loads(matches[0])
        out.update({"status":"READ_ONLY_COMPLETE","inventory":inventory})
        code=0
    except Exception as e:
        out.update({"status":"BLOCKED","error_type":type(e).__name__})
        code=2
    print("PLASMA_PPU_V3_INVENTORY_JSON="+json.dumps(out,sort_keys=True))
    return code
if __name__=="__main__":
    raise SystemExit(main())

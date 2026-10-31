#!/usr/bin/env python3
"""Read-only fixed TCP 18081 listener identity inventory on enrolled Z2.

Only /proc/net/tcp{,6}, /proc/<pid>/fd, cmdline and exe symlink.
No env, secrets, files, arbitrary commands, installs or service changes.
"""
from __future__ import annotations
import argparse
import importlib.util
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REMOTE=r'''
import json, os, pathlib, re
port=18081
inode_set=set()
for file in ("/proc/net/tcp","/proc/net/tcp6"):
    try:
        lines=pathlib.Path(file).read_text().splitlines()[1:]
    except OSError: continue
    for line in lines:
        fields=line.split()
        if len(fields)<10: continue
        try:
            local_port=int(fields[1].rsplit(":",1)[1],16)
        except (ValueError,IndexError): continue
        if local_port==port and fields[3]=="0A":
            inode_set.add(fields[9])
found=[]
for path in pathlib.Path("/proc").iterdir():
    if not path.name.isdigit(): continue
    try:
        fd=path/"fd"
        matches=any(os.readlink(entry) in {"socket:["+i+"]" for i in inode_set} for entry in fd.iterdir())
        if not matches: continue
        cmd=(path/"cmdline").read_bytes().split(b"\0")
        exe=os.readlink(path/"exe")
        # Only return structural metadata; never raw cmdline or argv.
        found.append({"pid":int(path.name),
                      "exe_basename":pathlib.Path(exe).name[:80],
                      "argv_count":len([x for x in cmd if x]),
                      "python": "python" in pathlib.Path(exe).name.lower(),
                      "cwd_available":(path/"cwd").exists()})
    except (OSError,PermissionError): continue
print("PLASMA_Z2_PORT18081_JSON="+json.dumps(
    {"port":port,"listener_count":len(inode_set),"processes":found,
     "process_attribution":"READ_ONLY_NO_SOURCE_ATTESTATION"},sort_keys=True))
'''
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args()
    out={"schema":"plasma.ppu.z2-listener-inventory.v1","status":"NOT_RUN","b2":"NOT_QUALIFIED"}
    try:
        actual=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True,timeout=5).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40}",a.source_sha) or actual!=a.source_sha:
            raise RuntimeError("SOURCE_SHA_MISMATCH")
        spec=importlib.util.spec_from_file_location("ppu_listener_common",ROOT/"scripts/ppu_path2_hardware_baseline.py")
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        module._private_ipv4(a.host)
        hs=importlib.util.spec_from_file_location("ppu_listener_ssh",ROOT/"scripts/plasma_wordport_program.py")
        helper=importlib.util.module_from_spec(hs)
        sys.modules[hs.name]=helper
        hs.loader.exec_module(helper)
        credentials,known_hosts=helper.z2_login_credentials(Path.home())
        if credentials.get("ssh_host")!=a.host: raise RuntimeError("SSH_HOST_PIN_MISMATCH")
        rc,raw=helper.password_ssh_z2(["python3","-I","-c",REMOTE],credentials,known_hosts,timeout=45)
        if rc!=0: raise RuntimeError("REMOTE_INVENTORY_UNAVAILABLE")
        matches=re.findall(r"PLASMA_Z2_PORT18081_JSON=(\{[^\n]+\})",raw)
        if len(matches)!=1: raise RuntimeError("REMOTE_INVENTORY_UNAVAILABLE")
        out.update({"status":"READ_ONLY_COMPLETE","listener":json.loads(matches[0])})
        code=0
    except Exception as exc:
        out.update({"status":"BLOCKED","error_type":type(exc).__name__})
        code=2
    print("PLASMA_PPU_Z2_LISTENER_JSON="+json.dumps(out,sort_keys=True))
    return code
if __name__=="__main__":
    raise SystemExit(main())

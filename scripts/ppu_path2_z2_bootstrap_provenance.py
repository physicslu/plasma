#!/usr/bin/env python3
"""Read-only, PID-pinned provenance for the real Z2 Bootstrap listener.

Only /proc/net/tcp socket ownership and /proc/<pid>/{cmdline,cwd,exe}, then
read at most one validated Python entrypoint source. Never output argv,
environment, tokens, source text, arbitrary paths or logs.
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
import hashlib,json,os,pathlib
pid=32533
p=pathlib.Path("/proc")/str(pid)
out={"pid_pinned":pid,"port":18081,"listener_owned":False,"entrypoint":"NOT_ATTESTED",
     "source_sha256":"NOT_ATTESTED","bundle_v3_literal":False}
try:
    sock=set()
    for name in ("/proc/net/tcp","/proc/net/tcp6"):
        try: lines=pathlib.Path(name).read_text().splitlines()[1:]
        except OSError: continue
        for line in lines:
            f=line.split()
            if len(f)>=10 and f[3]=="0A" and int(f[1].rsplit(":",1)[1],16)==18081:
                sock.add("socket:["+f[9]+"]")
    out["listener_owned"]=any(os.readlink(fd) in sock for fd in (p/"fd").iterdir())
    if not out["listener_owned"]: raise RuntimeError("PID_NOT_LISTENER")
    argv=[v.decode("utf-8","replace") for v in (p/"cmdline").read_bytes().split(b"\0") if v]
    # Never emit raw argv; only inspect fixed argv positions for a source path.
    candidates=[]
    for i,value in enumerate(argv[1:],start=1):
        if value in ("-m","-c"): break
        if value.endswith(".py") and not value.startswith("-"):
            candidates.append(value)
    cwd=os.readlink(p/"cwd")
    for value in candidates[:2]:
        path=pathlib.Path(value)
        if not path.is_absolute(): path=pathlib.Path(cwd)/path
        path=path.resolve(strict=True)
        if not (path.is_file() and path.suffix==".py" and path.stat().st_size<=512000): continue
        data=path.read_bytes()
        out.update({"entrypoint":"PYTHON_SOURCE_ATTESTED","source_sha256":hashlib.sha256(data).hexdigest(),
                    "source_size":len(data),"bundle_v3_literal":b"plasma.ppu.bundle.v3" in data,
                    "bundle_v2_literal":b"plasma.ppu.bundle.v2" in data,
                    "source_basename":path.name[:80]})
        break
except Exception as exc:
    out["diagnostic_error"]=type(exc).__name__
print("PLASMA_Z2_BOOTSTRAP_PROVENANCE_JSON="+json.dumps(out,sort_keys=True))
'''
def main():
    p=argparse.ArgumentParser()
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    a=p.parse_args()
    out={"schema":"plasma.ppu.z2-bootstrap-provenance.v1","status":"NOT_RUN","b2":"NOT_QUALIFIED"}
    try:
        actual=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,text=True,capture_output=True,check=True,timeout=5).stdout.strip()
        if not re.fullmatch(r"[0-9a-f]{40}",a.source_sha) or actual!=a.source_sha:
            raise RuntimeError("SOURCE_SHA_MISMATCH")
        spec=importlib.util.spec_from_file_location("ppu_provenance_common",ROOT/"scripts/ppu_path2_hardware_baseline.py")
        module=importlib.util.module_from_spec(spec)
        sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        module._private_ipv4(a.host)
        hs=importlib.util.spec_from_file_location("ppu_provenance_ssh",ROOT/"scripts/plasma_wordport_program.py")
        helper=importlib.util.module_from_spec(hs)
        sys.modules[hs.name]=helper
        hs.loader.exec_module(helper)
        credentials,known_hosts=helper.z2_login_credentials(Path.home())
        if credentials.get("ssh_host")!=a.host: raise RuntimeError("SSH_HOST_PIN_MISMATCH")
        rc,raw=helper.password_ssh_z2(["python3","-I","-c",REMOTE],credentials,known_hosts,timeout=45)
        if rc!=0: raise RuntimeError("REMOTE_PROVENANCE_UNAVAILABLE")
        matches=re.findall(r"PLASMA_Z2_BOOTSTRAP_PROVENANCE_JSON=(\{[^\n]+\})",raw)
        if len(matches)!=1: raise RuntimeError("REMOTE_PROVENANCE_UNAVAILABLE")
        out.update({"status":"READ_ONLY_COMPLETE","provenance":json.loads(matches[0])})
        code=0
    except Exception as exc:
        out.update({"status":"BLOCKED","error_type":type(exc).__name__})
        code=2
    print("PLASMA_PPU_Z2_PROVENANCE_JSON="+json.dumps(out,sort_keys=True))
    return code
if __name__=="__main__":
    raise SystemExit(main())

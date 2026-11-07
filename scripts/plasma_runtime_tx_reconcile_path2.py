#!/usr/bin/env python3
"""Bounded read-only Z2 Runtime transaction journal reconciliation (Path 2).

Temporary engineering probe for one known transaction. Prints ONLY allowlisted
journal fields; never reads a token, changes a file, calls an installer,
restarts a service or touches FPGA/SWD/DUT.
"""
from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
SHA = re.compile(r"[0-9a-f]{40}\Z")
TX = re.compile(r"[0-9a-f]{32}\Z")
DEVICE = re.compile(r"ppu-device-[a-f0-9]{16,64}\Z")
PREFIX = "PLASMA_RUNTIME_TX_RECONCILE="

REMOTE = r'''
import json,os,pathlib,re,stat
API=pathlib.Path("/var/lib/plasma-bootstrap/deployment-api.json")
COORD=pathlib.Path("/var/lib/plasma-bootstrap/deployment.json")
CURRENT=pathlib.Path("/opt/plasma/current")
def field(value,limit=128):
    return value if type(value) is str and len(value)<=limit and re.fullmatch(r"[A-Za-z0-9._-]+",value) else "UNKNOWN"
def read_file(path):
    try:
        st=path.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=0 or (st.st_mode&0o077) or st.st_size>1048576:
            return None,"FILE_NOT_PRIVATE_REGULAR"
        with path.open("rb") as fp:
            raw=fp.read(1048577)
        if len(raw)>1048576:return None,"FILE_TOO_LARGE"
        obj=json.loads(raw)
        if type(obj) is not dict:return None,"JSON_NOT_OBJECT"
        return obj,"OK"
    except FileNotFoundError:return None,"MISSING"
    except (OSError,TypeError,ValueError,UnicodeError):return None,"READ_ERROR"
def reason(value):
    if type(value) is not str:return "NO_ERROR_STRING"
    for token in ("FileNotFoundError","ModuleNotFoundError","PermissionError",
                  "libgpiod","memory","No space left","health","rollback",
                  "deployment Coordinator receipt is missing",
                  "deployment API and Coordinator result are not reconciled",
                  "API_HTTP_REJECTED","TimeoutExpired","ImportError","OSError"):
        if token.lower() in value.lower():return token.replace(" ","_")
    return "OTHER_OR_NONE"
def libgpiod_detail(value):
    if type(value) is not str:return "NO_DETAIL"
    match=re.search(r"(?i).{0,50}libgpiod.{0,135}",value)
    if match is None:return "NOT_RECORDED"
    # Only the bounded dependency error fragment, never raw private journals.
    return "".join(ch if ch.isascii() and (ch.isalnum() or ch in " .:_/-=(),") else " " for ch in match.group(0))[:185]
def soname_loadable():
    try:
        import ctypes
        ctypes.CDLL("libgpiod.so.2")
        return True
    except OSError:return False
def bounded_error_excerpt(value):
    if type(value) is not str:return {"length":0,"start":"NOT_AVAILABLE","end":"NOT_AVAILABLE"}
    def sanitize(chunk):
        # Strip secrets/opaque IDs; keep only legible low-entropy diagnostics.
        chunk=re.sub(r"[A-Za-z0-9_/-]{35,}","[REDACTED]",chunk)
        chunk=re.sub(r"(?i)(Bearer|token|password|Authorization)[^\r\n]{0,100}","[REDACTED]",chunk)
        return "".join(c if c.isascii() and (c.isalnum() or c in " .,;:()[]_/-=+!?\n") else " " for c in chunk)
    return {"length":len(value),
            "start":sanitize(value[:500]),"end":sanitize(value[-300:])}
api,a=read_file(API);coord,c=read_file(COORD)
out={"schema":"plasma.runtime-tx-readonly.v1","api_file":a,"coordinator_file":c,
     "api":{},"coordinator":{},"active_release":"UNVERIFIED","mutations":"NOT_RUN"}
if api is not None:
    out["api"]={k:field(api.get(k),128) for k in ("state","transaction_id","error_code")}
    out["api"]["error_class"]=reason(api.get("error"))
    out["api"]["dependency_detail"]=libgpiod_detail(api.get("error"))
    out["api"]["libgpiod_so2_loadable"]=soname_loadable()
    out["api"]["error_excerpt"]=bounded_error_excerpt(api.get("error"))
    out["api"]["result_present"]=api.get("result") is not None
if coord is not None:
    out["coordinator"]={k:field(coord.get(k),128) for k in
                        ("state","kind","transaction_id","api_transaction_id",
                         "release_id","error_code","previous_release")}
    out["coordinator"]["error_class"]=reason(coord.get("error_message"))
    out["coordinator"]["dependency_detail"]=libgpiod_detail(coord.get("error_message"))
    out["coordinator"]["result_present"]=coord.get("result") is not None
try:
    if CURRENT.is_symlink():
        resolved=CURRENT.resolve(strict=True)
        if resolved.parent == pathlib.Path("/opt/plasma/releases"):
            out["active_release"]=field(resolved.name)
except OSError:pass
# Bounded, read-only journal excerpt for THIS activation failure: no raw logs.
def gateway_errors(unit):
    import subprocess
    try:
        p=subprocess.run(["journalctl","-u",unit,"-n","400","--no-pager",
                          "--output=cat"],capture_output=True,text=True,
                         timeout=12,check=False)
        if p.returncode!=0:return ["JOURNAL_UNAVAILABLE"]
        lines=p.stdout.splitlines()[-400:]
        keys=("Traceback","Error","Exception","ModuleNotFound",
              "ImportError","Permission denied","Address already in use",
              "Failed","failed","Connection refused","No module named",
              "No such file","not found","AttributeError","TypeError")
        selected=[line for line in lines if any(key.lower() in line.lower() for key in keys)]
        def scrub(line):
            line=re.sub(r"(?i)(Bearer|token|password|Authorization)[^\\r\\n]{0,100}","[REDACTED]",line)
            line=re.sub(r"[A-Za-z0-9_/-]{40,}","[REDACTED]",line)
            return "".join(c if c.isascii() and (c.isalnum() or c in " .,;:()[]_/-=+!?") else " " for c in line)[:250]
        return [scrub(line) for line in selected[-30:]]
    except (OSError,subprocess.TimeoutExpired):return ["JOURNAL_TIMEOUT"]
out["gateway_service_errors"]={
    "plasma-web.service":gateway_errors("plasma-web.service"),
    "plasma-server.service":gateway_errors("plasma-server.service"),
}
print("PLASMA_RUNTIME_TX_RECONCILE="+json.dumps(out,sort_keys=True,separators=(",",":")))
'''

def load(path: str, name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / path)
    if spec is None or spec.loader is None:
        raise RuntimeError("REVIEWED_HELPER_UNAVAILABLE")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod

def run(host: str, expected_device: str, tx: str, source_sha: str) -> dict:
    actual = subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                            capture_output=True,text=True,timeout=5,check=True).stdout.strip()
    if not SHA.fullmatch(source_sha) or actual != source_sha:
        raise RuntimeError("SOURCE_SHA_MISMATCH")
    if host != "192.168.2.99" or ipaddress.ip_address(host).version != 4:
        raise RuntimeError("Z2_HOST_DENIED")
    if not DEVICE.fullmatch(expected_device) or not TX.fullmatch(tx):
        raise RuntimeError("TARGET_IDENTITY_INVALID")
    baseline = load("scripts/ppu_path2_hardware_baseline.py", "tx_reconcile_bootstrap")
    observed = baseline.probe_status(host)
    if observed.get("device_id_observed") != expected_device:
        raise RuntimeError("DEVICE_ID_MISMATCH")
    helper = load("scripts/plasma_wordport_program.py", "tx_reconcile_ssh")
    creds,hosts = helper.z2_login_credentials(Path.home())
    if creds.get("ssh_host") != host:
        raise RuntimeError("ENROLLED_HOST_MISMATCH")
    rc,output = helper.password_ssh_z2(["python3","-I","-B","-c",REMOTE],
                                      creds,hosts,timeout=90)
    if rc != 0:
        raise RuntimeError("PINNED_READONLY_SSH_DENIED")
    rows = re.findall(r"(?m)^PLASMA_RUNTIME_TX_RECONCILE=(\{[^\r\n]{1,8192}\})\s*$",output)
    if len(rows) != 1:
        raise RuntimeError("REMOTE_RECEIPT_INVALID")
    record = json.loads(rows[0])
    if record.get("schema") != "plasma.runtime-tx-readonly.v1":
        raise RuntimeError("REMOTE_SCHEMA_DENIED")
    if record.get("api",{}).get("transaction_id") != tx:
        raise RuntimeError("TRANSACTION_ID_MISMATCH")
    return record

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host",required=True)
    parser.add_argument("--device-id",required=True)
    parser.add_argument("--transaction-id",required=True)
    parser.add_argument("--source-sha",required=True)
    args = parser.parse_args()
    try:
        output=run(args.host,args.device_id,args.transaction_id,args.source_sha)
        code=0
    except Exception as exc:
        allowed={"SOURCE_SHA_MISMATCH","Z2_HOST_DENIED","TARGET_IDENTITY_INVALID",
                 "DEVICE_ID_MISMATCH","ENROLLED_HOST_MISMATCH","PINNED_READONLY_SSH_DENIED",
                 "REMOTE_RECEIPT_INVALID","REMOTE_SCHEMA_DENIED","TRANSACTION_ID_MISMATCH",
                 "REVIEWED_HELPER_UNAVAILABLE"}
        reason=str(exc) if isinstance(exc,RuntimeError) and str(exc) in allowed else type(exc).__name__
        output={"schema":"plasma.runtime-tx-readonly.v1","status":"BLOCKED",
                "reason":reason,"mutations":"NOT_RUN"}
        code=69
    print(PREFIX+json.dumps(output,sort_keys=True,separators=(",",":")))
    return code

if __name__=="__main__":
    raise SystemExit(main())

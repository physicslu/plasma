#!/usr/bin/env python3
"""Read-only Site 2 REST Job failure + live Site Worker Python identity snapshot."""
from __future__ import annotations
import argparse
import http.client
import importlib.util
import ipaddress
import json
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote
ROOT=Path(__file__).resolve().parents[1]
SHA40=re.compile(r"[0-9a-f]{40}\Z")
JOB=re.compile(r"job-[0-9]{8}-[0-9]{6}-[a-f0-9]{8}\Z")
MARK="PLASMA_SITE2_WORKER_INTERPRETER="
REMOTE=r'''
import json,pathlib,re,subprocess
out={"schema":"plasma.site2.worker-python-observation.v1",
     "state":"UNAVAILABLE","worker_python":"UNVERIFIED",
     "worker_native_python":False,"worker_pid":0}
try:
    r=subprocess.run(["/bin/systemctl","show","--property=MainPID","--value",
        "plasma-site-worker.service"],capture_output=True,text=True,timeout=6)
    pid=r.stdout.strip()
    if r.returncode!=0 or not pid.isdigit() or int(pid)<2:
        raise ValueError("NO_ACTIVE_WORKER_PID")
    path=(pathlib.Path("/proc")/pid/"exe").resolve(strict=True)
    name=str(path)
    if len(name)>180 or re.fullmatch(r"[A-Za-z0-9/_.+-]{1,180}",name) is None:
        raise ValueError("EXECUTABLE_PATH_UNTRUSTED")
    out.update({"state":"OBSERVED","worker_python":name,"worker_pid":int(pid),
                "worker_native_python":name.startswith("/opt/plasma/python/3.12.13/")})
except (OSError,ValueError,subprocess.SubprocessError):
    pass
print("PLASMA_SITE2_WORKER_INTERPRETER="+json.dumps(out,sort_keys=True,separators=(",",":")))
'''
def load(path,name):
    spec=importlib.util.spec_from_file_location(name,ROOT/path)
    if spec is None or spec.loader is None:raise RuntimeError("REVIEWED_HELPER_MISSING")
    mod=importlib.util.module_from_spec(spec)
    sys.modules[spec.name]=mod
    spec.loader.exec_module(mod)
    return mod
def safe_text(value):
    if type(value) is not str:return "NOT_RECORDED"
    value=value[:150]
    if re.fullmatch(r"[A-Za-z0-9_.:/ +-]{1,150}",value):
        return value
    return "REDACTED"
def run(host,sha,job_id,*,helper=None,preflight=None):
    cur=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,
                       capture_output=True,text=True,check=True,timeout=6).stdout.strip()
    if not SHA40.fullmatch(sha) or sha!=cur:raise RuntimeError("SOURCE_SHA_MISMATCH")
    ip=ipaddress.ip_address(host)
    if ip.version!=4 or not ip.is_private:raise RuntimeError("HOST_SCOPE_DENIED")
    if not JOB.fullmatch(job_id):raise RuntimeError("JOB_ID_DENIED")
    conn=http.client.HTTPConnection(host,18080,timeout=9)
    try:
        conn.request("GET","/api/status?job="+quote(job_id,safe=""))
        resp=conn.getresponse()
        raw=resp.read(65537)
        if resp.status!=200 or len(raw)>65536:raise RuntimeError("GATEWAY_JOB_GET_FAILED")
        payload=json.loads(raw)
    finally:
        conn.close()
    if type(payload)!=dict or type(payload.get("job"))!=dict:
        raise RuntimeError("JOB_RESPONSE_INVALID")
    job=payload["job"]
    if job.get("job_id")!=job_id:raise RuntimeError("JOB_ID_MISMATCH")
    result=job.get("result") if type(job.get("result")) is dict else {}
    error=job.get("error") if type(job.get("error")) is dict else {}
    reason=job.get("reason") if type(job.get("reason")) is dict else {}
    job_result={
        "job_id":job_id,
        "state":safe_text(job.get("state")),
        "operation":safe_text(job.get("operation")),
        "error_code":safe_text(error.get("error_code",error.get("code",job.get("error_code")))),
        "error_type":safe_text(error.get("error_type",error.get("type",job.get("error_type")))),
        "failure_source":safe_text(error.get("failure_source",job.get("failure_source"))),
        "result_code":safe_text(result.get("code",result.get("error_code"))),
        "reason_code":safe_text(reason.get("code")),
        "job_keys":sorted(k for k in job if type(k) is str and len(k)<=64),
        "result_keys":sorted(k for k in result if type(k) is str and len(k)<=64),
    }
    if preflight is None:preflight=load("scripts/plasma_site2_path2_preflight.py","plasma_job_provenance")
    site=preflight.run(host,sha)
    if helper is None:helper=load("scripts/plasma_wordport_program.py","plasma_job_enrolled_ssh")
    creds,hosts=helper.z2_login_credentials(Path.home())
    if creds.get("ssh_host")!=host:raise RuntimeError("ENROLLED_HOST_MISMATCH")
    rc,txt=helper.password_ssh_z2(["python3","-I","-c",REMOTE],creds,hosts,timeout=55)
    if rc!=0:raise RuntimeError("WORKER_PYTHON_SSH_FAILED")
    hits=re.findall(r"(?m)^PLASMA_SITE2_WORKER_INTERPRETER=(\{[^\r\n]{1,1024}\})\s*$",txt)
    if len(hits)!=1:raise RuntimeError("WORKER_PYTHON_RECEIPT_INVALID")
    worker=json.loads(hits[0])
    if type(worker)!=dict or worker.get("schema")!="plasma.site2.worker-python-observation.v1":
        raise RuntimeError("WORKER_PYTHON_RECEIPT_INVALID")
    return {"schema":"plasma.site2.job-failure-snapshot.v1",
            "source_sha":sha,"job":job_result,"worker":worker,
            "runtime_release":site["z2"]["release"],
            "site2_sealed":site["z2"]["site2_seal"].get("present"),
            "admission_record_present":site["z2"]["site2_admission"].get("present"),
            "openocd_pids":site["z2"]["openocd_pids"],
            "site2_rest":site["rest"],
            "flash":"NOT_RUN","fpga_reload":"NOT_RUN","recovery":"NOT_RUN"}
def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host",required=True)
    p.add_argument("--source-sha",required=True)
    p.add_argument("--job-id",required=True)
    a=p.parse_args(argv)
    try:ret=run(a.host,a.source_sha,a.job_id);rc=0
    except Exception as exc:
        allow={"SOURCE_SHA_MISMATCH","HOST_SCOPE_DENIED","JOB_ID_DENIED",
               "GATEWAY_JOB_GET_FAILED","JOB_RESPONSE_INVALID","JOB_ID_MISMATCH",
               "ENROLLED_HOST_MISMATCH","WORKER_PYTHON_SSH_FAILED",
               "WORKER_PYTHON_RECEIPT_INVALID"}
        reason=str(exc) if isinstance(exc,RuntimeError) and str(exc) in allow else type(exc).__name__
        ret={"schema":"plasma.site2.job-failure-snapshot.v1",
             "status":"BLOCKED","reason":reason,"flash":"NOT_RUN"};rc=69
    print("PLASMA_SITE2_JOB_FAILURE="+json.dumps(ret,sort_keys=True,separators=(",",":")))
    return rc
if __name__=="__main__":raise SystemExit(main())

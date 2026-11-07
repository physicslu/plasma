#!/usr/bin/env python3
"""Read-only enrolled Z2 Site 2 pre-Flash Active OPF identity checkpoint.

No Bundle receive/install, Engine selection, service restart, FPGA/DUT operation
or POST. Observe only Root/Gateway Site readiness and the existing Active asset
set through the trusted installed PPU read_active verifier.
"""
from __future__ import annotations

import argparse
import ipaddress
import json
import re
import subprocess
from pathlib import Path

import opf_site2_joint_acceptance as opf
import plasma_site2_path2_preflight as site
import plasma_wordport_program as pairing

ROOT=Path(__file__).resolve().parents[1]
SHA40=re.compile(r"[0-9a-f]{40}\\Z")
BIN="b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
ADM="3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"

def run(source_sha: str, *, helper=pairing, preflight=site, active=opf) -> dict:
    sha=subprocess.run(["git","rev-parse","HEAD"],cwd=ROOT,check=True,
                       text=True,capture_output=True,timeout=8).stdout.strip()
    if not SHA40.fullmatch(source_sha) or sha!=source_sha:
        raise RuntimeError("SOURCE_SHA_MISMATCH")
    credentials,_known=helper.z2_login_credentials(Path.home())
    host=credentials.get("ssh_host")
    try:
        addr=ipaddress.ip_address(host)
    except (ValueError,TypeError) as exc:
        raise RuntimeError("PAIRED_HOST_INVALID") from exc
    if addr.version!=4 or not addr.is_private:
        raise RuntimeError("PAIRED_HOST_INVALID")
    snapshot=preflight.run(host,source_sha,helper=helper)
    e=snapshot.get("z2",{}).get("engine",{})
    r=snapshot.get("rest",{})
    if (snapshot.get("readiness")!="NO_KNOWN_BLOCKER_IN_OBSERVED_FIELDS"
        or snapshot.get("blockers")!=[]
        or e.get("status")!="VERIFIED" or e.get("abi")!=5
        or e.get("driver")!="plasma_swd"
        or e.get("openocd_sha256_observed")!=BIN
        or e.get("admission_sha256_observed")!=ADM
        or r.get("active_job_count")!=0 or r.get("activation_active") is not False
        or r.get("lease_busy") is not False or r.get("site2_idle") is not True):
        raise RuntimeError("SITE2_PREFLIGHT_NOT_READY")
    current=active.observe_active(host,helper=helper)
    if current.get("state")!="ACTIVE" or current.get("opf_static")!="PASS":
        raise RuntimeError("ACTIVE_OPF_NOT_VERIFIED")
    asset_sha=current.get("asset_set_sha256")
    if not isinstance(asset_sha,str) or not re.fullmatch(r"[0-9a-f]{64}",asset_sha):
        raise RuntimeError("ACTIVE_ASSET_SHA_INVALID")
    return {"schema":"plasma.site2.active-readonly.v1",
            "source_sha":source_sha,"readiness":"PASS",
            "asset_set_sha256":asset_sha,"opf_static":"PASS",
            "engine_binary_sha256":BIN,"engine_admission_sha256":ADM,
            "active_job_count":0,"site2_idle":True,
            "flash":"NOT_RUN","bundle_deploy":"NOT_RUN",
            "fpga_reload":"NOT_RUN","engine_switch":"NOT_RUN"}

def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--source-sha",required=True)
    args=p.parse_args()
    try:
        result=run(args.source_sha)
        rc=0
    except Exception as exc:
        rc=69
        reason=(str(exc) if isinstance(exc,RuntimeError) and
                str(exc) in {"SOURCE_SHA_MISMATCH","PAIRED_HOST_INVALID",
                "SITE2_PREFLIGHT_NOT_READY","ACTIVE_OPF_NOT_VERIFIED",
                "ACTIVE_ASSET_SHA_INVALID"} else type(exc).__name__)
        result={"schema":"plasma.site2.active-readonly.v1",
                "readiness":"BLOCKED","reason":reason,
                "flash":"NOT_RUN","bundle_deploy":"NOT_RUN",
                "fpga_reload":"NOT_RUN","engine_switch":"NOT_RUN"}
    print("PLASMA_SITE2_ACTIVE_READONLY="+json.dumps(result,sort_keys=True,separators=(",",":")))
    return rc

if __name__=="__main__":
    raise SystemExit(main())

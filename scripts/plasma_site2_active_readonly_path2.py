#!/usr/bin/env python3
"""Read-only enrolled Z2 Site 2 pre-Flash Active OPF identity checkpoint.

No Bundle receive/install, Engine selection, service restart, FPGA/DUT operation
or POST. Observe only Root/Gateway Site readiness and the existing Active asset
set through the trusted installed PPU read_active verifier.
"""
from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import re
import subprocess
from pathlib import Path

import plasma_site2_path2_preflight as site
import plasma_wordport_program as pairing

MARKER = "PLASMA_OPF_STATIC_READONLY:"

# Only installed, protected Z2 files are inspected, never Bundle executable code.
# ppu_asset_set.read_active independently verifies B3 receipt and every file.
REMOTE_OBSERVE = """
import base64,json,sys
from pathlib import Path
root=Path('/opt/plasma')
sys.path.insert(0,str(root/'bootstrap'))
from ppu_asset_set import read_active
record=read_active(root)
sha=record.get('asset_set_sha256')
status={'state':record.get('state'),'asset_set_sha256':sha,
        'generation':record.get('generation'),'opf_static':'NOT_APPLICABLE'}
if record.get('state')=='ACTIVE':
    manifest=json.loads((root/'assets/staged'/sha/'manifest.json').read_bytes())
    pkgs={p['id']:p for p in manifest['packages']}
    provider=pkgs.get('openocd-platform-reference')
    profile=pkgs.get('stm32f103c8t6-site2')
    if provider and profile:
        provider_path='payload/packages/openocd-platform-reference/data/plasma-provider-options.json'
        profile_paths={
          'payload/packages/stm32f103c8t6-site2/data/plasma-provider.json',
          'payload/packages/stm32f103c8t6-site2/data/plasma-flash-profile.json'}
        paths={e['path'] for e in provider['files']}
        profile_entries={e['path'] for e in profile['files']}
        valid=(provider['kind']=='platform-provider'
          and profile['kind']=='programming-profile'
          and profile['requires']==['openocd-platform-reference']
          and paths=={provider_path} and profile_entries==profile_paths
          and all(e.get('executable') is False for e in provider['files']+profile['files']))
        if valid:
            descriptor=json.loads((root/'assets/staged'/sha/
              'payload/packages/stm32f103c8t6-site2/data/plasma-provider.json').read_bytes())
            valid=(descriptor.get('schema')=='plasma.ppu.provider-capabilities.v1'
              and descriptor.get('provider_package')=='openocd-platform-reference'
              and descriptor.get('target')=='STM32F103C8T6')
        status['opf_static']='PASS' if valid else 'FAIL'
print('PLASMA_OPF_STATIC_READONLY:'+base64.b64encode(
  json.dumps(status,sort_keys=True,separators=(',',':')).encode()).decode())
"""


class ActiveObservationDenied(RuntimeError):
    """Fixed, non-secret diagnostic code."""


def observe_active(host: str, *, helper) -> dict:
    credentials, hosts = helper.z2_login_credentials(Path.home())
    if credentials.get("ssh_host") != host:
        raise ActiveObservationDenied("PAIRED_TARGET_MISMATCH")
    rc, transcript = helper.password_ssh_z2(
        ["python3", "-I", "-c", REMOTE_OBSERVE], credentials, hosts, timeout=60)
    if rc != 0:
        raise ActiveObservationDenied("ACTIVE_SET_READ_ONLY_OBSERVATION_FAILED")
    matches = re.findall(re.escape(MARKER) + r"([A-Za-z0-9+/=]{40,8192})", transcript)
    if len(matches) != 1:
        raise ActiveObservationDenied("ACTIVE_SET_RECEIPT_INVALID")
    try:
        result = json.loads(base64.b64decode(matches[0], validate=True))
        if (type(result) is not dict
                or result.get("state") not in ("ACTIVE", "EMPTY")
                or result.get("opf_static") not in ("PASS", "FAIL", "NOT_APPLICABLE")
                or (result["state"] == "ACTIVE"
                    and not (type(result.get("asset_set_sha256")) is str
                             and HEX64.fullmatch(result["asset_set_sha256"])))):
            raise ValueError("invalid")
    except (ValueError, UnicodeError) as exc:
        raise ActiveObservationDenied("ACTIVE_SET_RECEIPT_INVALID") from exc
    return result


ROOT=Path(__file__).resolve().parents[1]
SHA40=re.compile(r"[0-9a-f]{40}")
BIN="b8a7db6706493401c48f0fa08b46a3a167633a7aa314bf0ca209fd7c7ce0f861"
ADM="3f5d5feca0582c91f1432496a6cf4b02112f52461bd0adc2a07c14242ded965b"

def run(source_sha: str, *, helper=pairing, preflight=site,
        active_observer=observe_active) -> dict:
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
    current=active_observer(host,helper=helper)
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

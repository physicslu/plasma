#!/usr/bin/env python3
"""Path 2 Site 2 joint acceptance: Doctor -> reconcile -> B1/B2/B3 -> Doctor.

Uses the existing read-only plasma_z2 Doctor and the existing reviewed OPF
Bootstrap deployment adapter. No direct installer, shell, service restart,
FPGA load, Engine switch, or DUT operation. No retry after ambiguous writes.
"""
from __future__ import annotations

import argparse
import base64
import json
import re
import sys
from argparse import Namespace
from pathlib import Path

import plasma_z2
import opf_site2_path2_bundle_deploy as deployer

ROOT = Path(__file__).resolve().parents[1]
OLD = deployer.OLD_SHA
HEX64 = re.compile(r"[0-9a-f]{64}\Z")
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


class JointDenied(RuntimeError):
    """Fixed, non-secret diagnostic code."""


def observe_active(host: str, *, helper) -> dict:
    credentials, hosts = helper.z2_login_credentials(Path.home())
    if credentials.get("ssh_host") != host:
        raise JointDenied("PAIRED_TARGET_MISMATCH")
    rc, transcript = helper.password_ssh_z2(
        ["python3", "-I", "-c", REMOTE_OBSERVE], credentials, hosts, timeout=60)
    if rc != 0:
        raise JointDenied("ACTIVE_SET_READ_ONLY_OBSERVATION_FAILED")
    matches = re.findall(re.escape(MARKER) + r"([A-Za-z0-9+/=]{40,8192})", transcript)
    if len(matches) != 1:
        raise JointDenied("ACTIVE_SET_RECEIPT_INVALID")
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
        raise JointDenied("ACTIVE_SET_RECEIPT_INVALID") from exc
    return result


def doctor_snapshot() -> tuple[dict, str]:
    host = plasma_z2.paired_host()
    # Resolve the authenticated local target exactly once. Doctor uses that
    # same host instead of reading mutable paired config a second time.
    args = Namespace(repo=ROOT, host=host, paired_host=False,
                     ssh_user=None, known_hosts=Path.home() /
                     ".config/plasma/z2-login-known_hosts")
    document = plasma_z2.doctor(args)
    indexed = {row["check"]: row for row in document["checks"]}
    expected = ("tcp_18080", "tcp_18081",
                "bootstrap_health", "bootstrap_status", "deployment_guard")
    if any(indexed.get(key, {}).get("status") != "PASS" for key in expected):
        raise JointDenied("DOCTOR_REMOTE_GATE_NOT_PASS")
    guard = indexed["deployment_guard"]
    caps = guard.get("capabilities")
    if (guard.get("bootstrap_state") != "bootstrap_ready"
            or guard.get("runtime_state") != "runtime_active"
            or not isinstance(caps, dict)
            or caps.get("bundle_v3_b3_install") is not True):
        raise JointDenied("BOOTSTRAP_B3_NOT_QUALIFIED")
    # Local Git/engineering warnings in a detached PR checkout are not
    # device facts; do not turn them into a hardware safety bypass.
    return document, host


def execute() -> dict:
    predoctor, host = doctor_snapshot()
    helper = deployer._load("plasma_wordport_program.py", "joint_site2_pinned_ssh")
    original = observe_active(host, helper=helper)

    if original["state"] == "ACTIVE" and original["opf_static"] == "PASS":
        # Even on the no-write path, honor the full pre/post observation.
        # The matching hash proves stable Active identity, NOT which actor
        # originally deployed that Bundle.
        postdoctor, host2 = doctor_snapshot()
        if host2 != host:
            raise JointDenied("PAIRED_TARGET_CHANGED_DURING_NOOP")
        final = observe_active(host, helper=helper)
        if (final.get("state") != "ACTIVE"
                or final.get("asset_set_sha256") != original["asset_set_sha256"]
                or final.get("opf_static") != "PASS"):
            raise JointDenied("NOOP_POST_ACTIVE_OPF_MISMATCH")
        return {"result": "PASS", "action": "ALREADY_ACTIVE_NO_REDEPLOY",
                "asset_set_sha256": original["asset_set_sha256"],
                "pre_doctor": predoctor["overall"],
                "post_doctor": postdoctor["overall"],
                "deployment_provenance": "NOT_VERIFIED",
                "opf_static": "PASS", "fpga_reload": "NOT_RUN",
                "dut": "NOT_RUN", "b3": "NOT_RUN_ALREADY_ACTIVE"}

    if original.get("asset_set_sha256") != OLD:
        raise JointDenied("ACTIVE_SET_NOT_EXPECTED_GEN7_DO_NOT_DEPLOY")

    result = deployer.run(host)
    if result.get("result") != "PASS" or result.get("fpga_reload") != "NOT_RUN":
        raise JointDenied("DEPLOY_RECEIPT_INVALID")
    # A one-shot deployment is never automatically repeated here.
    postdoctor, host2 = doctor_snapshot()
    if host2 != host:
        raise JointDenied("PAIRED_TARGET_CHANGED_AFTER_B3")
    final = observe_active(host, helper=helper)
    if (final.get("state") != "ACTIVE"
            or final.get("asset_set_sha256") != result["new_asset_set_sha256"]
            or final.get("opf_static") != "PASS"):
        raise JointDenied("B3_POST_ACTIVE_OPF_MISMATCH")
    return {
        "result": "PASS", "action": "B3_DEPLOYED_AND_VERIFIED",
        "new_asset_set_sha256": result["new_asset_set_sha256"],
        "previous_asset_set_sha256": OLD,
        "b2_transaction_id": result["b2_transaction_id"],
        "b3_transaction_id": result["b3_transaction_id"],
        "b3_state": result["b3_state"], "pre_doctor": predoctor["overall"],
        "post_doctor": postdoctor["overall"], "opf_static": final["opf_static"],
        "fpga_reload": "NOT_RUN", "dut": "NOT_RUN"
    }


def main() -> int:
    try:
        result = execute()
        code = 0
    except Exception as exc:
        name = str(exc) if isinstance(exc, JointDenied) else type(exc).__name__
        result = {"result": "FAIL_OR_NOT_RUN", "error_code": name,
                  "note": "Never retry a possibly submitted B1/B2/B3 without reconciling the device transaction"}
        code = 1
    print("PLASMA_SITE2_JOINT_ACCEPTANCE_JSON=" + json.dumps(result, sort_keys=True))
    return code


if __name__ == "__main__":
    raise SystemExit(main())

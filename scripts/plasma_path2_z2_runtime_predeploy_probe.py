#!/usr/bin/env python3
"""Bounded, strictly read-only Path 2 readiness check for a Z2 Runtime Kit.

Checks that the existing SWPC non-root runner can READ the exact GitHub Actions
artifact, and that installed Z2 Bootstrap/Stage C/runtime can accept an update.
Does NOT download, stage, install, restart, manipulate a device, or print secrets.
"""
from __future__ import annotations

import argparse
import importlib.util
import ipaddress
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
ARTIFACT_REPOSITORY = "physicslu/plasma"
EXPECTED_RUN = 41792402221
EXPECTED_ARTIFACT_ID = 13303674147
EXPECTED_ARTIFACT_NAME = "plasma-z2-ps-kit-0.2.1-7ef3509265bc"
EXPECTED_MERGE_COMMIT = "7ef3509265bc4773ca8629eec99727f94646ab7b"
EXPECTED_PARENT_HEAD = "d53953e517f27582c2071fc84795f21cc89de77c"
EXPECTED_KIT_SHA256 = "e83dbb429c795b43cbb5556c76b2d488ffe454257e6fdb5ef952c9a4316283f8"


class ProbeError(Exception):
    pass


def artifact_readability(*, runner=None, which=shutil.which) -> dict:
    tool = which("gh")
    if tool is None:
        return {"artifact_fetch_qualified": False, "reason": "GH_CLI_MISSING"}
    if runner is None:
        runner = subprocess.run
    args = [tool, "api", "--method", "GET",
            f"/repos/{ARTIFACT_REPOSITORY}/actions/runs/{EXPECTED_RUN}/artifacts"]
    try:
        result = runner(args, capture_output=True, text=True, timeout=25, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return {"artifact_fetch_qualified": False, "reason": "GH_API_UNAVAILABLE"}
    if result.returncode != 0:
        # Never print gh stderr: it can contain owner auth/config diagnostics.
        return {"artifact_fetch_qualified": False, "reason": "GH_ARTIFACT_ACCESS_DENIED"}
    try:
        payload = json.loads(result.stdout)
    except ValueError:
        return {"artifact_fetch_qualified": False, "reason": "GH_API_JSON_INVALID"}
    if not isinstance(payload, dict) or not isinstance(payload.get("artifacts"), list):
        return {"artifact_fetch_qualified": False, "reason": "GH_API_FORMAT_INVALID"}
    found = [
        z for z in payload["artifacts"]
        if isinstance(z, dict) and z.get("id") == EXPECTED_ARTIFACT_ID
        and z.get("name") == EXPECTED_ARTIFACT_NAME and z.get("expired") is False
        and z.get("workflow_run", {}).get("id", EXPECTED_RUN) == EXPECTED_RUN
    ]
    if len(found) != 1:
        return {"artifact_fetch_qualified": False, "reason": "PINNED_ARTIFACT_NOT_FOUND"}
    return {
        "artifact_fetch_qualified": True,
        "artifact_id": EXPECTED_ARTIFACT_ID, "artifact_name": EXPECTED_ARTIFACT_NAME,
        "source_merge_sha": EXPECTED_MERGE_COMMIT,
        "candidate_parent_sha": EXPECTED_PARENT_HEAD,
        "expected_kit_sha256": EXPECTED_KIT_SHA256,
    }


# The remote script reads only PUBLIC METADATA and returns a sanitized JSON.
# It does not examine PPU secrets, firmware or other operators' private files.
_REMOTE = r"""
import json,os,pathlib
base=pathlib.Path('/opt/plasma')
current=base/'current'
link=current.readlink().as_posix() if current.is_symlink() else None
unit=pathlib.Path('/etc/systemd/system/plasma-site-worker.service')
renderer=base/'bootstrap'/'ppu_package_units.py'
engine=pathlib.Path('/etc/plasma/site-worker-engine.json')
res={
 'bootstrap_stage_c_renderer_available':renderer.is_file() and not renderer.is_symlink(),
 'site_worker_unit_installed':unit.is_file() and not unit.is_symlink(),
 'current_release_symlink':link,
 'installed_openocd_engine_manifest':engine.is_file() and not engine.is_symlink(),
 'runtime_control_socket_present':pathlib.Path('/run/plasma-server/control.sock').is_socket(),
}
print('PLASMA_READONLY_Z2_STATE='+json.dumps(res,sort_keys=True,separators=(',',':')))
"""


def z2_readiness(host: str, *, helper=None, home=None) -> dict:
    try:
        ip = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ProbeError("Z2_HOST_INVALID") from exc
    if ip.version != 4 or not ip.is_private:
        raise ProbeError("Z2_HOST_NOT_PRIVATE")
    if helper is None:
        source = ROOT / "scripts/plasma_wordport_program.py"
        spec = importlib.util.spec_from_file_location("z2_pinned_owner_transport", source)
        if spec is None or spec.loader is None:
            raise ProbeError("SSH_HELPER_MISSING")
        helper = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = helper
        spec.loader.exec_module(helper)
    try:
        creds, hosts = helper.z2_login_credentials(home or Path.home())
        if creds.get("ssh_host") != host:
            raise ProbeError("ENROLLED_HOST_MISMATCH")
        rc, stdout = helper.password_ssh_z2(
            ["python3", "-I", "-c", _REMOTE], creds, hosts, timeout=45)
    except ProbeError:
        raise
    except Exception as exc:
        raise ProbeError("PINNED_SSH_READ_UNAVAILABLE") from exc
    if rc != 0:
        raise ProbeError("REMOTE_READ_REJECTED")
    marker = "PLASMA_READONLY_Z2_STATE="
    matches = [v.partition(marker)[2] for v in stdout.splitlines() if v.startswith(marker)]
    if len(matches) != 1:
        raise ProbeError("REMOTE_RECEIPT_INVALID")
    try:
        state = json.loads(matches[0])
    except ValueError as exc:
        raise ProbeError("REMOTE_RECEIPT_INVALID") from exc
    if (not isinstance(state, dict) or
            set(state) != {
                "bootstrap_stage_c_renderer_available",
                "site_worker_unit_installed",
                "current_release_symlink",
                "installed_openocd_engine_manifest",
                "runtime_control_socket_present",
            }):
        raise ProbeError("REMOTE_RECEIPT_FIELDS_INVALID")
    for field in ("bootstrap_stage_c_renderer_available", "site_worker_unit_installed",
                  "installed_openocd_engine_manifest", "runtime_control_socket_present"):
        if not isinstance(state[field], bool):
            raise ProbeError("REMOTE_BOOLEAN_INVALID")
    link = state["current_release_symlink"]
    if link is not None and (not isinstance(link, str) or
                             re.fullmatch(r"releases/[A-Za-z0-9._-]{1,90}", link) is None):
        # Report only that a link exists, not any unexpected filesystem path.
        state["current_release_symlink"] = "UNRECOGNIZED_SOURCE_PATH"
    return state


def run(host: str, *, artifact_probe=artifact_readability, z2_probe=z2_readiness) -> dict:
    artifact = artifact_probe()
    remote = z2_probe(host)
    qualified = (
        artifact.get("artifact_fetch_qualified") is True and
        remote["bootstrap_stage_c_renderer_available"] is True and
        remote["runtime_control_socket_present"] is True and
        remote["site_worker_unit_installed"] is True and
        remote["installed_openocd_engine_manifest"] is True and
        remote["current_release_symlink"] is not None and
        remote["current_release_symlink"] != "UNRECOGNIZED_SOURCE_PATH"
    )
    return {
        "result": "READ_ONLY_PREDEPLOY_READY" if qualified else "READ_ONLY_PREDEPLOY_BLOCKED",
        "artifact": artifact, "z2": remote,
        "source_sha": EXPECTED_MERGE_COMMIT,
        "no_transfer": True, "no_install": True,
        "no_service_restart": True, "no_dut_action": True,
        "physical_hil_verified": False,
    }


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--host", required=True)
    args = p.parse_args(argv)
    try:
        receipt = run(args.host)
        print(json.dumps(receipt, sort_keys=True))
        return 0 if receipt["result"] == "READ_ONLY_PREDEPLOY_READY" else 69
    except ProbeError as exc:
        print(json.dumps({"result": "READ_ONLY_PREDEPLOY_BLOCKED",
                          "reason": str(exc), "no_mutations": True}), file=sys.stderr)
        return 69


if __name__ == "__main__":
    raise SystemExit(main())

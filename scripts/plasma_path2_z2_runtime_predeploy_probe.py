#!/usr/bin/env python3
"""Bounded, strictly read-only Path 2 readiness check for a Z2 Runtime Kit.

Checks that the existing SWPC non-root runner can READ the exact GitHub Actions
artifact, and that installed Z2 Bootstrap/Stage C/runtime can accept an update.
Does NOT download, stage, install, restart, manipulate a device, or print secrets.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import ipaddress
import json
import os
from pathlib import Path
import re
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


def artifact_readability(*, directory: Path | None = None) -> dict:
    """Verify only bytes delivered by the trusted Workflow, never invoke gh.

    A PR candidate must not inherit the GitHub credential used by the trusted
    download step. A valid archive SHA is required in addition to the sidecar.
    """
    if directory is None:
        supplied = os.environ.get("PLASMA_Z2_KIT_ARTIFACT_DIR", "")
        if not supplied:
            return {"artifact_fetch_qualified": False,
                    "reason": "TRUSTED_ARTIFACT_NOT_DELIVERED"}
        directory = Path(supplied)
    if directory.is_symlink() or not directory.is_dir():
        return {"artifact_fetch_qualified": False,
                "reason": "TRUSTED_ARTIFACT_DIR_INVALID"}
    archive = directory / (EXPECTED_ARTIFACT_NAME + ".tar.gz")
    sidecar = directory / (archive.name + ".sha256")
    if (archive.is_symlink() or sidecar.is_symlink() or
            not archive.is_file() or not sidecar.is_file() or
            archive.stat().st_size > 1_000_000_000 or
            sidecar.stat().st_size > 256):
        return {"artifact_fetch_qualified": False,
                "reason": "PINNED_KIT_MISSING_OR_UNTRUSTED"}
    try:
        line = sidecar.read_text(encoding="ascii").strip()
    except (OSError, UnicodeError):
        return {"artifact_fetch_qualified": False,
                "reason": "KIT_SIDECAR_INVALID"}
    if line != f"{EXPECTED_KIT_SHA256}  {archive.name}":
        return {"artifact_fetch_qualified": False,
                "reason": "KIT_SIDECAR_MISMATCH"}
    digest = hashlib.sha256()
    try:
        with archive.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError:
        return {"artifact_fetch_qualified": False,
                "reason": "PINNED_KIT_UNREADABLE"}
    if digest.hexdigest() != EXPECTED_KIT_SHA256:
        return {"artifact_fetch_qualified": False,
                "reason": "PINNED_KIT_SHA256_MISMATCH"}
    return {
        "artifact_fetch_qualified": True,
        "artifact_id": EXPECTED_ARTIFACT_ID,
        "artifact_name": EXPECTED_ARTIFACT_NAME,
        "source_merge_sha": EXPECTED_MERGE_COMMIT,
        "candidate_parent_sha": EXPECTED_PARENT_HEAD,
        "expected_kit_sha256": EXPECTED_KIT_SHA256,
        "verification": "TRUSTED_DELIVERY_AND_SHA256",
    }

# The remote script reads only PUBLIC METADATA and returns a sanitized JSON.
# It does not examine PPU secrets, firmware or other operators' private files.
_REMOTE = r"""
import json,os,pathlib
base=pathlib.Path('/opt/plasma')
current=base/'current'
link=current.readlink().as_posix() if current.is_symlink() else None
try:
    target=current.resolve(strict=True) if current.is_symlink() else None
except (OSError, RuntimeError):
    target=None
valid_target=bool(target is not None and target.is_dir() and
                  target.parent==base/'releases')
unit=pathlib.Path('/etc/systemd/system/plasma-site-worker.service')
renderer=base/'bootstrap'/'ppu_package_units.py'
engine=pathlib.Path('/etc/plasma/site-worker-engine.json')
res={
 'bootstrap_stage_c_renderer_available':renderer.is_file() and not renderer.is_symlink(),
 'site_worker_unit_installed':unit.is_file() and not unit.is_symlink(),
 'current_release_symlink':link,
 'current_release_target_valid':valid_target,
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
                "current_release_target_valid",
                "installed_openocd_engine_manifest",
                "runtime_control_socket_present",
            }):
        raise ProbeError("REMOTE_RECEIPT_FIELDS_INVALID")
    for field in ("bootstrap_stage_c_renderer_available", "site_worker_unit_installed",
                  "installed_openocd_engine_manifest", "runtime_control_socket_present",
                  "current_release_target_valid"):
        if not isinstance(state[field], bool):
            raise ProbeError("REMOTE_BOOLEAN_INVALID")
    link = state["current_release_symlink"]
    if link is not None:
        # Installer creates an absolute /opt/plasma/releases/<id> link; older
        # valid images may use releases/<id>. Canonicalize both for receipts.
        match = (re.fullmatch(
            r"(?:/opt/plasma/)?releases/([A-Za-z0-9._-]{1,90})", link)
            if isinstance(link, str) else None)
        if match is None or match.group(1) in (".", ".."):
            state["current_release_symlink"] = "UNRECOGNIZED_SOURCE_PATH"
        else:
            state["current_release_symlink"] = "releases/" + match.group(1)
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
        remote["current_release_symlink"] != "UNRECOGNIZED_SOURCE_PATH" and
        remote["current_release_target_valid"] is True
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

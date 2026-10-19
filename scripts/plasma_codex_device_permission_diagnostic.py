#!/usr/bin/env python3
"""Observe SWPC-plasma-codex device-node metadata only, never open a device.

Replicates the exact short-circuit predicates/order of the failed software-only
preflight in GitHub Actions run 39190291831. Not an isolation certification.
"""
from __future__ import annotations

import argparse
import glob
import json
import os
from pathlib import Path
import pwd
import grp
import stat
import subprocess
import sys

TARGET_RUN = 39190291831
PATTERNS = (
    "/dev/mem", "/dev/uio*", "/dev/ttyUSB*", "/dev/ttyACM*",
    "/dev/hidraw*", "/dev/gpiochip*", "/dev/bus/usb/*/*",
)
DENIED_GROUPS = frozenset((
    "sudo", "docker", "adm", "dialout", "gpio", "i2c", "video", "plasma-hil",
))
MAX_NODES = 128
MAX_ACL_BYTES = 8192


def path_candidates(patterns=PATTERNS):
    """Match Bash for-loop expansion: pattern order and sorted glob matches."""
    for pattern in patterns:
        if glob.has_magic(pattern):
            for path in sorted(glob.glob(pattern)):
                if os.path.exists(path):
                    yield path
        elif os.path.exists(pattern):
            yield pattern


def safe_name(mapping, identifier):
    try:
        return mapping(identifier).pw_name if mapping is pwd.getpwuid else mapping(identifier).gr_name
    except KeyError:
        return str(identifier)


def metadata(path, access=os.access):
    """os.stat and os.access only: do not open, read, write or ioctl the node."""
    info = os.stat(path)
    try:
        readable = bool(access(path, os.R_OK, effective_ids=True))
        writable = bool(access(path, os.W_OK, effective_ids=True))
    except TypeError:
        # Failure is preferable to silently using the wrong credential model.
        raise RuntimeError("EFFECTIVE_ACCESS_UNAVAILABLE")
    mode = info.st_mode
    kind = ("char_device" if stat.S_ISCHR(mode) else
            "block_device" if stat.S_ISBLK(mode) else
            "symlink_target_other")
    return {
        "path": path,
        "kind": kind,
        "mode": f"{stat.S_IMODE(mode):04o}",
        "uid": info.st_uid,
        "gid": info.st_gid,
        "user": safe_name(pwd.getpwuid, info.st_uid),
        "group": safe_name(grp.getgrgid, info.st_gid),
        "readable": readable,
        "writable": writable,
        "triggers_original_no_go": bool(readable or writable),
    }


def acl_metadata(path):
    """Optional POSIX ACL text only; bounded and without device-file access."""
    try:
        done = subprocess.run(
            ["getfacl", "-cp", "--", path], stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL, timeout=3, check=False,
            env={"PATH": "/usr/bin:/bin", "LC_ALL": "C"},
        )
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return {"status": "NOT_CHECKED"}
    if done.returncode or len(done.stdout) > MAX_ACL_BYTES:
        return {"status": "NOT_CHECKED"}
    lines = done.stdout.decode("utf-8", errors="replace").splitlines()
    # ACL only: no paths, no optional comments or arbitrary udev environment.
    allowed = ("user:", "group:", "mask:", "other:")
    return {"status": "OBSERVED", "entries": [
        line for line in lines if line.startswith(allowed)
    ][:40]}


def collect(paths=None, *, acl=acl_metadata):
    username = pwd.getpwuid(os.geteuid()).pw_name
    group_ids = sorted(set(os.getgroups()) | {os.getegid()})
    group_names = sorted(safe_name(grp.getgrgid, gid) for gid in group_ids)
    result = {
        "schema": "plasma-codex-device-metadata-v1",
        "original_run": TARGET_RUN,
        "hostname": os.uname().nodename,
        "username": username,
        "euid": os.geteuid(),
        "groups": group_names,
        "denied_groups_present": sorted(DENIED_GROUPS.intersection(group_names)),
        "check_type": "METADATA_ONLY_NO_DEVICE_OPEN",
        "original_predicate": "test -e path && (test -r path || test -w path)",
        "patterns": list(PATTERNS),
        "nodes": [],
        "first_trigger": None,
        "status": "NO_GO_UNDETERMINED",
        "notes": [
            "No device files were opened. stat/access/getfacl inspect metadata only.",
            "Readability alone triggered the old NO_GO; it does not prove an ioctl or hardware operation is possible.",
            "ACL may be unavailable. Effective udev rule, device sandbox and network isolation are not proven.",
            "This inspection reflects time of diagnostic, not historical device state during original run.",
        ],
    }
    candidates = list(paths if paths is not None else path_candidates())
    if len(candidates) > MAX_NODES:
        result["status"] = "NO_GO_TOO_MANY_NODES"
        result["candidate_count"] = len(candidates)
        return result
    for path in candidates:
        try:
            node = metadata(path)
            if node["triggers_original_no_go"]:
                node["acl"] = acl(path)
            result["nodes"].append(node)
            if result["first_trigger"] is None and node["triggers_original_no_go"]:
                result["first_trigger"] = path
        except (OSError, RuntimeError) as error:
            # Metadata may race with udev. Never silently assume isolation.
            result["status"] = "NO_GO_METADATA_ERROR"
            result["metadata_error_type"] = type(error).__name__
            return result
    if result["first_trigger"] is not None:
        result["status"] = "NO_GO_REPRODUCED"
    else:
        result["status"] = "NO_GO_NOT_REPRODUCED"
    return result


def enforce_github_identity():
    env = os.environ
    if not (
        env.get("GITHUB_EVENT_NAME") == "workflow_dispatch"
        and env.get("GITHUB_REPOSITORY") == "physicslu/plasma"
        and env.get("GITHUB_ACTOR") == "physicslu"
        and env.get("GITHUB_REF") == "refs/heads/main"
        and env.get("GITHUB_RUN_ATTEMPT") == "1"
        and env.get("RUNNER_ENVIRONMENT") == "self-hosted"
        and env.get("RUNNER_NAME") == "SWPC-plasma-codex"
        and os.uname().nodename == "SWPC"
        and pwd.getpwuid(os.geteuid()).pw_name == "plasma-codex"
        and os.geteuid() != 0
        and env.get("INPUT_ORIGINAL_RUN") == str(TARGET_RUN)
        and env.get("INPUT_CONFIRM_READ_ONLY") == "true"
    ):
        raise RuntimeError("TRUSTED_READONLY_SWPC_IDENTITY_REQUIRED")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        enforce_github_identity()
        if args.output.is_symlink() or args.output.exists():
            raise RuntimeError("OUTPUT_MUST_NOT_EXIST")
        # Do not write into repo, /dev, /sys, /proc or any arbitrary input.
        root = os.environ.get("RUNNER_TEMP", "")
        if not root or args.output.resolve().parent != Path(root).resolve():
            raise RuntimeError("OUTPUT_MUST_BE_RUNNER_TEMP")
        result = collect()
        args.output.write_text(json.dumps(result, sort_keys=True, indent=2) + "\n")
        print(json.dumps({
            "status": result["status"], "original_run": TARGET_RUN,
            "first_trigger": result["first_trigger"],
            "triggered_count": sum(n["triggers_original_no_go"] for n in result["nodes"]),
            "output_in_runner_temp": True,
            "hardware_operated": False, "codex_executed": False,
        }, sort_keys=True))
        return 0 if result["status"] in ("NO_GO_REPRODUCED", "NO_GO_NOT_REPRODUCED") else 2
    except (OSError, RuntimeError, ValueError) as exc:
        print(json.dumps({"status":"NO_GO_DIAGNOSTIC_FAILED",
                          "reason":str(exc),"codex_executed":False}, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())

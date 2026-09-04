from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from typing import Any


ARM_IMAGE = "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c"


def _run(command: list[str]) -> str:
    completed = subprocess.run(
        command,
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return completed.stdout.strip()


def _require_tool(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        raise RuntimeError(f"required tool is unavailable: {name}")
    return path


def _filesystem_type(path: Path) -> str:
    return _run(["stat", "-f", "-c", "%T", str(path)])


def _os_release() -> dict[str, str]:
    try:
        release = platform.freedesktop_os_release()
    except OSError as exc:
        raise RuntimeError("unable to read Linux OS release metadata") from exc
    keys = ("NAME", "VERSION", "ID", "VERSION_ID")
    return {key: release[key] for key in keys if key in release}


def _default_routes() -> tuple[list[dict[str, Any]], str]:
    raw = _run(["ip", "-json", "route", "show", "default"])
    routes = json.loads(raw or "[]")
    if not isinstance(routes, list) or not routes:
        raise RuntimeError("candidate integration host has no default route")
    normalized = json.dumps(routes, sort_keys=True, separators=(",", ":"))
    signature = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
    return routes, signature


def _docker_boundary() -> dict[str, Any]:
    server_version = _run(["docker", "version", "--format", "{{.Server.Version}}"])
    security_raw = _run(["docker", "info", "--format", "{{json .SecurityOptions}}"])
    root_dir = _run(["docker", "info", "--format", "{{.DockerRootDir}}"])
    try:
        security_options = json.loads(security_raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"unable to parse Docker security options: {security_raw!r}") from exc
    if not isinstance(security_options, list):
        raise RuntimeError("Docker security options are not a list")
    rootless = any("rootless" in str(option).lower() for option in security_options)
    if rootless:
        raise RuntimeError(
            "rootless Docker cannot prove the required real root:root ownership parity"
        )
    return {
        "server_version": server_version,
        "security_options": security_options,
        "rootless": False,
        "root_dir": root_dir,
        "host_security_note": (
            "non-root runner access to a rootful Docker daemon is host-privileged; "
            "this host is not a sandbox"
        ),
    }


def _armv7_boundary() -> dict[str, Any]:
    try:
        _run(["docker", "image", "inspect", ARM_IMAGE, "--format", "{{.Id}}"])
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(
            "pinned ARMv7 image is not pre-provisioned locally; readiness will not pull it"
        ) from exc

    program = (
        "import json,platform; "
        "print(json.dumps({'machine': platform.machine(), 'python': platform.python_version()}))"
    )
    raw = _run(
        [
            "docker",
            "run",
            "--rm",
            "--pull=never",
            "--platform",
            "linux/arm/v7",
            "--network",
            "none",
            "--cap-drop",
            "ALL",
            "--security-opt",
            "no-new-privileges:true",
            ARM_IMAGE,
            "python3",
            "-c",
            program,
        ]
    )
    try:
        evidence = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"unable to parse ARMv7 probe output: {raw!r}") from exc
    machine = str(evidence.get("machine", ""))
    if not machine.startswith("arm"):
        raise RuntimeError(f"ARMv7 execution boundary returned unexpected machine: {machine!r}")
    evidence.update(
        {
            "image": ARM_IMAGE,
            "image_preprovisioned": True,
            "pull_policy": "never",
            "network": "none",
            "capabilities": "none",
            "no_new_privileges": True,
        }
    )
    return evidence


def _persistent_root(path: Path, *, uid: int, gid: int) -> dict[str, Any]:
    expanded = path.expanduser().absolute()
    if not expanded.exists():
        raise RuntimeError(
            f"persistent root must be provisioned before readiness is run: {expanded}"
        )
    if expanded.is_symlink():
        raise RuntimeError(f"persistent root must not be a symlink: {expanded}")
    resolved = expanded.resolve(strict=True)
    info = resolved.lstat()
    mode = stat.S_IMODE(info.st_mode)
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"persistent root is not a directory: {resolved}")
    if info.st_uid != uid or info.st_gid != gid:
        raise RuntimeError(
            "persistent root must be owned by the intended non-root runner identity "
            f"(expected {uid}:{gid}, found {info.st_uid}:{info.st_gid})"
        )
    if mode & 0o022:
        raise RuntimeError(
            f"persistent root must not be group/world writable (mode={mode:04o})"
        )
    return {
        "path": str(resolved),
        "uid": info.st_uid,
        "gid": info.st_gid,
        "mode": f"{mode:04o}",
        "filesystem": _filesystem_type(resolved),
        "preexisting": True,
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Non-provisioning readiness check for a candidate Plasma persistent "
            "integration host."
        )
    )
    parser.add_argument("--persistent-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "FAIL",
        "qualification_state": "UNPROVISIONED",
        "evidence_level": "L4_host_readiness",
        "mutates_host_configuration": False,
        "z2_hardware_claim": "NONE",
    }
    try:
        if platform.system() != "Linux":
            raise RuntimeError(f"candidate integration host must be Linux, found {platform.system()!r}")
        if platform.machine() not in {"x86_64", "amd64"}:
            raise RuntimeError(
                f"candidate integration host must be x64, found {platform.machine()!r}"
            )

        uid = os.geteuid()
        gid = os.getegid()
        if uid == 0:
            raise RuntimeError("intended GitHub Actions runner identity must be non-root")

        tools = {
            name: _require_tool(name)
            for name in ("docker", "git", "ip", "node", "npm", "python3", "stat")
        }
        report.update(
            {
                "host": {
                    "hostname": platform.node(),
                    "uid": uid,
                    "gid": gid,
                    "kernel_system": platform.system(),
                    "kernel_release": platform.release(),
                    "machine": platform.machine(),
                    "os_release": _os_release(),
                    "python": platform.python_version(),
                    "git": _run(["git", "--version"]),
                    "node": _run(["node", "--version"]),
                    "npm": _run(["npm", "--version"]),
                    "tools": tools,
                },
                "persistent_root": _persistent_root(args.persistent_root, uid=uid, gid=gid),
                "docker": _docker_boundary(),
                "armv7": _armv7_boundary(),
            }
        )
        routes, route_signature = _default_routes()
        report["network"] = {
            "default_routes": routes,
            "default_route_signature_sha256": route_signature,
            "configuration_mutated": False,
        }
        report["qualification_state"] = "HOST_READY"
        report["status"] = "PASS"
        _write_report(args.report, report)
        print(
            "PLASMA_PERSISTENT_INTEGRATION_HOST_READINESS="
            + json.dumps(report, sort_keys=True, separators=(",", ":")),
            flush=True,
        )
        return 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        _write_report(args.report, report)
        print(f"[FAIL] persistent integration host readiness: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

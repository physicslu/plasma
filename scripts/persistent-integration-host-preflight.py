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
EXPECTED_EVENT = "workflow_dispatch"
EXPECTED_REF = "refs/heads/main"


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


def _inside(child: Path, parent: Path) -> bool:
    return child == parent or parent in child.parents


def _filesystem_type(path: Path) -> str:
    return _run(["stat", "-f", "-c", "%T", str(path)])


def _default_routes() -> tuple[list[dict[str, Any]], str]:
    raw = _run(["ip", "-json", "route", "show", "default"])
    routes = json.loads(raw or "[]")
    if not isinstance(routes, list) or not routes:
        raise RuntimeError("persistent integration host has no default route")
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
            "this runner is not a sandbox"
        ),
    }


def _armv7_boundary() -> dict[str, Any]:
    program = (
        "import json,platform; "
        "print(json.dumps({'machine': platform.machine(), 'python': platform.python_version()}))"
    )
    raw = _run(
        [
            "docker",
            "run",
            "--rm",
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
    evidence["image"] = ARM_IMAGE
    evidence["network"] = "none"
    evidence["capabilities"] = "none"
    evidence["no_new_privileges"] = True
    return evidence


def _persistent_root(path: Path, *, uid: int, gid: int, workspace: Path, runner_temp: Path) -> dict[str, Any]:
    if path.exists() and path.is_symlink():
        raise RuntimeError(f"persistent root must not be a symlink: {path}")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    resolved = path.resolve(strict=True)
    if _inside(resolved, workspace):
        raise RuntimeError("persistent root must live outside GITHUB_WORKSPACE")
    if _inside(resolved, runner_temp):
        raise RuntimeError("persistent root must live outside RUNNER_TEMP")

    info = resolved.lstat()
    mode = stat.S_IMODE(info.st_mode)
    if not stat.S_ISDIR(info.st_mode):
        raise RuntimeError(f"persistent root is not a directory: {resolved}")
    if info.st_uid != uid or info.st_gid != gid:
        raise RuntimeError(
            "persistent root must be owned by the non-root runner identity "
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
        "outside_workspace": True,
        "outside_runner_temp": True,
    }


def _identity(expected_repository: str) -> dict[str, Any]:
    event_name = os.environ.get("GITHUB_EVENT_NAME", "")
    repository = os.environ.get("GITHUB_REPOSITORY", "")
    ref = os.environ.get("GITHUB_REF", "")
    event_sha = os.environ.get("GITHUB_SHA", "")
    if event_name != EXPECTED_EVENT:
        raise RuntimeError(f"expected {EXPECTED_EVENT}, found {event_name!r}")
    if repository != expected_repository:
        raise RuntimeError(f"expected repository {expected_repository!r}, found {repository!r}")
    if ref != EXPECTED_REF:
        raise RuntimeError(f"persistent qualification is main-only; found ref {ref!r}")
    checked_out_sha = _run(["git", "rev-parse", "HEAD"])
    if not event_sha or checked_out_sha != event_sha:
        raise RuntimeError(
            "checked-out commit does not match workflow dispatch SHA "
            f"(checkout={checked_out_sha!r}, event={event_sha!r})"
        )
    return {
        "event": event_name,
        "repository": repository,
        "ref": ref,
        "event_sha": event_sha,
        "checked_out_sha": checked_out_sha,
        "main_only": True,
        "pre_merge_pr_gate_claim": "NONE",
    }


def _write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Fail-closed preflight for the persistent Plasma integration host."
    )
    parser.add_argument("--persistent-root", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--expected-repository", required=True)
    return parser


def main() -> int:
    args = _parser().parse_args()
    report: dict[str, Any] = {
        "schema_version": 1,
        "status": "FAIL",
        "evidence_level": "L4_persistent_integration_preflight",
        "z2_hardware_claim": "NONE",
    }
    try:
        if platform.system() != "Linux":
            raise RuntimeError(f"persistent integration host must be Linux, found {platform.system()!r}")
        if platform.machine() not in {"x86_64", "amd64"}:
            raise RuntimeError(
                f"persistent integration host must be x64, found {platform.machine()!r}"
            )

        uid = os.geteuid()
        gid = os.getegid()
        if uid == 0:
            raise RuntimeError("persistent integration runner must run as a non-root host user")

        for tool in ("docker", "git", "ip", "node", "npm", "python3", "stat"):
            _require_tool(tool)

        workspace_raw = os.environ.get("GITHUB_WORKSPACE", "")
        runner_temp_raw = os.environ.get("RUNNER_TEMP", "")
        if not workspace_raw or not runner_temp_raw:
            raise RuntimeError("GITHUB_WORKSPACE and RUNNER_TEMP are required")
        workspace = Path(workspace_raw).resolve(strict=True)
        runner_temp = Path(runner_temp_raw).resolve(strict=True)

        report.update(
            {
                "identity": _identity(args.expected_repository),
                "host": {
                    "uid": uid,
                    "gid": gid,
                    "kernel_system": platform.system(),
                    "kernel_release": platform.release(),
                    "machine": platform.machine(),
                    "python": platform.python_version(),
                    "node": _run(["node", "--version"]),
                    "npm": _run(["npm", "--version"]),
                    "workspace": str(workspace),
                    "runner_temp": str(runner_temp),
                },
                "persistent_root": _persistent_root(
                    args.persistent_root.expanduser().absolute(),
                    uid=uid,
                    gid=gid,
                    workspace=workspace,
                    runner_temp=runner_temp,
                ),
                "docker": _docker_boundary(),
                "armv7": _armv7_boundary(),
            }
        )
        routes, route_signature = _default_routes()
        report["network"] = {
            "default_routes": routes,
            "default_route_signature_sha256": route_signature,
        }
        report["status"] = "PASS"
        _write_report(args.report, report)
        print(
            "PLASMA_PERSISTENT_INTEGRATION_PREFLIGHT="
            + json.dumps(report, sort_keys=True, separators=(",", ":")),
            flush=True,
        )
        return 0
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        _write_report(args.report, report)
        print(f"[FAIL] persistent integration preflight: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

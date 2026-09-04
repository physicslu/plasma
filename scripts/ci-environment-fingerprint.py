#!/usr/bin/env python3
"""Capture deterministic CI/integration-host execution context as JSON evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

ARM_IMAGE = "arm32v7/python:3.12@sha256:45eb5cbc14fe248e7598eb23a5a61424d44e556aed3efa955dfab2ac9a67d91c"
RESULT_MARKER = "PLASMA_CI_ENVIRONMENT_FINGERPRINT="


class FingerprintError(RuntimeError):
    pass


def _run(command: Sequence[str]) -> str:
    result = subprocess.run(
        list(command),
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()
        raise FingerprintError(f"command failed ({' '.join(command)}): {detail}")
    return result.stdout.strip()


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _json_command(command: Sequence[str]) -> Any:
    text = _run(command)
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise FingerprintError(f"command did not return JSON ({' '.join(command)}): {text!r}") from exc


def _uplink_fingerprint() -> dict[str, Any]:
    routes = _json_command(["ip", "-json", "route", "show", "default"])
    if not isinstance(routes, list) or not routes:
        raise FingerprintError("default route is unavailable")
    route = routes[0]
    if not isinstance(route, dict) or not isinstance(route.get("dev"), str) or not route["dev"]:
        raise FingerprintError(f"default route has no uplink device: {route!r}")
    uplink = route["dev"]
    addresses = _json_command(["ip", "-json", "addr", "show", "dev", uplink])
    normalized = json.dumps(
        {"route": route, "addresses": addresses},
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return {
        "interface": uplink,
        "signature_sha256": hashlib.sha256(normalized).hexdigest(),
        "default_route": route,
    }


def _docker_fingerprint() -> dict[str, Any]:
    security_options_text = _run(["docker", "info", "--format", "{{json .SecurityOptions}}"])
    try:
        security_options = json.loads(security_options_text)
    except json.JSONDecodeError as exc:
        raise FingerprintError(f"invalid Docker SecurityOptions JSON: {security_options_text!r}") from exc
    if not isinstance(security_options, list):
        raise FingerprintError(f"unexpected Docker SecurityOptions: {security_options!r}")
    normalized_options = [str(item) for item in security_options]
    return {
        "server_version": _run(["docker", "version", "--format", "{{.Server.Version}}"]),
        "security_options": normalized_options,
        "rootless": any("rootless" in item.lower() for item in normalized_options),
        "docker_root_dir": _run(["docker", "info", "--format", "{{.DockerRootDir}}"]),
    }


def _qemu_fingerprint() -> dict[str, Any]:
    machine = _run(
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
            "import platform; print(platform.machine())",
        ]
    )
    if not machine.startswith("arm"):
        raise FingerprintError(f"ARMv7 execution did not report an ARM machine: {machine!r}")
    return {
        "platform": "linux/arm/v7",
        "machine": machine,
        "image": ARM_IMAGE,
    }


def _main(args: argparse.Namespace) -> int:
    if platform.system() != "Linux":
        raise FingerprintError("integration environment fingerprint requires Linux")
    for command in ("docker", "git", "ip", "stat"):
        if shutil.which(command) is None:
            raise FingerprintError(f"required command is missing: {command}")

    repo = Path(__file__).resolve().parents[1]
    artifact = args.artifact.resolve()
    work_dir = args.work_dir.resolve()
    report = args.report.resolve()
    if not artifact.is_file():
        raise FingerprintError(f"artifact is missing: {artifact}")
    work_dir.mkdir(parents=True, exist_ok=True)
    report.parent.mkdir(parents=True, exist_ok=True)

    uname = platform.uname()
    docker = _docker_fingerprint()
    uplink = _uplink_fingerprint()
    qemu = _qemu_fingerprint()
    result = {
        "git_sha": _run(["git", "-C", str(repo), "rev-parse", "HEAD"]),
        "uid": os.geteuid(),
        "gid": os.getegid(),
        "python": sys.version.split()[0],
        "kernel": {
            "system": uname.system,
            "release": uname.release,
            "version": uname.version,
            "machine": uname.machine,
        },
        "filesystem": {
            "path": str(work_dir),
            "type": _run(["stat", "-f", "-c", "%T", str(work_dir)]),
        },
        "docker": docker,
        "qemu": qemu,
        "host_uplink": uplink,
        "artifact": {
            "name": artifact.name,
            "sha256": _sha256_file(artifact),
            "size": artifact.stat().st_size,
        },
        "evidence_boundary": "linux-integration-environment-only",
        "z2_network_backend_claim": "NONE",
    }
    report.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(RESULT_MARKER + json.dumps(result, separators=(",", ":"), sort_keys=True))
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Capture CI/integration-host environment fingerprint")
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--work-dir", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        return _main(args)
    except (FingerprintError, OSError, subprocess.SubprocessError, ValueError) as exc:
        print(f"ci-environment-fingerprint: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

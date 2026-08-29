#!/usr/bin/env python3
"""Read-only readiness audit for Plasma product deployment roles.

This script deliberately does not install packages, create directories, change
services, update Git, or touch hardware.  It is the bootstrap boundary between
the existing SWPC integration-host workflow and future product installers.
"""

from __future__ import annotations

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Callable, Sequence


MIN_PYTHON = (3, 11, 0)
MIN_NODE = (22, 13, 0)
ROLE_CONTROL_STATION = "control-station"
ROLE_PPU = "ppu"
ROLES = (ROLE_CONTROL_STATION, ROLE_PPU)


@dataclass(frozen=True)
class Check:
    name: str
    status: str
    detail: str


@dataclass(frozen=True)
class AuditReport:
    role: str
    system: str
    architecture: str
    python_version: str
    checks: tuple[Check, ...]

    @property
    def ready(self) -> bool:
        return all(check.status != "fail" for check in self.checks)

    def as_json(self) -> dict[str, object]:
        payload = asdict(self)
        payload["ready"] = self.ready
        return payload


def _version_tuple(text: str) -> tuple[int, int, int] | None:
    match = re.search(r"(?:^|[^0-9])(\d+)\.(\d+)(?:\.(\d+))?", text)
    if match is None:
        return None
    major, minor, patch = match.groups()
    return int(major), int(minor), int(patch or 0)


def _command_version(path: str, args: Sequence[str]) -> str | None:
    try:
        completed = subprocess.run(
            [path, *args],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first_line = completed.stdout.strip().splitlines()
    return first_line[0] if first_line else None


def _required_command(
    name: str,
    *,
    lookup: Callable[[str], str | None],
    detail: str,
) -> Check:
    path = lookup(name)
    if path is None:
        return Check(name, "fail", f"missing: {detail}")
    return Check(name, "pass", path)


def _not_required_command(
    name: str,
    *,
    lookup: Callable[[str], str | None],
    detail: str,
) -> Check:
    path = lookup(name)
    if path is None:
        return Check(name, "info", f"not installed; {detail}")
    return Check(name, "info", f"present at {path}; {detail}")


def _python_check(version_info: Sequence[int]) -> Check:
    current = tuple(int(part) for part in version_info[:3])
    if current < MIN_PYTHON:
        return Check(
            "python",
            "fail",
            f"Python {current[0]}.{current[1]}.{current[2]} < required 3.11",
        )
    return Check(
        "python",
        "pass",
        f"Python {current[0]}.{current[1]}.{current[2]} >= 3.11",
    )


def _node_check(
    *,
    lookup: Callable[[str], str | None],
    version_reader: Callable[[str, Sequence[str]], str | None],
) -> Check:
    path = lookup("node")
    if path is None:
        return Check(
            "node",
            "fail",
            "Node.js is missing; current Control Console runtime requires >= 22.13",
        )
    text = version_reader(path, ("--version",))
    parsed = _version_tuple(text or "")
    if parsed is None:
        return Check("node", "fail", f"cannot determine Node.js version from {path}")
    if parsed < MIN_NODE:
        return Check(
            "node",
            "fail",
            f"Node.js {parsed[0]}.{parsed[1]}.{parsed[2]} < required 22.13",
        )
    return Check(
        "node",
        "pass",
        f"Node.js {parsed[0]}.{parsed[1]}.{parsed[2]} >= 22.13 ({path})",
    )


def audit_control_station(
    *,
    system: str,
    architecture: str,
    version_info: Sequence[int],
    home: Path,
    lookup: Callable[[str], str | None],
    version_reader: Callable[[str, Sequence[str]], str | None],
) -> AuditReport:
    checks: list[Check] = [_python_check(version_info)]

    checks.append(
        Check(
            "operating-system",
            "pass" if system == "Darwin" else "fail",
            f"detected {system}; product Control Station baseline is macOS/Darwin",
        )
    )
    checks.append(
        Check(
            "architecture",
            "pass" if architecture in {"arm64", "aarch64", "x86_64"} else "warn",
            f"detected {architecture}; supported Mac baseline is arm64/x86_64",
        )
    )
    checks.append(
        _required_command(
            "launchctl",
            lookup=lookup,
            detail="macOS product services use launchd/LaunchAgent, not systemd",
        )
    )
    checks.append(_node_check(lookup=lookup, version_reader=version_reader))
    checks.append(
        _not_required_command(
            "npm",
            lookup=lookup,
            detail="target deployment must consume a prebuilt Console artifact; npm is a build-time tool",
        )
    )
    checks.append(
        _not_required_command(
            "git",
            lookup=lookup,
            detail="product deployment must not require git pull on the Control Station",
        )
    )
    checks.append(
        _not_required_command(
            "timeout",
            lookup=lookup,
            detail="GNU timeout is a CI/source-build dependency, not a Control Station runtime requirement",
        )
    )

    library = home / "Library"
    if library.is_dir() and os.access(library, os.W_OK):
        checks.append(
            Check(
                "application-support-root",
                "pass",
                str(library / "Application Support" / "Plasma"),
            )
        )
    else:
        checks.append(
            Check(
                "application-support-root",
                "fail",
                f"expected writable macOS user Library at {library}",
            )
        )

    checks.append(
        Check(
            "service-scope",
            "info",
            "v1 Control Station baseline uses per-user launchd LaunchAgents; no systemd dependency",
        )
    )
    return AuditReport(
        role=ROLE_CONTROL_STATION,
        system=system,
        architecture=architecture,
        python_version=platform.python_version(),
        checks=tuple(checks),
    )


def audit_ppu(
    *,
    system: str,
    architecture: str,
    version_info: Sequence[int],
    lookup: Callable[[str], str | None],
    systemd_runtime: Path,
    os_release: Path,
) -> AuditReport:
    checks: list[Check] = [_python_check(version_info)]

    checks.append(
        Check(
            "operating-system",
            "pass" if system == "Linux" else "fail",
            f"detected {system}; product PPU baseline is embedded Linux",
        )
    )
    if architecture in {"armv7l", "armv7", "armhf", "aarch64", "arm64"}:
        architecture_status = "pass"
        architecture_detail = f"detected ARM target architecture {architecture}"
    elif architecture == "x86_64":
        architecture_status = "warn"
        architecture_detail = "x86_64 is suitable for development/staging, not the Z2 product target"
    else:
        architecture_status = "warn"
        architecture_detail = f"unclassified PPU architecture {architecture}"
    checks.append(Check("architecture", architecture_status, architecture_detail))
    checks.append(
        _required_command(
            "systemctl",
            lookup=lookup,
            detail="PPU product services use system-level systemd units",
        )
    )
    checks.append(
        Check(
            "systemd-runtime",
            "pass" if systemd_runtime.is_dir() else "fail",
            f"systemd runtime directory: {systemd_runtime}",
        )
    )
    checks.append(
        Check(
            "os-release",
            "pass" if os_release.is_file() else "warn",
            f"OS identity source: {os_release}",
        )
    )
    ip_path = lookup("ip")
    checks.append(
        Check(
            "ip",
            "pass" if ip_path else "warn",
            ip_path or "iproute2 command is missing; network diagnostics will be limited",
        )
    )
    checks.append(
        _not_required_command(
            "node",
            lookup=lookup,
            detail="Node.js is not part of the PPU product runtime",
        )
    )
    checks.append(
        _not_required_command(
            "npm",
            lookup=lookup,
            detail="npm is not part of the PPU product runtime",
        )
    )
    checks.append(
        _not_required_command(
            "git",
            lookup=lookup,
            detail="product PPU deployment must consume a release artifact, not git pull",
        )
    )
    checks.append(
        Check(
            "service-scope",
            "info",
            "PPU baseline uses system-level systemd services; installation/upgrade may require elevated privilege",
        )
    )
    checks.append(
        Check(
            "hardware-boundary",
            "info",
            "readiness audit does not load FPGA bitstreams, access PL, change power, or program ICs",
        )
    )
    return AuditReport(
        role=ROLE_PPU,
        system=system,
        architecture=architecture,
        python_version=platform.python_version(),
        checks=tuple(checks),
    )


def run_audit(role: str) -> AuditReport:
    common = {
        "system": platform.system(),
        "architecture": platform.machine(),
        "version_info": sys.version_info,
        "lookup": shutil.which,
    }
    if role == ROLE_CONTROL_STATION:
        return audit_control_station(
            **common,
            home=Path.home(),
            version_reader=_command_version,
        )
    if role == ROLE_PPU:
        return audit_ppu(
            **common,
            systemd_runtime=Path("/run/systemd/system"),
            os_release=Path("/etc/os-release"),
        )
    raise ValueError(f"unsupported role: {role}")


def _print_text(report: AuditReport) -> None:
    print(f"Plasma product deployment audit: {report.role}")
    print(f"Platform: {report.system} {report.architecture}")
    print(f"Python:   {report.python_version}")
    print()
    for check in report.checks:
        print(f"[{check.status.upper():4}] {check.name}: {check.detail}")
    print()
    print(f"Result: {'READY' if report.ready else 'BLOCKED'}")


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Read-only Plasma product deployment readiness audit"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    audit_parser = subparsers.add_parser("audit", help="run a read-only role audit")
    audit_parser.add_argument("role", choices=ROLES)
    audit_parser.add_argument("--json", action="store_true", dest="as_json")
    args = parser.parse_args(argv)

    report = run_audit(args.role)
    if args.as_json:
        print(json.dumps(report.as_json(), indent=2, sort_keys=True))
    else:
        _print_text(report)
    return 0 if report.ready else 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Install the stable Plasma PPU Bootstrap factory/recovery layer.

This installer is intentionally separate from the Plasma Product Runtime.
It copies only the bootstrap control scripts, creates private bootstrap state,
and installs a systemd unit that launches the authenticated Bootstrap service.
It does not install a Plasma Runtime, provision a control token, load FPGA
content, or change Site/target power.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Sequence

REQUIRED_SCRIPTS = (
    "ppu-bootstrap.py",
    "ppu-bootstrap-service.py",
    "ppu-bootstrap-deployment.py",
    "ppu-bootstrap-kit.py",
    "ppu_unified_deployment.py",
    "ppu_bundle_authority.py",
    "ppu_asset_set.py",
    "ppu_asset_execution.py",
)

# Generic Bundle v3 B3 capability ships inside the SAME Bootstrap layer.
# Root-owned development-mode policy is factory provisioned, not an HTTP grant.
B3_FILES = (
    "ppu-z2-installer.py",
    "ppu-z2-installer-core.py",
    "ppu-bundle-install-policy.json",
)


class BootstrapInstallError(RuntimeError):
    pass


@dataclass(frozen=True)
class InstallPaths:
    install_root: Path = Path("/opt/plasma/bootstrap")
    state_root: Path = Path("/var/lib/plasma-bootstrap")
    systemd_unit: Path = Path("/etc/systemd/system/plasma-bootstrap.service")


def _load_base(path: Path):
    spec = importlib.util.spec_from_file_location("plasma_ppu_bootstrap_installer_base", path)
    if spec is None or spec.loader is None:
        raise BootstrapInstallError(f"cannot load Bootstrap base script: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _copy_scripts(source_root: Path, install_root: Path) -> None:
    source_root = source_root.resolve()
    # Reject an incomplete bundle before touching a previously installed service.
    for name in REQUIRED_SCRIPTS:
        if not (source_root / name).is_file():
            raise BootstrapInstallError(f"factory bundle is missing required script: {name}")
    install_root.mkdir(parents=True, exist_ok=True)
    install_root.chmod(0o755)
    # The generic policy grants install-only for previously admitted
    # canonical Bundles in development mode; not arbitrary code execution.
    policy_present = (source_root / "ppu-bundle-install-policy.json").is_file()
    b3_present = list(B3_FILES) if policy_present else []
    if policy_present and not all((source_root / name).is_file() for name in B3_FILES):
        raise BootstrapInstallError("factory B3 source set is incomplete")
    if policy_present:
        try:
            policy = json.loads((source_root / "ppu-bundle-install-policy.json").read_text())
        except (OSError, ValueError) as exc:
            raise BootstrapInstallError("factory B3 policy unreadable") from exc
        if (type(policy) is not dict
                or set(policy) != {"schema", "mode", "install_only", "actions"}
                or policy.get("schema") != "plasma.ppu.b3-install-policy.v1"
                or policy.get("mode") != "development"
                or policy.get("install_only") is not True
                or policy.get("actions") != ["install", "verify"]):
            raise BootstrapInstallError("factory B3 policy invalid")
    for name in (*REQUIRED_SCRIPTS, *(B3_FILES if b3_present else ())):
        source = source_root / name
        if source.is_symlink():
            raise BootstrapInstallError("factory Bootstrap source symlink denied")
        destination = install_root / name
        if destination.is_symlink():
            raise BootstrapInstallError("factory Bootstrap destination symlink denied")
        temporary = destination.with_name(destination.name + ".new")
        if temporary.is_symlink():
            raise BootstrapInstallError("factory Bootstrap temp symlink denied")
        shutil.copyfile(source, temporary)
        temporary.chmod(0o600 if name.endswith("-policy.json") else 0o755)
        os.replace(temporary, destination)


def install_bootstrap(
    *,
    source_root: Path,
    host: str,
    port: int,
    python_executable: str,
    paths: InstallPaths,
    enable_now: bool = False,
    refresh_only: bool = False,
    runner: Callable[..., subprocess.CompletedProcess[str]] = subprocess.run,
) -> dict[str, object]:
    if refresh_only:
        # One-board development B3 upgrade: update ONLY the existing factory
        # scripts, preserving systemd unit, enrollment, token and Runtime.
        if enable_now:
            raise BootstrapInstallError("B3_REFRESH_CANNOT_ENABLE_SERVICE")
        if not (paths.install_root.is_dir()
                and not paths.install_root.is_symlink()
                and (paths.install_root / "ppu-bootstrap-service.py").is_file()
                and paths.state_root.is_dir()
                and not paths.state_root.is_symlink()
                and not paths.systemd_unit.is_symlink()
                and paths.systemd_unit.is_file()):
            raise BootstrapInstallError("B3_REFRESH_REQUIRES_EXISTING_FACTORY")
        if (source_root / "ppu-bundle-install-policy.json").is_symlink() or not (
                source_root / "ppu-bundle-install-policy.json").is_file():
            raise BootstrapInstallError("B3_REFRESH_SOURCE_POLICY_REQUIRED")
        _copy_scripts(source_root, paths.install_root)
        return {
            "schema_version": 1,
            "result": "PASS",
            "operation": "refresh_only",
            "install_root": str(paths.install_root),
            "state_root": str(paths.state_root),
            "systemd_unit": str(paths.systemd_unit),
            "service": "plasma-bootstrap.service",
            "unit_changed": False,
            "service_restarted": False,
            "control_token_provisioned": False,
            "runtime_installed": False,
            "fpga_update": False,
        }
    _copy_scripts(source_root, paths.install_root)
    paths.state_root.mkdir(parents=True, exist_ok=True)
    paths.state_root.chmod(0o700)

    base = _load_base(paths.install_root / "ppu-bootstrap.py")
    service_script = paths.install_root / "ppu-bootstrap-service.py"
    unit = base.render_systemd_unit(
        python_executable=python_executable,
        script_path=str(service_script),
        host=host,
        port=port,
    )
    paths.systemd_unit.parent.mkdir(parents=True, exist_ok=True)
    temporary = paths.systemd_unit.with_name(paths.systemd_unit.name + ".new")
    temporary.write_text(unit, encoding="utf-8")
    temporary.chmod(0o644)
    os.replace(temporary, paths.systemd_unit)

    if enable_now:
        for argv in (
            ["systemctl", "daemon-reload"],
            ["systemctl", "enable", "--now", "plasma-bootstrap.service"],
        ):
            completed = runner(
                argv,
                check=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            if completed.returncode != 0:
                tail = completed.stdout[-4000:] if completed.stdout else ""
                raise BootstrapInstallError(
                    f"Bootstrap systemd activation failed for {' '.join(argv)}: {tail}"
                )

    return {
        "schema_version": 1,
        "result": "PASS",
        "install_root": str(paths.install_root),
        "state_root": str(paths.state_root),
        "systemd_unit": str(paths.systemd_unit),
        "service": "plasma-bootstrap.service",
        "enabled_now": enable_now,
        "control_token_provisioned": False,
        "runtime_installed": False,
        "fpga_update": False,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Install Plasma PPU Bootstrap factory layer")
    parser.add_argument("--source-root", type=Path, required=True)
    parser.add_argument("--host", required=True)
    parser.add_argument("--port", type=int, default=18081)
    parser.add_argument("--python", dest="python_executable", default="/usr/bin/python3")
    parser.add_argument("--install-root", type=Path, default=Path("/opt/plasma/bootstrap"))
    parser.add_argument("--state-root", type=Path, default=Path("/var/lib/plasma-bootstrap"))
    parser.add_argument(
        "--systemd-unit",
        type=Path,
        default=Path("/etc/systemd/system/plasma-bootstrap.service"),
    )
    parser.add_argument("--enable-now", action="store_true")
    parser.add_argument("--refresh-only", action="store_true",
                        help="Refresh B3 scripts only; preserve existing factory unit/token/state")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        result = install_bootstrap(
            source_root=args.source_root,
            host=args.host,
            port=args.port,
            python_executable=args.python_executable,
            paths=InstallPaths(args.install_root, args.state_root, args.systemd_unit),
            enable_now=args.enable_now,
            refresh_only=args.refresh_only,
        )
    except BootstrapInstallError as exc:
        print(f"ppu-bootstrap-installer: {exc}", file=sys.stderr)
        return 2
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

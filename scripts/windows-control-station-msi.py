#!/usr/bin/env python3
"""Build an unsigned Windows MSI pilot from a verified Control Station release."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Mapping, Sequence
from xml.sax.saxutils import escape

REPO_ROOT = Path(__file__).resolve().parents[1]
WINSW_VERSION = "2.12.0"
WINSW_X64_SHA256 = "05b82d46ad331cc16bdc00de5c6332c1ef818df8ceefcd49c726553209b3a0da"
WIX_TOOLSET_VERSION = "4.0.6"
UPGRADE_CODE = "3A273357-8467-4C07-A06E-B40F8D1531E7"
SERVICE_MANAGER = "PlasmaManager"
SERVICE_CONSOLE = "PlasmaControlStationConsole"


class WindowsInstallerError(RuntimeError):
    pass


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise WindowsInstallerError(f"cannot load build tool: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _release_tool(repo_root: Path):
    return _load(repo_root / "scripts" / "product-release.py", "plasma_windows_product_release")


def _runtime_tool(repo_root: Path):
    return _load(repo_root / "scripts" / "control-station-runtime.py", "plasma_windows_runtime")


def normalize_architecture(machine: str) -> str:
    if machine.strip().lower() in {"amd64", "x86_64"}:
        return "x86_64"
    raise WindowsInstallerError(f"unsupported Windows architecture: {machine}")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_winsw(path: Path) -> None:
    if not path.is_file():
        raise WindowsInstallerError(f"WinSW executable is missing: {path}")
    actual = _sha256(path)
    if actual != WINSW_X64_SHA256:
        raise WindowsInstallerError(
            f"WinSW {WINSW_VERSION} SHA-256 mismatch: expected {WINSW_X64_SHA256}, got {actual}"
        )


def verify_release(repo_root: Path, artifact: Path, extract_to: Path) -> tuple[dict[str, object], Path]:
    release_tool = _release_tool(repo_root)
    try:
        manifest = release_tool.verify_release(
            artifact,
            extract_to=extract_to,
            expect_role=release_tool.ROLE_CONTROL_STATION,
            expect_platform="windows",
            expect_architecture="x86_64",
        )
        release_root = extract_to / "plasma-release"
        _runtime_tool(repo_root).validate_runtime(release_root / "runtime")
    except (OSError, ValueError) as exc:
        raise WindowsInstallerError(f"Control Station release verification failed: {exc}") from exc
    return dict(manifest), release_root


def _msi_version(version: str) -> str:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:[-+].*)?", version)
    if not match:
        raise WindowsInstallerError(f"product version is not MSI-compatible semantic version: {version}")
    major, minor, patch = (int(value) for value in match.groups())
    if major > 255 or minor > 255 or patch > 65535:
        raise WindowsInstallerError(f"product version exceeds MSI limits: {version}")
    return f"{major}.{minor}.{patch}"


def stage_payload(
    *, repo_root: Path, runtime_dir: Path, staging_root: Path, version: str,
    source_release: Mapping[str, object], winsw_exe: Path,
) -> tuple[Path, Path]:
    if staging_root.exists():
        raise WindowsInstallerError(f"refusing to overwrite staging root: {staging_root}")
    verify_winsw(winsw_exe)
    release_root = staging_root / "release"
    bin_dir = release_root / "bin"
    shutil.copytree(runtime_dir, release_root / "runtime")
    bin_dir.mkdir()
    packaging = repo_root / "packaging" / "windows"
    for name in ("run-manager.ps1", "run-console.ps1", "plasma-manager-service.xml", "plasma-console-service.xml"):
        source = packaging / name
        if not source.is_file():
            raise WindowsInstallerError(f"missing Windows packaging file: {source}")
        shutil.copy2(source, bin_dir / name)
    shutil.copy2(winsw_exe, bin_dir / "plasma-manager-service.exe")
    shutil.copy2(winsw_exe, bin_dir / "plasma-console-service.exe")
    licenses = release_root / "THIRD_PARTY_LICENSES"
    licenses.mkdir()
    shutil.copy2(packaging / "LICENSE-WINSW.txt", licenses / "WinSW.txt")
    installer_manifest = {
        "schema_version": 1,
        "product": "plasma",
        "role": "control-station",
        "platform": "windows",
        "architecture": "x86_64",
        "product_version": version,
        "service_manager": "windows-scm-via-winsw",
        "services": [SERVICE_MANAGER, SERVICE_CONSOLE],
        "program_files_root": rf"%ProgramFiles%\Plasma\releases\{version}",
        "program_data_root": r"%ProgramData%\Plasma",
        "external_prerequisites": {"node": ">=22.13", "python": ">=3.11"},
        "winsw": {"version": WINSW_VERSION, "sha256": WINSW_X64_SHA256, "license": r"THIRD_PARTY_LICENSES\WinSW.txt"},
        "wix_toolset_build_version": WIX_TOOLSET_VERSION,
        "source_release": {key: source_release.get(key) for key in ("artifact_sha256", "git_sha", "target", "contracts")},
        "signed": False,
        "pilot": True,
    }
    (release_root / "windows-installer.json").write_text(json.dumps(installer_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    seed = staging_root / "program-data-seed"
    seed.mkdir()
    (seed / "manager.yaml").write_text(
        "manager:\n  host: 127.0.0.1\n  port: 18180\n  request_timeout_s: 2.0\n  poll_interval_s: 2.0\n"
        "  observation_db_path: C:\\ProgramData\\Plasma\\state\\manager-observations.sqlite3\nppus: []\n",
        encoding="utf-8",
    )
    (seed / "selected-ppu-alias").write_text("", encoding="utf-8")
    return release_root, seed


def _xml_path(path: Path) -> str:
    return escape(str(path.resolve()), {'"': '&quot;'})


def generate_wix_source(*, release_root: Path, program_data_seed: Path, version: str, output_path: Path) -> None:
    root = _xml_path(release_root)
    manager_exe = _xml_path(release_root / "bin" / "plasma-manager-service.exe")
    console_exe = _xml_path(release_root / "bin" / "plasma-console-service.exe")
    manager_seed = _xml_path(program_data_seed / "manager.yaml")
    alias_seed = _xml_path(program_data_seed / "selected-ppu-alias")
    content = f'''<?xml version="1.0" encoding="utf-8"?>
<Wix xmlns="http://wixtoolset.org/schemas/v4/wxs">
  <Package Name="Plasma Control Station" Manufacturer="Plasma" Version="{_msi_version(version)}"
           UpgradeCode="{UPGRADE_CODE}" Language="1033" Scope="perMachine" InstallerVersion="500">
    <MajorUpgrade DowngradeErrorMessage="A newer Plasma Control Station is already installed." />
    <MediaTemplate EmbedCab="yes" />
    <StandardDirectory Id="ProgramFiles64Folder">
      <Directory Id="PlasmaProgramFiles" Name="Plasma">
        <Directory Id="PlasmaReleases" Name="releases">
          <Directory Id="PlasmaVersion" Name="{escape(version)}">
            <Directory Id="PlasmaBin" Name="bin" />
          </Directory>
        </Directory>
      </Directory>
    </StandardDirectory>
    <StandardDirectory Id="CommonAppDataFolder">
      <Directory Id="PlasmaProgramData" Name="Plasma">
        <Directory Id="PlasmaConfig" Name="config" />
        <Directory Id="PlasmaState" Name="state" />
        <Directory Id="PlasmaLogs" Name="logs" />
      </Directory>
    </StandardDirectory>
    <Files Directory="PlasmaVersion" Include="{root}\\**">
      <Exclude Files="{manager_exe}" />
      <Exclude Files="{console_exe}" />
    </Files>
    <Component Id="ManagerServiceComponent" Directory="PlasmaBin" Guid="A8D35F44-1410-4D2C-817D-797CE88EFA3B">
      <File Id="ManagerServiceExe" Source="{manager_exe}" KeyPath="yes" />
      <ServiceInstall Name="{SERVICE_MANAGER}" DisplayName="Plasma Manager" Description="Plasma Control Station fleet Manager"
                      Start="auto" Type="ownProcess" ErrorControl="normal" />
      <ServiceControl Name="{SERVICE_MANAGER}" Start="install" Stop="both" Remove="uninstall" Wait="yes" />
    </Component>
    <Component Id="ConsoleServiceComponent" Directory="PlasmaBin" Guid="2D6936ED-E228-427E-B579-7E58EC896335">
      <File Id="ConsoleServiceExe" Source="{console_exe}" KeyPath="yes" />
      <ServiceInstall Name="{SERVICE_CONSOLE}" DisplayName="Plasma Control Station" Description="Plasma operator Console and same-host BFF"
                      Start="auto" Type="ownProcess" ErrorControl="normal">
        <ServiceDependency Id="{SERVICE_MANAGER}" />
      </ServiceInstall>
      <ServiceControl Name="{SERVICE_CONSOLE}" Start="install" Stop="both" Remove="uninstall" Wait="yes" />
    </Component>
    <Component Id="ManagerConfigComponent" Directory="PlasmaConfig" Guid="974EBC1C-94C2-40D3-B41E-EBA0A629EE34" Permanent="yes" NeverOverwrite="yes">
      <File Source="{manager_seed}" Name="manager.yaml" KeyPath="yes" />
    </Component>
    <Component Id="SelectedAliasComponent" Directory="PlasmaConfig" Guid="9B132C47-B3B2-423D-A848-175FEAA11B82" Permanent="yes" NeverOverwrite="yes">
      <File Source="{alias_seed}" Name="selected-ppu-alias" KeyPath="yes" />
    </Component>
    <Component Id="StateDirectoryComponent" Directory="PlasmaState" Guid="00834C43-DAA7-4EC5-8E57-29E5479E9EC0" Permanent="yes" KeyPath="yes"><CreateFolder /></Component>
    <Component Id="LogDirectoryComponent" Directory="PlasmaLogs" Guid="05D1C6F2-447C-4B91-9E2A-A399D9B7EB9C" Permanent="yes" KeyPath="yes"><CreateFolder /></Component>
  </Package>
</Wix>
'''
    output_path.write_text(content, encoding="utf-8")


def build_msi(
    *, repo_root: Path, release_artifact: Path, winsw_exe: Path, output_dir: Path,
    wix: str = "wix", system: str | None = None, machine: str | None = None,
) -> Path:
    if (platform.system() if system is None else system) != "Windows":
        raise WindowsInstallerError("Windows MSI build requires Windows")
    normalize_architecture(platform.machine() if machine is None else machine)
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="plasma-windows-msi-") as temporary:
        work = Path(temporary)
        manifest, canonical = verify_release(repo_root.resolve(), release_artifact.resolve(), work / "verified")
        version = str(manifest["product_version"])
        package = output_dir / f"plasma-control-station-{version}-windows-x86_64.msi"
        sidecar = package.with_suffix(".msi.sha256")
        if package.exists() or sidecar.exists():
            raise WindowsInstallerError(f"refusing to overwrite immutable installer output: {package}")
        release_root, seed = stage_payload(
            repo_root=repo_root.resolve(), runtime_dir=canonical / "runtime", staging_root=work / "stage",
            version=version, source_release=manifest, winsw_exe=winsw_exe.resolve(),
        )
        wxs = work / "installer.wxs"
        generate_wix_source(release_root=release_root, program_data_seed=seed, version=version, output_path=wxs)
        try:
            subprocess.run([wix, "build", "-arch", "x64", "-o", str(package), str(wxs)], check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise WindowsInstallerError(f"WiX build failed: {exc}") from exc
    if not package.is_file() or package.stat().st_size <= 0:
        raise WindowsInstallerError("WiX did not create a non-empty MSI")
    sidecar.write_text(f"{_sha256(package)}  {package.name}\n", encoding="utf-8")
    return package


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the unsigned Plasma Windows Control Station MSI pilot")
    parser.add_argument("--release-artifact", required=True, type=Path)
    parser.add_argument("--winsw-exe", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--wix", default="wix")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        print(build_msi(repo_root=args.repo_root, release_artifact=args.release_artifact, winsw_exe=args.winsw_exe, output_dir=args.output_dir, wix=args.wix))
    except (WindowsInstallerError, OSError) as exc:
        print(f"windows-control-station-msi: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

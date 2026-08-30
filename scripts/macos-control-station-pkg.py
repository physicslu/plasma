#!/usr/bin/env python3
"""Build an unsigned macOS .pkg for the Plasma Control Station installer pilot."""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_ROOT_REL = Path("Library") / "Application Support" / "Plasma"
PACKAGE_ID = "com.plasma.control-station"


class MacOSInstallerError(RuntimeError):
    pass


def _load_runtime_module(repo_root: Path):
    script = repo_root / "scripts" / "control-station-runtime.py"
    spec = importlib.util.spec_from_file_location("plasma_control_station_runtime", script)
    if spec is None or spec.loader is None:
        raise MacOSInstallerError(f"cannot load runtime packaging module: {script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def product_version(repo_root: Path) -> str:
    path = repo_root / "release" / "product.json"
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        version = payload["product_version"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise MacOSInstallerError(f"cannot read product version from {path}") from exc
    if not isinstance(version, str) or not version or "/" in version or version in {".", ".."}:
        raise MacOSInstallerError(f"invalid product version: {version!r}")
    return version


def normalize_architecture(machine: str) -> str:
    normalized = machine.strip().lower()
    mapping = {"arm64": "arm64", "aarch64": "arm64", "x86_64": "x86_64", "amd64": "x86_64"}
    try:
        return mapping[normalized]
    except KeyError as exc:
        raise MacOSInstallerError(f"unsupported macOS architecture: {machine}") from exc


def stage_payload(*, repo_root: Path, runtime_dir: Path, staging_root: Path, version: str, validate_runtime: bool = True) -> Path:
    repo_root = repo_root.resolve()
    runtime_dir = runtime_dir.resolve()
    staging_root = staging_root.resolve()
    if staging_root.exists():
        raise MacOSInstallerError(f"refusing to overwrite staging root: {staging_root}")
    if validate_runtime:
        _load_runtime_module(repo_root).validate_runtime(runtime_dir)

    release_root = staging_root / PRODUCT_ROOT_REL / "releases" / version
    runtime_target = release_root / "runtime"
    bin_target = release_root / "bin"
    launchd_target = release_root / "launchd"
    runtime_target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(runtime_dir, runtime_target)
    bin_target.mkdir()
    launchd_target.mkdir()

    for name in ("run-manager.sh", "run-console.sh", "service-control.sh", "uninstall-pilot.sh"):
        source = repo_root / "packaging" / "macos" / name
        if not source.is_file():
            raise MacOSInstallerError(f"missing macOS packaging file: {source}")
        target = bin_target / name
        shutil.copy2(source, target)
        target.chmod(0o755)

    for name in ("com.plasma.manager.plist", "com.plasma.console.plist"):
        source = repo_root / "packaging" / "macos" / name
        if not source.is_file():
            raise MacOSInstallerError(f"missing macOS packaging file: {source}")
        shutil.copy2(source, launchd_target / name)

    installer_manifest = {
        "schema_version": 1,
        "product": "plasma",
        "role": "control-station",
        "platform": "macos",
        "product_version": version,
        "package_identifier": PACKAGE_ID,
        "runtime_root": f"/Library/Application Support/Plasma/releases/{version}/runtime",
        "activation_link": "/Library/Application Support/Plasma/current",
        "service_manager": "launchd-launchagent",
        "console": {"host": "127.0.0.1", "port": 18000},
        "manager": {"host": "127.0.0.1", "port": 18180},
        "external_prerequisites": {"node": ">=22.13", "python": ">=3.11"},
        "signed": False,
        "notarized": False,
        "pilot": True,
    }
    (release_root / "macos-installer.json").write_text(json.dumps(installer_manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return release_root


def _stage_scripts(*, repo_root: Path, scripts_dir: Path, version: str) -> None:
    scripts_dir.mkdir(parents=True)
    template = (repo_root / "packaging" / "macos" / "postinstall.sh").read_text(encoding="utf-8")
    if "__PLASMA_VERSION__" not in template:
        raise MacOSInstallerError("postinstall template is missing version placeholder")
    postinstall = scripts_dir / "postinstall"
    postinstall.write_text(template.replace("__PLASMA_VERSION__", version), encoding="utf-8")
    postinstall.chmod(0o755)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_pkg(*, repo_root: Path, runtime_dir: Path, output_dir: Path, version: str | None = None, pkgbuild: str = "pkgbuild", system: str | None = None, machine: str | None = None) -> Path:
    system = platform.system() if system is None else system
    if system != "Darwin":
        raise MacOSInstallerError(f"macOS .pkg build requires Darwin, got {system}")
    architecture = normalize_architecture(platform.machine() if machine is None else machine)
    version = product_version(repo_root) if version is None else version
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    package_path = output_dir / f"plasma-control-station-{version}-macos-{architecture}.pkg"
    if package_path.exists():
        raise MacOSInstallerError(f"refusing to overwrite package: {package_path}")

    with tempfile.TemporaryDirectory(prefix="plasma-macos-pkg-") as temporary:
        work = Path(temporary)
        root = work / "root"
        scripts = work / "scripts"
        stage_payload(repo_root=repo_root, runtime_dir=runtime_dir, staging_root=root, version=version)
        _stage_scripts(repo_root=repo_root, scripts_dir=scripts, version=version)
        command = [pkgbuild, "--root", str(root), "--scripts", str(scripts), "--identifier", PACKAGE_ID, "--version", version, "--install-location", "/", str(package_path)]
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise MacOSInstallerError(f"pkgbuild failed: {exc}") from exc

    if not package_path.is_file() or package_path.stat().st_size <= 0:
        raise MacOSInstallerError("pkgbuild did not create a non-empty package")
    digest = _sha256(package_path)
    package_path.with_suffix(package_path.suffix + ".sha256").write_text(f"{digest}  {package_path.name}\n", encoding="utf-8")
    return package_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build the Plasma macOS Control Station installer pilot")
    parser.add_argument("--runtime-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--version")
    args = parser.parse_args(argv)
    try:
        package_path = build_pkg(repo_root=args.repo_root, runtime_dir=args.runtime_dir, output_dir=args.output_dir, version=args.version)
    except (MacOSInstallerError, OSError) as exc:
        print(f"macos-control-station-pkg: {exc}", file=sys.stderr)
        return 2
    print(package_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

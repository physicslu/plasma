#!/usr/bin/env python3
"""Build an unsigned macOS .pkg from a verified Plasma Control Station release."""

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
from typing import Mapping, Sequence

REPO_ROOT = Path(__file__).resolve().parents[1]
PRODUCT_ROOT_REL = Path("Library") / "Application Support" / "Plasma"
PACKAGE_ID = "com.plasma.control-station"
RELEASE_ROOT = "plasma-release"


class MacOSInstallerError(RuntimeError):
    pass


def _load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise MacOSInstallerError(f"cannot load packaging module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _runtime_tool(repo_root: Path):
    return _load_script(
        repo_root / "scripts" / "control-station-runtime.py",
        "plasma_macos_control_station_runtime",
    )


def _release_tool(repo_root: Path):
    return _load_script(
        repo_root / "scripts" / "product-release.py",
        "plasma_macos_product_release",
    )


def normalize_architecture(machine: str) -> str:
    normalized = machine.strip().lower()
    mapping = {
        "arm64": "arm64",
        "aarch64": "arm64",
        "x86_64": "x86_64",
        "amd64": "x86_64",
    }
    try:
        return mapping[normalized]
    except KeyError as exc:
        raise MacOSInstallerError(f"unsupported macOS architecture: {machine}") from exc


def verify_release_input(
    *,
    repo_root: Path,
    release_artifact: Path,
    extract_to: Path,
    architecture: str,
) -> tuple[dict[str, object], Path]:
    """Verify the canonical release contract before installer staging."""
    repo_root = repo_root.resolve()
    release_artifact = release_artifact.resolve()
    extract_to = extract_to.resolve()
    release_tool = _release_tool(repo_root)
    try:
        manifest = release_tool.verify_release(
            release_artifact,
            extract_to=extract_to,
            expect_role=release_tool.ROLE_CONTROL_STATION,
            expect_platform="macos",
            expect_architecture=architecture,
        )
    except (OSError, ValueError) as exc:
        raise MacOSInstallerError(f"Control Station release verification failed: {exc}") from exc

    release_root = extract_to / RELEASE_ROOT
    runtime_dir = release_root / "runtime"
    try:
        _runtime_tool(repo_root).validate_runtime(runtime_dir)
    except (OSError, ValueError) as exc:
        raise MacOSInstallerError(f"verified release contains an invalid Control Station runtime: {exc}") from exc
    return dict(manifest), release_root


def stage_payload(
    *,
    repo_root: Path,
    runtime_dir: Path,
    staging_root: Path,
    version: str,
    architecture: str,
    source_release: Mapping[str, object],
) -> Path:
    """Stage installer-owned files from an already verified release runtime."""
    repo_root = repo_root.resolve()
    runtime_dir = runtime_dir.resolve()
    staging_root = staging_root.resolve()
    if staging_root.exists():
        raise MacOSInstallerError(f"refusing to overwrite staging root: {staging_root}")

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

    source_summary = {
        "artifact_sha256": source_release.get("artifact_sha256"),
        "git_sha": source_release.get("git_sha"),
        "target": source_release.get("target"),
        "contracts": source_release.get("contracts"),
    }
    installer_manifest = {
        "schema_version": 1,
        "product": "plasma",
        "role": "control-station",
        "platform": "macos",
        "architecture": architecture,
        "product_version": version,
        "package_identifier": PACKAGE_ID,
        "runtime_root": f"/Library/Application Support/Plasma/releases/{version}/runtime",
        "activation_link": "/Library/Application Support/Plasma/current",
        "service_manager": "launchd-launchagent",
        "console": {"host": "127.0.0.1", "port": 18000},
        "manager": {"host": "127.0.0.1", "port": 18180},
        "external_prerequisites": {"node": ">=22.13", "python": ">=3.11"},
        "source_release": source_summary,
        "signed": False,
        "notarized": False,
        "pilot": True,
    }
    (release_root / "macos-installer.json").write_text(
        json.dumps(installer_manifest, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
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


def build_pkg(
    *,
    repo_root: Path,
    release_artifact: Path,
    output_dir: Path,
    pkgbuild: str = "pkgbuild",
    system: str | None = None,
    machine: str | None = None,
) -> Path:
    system = platform.system() if system is None else system
    if system != "Darwin":
        raise MacOSInstallerError(f"macOS .pkg build requires Darwin, got {system}")
    architecture = normalize_architecture(platform.machine() if machine is None else machine)
    repo_root = repo_root.resolve()
    release_artifact = release_artifact.resolve()
    output_dir = output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="plasma-macos-pkg-") as temporary:
        work = Path(temporary)
        verified = work / "verified-release"
        manifest, canonical_release_root = verify_release_input(
            repo_root=repo_root,
            release_artifact=release_artifact,
            extract_to=verified,
            architecture=architecture,
        )
        version = str(manifest["product_version"])
        package_path = output_dir / f"plasma-control-station-{version}-macos-{architecture}.pkg"
        sidecar_path = package_path.with_suffix(package_path.suffix + ".sha256")
        if package_path.exists() or sidecar_path.exists():
            raise MacOSInstallerError(
                f"refusing to overwrite immutable installer output: {package_path} or {sidecar_path}"
            )

        root = work / "pkg-root"
        scripts = work / "pkg-scripts"
        stage_payload(
            repo_root=repo_root,
            runtime_dir=canonical_release_root / "runtime",
            staging_root=root,
            version=version,
            architecture=architecture,
            source_release=manifest,
        )
        _stage_scripts(repo_root=repo_root, scripts_dir=scripts, version=version)
        command = [
            pkgbuild,
            "--root",
            str(root),
            "--scripts",
            str(scripts),
            "--identifier",
            PACKAGE_ID,
            "--version",
            version,
            "--install-location",
            "/",
            str(package_path),
        ]
        try:
            subprocess.run(command, check=True)
        except (OSError, subprocess.CalledProcessError) as exc:
            raise MacOSInstallerError(f"pkgbuild failed: {exc}") from exc

    if not package_path.is_file() or package_path.stat().st_size <= 0:
        raise MacOSInstallerError("pkgbuild did not create a non-empty package")
    digest = _sha256(package_path)
    sidecar_path.write_text(f"{digest}  {package_path.name}\n", encoding="utf-8")
    return package_path


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build the Plasma macOS Control Station installer pilot from a verified Common Release Format artifact"
    )
    parser.add_argument("--release-artifact", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    args = parser.parse_args(argv)
    try:
        package_path = build_pkg(
            repo_root=args.repo_root,
            release_artifact=args.release_artifact,
            output_dir=args.output_dir,
        )
    except (MacOSInstallerError, OSError) as exc:
        print(f"macos-control-station-pkg: {exc}", file=sys.stderr)
        return 2
    print(package_path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

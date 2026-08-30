#!/usr/bin/env python3
"""Build and validate the source-tree-independent Control Station runtime payload.

This is a build-side packaging tool. It does not install services, mutate a host,
change product configuration, access a PPU, touch FPGA/PL state, or program ICs.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import platform
import shutil
import sys
import tempfile
import tomllib
import zipapp
import zipfile
from pathlib import Path
from typing import Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[1]
RUNTIME_SCHEMA_VERSION = 1
ROLE = "control-station"

FORBIDDEN_RUNTIME_SEGMENTS = {".git", ".hg", ".svn", ".wrangler", "tests"}
FORBIDDEN_RUNTIME_BASENAMES = {
    ".env",
    "package-lock.json",
    "pnpm-lock.yaml",
    "yarn.lock",
    "vite.config.ts",
    "next.config.ts",
}


class RuntimePackagingError(ValueError):
    """Raised when a Control Station runtime payload violates its contract."""


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimePackagingError(f"cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise RuntimePackagingError(f"JSON root must be an object: {path}")
    return value


def _runtime_versions(repo_root: Path) -> tuple[str, str]:
    package = _read_json(repo_root / "software" / "web" / "package.json")
    engines = package.get("engines")
    if not isinstance(engines, dict) or not isinstance(engines.get("node"), str):
        raise RuntimePackagingError("software/web/package.json must declare engines.node")
    node_requirement = str(engines["node"])

    pyproject_path = repo_root / "software" / "python" / "pyproject.toml"
    try:
        pyproject = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
        python_requirement = str(pyproject["project"]["requires-python"])
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise RuntimePackagingError(f"cannot determine Python runtime requirement: {exc}") from exc
    return node_requirement, python_requirement


def _validate_standalone_console(path: Path) -> None:
    if not path.is_dir():
        raise RuntimePackagingError(f"standalone Console directory does not exist: {path}")
    server = path / "server.js"
    if not server.is_file() or server.stat().st_size <= 0:
        raise RuntimePackagingError("standalone Console must contain a non-empty server.js")

    for item in path.rglob("*"):
        relative = item.relative_to(path)
        parts = {part.casefold() for part in relative.parts}
        forbidden = parts & FORBIDDEN_RUNTIME_SEGMENTS
        if forbidden:
            raise RuntimePackagingError(
                f"standalone Console contains source/development segment {sorted(forbidden)[0]!r}: "
                f"{relative.as_posix()}"
            )
        basename = item.name.casefold()
        if basename in FORBIDDEN_RUNTIME_BASENAMES or basename.startswith(".env."):
            raise RuntimePackagingError(
                f"standalone Console contains prohibited source/config file: {relative.as_posix()}"
            )
        if item.is_symlink():
            raise RuntimePackagingError(
                f"standalone Console symlinks are not allowed in the product payload: "
                f"{relative.as_posix()}"
            )


def _yaml_package_dir() -> Path:
    spec = importlib.util.find_spec("yaml")
    locations = list(spec.submodule_search_locations or ()) if spec is not None else []
    if len(locations) != 1:
        raise RuntimePackagingError(
            "PyYAML must be installed in the build environment to package Manager runtime"
        )
    package_dir = Path(locations[0]).resolve()
    if not (package_dir / "__init__.py").is_file():
        raise RuntimePackagingError(f"invalid PyYAML package directory: {package_dir}")
    return package_dir


def _pyyaml_license() -> tuple[str, str]:
    try:
        distribution = importlib.metadata.distribution("PyYAML")
        version = distribution.version
    except importlib.metadata.PackageNotFoundError as exc:
        raise RuntimePackagingError("PyYAML distribution metadata is unavailable") from exc

    license_text = distribution.read_text("LICENSE")
    if not license_text:
        for file in distribution.files or ():
            if Path(str(file)).name.upper().startswith("LICENSE"):
                candidate = distribution.locate_file(file)
                if candidate.is_file():
                    license_text = candidate.read_text(encoding="utf-8")
                    break
    if not license_text:
        raise RuntimePackagingError("PyYAML license text is unavailable in the build environment")
    return version, license_text


def _build_manager_zipapp(repo_root: Path, destination: Path) -> tuple[str, str]:
    manager_source = repo_root / "software" / "python" / "plasma_manager"
    if not manager_source.is_dir():
        raise RuntimePackagingError(f"Manager source package is missing: {manager_source}")
    yaml_source = _yaml_package_dir()
    pyyaml_version, license_text = _pyyaml_license()

    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="plasma-manager-zipapp-") as temporary:
        app_root = Path(temporary)
        shutil.copytree(manager_source, app_root / "plasma_manager")
        shutil.copytree(
            yaml_source,
            app_root / "yaml",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        (app_root / "__main__.py").write_text(
            "from plasma_manager.server import main\n\nmain()\n",
            encoding="utf-8",
        )
        zipapp.create_archive(app_root, destination, compressed=True)

    if not destination.is_file() or destination.stat().st_size <= 0:
        raise RuntimePackagingError("Manager zipapp was not created")
    with zipfile.ZipFile(destination, "r") as archive:
        names = set(archive.namelist())
    required = {"__main__.py", "plasma_manager/server.py", "yaml/__init__.py"}
    missing = sorted(required - names)
    if missing:
        raise RuntimePackagingError(f"Manager zipapp is incomplete: missing {missing}")
    return pyyaml_version, license_text


def _runtime_manifest(
    *, node_requirement: str, python_requirement: str, pyyaml_version: str
) -> dict[str, object]:
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "role": ROLE,
        "processes": {
            "console": {
                "runtime": "node",
                "runtime_requirement": node_requirement,
                "entrypoint": "console/server.js",
                "environment": [
                    "HOST",
                    "PORT",
                    "PLASMA_FLEET_UI_ENABLED",
                    "PLASMA_MANAGER_API_URL",
                    "PLASMA_MANAGER_PPU_ALIAS",
                ],
            },
            "manager": {
                "runtime": "python",
                "runtime_requirement": python_requirement,
                "entrypoint": "manager/manager.pyz",
                "arguments": ["--config", "<manager-config>"],
            },
        },
        "packaging": {
            "console": "vinext-standalone",
            "manager": "python-zipapp",
        },
        "third_party": {
            "PyYAML": {
                "version": pyyaml_version,
                "license": "manager/THIRD_PARTY_LICENSES/PyYAML.txt",
            }
        },
    }


def build_runtime(*, repo_root: Path, standalone_console: Path, output_dir: Path) -> Path:
    repo_root = repo_root.resolve()
    standalone_console = standalone_console.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise RuntimePackagingError(f"refusing to overwrite runtime output: {output_dir}")

    _validate_standalone_console(standalone_console)
    node_requirement, python_requirement = _runtime_versions(repo_root)

    output_dir.mkdir(parents=True)
    try:
        shutil.copytree(standalone_console, output_dir / "console")
        pyyaml_version, license_text = _build_manager_zipapp(
            repo_root, output_dir / "manager" / "manager.pyz"
        )
        license_dir = output_dir / "manager" / "THIRD_PARTY_LICENSES"
        license_dir.mkdir(parents=True, exist_ok=True)
        (license_dir / "PyYAML.txt").write_text(license_text, encoding="utf-8")
        manifest = _runtime_manifest(
            node_requirement=node_requirement,
            python_requirement=python_requirement,
            pyyaml_version=pyyaml_version,
        )
        (output_dir / "control-station-runtime.json").write_text(
            json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        validate_runtime(output_dir)
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise
    return output_dir


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise RuntimePackagingError(f"{field} must be an object")
    return value


def validate_runtime(runtime_dir: Path) -> dict[str, object]:
    runtime_dir = runtime_dir.resolve()
    if not runtime_dir.is_dir():
        raise RuntimePackagingError(f"runtime directory does not exist: {runtime_dir}")
    manifest = _read_json(runtime_dir / "control-station-runtime.json")
    if manifest.get("schema_version") != RUNTIME_SCHEMA_VERSION:
        raise RuntimePackagingError(
            f"unsupported Control Station runtime schema: {manifest.get('schema_version')!r}"
        )
    if manifest.get("role") != ROLE:
        raise RuntimePackagingError("runtime manifest must identify role='control-station'")

    processes = _require_mapping(manifest.get("processes"), "processes")
    if set(processes) != {"console", "manager"}:
        raise RuntimePackagingError("runtime manifest must define exactly console and manager")
    console = _require_mapping(processes["console"], "processes.console")
    manager = _require_mapping(processes["manager"], "processes.manager")
    if console.get("runtime") != "node" or console.get("entrypoint") != "console/server.js":
        raise RuntimePackagingError("Console runtime contract is invalid")
    if manager.get("runtime") != "python" or manager.get("entrypoint") != "manager/manager.pyz":
        raise RuntimePackagingError("Manager runtime contract is invalid")

    _validate_standalone_console(runtime_dir / "console")
    manager_app = runtime_dir / "manager" / "manager.pyz"
    if not manager_app.is_file() or manager_app.stat().st_size <= 0:
        raise RuntimePackagingError("Manager runtime is missing manager/manager.pyz")
    try:
        with zipfile.ZipFile(manager_app, "r") as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise RuntimePackagingError("Manager runtime is not a valid Python zipapp") from exc
    if not {"__main__.py", "plasma_manager/server.py", "yaml/__init__.py"} <= names:
        raise RuntimePackagingError("Manager zipapp is missing required modules")

    third_party = _require_mapping(manifest.get("third_party"), "third_party")
    pyyaml = _require_mapping(third_party.get("PyYAML"), "third_party.PyYAML")
    license_path = pyyaml.get("license")
    if license_path != "manager/THIRD_PARTY_LICENSES/PyYAML.txt":
        raise RuntimePackagingError("PyYAML license path is invalid")
    if not (runtime_dir / str(license_path)).is_file():
        raise RuntimePackagingError("PyYAML license text is missing from runtime payload")

    for item in runtime_dir.rglob("*"):
        relative = item.relative_to(runtime_dir)
        parts = {part.casefold() for part in relative.parts}
        forbidden = parts & FORBIDDEN_RUNTIME_SEGMENTS
        if forbidden:
            raise RuntimePackagingError(
                f"runtime payload contains source/development segment {sorted(forbidden)[0]!r}: "
                f"{relative.as_posix()}"
            )
        basename = item.name.casefold()
        if basename in FORBIDDEN_RUNTIME_BASENAMES or basename.startswith(".env."):
            raise RuntimePackagingError(
                f"runtime payload contains prohibited source/config file: {relative.as_posix()}"
            )
        if item.is_symlink():
            raise RuntimePackagingError(f"runtime payload symlinks are not allowed: {relative.as_posix()}")

    return manifest


def host_target() -> tuple[str, str]:
    system = platform.system()
    platform_name = {"Darwin": "macos", "Linux": "linux", "Windows": "windows"}.get(system)
    if platform_name is None:
        raise RuntimePackagingError(f"unsupported Control Station host OS: {system}")
    machine = platform.machine().strip().lower()
    architecture = {
        "amd64": "x86_64",
        "x86_64": "x86_64",
        "x64": "x86_64",
        "aarch64": "arm64",
        "arm64": "arm64",
    }.get(machine)
    if architecture is None:
        raise RuntimePackagingError(f"unsupported Control Station host architecture: {machine}")
    if platform_name == "windows" and architecture != "x86_64":
        raise RuntimePackagingError("Windows ARM64 is not a supported v1 Control Station target")
    return platform_name, architecture


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build and validate Plasma Control Station runtime payloads")
    subparsers = parser.add_subparsers(dest="command", required=True)

    build_parser = subparsers.add_parser("build")
    build_parser.add_argument("--standalone-console", required=True, type=Path)
    build_parser.add_argument("--output-dir", required=True, type=Path)
    build_parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)

    validate_parser = subparsers.add_parser("validate")
    validate_parser.add_argument("runtime_dir", type=Path)

    subparsers.add_parser("host-target")

    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            runtime = build_runtime(
                repo_root=args.repo_root,
                standalone_console=args.standalone_console,
                output_dir=args.output_dir,
            )
            print(runtime)
            return 0
        if args.command == "validate":
            print(json.dumps(validate_runtime(args.runtime_dir), indent=2, sort_keys=True))
            return 0
        if args.command == "host-target":
            platform_name, architecture = host_target()
            print(json.dumps({"platform": platform_name, "architecture": architecture}, sort_keys=True))
            return 0
    except (RuntimePackagingError, OSError) as exc:
        print(f"control-station-runtime: {exc}", file=sys.stderr)
        return 2
    raise AssertionError(f"unhandled command: {args.command}")


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Build and validate the source-tree-independent Plasma PPU runtime payload.

The PPU runtime contains only the Python control plane required for Plasma Server
and the REST Gateway. It deliberately excludes the Control Console, Manager,
Node.js/npm, Git metadata, FPGA bitstreams, PL access, and real-target tooling.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
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
ROLE = "ppu"
PPU_PACKAGES = (
    "plasma_core",
    "plasma_interfaces",
    "plasma_handlers",
    "plasma_server",
    "plasma_client",
    "plasma_web",
)


class PPURuntimePackagingError(ValueError):
    pass


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PPURuntimePackagingError(f"cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PPURuntimePackagingError(f"JSON root must be an object: {path}")
    return value


def _python_requirement(repo_root: Path) -> str:
    path = repo_root / "software" / "python" / "pyproject.toml"
    try:
        payload = tomllib.loads(path.read_text(encoding="utf-8"))
        return str(payload["project"]["requires-python"])
    except (OSError, KeyError, TypeError, tomllib.TOMLDecodeError) as exc:
        raise PPURuntimePackagingError(f"cannot determine Python runtime requirement: {exc}") from exc


def _yaml_package_dir() -> Path:
    spec = importlib.util.find_spec("yaml")
    locations = list(spec.submodule_search_locations or ()) if spec is not None else []
    if len(locations) != 1:
        raise PPURuntimePackagingError("PyYAML must be installed in the build environment")
    package_dir = Path(locations[0]).resolve()
    if not (package_dir / "__init__.py").is_file():
        raise PPURuntimePackagingError(f"invalid PyYAML package directory: {package_dir}")
    return package_dir


def _pyyaml_license() -> tuple[str, str]:
    try:
        distribution = importlib.metadata.distribution("PyYAML")
    except importlib.metadata.PackageNotFoundError as exc:
        raise PPURuntimePackagingError("PyYAML distribution metadata is unavailable") from exc
    license_text = distribution.read_text("LICENSE")
    if not license_text:
        for item in distribution.files or ():
            if Path(str(item)).name.upper().startswith("LICENSE"):
                candidate = distribution.locate_file(item)
                if candidate.is_file():
                    license_text = candidate.read_text(encoding="utf-8")
                    break
    if not license_text:
        raise PPURuntimePackagingError("PyYAML license text is unavailable")
    return distribution.version, license_text


def _dispatcher_source() -> str:
    return '''from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] in {"-h", "--help"}:
        print("usage: ppu.pyz {server|gateway} [arguments ...]")
        return
    command = sys.argv.pop(1)
    if command == "server":
        from plasma_server.server import main as entrypoint
    elif command == "gateway":
        from plasma_web.gateway_phase2 import main as entrypoint
    else:
        raise SystemExit(f"unsupported PPU process: {command}")
    entrypoint()


main()
'''


def _copy_python_package(source_root: Path, package: str, destination: Path) -> None:
    source = source_root / package
    if not source.is_dir():
        raise PPURuntimePackagingError(f"PPU Python package is missing: {source}")
    shutil.copytree(
        source,
        destination / package,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )


def _build_zipapp(repo_root: Path, destination: Path) -> tuple[str, str]:
    python_root = repo_root / "software" / "python"
    yaml_source = _yaml_package_dir()
    pyyaml_version, license_text = _pyyaml_license()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="plasma-ppu-zipapp-") as temporary:
        app_root = Path(temporary)
        for package in PPU_PACKAGES:
            _copy_python_package(python_root, package, app_root)
        shutil.copytree(
            yaml_source,
            app_root / "yaml",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        (app_root / "__main__.py").write_text(_dispatcher_source(), encoding="utf-8")
        zipapp.create_archive(app_root, destination, compressed=True)
    return pyyaml_version, license_text


def _copy_device_catalog(repo_root: Path, runtime_dir: Path) -> None:
    source = repo_root / "data" / "device-catalog" / "production"
    if not source.is_dir():
        raise PPURuntimePackagingError(f"production Device Catalog is missing: {source}")
    shutil.copytree(source, runtime_dir / "data" / "device-catalog" / "production")


def _manifest(*, python_requirement: str, pyyaml_version: str) -> dict[str, object]:
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "role": ROLE,
        "processes": {
            "server": {
                "runtime": "python",
                "runtime_requirement": python_requirement,
                "entrypoint": "ppu/ppu.pyz",
                "arguments": ["server", "--config", "<ppu-config>"],
                "default_bind": "127.0.0.1:9900",
            },
            "gateway": {
                "runtime": "python",
                "runtime_requirement": python_requirement,
                "entrypoint": "ppu/ppu.pyz",
                "arguments": [
                    "gateway",
                    "--host", "<gateway-bind>",
                    "--port", "18080",
                    "--plasma-host", "127.0.0.1",
                    "--plasma-port", "9900",
                ],
            },
        },
        "packaging": {"python": "python-zipapp"},
        "data": {
            "device_catalog_manifest": "data/device-catalog/production/icpn-v1-manifest.json"
        },
        "third_party": {
            "PyYAML": {
                "version": pyyaml_version,
                "license": "ppu/THIRD_PARTY_LICENSES/PyYAML.txt",
            }
        },
        "hardware_boundary": {
            "loads_fpga": False,
            "accesses_pl": False,
            "changes_target_power": False,
            "programs_real_ic": False,
        },
    }


def build_runtime(*, repo_root: Path, output_dir: Path) -> Path:
    repo_root = repo_root.resolve()
    output_dir = output_dir.resolve()
    if output_dir.exists():
        raise PPURuntimePackagingError(f"refusing to overwrite runtime output: {output_dir}")
    python_requirement = _python_requirement(repo_root)
    output_dir.mkdir(parents=True)
    try:
        pyyaml_version, license_text = _build_zipapp(repo_root, output_dir / "ppu" / "ppu.pyz")
        license_dir = output_dir / "ppu" / "THIRD_PARTY_LICENSES"
        license_dir.mkdir(parents=True, exist_ok=True)
        (license_dir / "PyYAML.txt").write_text(license_text, encoding="utf-8")
        _copy_device_catalog(repo_root, output_dir)
        (output_dir / "ppu-runtime.json").write_text(
            json.dumps(
                _manifest(
                    python_requirement=python_requirement,
                    pyyaml_version=pyyaml_version,
                ),
                indent=2,
                sort_keys=True,
            ) + "\n",
            encoding="utf-8",
        )
        validate_runtime(output_dir)
    except Exception:
        shutil.rmtree(output_dir, ignore_errors=True)
        raise
    return output_dir


def _require_mapping(value: object, field: str) -> Mapping[str, object]:
    if not isinstance(value, dict):
        raise PPURuntimePackagingError(f"{field} must be an object")
    return value


def validate_runtime(runtime_dir: Path) -> dict[str, object]:
    runtime_dir = runtime_dir.resolve()
    if not runtime_dir.is_dir():
        raise PPURuntimePackagingError(f"runtime directory does not exist: {runtime_dir}")
    manifest = _read_json(runtime_dir / "ppu-runtime.json")
    if manifest.get("schema_version") != RUNTIME_SCHEMA_VERSION or manifest.get("role") != ROLE:
        raise PPURuntimePackagingError("invalid PPU runtime identity/schema")
    processes = _require_mapping(manifest.get("processes"), "processes")
    if set(processes) != {"server", "gateway"}:
        raise PPURuntimePackagingError("PPU runtime must define exactly server and gateway")
    app = runtime_dir / "ppu" / "ppu.pyz"
    if not app.is_file() or app.stat().st_size <= 0:
        raise PPURuntimePackagingError("PPU runtime is missing ppu/ppu.pyz")
    try:
        with zipfile.ZipFile(app, "r") as archive:
            names = set(archive.namelist())
    except zipfile.BadZipFile as exc:
        raise PPURuntimePackagingError("PPU runtime is not a valid Python zipapp") from exc
    required = {
        "__main__.py",
        "plasma_core/config.py",
        "plasma_server/server.py",
        "plasma_client/client.py",
        "plasma_web/gateway.py",
        "plasma_web/gateway_phase2.py",
        "plasma_web/ppu_network_activation.py",
        "yaml/__init__.py",
    }
    missing = sorted(required - names)
    if missing:
        raise PPURuntimePackagingError(f"PPU zipapp is incomplete: missing {missing}")
    catalog = runtime_dir / "data" / "device-catalog" / "production" / "icpn-v1-manifest.json"
    if not catalog.is_file():
        raise PPURuntimePackagingError("PPU runtime is missing the production Device Catalog manifest")
    license_path = runtime_dir / "ppu" / "THIRD_PARTY_LICENSES" / "PyYAML.txt"
    if not license_path.is_file() or not license_path.read_text(encoding="utf-8").strip():
        raise PPURuntimePackagingError("PPU runtime is missing the PyYAML license")
    boundary = _require_mapping(manifest.get("hardware_boundary"), "hardware_boundary")
    if any(boundary.get(key) is not False for key in ("loads_fpga", "accesses_pl", "changes_target_power", "programs_real_ic")):
        raise PPURuntimePackagingError("PPU runtime must keep the PL/target hardware boundary closed")
    return manifest


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build or validate a Plasma PPU runtime payload")
    sub = parser.add_subparsers(dest="command", required=True)
    build = sub.add_parser("build")
    build.add_argument("--output-dir", required=True, type=Path)
    build.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    validate = sub.add_parser("validate")
    validate.add_argument("runtime_dir", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.command == "build":
            print(build_runtime(repo_root=args.repo_root, output_dir=args.output_dir))
        else:
            validate_runtime(args.runtime_dir)
            print(args.runtime_dir.resolve())
    except (OSError, PPURuntimePackagingError) as exc:
        print(f"ppu-runtime: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

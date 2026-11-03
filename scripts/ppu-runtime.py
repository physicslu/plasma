#!/usr/bin/env python3
"""Build and validate the source-tree-independent Plasma PPU runtime payload.

The PPU runtime contains only the Python control plane required for Plasma Server,
the REST Gateway, and the bounded local runtime-activation helper. It deliberately
excludes the Control Console, Manager, Node.js/npm, Git metadata, FPGA bitstreams,
PL access, and real-target tooling.
"""

from __future__ import annotations

import argparse
import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
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
IC_SUPPORT_RELATIVE_ROOT = "data/ic-support"
# IC Support is shipped as data only: repository tooling and tests (*.py) stay out.
IC_SUPPORT_DATA_SUFFIXES = frozenset({".json", ".md", ".txt"})
IC_SUPPORT_REQUIRED_DIRECTORIES = ("profiles", "bindings", "manufacturer-baseline", "device-basic")


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
        print("usage: ppu.pyz {server|gateway|runtime-activation-helper} [arguments ...]")
        return
    command = sys.argv.pop(1)
    if command == "server":
        from plasma_server.runtime_server import main as entrypoint
    elif command == "gateway":
        from plasma_web.gateway_phase3 import main as entrypoint
    elif command == "runtime-activation-helper":
        from plasma_web.runtime_activation_helper import main as entrypoint
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


def _ic_support_files(repo_root: Path) -> list[str]:
    source = repo_root / IC_SUPPORT_RELATIVE_ROOT
    if not source.is_dir():
        raise PPURuntimePackagingError(f"IC Support data is missing: {source}")
    try:
        listed = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z", "--", IC_SUPPORT_RELATIVE_ROOT],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        ).stdout.decode("utf-8")
    except (OSError, subprocess.CalledProcessError, UnicodeError) as exc:
        raise PPURuntimePackagingError(f"cannot list repository-owned IC Support data: {exc}") from exc
    prefix = IC_SUPPORT_RELATIVE_ROOT + "/"
    files = sorted(
        name[len(prefix):]
        for name in listed.split("\0")
        if name.startswith(prefix) and Path(name).suffix in IC_SUPPORT_DATA_SUFFIXES
    )
    if not files:
        raise PPURuntimePackagingError("repository-owned IC Support data is empty")
    return files


def _copy_ic_support(repo_root: Path, runtime_dir: Path) -> None:
    source = repo_root / IC_SUPPORT_RELATIVE_ROOT
    destination = runtime_dir / IC_SUPPORT_RELATIVE_ROOT
    for relative in _ic_support_files(repo_root):
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source / relative, target)


def _validate_ic_support(runtime_dir: Path, app: Path, relative: object) -> None:
    if relative != IC_SUPPORT_RELATIVE_ROOT:
        raise PPURuntimePackagingError("PPU runtime IC Support root must be data/ic-support")
    root = runtime_dir / IC_SUPPORT_RELATIVE_ROOT
    missing = [name for name in IC_SUPPORT_REQUIRED_DIRECTORIES if not (root / name).is_dir()]
    if missing:
        raise PPURuntimePackagingError(f"PPU runtime IC Support data is incomplete: missing {missing}")
    if any(path.suffix == ".py" for path in root.rglob("*")):
        raise PPURuntimePackagingError("PPU runtime IC Support data must not contain Python tooling")
    # Load the shipped data with the shipped code only, through the same
    # PLASMA_IC_SUPPORT_ROOT contract the installed services use.
    probe = (
        "import json\n"
        "from plasma_core.ic_support import get_default_ic_support_resolver\n"
        "from plasma_core.manufacturer_device_basic import get_default_manufacturer_device_basic_resolver\n"
        "get_default_manufacturer_device_basic_resolver()\n"
        "print(json.dumps(get_default_ic_support_resolver().summary()['resolved_exact_icpns']))\n"
    )
    environment = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "PLASMA_IC_SUPPORT_ROOT": str(root)}
    completed = subprocess.run(
        [sys.executable, "-I", "-B", "-c", f"import sys; sys.path.insert(0, {str(app)!r}); exec({probe!r})"],
        cwd=runtime_dir,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        timeout=120,
    )
    if completed.returncode != 0:
        raise PPURuntimePackagingError(
            "PPU runtime IC Support data does not load with the shipped runtime: "
            + completed.stderr.strip()[-400:]
        )
    try:
        resolved = int(completed.stdout.strip())
    except ValueError as exc:
        raise PPURuntimePackagingError("PPU runtime IC Support probe returned no summary") from exc
    if resolved <= 0:
        raise PPURuntimePackagingError("PPU runtime IC Support data resolves no exact ICPN")


def _manifest(*, python_requirement: str, pyyaml_version: str) -> dict[str, object]:
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "role": ROLE,
        "processes": {
            "server": {
                "runtime": "python",
                "runtime_requirement": python_requirement,
                "entrypoint": "ppu/ppu.pyz",
                "arguments": [
                    "server",
                    "--config", "<ppu-config>",
                    "--runtime-control-socket", "<server-control-socket>",
                ],
                "default_bind": "127.0.0.1:9900",
            },
            "gateway": {
                "runtime": "python",
                "runtime_requirement": python_requirement,
                "entrypoint": "ppu/ppu.pyz",
                "arguments": [
                    "gateway",
                    "--ppu-config", "<ppu-config>",
                    "--runtime-activation-socket", "<runtime-activation-socket>",
                    "--host", "<gateway-bind>",
                    "--port", "18080",
                    "--plasma-host", "127.0.0.1",
                    "--plasma-port", "9900",
                ],
            },
            "runtime_activation_helper": {
                "runtime": "python",
                "runtime_requirement": python_requirement,
                "entrypoint": "ppu/ppu.pyz",
                "arguments": [
                    "runtime-activation-helper",
                    "--socket", "<runtime-activation-socket>",
                    "--server-control-socket", "<server-control-socket>",
                ],
                "privilege_boundary": "restart-plasma-server-only",
            },
        },
        "packaging": {"python": "python-zipapp"},
        "data": {
            "device_catalog_manifest": "data/device-catalog/production/icpn-v1-manifest.json",
            "ic_support_root": IC_SUPPORT_RELATIVE_ROOT,
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
        _copy_ic_support(repo_root, output_dir)
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
    if set(processes) != {"server", "gateway", "runtime_activation_helper"}:
        raise PPURuntimePackagingError("PPU runtime must define server, gateway, and runtime activation helper")
    server = _require_mapping(processes.get("server"), "processes.server")
    gateway = _require_mapping(processes.get("gateway"), "processes.gateway")
    helper = _require_mapping(processes.get("runtime_activation_helper"), "processes.runtime_activation_helper")
    if server.get("arguments") != [
        "server", "--config", "<ppu-config>", "--runtime-control-socket", "<server-control-socket>"
    ]:
        raise PPURuntimePackagingError("PPU Server runtime must bind canonical config and local control socket")
    gateway_arguments = gateway.get("arguments")
    if not isinstance(gateway_arguments, list):
        raise PPURuntimePackagingError("PPU Gateway runtime arguments must be an array")
    for name, value in (
        ("--ppu-config", "<ppu-config>"),
        ("--runtime-activation-socket", "<runtime-activation-socket>"),
    ):
        try:
            index = gateway_arguments.index(name)
        except ValueError as exc:
            raise PPURuntimePackagingError(f"PPU Gateway runtime must bind {name}") from exc
        if index + 1 >= len(gateway_arguments) or gateway_arguments[index + 1] != value:
            raise PPURuntimePackagingError(f"PPU Gateway {name} has invalid binding")
    if helper.get("arguments") != [
        "runtime-activation-helper",
        "--socket", "<runtime-activation-socket>",
        "--server-control-socket", "<server-control-socket>",
    ] or helper.get("privilege_boundary") != "restart-plasma-server-only":
        raise PPURuntimePackagingError("runtime activation helper contract is not narrow enough")
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
        "plasma_server/runtime_server.py",
        "plasma_server/runtime_control.py",
        "plasma_client/client.py",
        "plasma_interfaces/openocd_rpc.py",
        "plasma_interfaces/openocd_worker.py",
        "plasma_web/gateway.py",
        "plasma_web/openocd_control_plane.py",
        "plasma_web/gateway_phase2.py",
        "plasma_web/gateway_phase3.py",
        "plasma_web/runtime_activation.py",
        "plasma_web/runtime_activation_helper.py",
        "plasma_web/ppu_network_activation.py",
        "yaml/__init__.py",
    }
    missing = sorted(required - names)
    if missing:
        raise PPURuntimePackagingError(f"PPU zipapp is incomplete: missing {missing}")
    catalog = runtime_dir / "data" / "device-catalog" / "production" / "icpn-v1-manifest.json"
    if not catalog.is_file():
        raise PPURuntimePackagingError("PPU runtime is missing the production Device Catalog manifest")
    data = _require_mapping(manifest.get("data"), "data")
    _validate_ic_support(runtime_dir, app, data.get("ic_support_root"))
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

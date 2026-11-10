#!/usr/bin/env python3
"""Build and validate the source-tree-independent Plasma PPU runtime payload.

The PPU runtime contains only the Python control plane required for Plasma Server,
the REST Gateway, and the bounded local runtime-activation helper. It deliberately
excludes the Control Console, Manager, Node.js/npm, Git metadata, FPGA bitstreams,
PL access, real-target tooling, and every IC Catalog / IC Support / qualification
module and data file (offline governance; never a PPU Runtime dependency).
"""

from __future__ import annotations

import argparse
import ast
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import shutil
import sys
import tempfile
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
    "plasma_opf",
    "plasma_server",
    "plasma_client",
    "plasma_web",
)
# OPF S5 / PR-C1: IC Catalog, IC Support and L0-L2 qualification are offline
# governance owned outside the PPU (Device Selector belongs to Manager). The PPU
# runtime ships no Catalog data and none of these Catalog-only modules; the
# Server, Gateway and activation helper never import them.
CATALOG_ONLY_MODULES = (
    "plasma_core/ic_support.py",
    "plasma_core/manufacturer_device_basic.py",
    "plasma_web/legacy_device_selector.py",
    "plasma_web/device_catalog.py",
    "plasma_web/programming_qualification.py",
    "plasma_web/openocd_software_qualification.py",
    "plasma_web/openocd_provider_registry.py",
    "plasma_web/backend_candidate_registry.py",
    "plasma_web/backend_provenance.py",
    "plasma_web/backend_source_reference.py",
    "plasma_web/runtime_evidence_root.py",
    "plasma_web/route_evidence_admission.py",
    "plasma_web/catalog_promotion_framework.py",
    "plasma_web/nxp_kl25_qualification.py",
    "plasma_web/nxp_manufacturer_device_evidence.py",
    "plasma_web/nxp_mcxa_route_evidence.py",
    "plasma_web/microchip_phase1_admission_guard.py",
    "plasma_web/microchip_pic32mx_route_evidence.py",
    "plasma_web/microchip_saml1x_route_evidence.py",
    "plasma_web/microchip_upstream_openocd_evidence.py",
    "plasma_web/c5_host_loader_guard.py",
    "plasma_web/h5_host_readback_guard.py",
)


# PR-B Full-Copy: the Runtime payload carries the complete same-commit
# Bootstrap control plane (Bootstrap, Site Worker v3, Adapter, asset helpers).
# The file set comes from the Bootstrap installer itself (single source).
CONTROL_PLANE_DIR = "control-plane"
CONTROL_PLANE_MANIFEST = "control-plane-manifest.json"
CONTROL_PLANE_SCHEMA = "plasma.ppu.control-plane.v1"
SITE_ADAPTER_MODULE = "ppu_site_adapter_abi5.py"
RUNTIME_SITE_WORKER_CLIENT = "plasma_interfaces/site_worker_c3.py"


class PPURuntimePackagingError(ValueError):
    pass


def _load_script(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise PPURuntimePackagingError(f"cannot load build tool: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _module_assignment(source: str, name: str) -> ast.expr:
    for node in ast.parse(source).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name) and node.targets[0].id == name):
            return node.value
    raise PPURuntimePackagingError(f"module constant is missing: {name}")


def _string_constant(source: str, name: str) -> str:
    value = _module_assignment(source, name)
    if not isinstance(value, ast.Constant) or not isinstance(value.value, str):
        raise PPURuntimePackagingError(f"module constant is not a string literal: {name}")
    return value.value


def _driver_abi(source: str) -> dict[str, list[int]]:
    """``SUPPORTED_DRIVER_ABI = {"driver": frozenset({5})}`` without importing."""
    value = _module_assignment(source, "SUPPORTED_DRIVER_ABI")
    result: dict[str, list[int]] = {}
    if not isinstance(value, ast.Dict):
        raise PPURuntimePackagingError("SUPPORTED_DRIVER_ABI must be a dict literal")
    for key, item in zip(value.keys, value.values):
        if not (isinstance(key, ast.Constant) and isinstance(key.value, str)
                and isinstance(item, ast.Call) and isinstance(item.func, ast.Name)
                and item.func.id == "frozenset" and len(item.args) == 1
                and isinstance(item.args[0], ast.Set)
                and all(isinstance(e, ast.Constant) and type(e.value) is int
                        for e in item.args[0].elts)):
            raise PPURuntimePackagingError("SUPPORTED_DRIVER_ABI has an unsupported shape")
        result[key.value] = sorted(e.value for e in item.args[0].elts)
    return result


def _control_plane_source(repo_root: Path, relative: str) -> Path:
    # Same layout as the factory Bootstrap bundle: flat scripts plus pl/hil,
    # software/python/plasma_interfaces and z2/ source-only inputs.
    if relative.startswith(("pl/", "software/")):
        return repo_root / relative
    return repo_root / "scripts" / relative


def _build_control_plane(repo_root: Path, destination: Path) -> str:
    installer = _load_script(repo_root / "scripts" / "ppu-bootstrap-installer.py",
                             "plasma_ppu_runtime_bootstrap_installer")
    files: dict[str, str] = {}
    for relative in installer.control_plane_files():
        source = _control_plane_source(repo_root, relative)
        if source.is_symlink() or not source.is_file():
            raise PPURuntimePackagingError(f"control-plane source is missing: {relative}")
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        target.chmod(0o755 if os.access(source, os.X_OK) else 0o644)
        files[relative] = hashlib.sha256(target.read_bytes()).hexdigest()
    protocol = _string_constant((destination / "ppu_site_worker.py").read_text(encoding="utf-8"),
                                "PROTOCOL")
    manifest = {
        "schema": CONTROL_PLANE_SCHEMA,
        "site_worker_protocol": protocol,
        "site_adapter": {
            "module": SITE_ADAPTER_MODULE,
            "driver_abi": _driver_abi((destination / "ppu_site_engine.py").read_text(encoding="utf-8")),
        },
        "files": dict(sorted(files.items())),
    }
    (destination / CONTROL_PLANE_MANIFEST).write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return protocol


def _read_json(path: Path) -> dict[str, object]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PPURuntimePackagingError(f"cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise PPURuntimePackagingError(f"JSON root must be an object: {path}")
    return value


def _python_requirement(repo_root: Path) -> str:
    import tomllib  # build host only (Python >= 3.11); kept local for 3.10 test import

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
        for relative in CATALOG_ONLY_MODULES:
            (app_root / relative).unlink(missing_ok=True)
        shutil.copytree(
            yaml_source,
            app_root / "yaml",
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
        )
        (app_root / "__main__.py").write_text(_dispatcher_source(), encoding="utf-8")
        zipapp.create_archive(app_root, destination, compressed=True)
    return pyyaml_version, license_text


def _manifest(*, python_requirement: str, pyyaml_version: str,
              site_worker_protocol: str) -> dict[str, object]:
    return {
        "schema_version": RUNTIME_SCHEMA_VERSION,
        "role": ROLE,
        "control_plane": {
            "path": CONTROL_PLANE_DIR,
            "manifest": CONTROL_PLANE_MANIFEST,
            "site_worker_protocol": site_worker_protocol,
        },
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
                    "--controller-admission-socket", "<controller-admission-socket>",
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
        client_protocol = _string_constant(
            (repo_root / "software" / "python" / RUNTIME_SITE_WORKER_CLIENT).read_text(encoding="utf-8"),
            "PROTOCOL")
        worker_protocol = _build_control_plane(repo_root, output_dir / CONTROL_PLANE_DIR)
        if client_protocol != worker_protocol:
            raise PPURuntimePackagingError(
                f"Site Worker protocol mismatch: Runtime {client_protocol!r} vs Worker {worker_protocol!r}")
        license_dir = output_dir / "ppu" / "THIRD_PARTY_LICENSES"
        license_dir.mkdir(parents=True, exist_ok=True)
        (license_dir / "PyYAML.txt").write_text(license_text, encoding="utf-8")
        (output_dir / "ppu-runtime.json").write_text(
            json.dumps(
                _manifest(
                    python_requirement=python_requirement,
                    pyyaml_version=pyyaml_version,
                    site_worker_protocol=client_protocol,
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
        ("--controller-admission-socket", "<controller-admission-socket>"),
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
        "plasma_opf/__init__.py",
        "plasma_opf/contract.py",
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
    license_path = runtime_dir / "ppu" / "THIRD_PARTY_LICENSES" / "PyYAML.txt"
    if not license_path.is_file() or not license_path.read_text(encoding="utf-8").strip():
        raise PPURuntimePackagingError("PPU runtime is missing the PyYAML license")
    boundary = _require_mapping(manifest.get("hardware_boundary"), "hardware_boundary")
    if any(boundary.get(key) is not False for key in ("loads_fpga", "accesses_pl", "changes_target_power", "programs_real_ic")):
        raise PPURuntimePackagingError("PPU runtime must keep the PL/target hardware boundary closed")
    _validate_control_plane(runtime_dir, manifest, app)
    return manifest


def _validate_control_plane(runtime_dir: Path, manifest: Mapping[str, object], app: Path) -> None:
    """Same verifier the Z2 installer runs, plus the zipapp client protocol."""
    core = _load_script(REPO_ROOT / "scripts" / "ppu-z2-installer-core.py",
                        "plasma_ppu_runtime_installer_core")
    try:
        plane = core.verify_control_plane_tree(runtime_dir, manifest)
    except core.Z2InstallerError as exc:
        raise PPURuntimePackagingError(str(exc)) from exc
    with zipfile.ZipFile(app, "r") as archive:
        try:
            client = archive.read(RUNTIME_SITE_WORKER_CLIENT).decode("utf-8")
        except KeyError as exc:
            raise PPURuntimePackagingError("PPU zipapp is missing the Site Worker client") from exc
    if _string_constant(client, "PROTOCOL") != plane.site_worker_protocol:
        raise PPURuntimePackagingError("Runtime Site Worker client protocol does not match the control plane")


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

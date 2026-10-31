"""Retired standalone Package v1: admission is forbidden.

The reusable integrity, kind, FPGA and rollback contracts are now exercised
against canonical Bundle v3 in test_ppu_bundle_v3_packages_contract.py.
No real hardware, deployment or production files are touched.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SOURCE = "a" * 40
TARGET = {"platform": "linux-armv7", "board": "pynq-z2", "fpga_part": "xc7z020clg400-1"}


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = load("ppu_retired_v1_contract", "ppu_unified_deployment.py")
engine = load("ppu_retired_v1_engine", "ppu-bootstrap-deployment.py")


@pytest.mark.parametrize("kind,filename,data", [
    ("python", "payload/python/wordport.py", b"# retired"),
    ("native-c", "payload/bin/bridge", b"\\x7fELF"),
    ("fpga-image", "payload/fpga/image.bit", b"retired"),
])
def test_retired_v1_cannot_admit_or_stage(tmp_path: Path, kind: str, filename: str, data: bytes):
    archive = tmp_path / "retired-v1.zip"
    manifest = {
        "schema": "plasma.ppu.package.v1", "name": "retired-v1",
        "kind": kind, "version": "1.0.0", "source_commit": SOURCE,
        "target": TARGET,
        "files": [{"path": filename, "sha256": hashlib.sha256(data).hexdigest(),
                   "size": len(data), "executable": filename.startswith("payload/bin/")}],
    }
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        output.writestr(filename, data)
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    paths = engine.DeploymentPaths(
        bootstrap_state_root=tmp_path / "state",
        product_root=tmp_path / "production", config_root=tmp_path / "config",
        runtime_state_root=tmp_path / "runtime", log_root=tmp_path / "logs",
        systemd_root=tmp_path / "systemd",
    )
    co = engine.DeploymentCoordinator(paths=paths, installer=SimpleNamespace(), clock=lambda: 123.0)
    request = engine.HostOnlyPackageRequest(archive, SOURCE, digest, TARGET)
    with pytest.raises(engine.DeploymentError, match="PACKAGE_SCHEMA_UNSUPPORTED"):
        co.execute_package_host_only(request)
    assert not paths.product_root.exists()
    assert not (paths.bootstrap_state_root / "host-only-packages" / "active").exists()


# Legacy wire-format fixture retained solely for explicit rejection tests.
# It is not an admission entitlement or an execution compatibility layer.
SAMPLES = (
    ("wordport", "python", {"payload/python/wordport.py": b"# retired"}),
    ("openocd-integration", "python", {"payload/python/openocd.py": b"# retired"}),
    ("abtest", "python", {"payload/python/abtest.py": b"# retired"}),
)


def package(tmp: Path, name: str, kind: str, files: dict[str, bytes], *,
            alterations: dict | None = None, names_override=None) -> tuple[Path, str]:
    """Construct a retired v1 fixture for negative admission coverage only."""
    tmp.mkdir(parents=True, exist_ok=True)
    entries = [{"path": filename, "sha256": hashlib.sha256(data).hexdigest(),
                "size": len(data), "executable": filename.startswith("payload/bin/")}
               for filename, data in files.items()]
    manifest = {
        "schema": contract.PACKAGE_SCHEMA, "name": name, "kind": kind,
        "version": "2026.10.29", "source_commit": SOURCE,
        "target": TARGET, "files": entries,
    }
    if kind == "fpga-image":
        manifest["fpga_pair"] = {
            "image": "payload/fpga/z2-identity.bit", "handoff": "payload/fpga/z2-identity.hwh"
        }
    if alterations:
        manifest.update(alterations)
    archive = tmp / f"{name}.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("manifest.json", json.dumps(manifest))
        for filename, data in files.items():
            output.writestr(filename if names_override is None else names_override, data)
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()

"""Shared inert ZIP fixtures for host-only deployment tests."""
from __future__ import annotations
import hashlib
import importlib.util
import json
import io
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[3]


def load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


contract = load("ppu_generic_package_contract_gate1", "ppu_unified_deployment.py")
engine = load("ppu_generic_package_engine_gate1", "ppu-bootstrap-deployment.py")
SOURCE = "a" * 40
TARGET = {"platform": "linux-armv7", "board": "pynq-z2", "fpga_part": "xc7z020clg400-1"}
SAMPLES = (
    ("wordport", "python", {
        "payload/python/wordport.py": b"# wordport engine\n",
        "payload/python/wordport.json": b"{\"mode\":\"host-only\"}",
    }),
    ("openocd-integration", "python", {"payload/python/openocd.py": b"# openocd integration\n"}),
    ("abtest", "python", {"payload/python/abtest.py": b"# A/B runner\n"}),
    ("native-bridge", "native-c", {
        "payload/bin/bridge": b"\x7fELFtest-fixture",
        "payload/lib/bridge.so": b"\x7fELFlibrary-fixture",
        "payload/include/bridge.h": b"/* interface fixture */\n",
    }),
    ("z2-identity", "fpga-image", {
        "payload/fpga/z2-identity.bit": b"host-only-image-fixture",
        "payload/fpga/z2-identity.hwh": b"host-only-handoff-fixture",
        "payload/fpga/z2-identity.json": b"{\"schema\":\"host-only-fixture\"}",
    }),
)


def package(tmp: Path, name: str, kind: str, files: dict[str, bytes], *,
            alterations: dict | None = None, names_override=None) -> tuple[Path, str]:
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


def coordinator(tmp: Path):
    paths = engine.DeploymentPaths(
        bootstrap_state_root=tmp / "isolated-bootstrap-state",
        product_root=tmp / "production-untouched", config_root=tmp / "config-untouched",
        runtime_state_root=tmp / "runtime-untouched", log_root=tmp / "log-untouched",
        systemd_root=tmp / "systemd-untouched",
    )
    return engine.DeploymentCoordinator(paths=paths, installer=SimpleNamespace(),
                                       clock=lambda: 123.0)


def request(archive: Path, digest: str):
    return engine.HostOnlyPackageRequest(archive, SOURCE, digest, TARGET)

"""Minimal PR-B Full-Copy control plane for Host-only release fixtures."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

PROTOCOL = "plasma.ppu.site-worker.v3"
REQUIRED = (
    "ppu-bootstrap-installer.py",
    "ppu-bootstrap-deployment.py",
    "ppu_site_worker.py",
    "ppu_site_worker_service.py",
    "ppu_site_engine.py",
    "ppu_site_adapter_abi5.py",
    "ppu_asset_set.py",
)


def write_control_plane(runtime_dir: Path, *, protocol: str = PROTOCOL,
                        worker_protocol: str | None = None,
                        driver_abi: dict | None = None,
                        extra: dict[str, bytes] | None = None) -> dict[str, str]:
    """Write ``runtime_dir/control-plane`` and return the Runtime declaration."""
    root = runtime_dir / "control-plane"
    root.mkdir(parents=True, exist_ok=True)
    contents = {name: f"# {name}\n".encode() for name in REQUIRED}
    contents["ppu_site_worker.py"] = (
        f'"""fixture"""\nPROTOCOL = "{worker_protocol or protocol}"\n'.encode())
    contents.update(extra or {})
    files = {}
    for name, payload in contents.items():
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(payload)
        files[name] = hashlib.sha256(payload).hexdigest()
    manifest = {
        "schema": "plasma.ppu.control-plane.v1",
        "site_worker_protocol": worker_protocol or protocol,
        "site_adapter": {"module": "ppu_site_adapter_abi5.py",
                         "driver_abi": driver_abi or {"plasma_swd": [5]}},
        "files": dict(sorted(files.items())),
    }
    (root / "control-plane-manifest.json").write_text(
        json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {"path": "control-plane", "manifest": "control-plane-manifest.json",
            "site_worker_protocol": protocol}


_REAL: tuple | None = None


def _script(name: str, module: str):
    import importlib.util
    import sys
    root = Path(__file__).resolve().parents[3]
    spec = importlib.util.spec_from_file_location(module, root / "scripts" / name)
    loaded = importlib.util.module_from_spec(spec)
    sys.modules[module] = loaded
    spec.loader.exec_module(loaded)
    return loaded


def real_control_plane():
    """(installer core, runtime dir, runtime manifest) for the repo's real
    same-commit control plane, built once by the release builder."""
    global _REAL
    if _REAL is None:
        import tempfile
        root = Path(__file__).resolve().parents[3]
        core = _script("ppu-z2-installer.py", "ppu_control_plane_fixture_installer_core")
        runtime_tool = _script("ppu-runtime.py", "ppu_control_plane_fixture_runtime_tool")
        runtime = Path(tempfile.mkdtemp(prefix="plasma-full-copy-runtime-"))
        protocol = runtime_tool._build_control_plane(root, runtime / "control-plane")
        _REAL = (core, runtime, {"control_plane": {
            "path": "control-plane", "manifest": "control-plane-manifest.json",
            "site_worker_protocol": protocol}})
    return _REAL


def verify_real_control_plane(_verified=None):
    core, runtime, manifest = real_control_plane()
    return core.verify_control_plane_tree(runtime, manifest)


def installed_control_plane(base: Path, *, git_sha: str = "a" * 40,
                            identity_sha: str | None = None,
                            protocol: str = PROTOCOL) -> tuple[Path, Path]:
    """An installed Bootstrap tree bound to an Active Runtime release:
    returns (control_plane_dir, product_root)."""
    import shutil
    _core, runtime, _manifest = real_control_plane()
    control_plane = base / "bootstrap"
    shutil.copytree(runtime / "control-plane", control_plane)
    (control_plane / "control-plane.json").write_text(json.dumps({
        "schema": "plasma.ppu.control-plane-identity.v1",
        "release_git_sha": identity_sha or git_sha,
        "site_worker_protocol": protocol,
    }), encoding="utf-8")
    product = base / "product"
    (product / "current").mkdir(parents=True)
    (product / "current" / "release.json").write_text(
        json.dumps({"git_sha": git_sha}), encoding="utf-8")
    return control_plane, product

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load(name: str, file_name: str):
    path = ROOT / "scripts" / file_name
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bootstrap = _load("ppu_bootstrap_core", "ppu-bootstrap.py")
service = _load("ppu_bootstrap_service_core", "ppu-bootstrap-service.py")
installer = _load("ppu_bootstrap_installer_core", "ppu-bootstrap-installer.py")


def _machine_id(tmp_path: Path) -> Path:
    path = tmp_path / "machine-id"
    path.write_text("0123456789abcdef0123456789abcdef\n", encoding="utf-8")
    return path


def test_factory_bootstrap_is_independent_when_runtime_is_absent(tmp_path: Path):
    paths = bootstrap.BootstrapPaths(
        product_root=tmp_path / "opt" / "plasma",
        state_root=tmp_path / "state",
        machine_id_path=_machine_id(tmp_path),
    )
    status = bootstrap.status_document(paths)
    assert status["bootstrap"]["state"] == "bootstrap_ready"
    assert status["runtime"]["state"] == "runtime_absent"
    assert status["capabilities"]["fpga_update"] is False
    assert status["identity"]["device_id"].startswith("ppu-device-")


def test_runtime_inspection_accepts_only_canonical_managed_release(tmp_path: Path):
    product = tmp_path / "opt" / "plasma"
    release_id = "0.3.2-" + "a" * 12
    release = product / "releases" / release_id
    release.mkdir(parents=True)
    (release / "release.json").write_text(json.dumps({
        "role": "ppu", "target": "linux-armv7l", "product_version": "0.3.2", "git_sha": "a" * 40,
    }), encoding="utf-8")
    product.mkdir(parents=True, exist_ok=True)
    (product / "current").symlink_to(release)
    paths = bootstrap.BootstrapPaths(product, tmp_path / "state", _machine_id(tmp_path))
    runtime = bootstrap.inspect_runtime(paths)
    assert runtime.state == "runtime_active"
    assert runtime.release_id == release_id


def test_bootstrap_token_is_private_and_rotation_is_explicit(tmp_path: Path):
    token_file = tmp_path / "control-token"
    token = service.provision_token(token_file, token="x" * 40)
    assert token == "x" * 40
    assert token_file.stat().st_mode & 0o777 == 0o600
    assert service.load_token(token_file) == token
    with pytest.raises(service.BootstrapServiceError, match="already exists"):
        service.provision_token(token_file, token="y" * 40)
    token_file.chmod(0o644)
    with pytest.raises(service.BootstrapServiceError, match="permissions"):
        service.load_token(token_file)


def test_chunked_upload_commits_only_after_full_sha256_match(tmp_path: Path):
    paths = service.ServicePaths(
        product_root=tmp_path / "product",
        state_root=tmp_path / "state",
        machine_id_path=_machine_id(tmp_path),
        bootstrap_script=ROOT / "scripts" / "ppu-bootstrap.py",
        kit_tool=ROOT / "scripts" / "ppu-bootstrap-kit.py",
    )
    payload = b"plasma-z2-kit"
    digest = hashlib.sha256(payload).hexdigest()
    created = service.create_upload(paths, size=len(payload), sha256=digest)
    upload_id = created["upload_id"]
    import base64
    service.append_chunk(
        paths,
        upload_id,
        offset=0,
        data_base64=base64.b64encode(payload).decode("ascii"),
        sha256=digest,
    )
    committed = service.commit_upload(paths, upload_id)
    assert committed["state"] == "committed"
    artifact = Path(committed["artifact"])
    assert artifact.read_bytes() == payload
    assert artifact.stat().st_mode & 0o777 == 0o400


def test_interrupted_bootstrap_api_transaction_fails_closed(tmp_path: Path):
    paths = service.ServicePaths(state_root=tmp_path / "state")
    paths.state_root.mkdir(parents=True)
    record = {
        "schema_version": 1,
        "transaction_id": "tx",
        "state": "running",
        "upload_id": "a" * 32,
        "started_at_epoch_s": 1.0,
        "updated_at_epoch_s": 2.0,
        "error_code": None,
        "error": None,
        "result": None,
    }
    paths.deployment_record.write_text(json.dumps(record), encoding="utf-8")
    paths.deployment_record.chmod(0o600)
    recovered = service._recover_interrupted_api_deployment(paths)
    assert recovered["state"] == "recovery_required"
    assert recovered["error_code"] == "interrupted_service_restart"


def test_factory_installer_requires_complete_bootstrap_bundle(tmp_path: Path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "ppu-bootstrap.py").write_text("pass\n", encoding="utf-8")
    with pytest.raises(installer.BootstrapInstallError, match="missing required script"):
        installer.install_bootstrap(
            source_root=source,
            host="192.168.2.99",
            port=18081,
            python_executable="/usr/bin/python3",
            paths=installer.InstallPaths(tmp_path / "install", tmp_path / "state", tmp_path / "unit"),
        )

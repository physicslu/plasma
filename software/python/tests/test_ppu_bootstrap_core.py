from __future__ import annotations

import base64
import hashlib
import importlib.util
import json
import shutil
import sys
import zipfile
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



def _installed_factory_service(tmp_path: Path):
    """Exercise the installed factory copy, not the repository source service."""
    install_root = tmp_path / "factory" / "opt" / "plasma" / "bootstrap"
    state_root = tmp_path / "factory" / "var" / "lib" / "plasma-bootstrap"
    unit = tmp_path / "factory" / "etc" / "systemd" / "system" / "plasma-bootstrap.service"
    result = installer.install_bootstrap(
        source_root=ROOT / "scripts", host="127.0.0.1", port=18081,
        python_executable=sys.executable,
        paths=installer.InstallPaths(install_root, state_root, unit),
        enable_now=False,
    )
    assert result["result"] == "PASS" and result["enabled_now"] is False
    assert result["runtime_installed"] is False and result["fpga_update"] is False
    assert unit.is_file()
    assert state_root.stat().st_mode & 0o777 == 0o700
    for filename in installer.REQUIRED_SCRIPTS:
        destination = install_root / filename
        assert destination.is_file(), filename
        assert destination.read_bytes() == (ROOT / "scripts" / filename).read_bytes()
    assert "ppu_unified_deployment.py" in installer.REQUIRED_SCRIPTS
    assert not (tmp_path / "factory" / "opt" / "plasma" / "current").exists()
    assert not (tmp_path / "factory" / "etc" / "plasma" / "ppu-package-target.json").exists()

    spec = importlib.util.spec_from_file_location(
        "ppu_factory_install_service", install_root / "ppu-bootstrap-service.py"
    )
    assert spec is not None and spec.loader is not None
    installed_service = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = installed_service
    spec.loader.exec_module(installed_service)
    return installed_service, state_root, install_root


def _factory_python_upload(installed_service, paths, tmp_path: Path):
    from .test_ppu_generic_package_host_only_gate1 import TARGET

    file_data = b"# inert factory admission fixture\n"
    file_name = "payload/packages/wordport/wordport.py"
    manifest = {
        "schema": "plasma.ppu.bundle.v3",
        "name": "factory-smoke", "version": "1.0",
        "source_commit": "a" * 40, "target": TARGET,
        "purpose": "factory-smoke",
        "packages": [{
            "id": "wordport", "kind": "python", "version": "1.0",
            "requires": [],
            "files": [{
                "path": file_name, "size": len(file_data),
                "sha256": hashlib.sha256(file_data).hexdigest(),
                "executable": False,
            }],
        }],
    }
    archive = tmp_path / "factory-smoke.zip"
    with zipfile.ZipFile(archive, "w") as zf:
        zf.writestr("manifest.json", json.dumps(manifest))
        zf.writestr(file_name, file_data)
    payload = archive.read_bytes()
    digest = hashlib.sha256(payload).hexdigest()
    created = installed_service.create_upload(paths, size=len(payload), sha256=digest)
    uid = created["upload_id"]
    installed_service.append_chunk(
        paths, uid, offset=0,
        data_base64=base64.b64encode(payload).decode("ascii"),
        sha256=digest,
    )
    assert installed_service.commit_upload(paths, uid)["state"] == "committed"
    return uid, digest


def test_factory_installed_service_can_admit_package_without_installing(tmp_path: Path):
    from .test_ppu_generic_package_host_only_gate1 import TARGET

    installed_service, state_root, install_root = _installed_factory_service(tmp_path)
    profile = tmp_path / "device-owned-profile.json"
    profile.write_text(json.dumps(TARGET), encoding="utf-8")
    profile.chmod(0o600)
    paths = installed_service.ServicePaths(
        state_root=state_root, product_root=tmp_path / "runtime-untouched",
        package_target_file=profile,
        bootstrap_script=install_root / "ppu-bootstrap.py",
        kit_tool=install_root / "ppu-bootstrap-kit.py",
    )
    uid, digest = _factory_python_upload(installed_service, paths, tmp_path)
    server = installed_service.BootstrapHTTPServer(
        ("127.0.0.1", 0), paths=paths, base_module=object(),
        deployment_runner=lambda *_: pytest.fail("runtime deployment must not execute"),
    )
    try:
        result = server.admit_package({"kind": "bundle", "upload_id": uid})
        assert result["state"] == "admitted"
        receipt = result["result"]
        assert receipt["result"] == "PASS"
        assert receipt["stage"] == "package_admission_only"
        assert receipt["install_qualified"] is False
        assert receipt["plan"]["archive_sha256"] == digest
        assert receipt["plan"]["execution_permitted"] is False
        assert receipt["plan"]["target"] == TARGET
        assert server.deployment_thread is None
        assert not paths.coordinator_journal.exists()
        assert not paths.product_root.exists()
    finally:
        server.server_close()


def test_factory_missing_verifier_rejected_before_any_install_changes(tmp_path: Path):
    source = tmp_path / "incomplete-bundle"
    source.mkdir()
    for filename in installer.REQUIRED_SCRIPTS:
        if filename != "ppu_unified_deployment.py":
            shutil.copyfile(ROOT / "scripts" / filename, source / filename)
    root = tmp_path / "existing-bootstrap"
    root.mkdir()
    old_service = root / "ppu-bootstrap-service.py"
    old_service.write_bytes(b"prior-installed-service\n")
    unit = tmp_path / "unit-not-written"
    state = tmp_path / "state-not-written"
    with pytest.raises(installer.BootstrapInstallError,
                       match="missing required script: ppu_unified_deployment.py"):
        installer.install_bootstrap(
            source_root=source, host="127.0.0.1", port=18081,
            python_executable=sys.executable,
            paths=installer.InstallPaths(root, state, unit),
        )
    assert old_service.read_bytes() == b"prior-installed-service\n"
    assert not unit.exists() and not state.exists()


def test_factory_admission_without_device_owned_target_is_denied(tmp_path: Path):
    installed_service, state_root, _ = _installed_factory_service(tmp_path)
    paths = installed_service.ServicePaths(
        state_root=state_root, product_root=tmp_path / "runtime-untouched",
        package_target_file=tmp_path / "never-provisioned-target.json",
    )
    uid, _ = _factory_python_upload(installed_service, paths, tmp_path)
    server = installed_service.BootstrapHTTPServer(
        ("127.0.0.1", 0), paths=paths, base_module=object(),
        deployment_runner=lambda *_: pytest.fail("runtime deployment must not execute"),
    )
    try:
        with pytest.raises(installed_service.BootstrapServiceError,
                           match="PACKAGE_TARGET_PROFILE_UNAVAILABLE"):
            server.admit_package({"kind": "python", "upload_id": uid})
        assert not paths.deployment_record.exists()
        assert not paths.coordinator_journal.exists()
        assert not paths.product_root.exists()
    finally:
        server.server_close()

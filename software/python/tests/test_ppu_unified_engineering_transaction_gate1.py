"""Host-only unified PPU Engineering transaction tests; no Z2/SSH/Root."""
from __future__ import annotations

import fcntl
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "ppu_bootstrap_deployment_unified_gate1",
    ROOT / "scripts" / "ppu-bootstrap-deployment.py",
)
assert SPEC and SPEC.loader
deployment = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = deployment
SPEC.loader.exec_module(deployment)


class QualifiedFakeInstaller:
    """Only a Host-test fake. The production PS-only installer lacks these methods."""

    @staticmethod
    def InstallPaths(**kwargs):
        return SimpleNamespace(**kwargs)

    def __init__(self, *, error: str | None = None):
        self.events: list[str] = []
        self.error = error

    def verify_engineering_package(
        self, artifact: Path, *, module: str, source_commit: str, expected_sha256: str
    ):
        self.events.append("verify")
        assert artifact.read_bytes() == b"mock-reviewed-archive"
        assert module in ("wordport", "openocd-integration", "abtest")
        assert source_commit == "a" * 40
        assert expected_sha256 == hashlib.sha256(b"mock-reviewed-archive").hexdigest()
        return SimpleNamespace(module=module, artifact_sha256=expected_sha256)

    def install_engineering_package(self, verified, *, paths):
        self.events.append("install")
        if self.error == "restored":
            raise deployment.EngineeringInstallRolledBack("verified complete restoration")
        if self.error == "unknown":
            raise RuntimeError("activation interrupted and rollback unconfirmed")
        return {
            "result": "PASS",
            "module": verified.module,
            "archive_sha256": verified.artifact_sha256,
            "no_device_operation": True,
        }


def paths(tmp_path: Path):
    return deployment.DeploymentPaths(
        bootstrap_state_root=tmp_path / "bootstrap",
        product_root=tmp_path / "opt" / "plasma",
        config_root=tmp_path / "etc" / "plasma",
        runtime_state_root=tmp_path / "var" / "lib" / "plasma",
        log_root=tmp_path / "var" / "log" / "plasma",
        systemd_root=tmp_path / "etc" / "systemd" / "system",
    )


def make_request(tmp_path: Path, module: str = "wordport"):
    archive = tmp_path / "engineering.zip"
    archive.write_bytes(b"mock-reviewed-archive")
    return deployment.EngineeringDeploymentRequest(
        archive, module, "a" * 40,
        hashlib.sha256(archive.read_bytes()).hexdigest(),
    )


def coordinator(tmp_path: Path, installer):
    return deployment.DeploymentCoordinator(
        paths=paths(tmp_path), installer=installer,
        clock=lambda: 12345.0,
        transaction_id_factory=lambda: "fixed-transaction",
    )


@pytest.mark.parametrize("module", ["wordport", "openocd-integration", "abtest"])
def test_three_modules_share_one_lock_and_journal(tmp_path: Path, module: str) -> None:
    installer = QualifiedFakeInstaller()
    co = coordinator(tmp_path, installer)
    result = co.execute_engineering(make_request(tmp_path, module))
    assert result["result"] == "PASS"
    assert result["transaction"]["state"] == "engineering_active"
    assert result["transaction"]["kind"] == "engineering-module"
    assert result["transaction"]["module"] == module
    assert installer.events == ["verify", "install"]
    journal = json.loads(co.paths.journal.read_text())
    assert journal["state"] == "engineering_active"
    assert journal["module"] == module
    assert co.paths.journal.stat().st_mode & 0o077 == 0
    assert co.paths.lock.stat().st_mode & 0o077 == 0
    assert "engineering_active" in deployment.SAFE_RESTART_STATES


def test_real_ps_only_installer_has_no_engineering_entry(tmp_path: Path) -> None:
    # No new Root write path is installed or remotely reachable by this PR.
    spec = importlib.util.spec_from_file_location(
        "ppu_ps_only_installer_gate1",
        ROOT / "scripts" / "ppu-z2-installer-core.py",
    )
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = installer
    spec.loader.exec_module(installer)
    co = coordinator(tmp_path, installer)
    with pytest.raises(deployment.DeploymentError, match="ENGINEERING_INSTALL_NOT_QUALIFIED"):
        co.execute_engineering(make_request(tmp_path))
    assert not co.paths.journal.exists()


def test_held_deployment_lock_blocks_engineering(tmp_path: Path) -> None:
    co = coordinator(tmp_path, QualifiedFakeInstaller())
    co.paths.bootstrap_state_root.mkdir(parents=True)
    with co.paths.lock.open("a+b") as held:
        fcntl.flock(held.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        with pytest.raises(deployment.DeploymentError, match="another PPU deployment"):
            co.execute_engineering(make_request(tmp_path))
        assert not co.paths.journal.exists()


@pytest.mark.parametrize("existing", ["runtime_active", "engineering_active", "rolled_back"])
def test_terminal_previous_transaction_admits_engineering(tmp_path: Path, existing: str) -> None:
    co = coordinator(tmp_path, QualifiedFakeInstaller())
    co.paths.bootstrap_state_root.mkdir(parents=True)
    co.paths.journal.write_text(json.dumps({
        "schema_version": 1, "transaction_id": "prior", "state": existing,
        "sequence": 2, "started_at_epoch_s": 1.0, "updated_at_epoch_s": 1.0,
        "release_artifact": "prior.tar.gz",
        "error_code": None, "error_message": None,
    }))
    co.paths.journal.chmod(0o600)
    result = co.execute_engineering(make_request(tmp_path))
    assert result["transaction"]["state"] == "engineering_active"


@pytest.mark.parametrize("previous", ["recovery_required", "activating", "staged", "verifying"])
def test_inflight_unknown_and_recovery_block_without_install(
    tmp_path: Path, previous: str
) -> None:
    installer = QualifiedFakeInstaller()
    co = coordinator(tmp_path, installer)
    co.paths.bootstrap_state_root.mkdir(parents=True)
    co.paths.journal.write_text(json.dumps({
        "schema_version": 1, "transaction_id": "prior", "state": previous,
        "sequence": 2, "started_at_epoch_s": 1.0, "updated_at_epoch_s": 1.0,
        "release_artifact": "prior.tar.gz",
        "error_code": None, "error_message": None,
    }))
    co.paths.journal.chmod(0o600)
    with pytest.raises(deployment.DeploymentError, match="recovery"):
        co.execute_engineering(make_request(tmp_path))
    assert not installer.events
    assert json.loads(co.paths.journal.read_text())["state"] == "recovery_required"


@pytest.mark.parametrize("failure,expected", [
    ("restored", "rolled_back"),
    ("unknown", "recovery_required"),
])
def test_engineering_activation_classifies_recovery_explicitly(
    tmp_path: Path, failure: str, expected: str,
) -> None:
    co = coordinator(tmp_path, QualifiedFakeInstaller(error=failure))
    with pytest.raises(deployment.DeploymentError):
        co.execute_engineering(make_request(tmp_path))
    journal = json.loads(co.paths.journal.read_text())
    assert journal["state"] == expected


def test_broken_integrity_blocks_before_any_activation(tmp_path: Path) -> None:
    req = make_request(tmp_path)
    req.release_artifact.write_bytes(b"tampered-package")
    installer = QualifiedFakeInstaller()
    co = coordinator(tmp_path, installer)
    with pytest.raises(deployment.DeploymentError, match="SHA256_MISMATCH"):
        co.execute_engineering(req)
    assert installer.events == []
    assert json.loads(co.paths.journal.read_text())["state"] == "verify_failed"


@pytest.mark.parametrize("module", ["", "../wordport", "unreviewed", "openocd"])
def test_unapproved_module_never_reaches_installer(tmp_path: Path, module: str) -> None:
    req = make_request(tmp_path, module)
    co = coordinator(tmp_path, QualifiedFakeInstaller())
    with pytest.raises(deployment.DeploymentError, match="MODULE_NOT_ALLOWED"):
        co.execute_engineering(req)
    assert not co.paths.journal.exists()


def test_symlink_archive_never_reaches_installer(tmp_path: Path) -> None:
    req = make_request(tmp_path)
    link = tmp_path / "archive-link.zip"
    link.symlink_to(req.release_artifact)
    co = coordinator(tmp_path, QualifiedFakeInstaller())
    with pytest.raises(deployment.DeploymentError, match="ARCHIVE_UNTRUSTED"):
        co.execute_engineering(
            deployment.EngineeringDeploymentRequest(
                link, req.module, req.source_commit, req.artifact_sha256
            )
        )


def test_engineering_not_exposed_by_existing_http_api(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "ppu_bootstrap_server_engineering_gate1",
        ROOT / "scripts" / "ppu-bootstrap-service.py",
    )
    assert spec and spec.loader
    service = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = service
    spec.loader.exec_module(service)
    with pytest.raises(service.BootstrapServiceError, match="ENGINEERING_INSTALL_NOT_QUALIFIED"):
        service._deployment_request({"kind": "engineering-module", "module": "abtest"})


def test_no_second_ssh_helper_or_installer_added() -> None:
    source = (ROOT / "scripts" / "ppu-bootstrap-deployment.py").read_text()
    assert source.count("def _deployment_lock(") == 1
    assert source.count("fcntl.flock(lock_stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)") == 1
    assert "def execute_engineering(" in source
    assert "install_engineering_package" in source
    assert "python -c" not in source
    assert "subprocess.run(" not in source.split("def execute_engineering(", 1)[1].split("def _execute_locked(",1)[0]


def test_existing_core_verifies_real_bundle_for_all_three_modules_without_install() -> None:
    spec = importlib.util.spec_from_file_location(
        "ppu_z2_verified_engineering_bundle_gate1",
        ROOT / "scripts" / "ppu-z2-installer-core.py",
    )
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = installer
    spec.loader.exec_module(installer)
    client_spec = importlib.util.spec_from_file_location(
        "ppu_engineering_build_client_gate1",
        ROOT / "scripts" / "ppu_deploy.py",
    )
    assert client_spec and client_spec.loader
    client = importlib.util.module_from_spec(client_spec)
    sys.modules[client_spec.name] = client
    client_spec.loader.exec_module(client)
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        for module in client.MODULES:
            manifest, archive_bytes, local = client.build_bundle(module, "a" * 40)
            package = Path(tmp) / (module + ".zip")
            package.write_bytes(archive_bytes)
            receipt = installer.verify_engineering_package(
                package, module=module, source_commit="a" * 40,
                expected_sha256=hashlib.sha256(archive_bytes).hexdigest(),
            )
            assert receipt.module == module
            assert receipt.install_qualified is False
            assert set(receipt.file_names) == set(client.Z2_FILES)
            assert not hasattr(installer, "install_engineering_package")


def test_existing_core_rejects_changed_artifact_and_spoofed_source(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "ppu_z2_engineering_negative_gate1",
        ROOT / "scripts" / "ppu-z2-installer-core.py",
    )
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = installer
    spec.loader.exec_module(installer)
    client_spec = importlib.util.spec_from_file_location(
        "ppu_deploy_package_negative_gate1",
        ROOT / "scripts" / "ppu_deploy.py",
    )
    assert client_spec and client_spec.loader
    client = importlib.util.module_from_spec(client_spec)
    sys.modules[client_spec.name] = client
    client_spec.loader.exec_module(client)
    _, archive_bytes, _ = client.build_bundle("wordport", "a"*40)
    package = tmp_path / "wordport.zip"
    package.write_bytes(archive_bytes)
    digest = hashlib.sha256(archive_bytes).hexdigest()
    with pytest.raises(installer.Z2InstallerError, match="MANIFEST_CONTENT"):
        installer.verify_engineering_package(
            package, module="wordport", source_commit="b"*40, expected_sha256=digest
        )
    package.write_bytes(archive_bytes + b"tampered")
    with pytest.raises(installer.Z2InstallerError, match="SHA256"):
        installer.verify_engineering_package(
            package, module="wordport", source_commit="a"*40, expected_sha256=digest
        )


def test_existing_core_rejects_symlink_package(tmp_path: Path) -> None:
    spec = importlib.util.spec_from_file_location(
        "ppu_z2_engineering_symlink_gate1",
        ROOT / "scripts" / "ppu-z2-installer-core.py",
    )
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = installer
    spec.loader.exec_module(installer)
    package = tmp_path / "engineering.zip"
    package.write_bytes(b"fake")
    link = tmp_path / "shadow.zip"
    link.symlink_to(package)
    with pytest.raises(installer.Z2InstallerError, match="UNTRUSTED"):
        installer.verify_engineering_package(
            link, module="wordport", source_commit="a"*40,
            expected_sha256=hashlib.sha256(b"fake").hexdigest(),
        )


def test_engineering_bundle_rejects_duplicate_manifest_keys() -> None:
    spec = importlib.util.spec_from_file_location(
        "ppu_core_duplicate_json_gate1", ROOT / "scripts" / "ppu-z2-installer-core.py"
    )
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = installer
    spec.loader.exec_module(installer)
    with pytest.raises(installer.Z2InstallerError, match="DUPLICATE_JSON_KEY"):
        json.loads(
            '{"schema":"v1","schema":"v2"}',
            object_pairs_hook=installer._unique_engineering_json_pairs,
        )


def test_engineering_bundle_rejects_zip_symlink(tmp_path: Path) -> None:
    import io
    import stat
    import zipfile
    spec = importlib.util.spec_from_file_location(
        "ppu_core_zip_symlink_gate1", ROOT / "scripts" / "ppu-z2-installer-core.py"
    )
    assert spec and spec.loader
    installer = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = installer
    spec.loader.exec_module(installer)
    client_spec = importlib.util.spec_from_file_location(
        "ppu_deploy_zip_symlink_gate1", ROOT / "scripts" / "ppu_deploy.py"
    )
    assert client_spec and client_spec.loader
    client = importlib.util.module_from_spec(client_spec)
    sys.modules[client_spec.name] = client
    client_spec.loader.exec_module(client)
    _, original, _ = client.build_bundle("wordport", "a" * 40)
    output = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(original)) as source:
        with zipfile.ZipFile(output, "w") as destination:
            for info in source.infolist():
                content = source.read(info.filename)
                if info.filename == "scripts/plasma_wordport_program.py":
                    info = zipfile.ZipInfo(info.filename)
                    info.create_system = 3
                    info.external_attr = (stat.S_IFLNK | 0o777) << 16
                destination.writestr(info, content)
    package = tmp_path / "symlink-package.zip"
    payload = output.getvalue()
    package.write_bytes(payload)
    with pytest.raises(installer.Z2InstallerError, match="FILE_SET_DENIED"):
        installer.verify_engineering_package(
            package, module="wordport", source_commit="a"*40,
            expected_sha256=hashlib.sha256(payload).hexdigest(),
        )

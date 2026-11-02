"""B3 device-installer seam: local filesystem tests, NO real Z2/FPGA/DUT.

Exercise existing Coordinator lock/journal and existing Installer core.
The Bootstrap API test uses its real B1/B2 admission method with a bounded
local runner, not network, systemd or privileged Z2 I/O.
"""
from __future__ import annotations

import base64
import hashlib
import json
import threading
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import (
    ROOT, SOURCE, TARGET, contract, engine, load,
)
from .test_ppu_bundle_v3_smoke_execution_gate1 import (
    build_smoke, run_fixture,
)

installer = load("ppu_b3_z2_installer_gate1", "ppu-z2-installer.py")
bootstrap = load("ppu_b3_bootstrap_service_gate1", "ppu-bootstrap-service.py")


def make_coordinator(tmp_path):
    paths = engine.DeploymentPaths(
        bootstrap_state_root=tmp_path / "state",
        product_root=tmp_path / "product",
        config_root=tmp_path / "config-untouched",
        runtime_state_root=tmp_path / "runtime-untouched",
        log_root=tmp_path / "logs-untouched",
        systemd_root=tmp_path / "systemd-untouched",
    )
    return engine.DeploymentCoordinator(
        paths=paths, installer=installer, clock=lambda: 123.0,
    )


def b3_request(archive, digest):
    return engine.BundleV3InstallRequest(
        archive=archive, source_commit=SOURCE,
        artifact_sha256=digest, target_profile=dict(TARGET),
        api_transaction_id="b" * 32,
    )


def test_real_installer_b3_stages_and_verifies_three_packages_without_activation(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    co = make_coordinator(tmp_path)
    result = co.execute_bundle_v3_install(b3_request(archive, digest))
    assert result["stage"] == "bundle_install_only"
    assert result["transaction"]["state"] == "bundle_installed"
    assert result["per_package_install_executed"] is True
    assert result["runtime_activation_executed"] is False
    assert result["package_order"] == ["ic-catalog", "programming-profile", "python-smoke"]
    assert result["files_verified"] == 3
    root = Path(result["install_path"])
    assert root.is_dir() and root.is_relative_to(co.paths.product_root)
    assert (root / "b3-install.json").is_file()
    # The installed smoke is executed by Z2 nobody, not the root installer.
    assert (root.stat().st_mode & 0o777) == 0o755
    assert ((root / "payload/packages/python-smoke").stat().st_mode & 0o777) == 0o755
    assert ((root / "b3-install.json").stat().st_mode & 0o777) == 0o600
    assert run_fixture(root).stdout.strip().endswith("PASS")
    assert not co.paths.systemd_root.exists()
    assert not co.paths.config_root.exists()
    assert not (co.paths.product_root / "current").exists()


def test_b3_repeat_install_direct_overwrite_without_backup_or_b4(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    co = make_coordinator(tmp_path)
    first = co.execute_bundle_v3_install(b3_request(archive, digest))
    second = co.execute_bundle_v3_install(b3_request(archive, digest))
    assert second["result"] == "PASS"
    assert first["install_path"] == second["install_path"]
    assert second["transaction"]["state"] == "bundle_installed"
    root = Path(second["install_path"])
    assert not list(root.parent.glob(".*.staging"))
    assert not list(root.parent.glob("*.old"))
    assert run_fixture(root).returncode == 0


def test_b3_archive_hash_denied_without_product_mutation(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    co = make_coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match="B3_BUNDLE_VERIFICATION_DENIED"):
        co.execute_bundle_v3_install(b3_request(archive, "0" * 64))
    assert co.journal.read().state == "verify_failed"
    assert not co.paths.product_root.exists()


def test_b3_existing_unowned_directory_is_never_deleted(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    co = make_coordinator(tmp_path)
    dest = co.paths.product_root / "bundles" / "ppu-b3-smoke"
    dest.mkdir(parents=True)
    (dest / "important.txt").write_text("unrelated")
    with pytest.raises(engine.DeploymentError, match="B3_INSTALL_REQUIRES_RECOVERY"):
        co.execute_bundle_v3_install(b3_request(archive, digest))
    assert (dest / "important.txt").read_text() == "unrelated"
    assert co.journal.read().state == "recovery_required"


def test_b3_existing_symlink_fail_closed(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    co = make_coordinator(tmp_path)
    dest = co.paths.product_root / "bundles" / "ppu-b3-smoke"
    dest.parent.mkdir(parents=True)
    external = tmp_path / "external"
    external.mkdir()
    dest.symlink_to(external, target_is_directory=True)
    with pytest.raises(engine.DeploymentError, match="B3_INSTALL_REQUIRES_RECOVERY"):
        co.execute_bundle_v3_install(b3_request(archive, digest))
    assert dest.is_symlink()
    assert not list(external.iterdir())
    assert co.journal.read().state == "recovery_required"


def test_bootstrap_b2_admission_then_b3_requires_exact_factory_policy(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    source_policy = {
        "schema": "plasma.ppu.b3-factory-policy.v1",
        "bundle_name": "ppu-b3-smoke",
        "source_commit": SOURCE,
        "archive_sha256": digest,
        "target": dict(TARGET),
        "actions": ["install", "verify"],
    }
    paths = bootstrap.ServicePaths(
        product_root=tmp_path / "product",
        state_root=tmp_path / "state",
        package_target_file=tmp_path / "trusted-target.json",
        bundle_install_policy=tmp_path / "trusted-policy.json",
    )
    paths.package_target_file.write_text(json.dumps(TARGET))
    paths.package_target_file.chmod(0o600)
    paths.bundle_install_policy.write_text(json.dumps(source_policy))
    paths.bundle_install_policy.chmod(0o600)

    srv = object.__new__(bootstrap.BootstrapHTTPServer)
    srv.bootstrap_paths = paths
    srv.mutation_lock = threading.RLock()
    srv.deployment_thread = None

    def runner(used_paths, upload_id, request):
        assert used_paths is paths
        assert request["api_transaction_id"] != "b" * 32
        co = make_coordinator(tmp_path)
        real = engine.BundleV3InstallRequest(
            archive=bootstrap._upload_paths(paths, upload_id).committed,
            source_commit=SOURCE, artifact_sha256=digest,
            target_profile=TARGET, api_transaction_id=request["api_transaction_id"],
        )
        return co.execute_bundle_v3_install(real)
    srv.bundle_install_runner = runner
    # Without B2, B3 is forbidden and cannot stage software.
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_MATCHING_B2_ADMISSION_REQUIRED"):
        srv.start_deployment({"kind": "bundle", "upload_id": "a" * 32, "install_only": True})
    raw = archive.read_bytes()
    upload = bootstrap.create_upload(paths, size=len(raw), sha256=digest)
    upload_id = upload["upload_id"]
    bootstrap.append_chunk(
        paths, upload_id, offset=0,
        data_base64=base64.b64encode(raw).decode("ascii"),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    bootstrap.commit_upload(paths, upload_id)
    b2 = srv.start_deployment({"kind": "bundle", "upload_id": upload_id})
    assert b2["state"] == "admitted"
    assert b2["result"]["plan"]["bundle_schema"] == contract.BUNDLE_SCHEMA
    assert b2["result"]["install_qualified"] is False
    assert not paths.product_root.exists()

    # Policy is supplied from the factory root, never an HTTP caller field.
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_INSTALL_REQUEST_FIELDS_DENIED"):
        srv.start_deployment({"kind": "bundle", "upload_id": upload_id,
                              "install_only": True, "publisher": "caller"})
    new = dict(source_policy, archive_sha256="f" * 64)
    paths.bundle_install_policy.write_text(json.dumps(new))
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_ADMISSION_NOT_PINNED"):
        srv.start_deployment({"kind": "bundle", "upload_id": upload_id,
                              "install_only": True})
    paths.bundle_install_policy.write_text(json.dumps(source_policy))

    srv.start_deployment({"kind": "bundle", "upload_id": upload_id, "install_only": True})
    assert srv.deployment_thread is not None
    srv.deployment_thread.join(timeout=10)
    assert not srv.deployment_thread.is_alive()
    result = bootstrap._deployment_api_record(paths)
    assert result["state"] == "succeeded", result.get("error_code")
    assert result["result"]["stage"] == "bundle_install_only"
    assert result["result"]["coordinator_receipt"]["coordinator_state"] == "bundle_installed"
    assert result["result"]["runtime_activation_executed"] is False
    assert not (paths.product_root / "current").exists()

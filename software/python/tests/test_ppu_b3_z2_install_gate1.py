"""B3 device-installer seam: local filesystem tests, NO real Z2/FPGA/DUT.

Exercise existing Coordinator lock/journal and existing Installer core.
The Bootstrap API test uses its real B1/B2 admission method with a bounded
local runner, not network, systemd or privileged Z2 I/O.
"""
from __future__ import annotations

import base64
from contextlib import contextmanager
import hashlib
import json
import stat
import threading
import zipfile
from pathlib import Path

import pytest

from .ppu_owner_authorization_fixture import admit_body, install_body, machine_id_file

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


def b3_request(archive, digest, *, mode="stage_only"):
    return engine.BundleV3InstallRequest(
        archive=archive,
        artifact_sha256=digest, target_profile=dict(TARGET),
        api_transaction_id="b" * 32, mode=mode,
    )


def test_real_installer_b3_stages_and_verifies_three_packages_without_activation(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    co = make_coordinator(tmp_path)
    result = co.execute_bundle_v3_install(b3_request(archive, digest))
    assert result["stage"] == "bundle_staged_only"
    assert result["transaction"]["state"] == "bundle_installed"
    assert result["per_package_install_executed"] is True
    assert result["runtime_activation_executed"] is False
    assert result["package_order"] == ["ic-catalog", "programming-profile", "python-smoke"]
    assert result["files_verified"] == 3
    root = Path(result["install_path"])
    assert root.is_dir() and root.is_relative_to(co.paths.product_root)
    assert (root / "b3-install.json").is_file()
    assert (root / "manifest.json").is_file()
    assert json.loads((root / "manifest.json").read_text())["schema"] == "plasma.ppu.bundle.v3"
    assert root.parent.name == "staged"
    assert root.name == digest
    # The installed smoke is executed by Z2 nobody, not the root installer.
    assert (root.stat().st_mode & 0o777) == 0o755
    assert ((root / "payload/packages/python-smoke").stat().st_mode & 0o777) == 0o755
    assert ((root / "b3-install.json").stat().st_mode & 0o777) == 0o444
    assert run_fixture(root).stdout.strip().endswith("PASS")
    assert not co.paths.systemd_root.exists()
    assert not co.paths.config_root.exists()
    assert not (co.paths.product_root / "current").exists()


def test_b3_repeat_install_reuses_immutable_content_without_backup_or_b4(tmp_path):
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
    dest = co.paths.product_root / "assets" / "staged" / digest
    dest.mkdir(parents=True)
    (dest / "important.txt").write_text("unrelated")
    with pytest.raises(engine.DeploymentError, match="B3_INSTALL_REQUIRES_RECOVERY"):
        co.execute_bundle_v3_install(b3_request(archive, digest))
    assert (dest / "important.txt").read_text() == "unrelated"
    assert co.journal.read().state == "recovery_required"


def test_b3_existing_symlink_fail_closed(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    co = make_coordinator(tmp_path)
    dest = co.paths.product_root / "assets" / "staged" / digest
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
        "schema": "plasma.ppu.b3-install-policy.v2",
        "mode": "development",
        "modes": ["activate", "stage_only"],
        "actions": ["install", "verify"],
    }
    paths = bootstrap.ServicePaths(
        product_root=tmp_path / "product",
        state_root=tmp_path / "state",
        package_target_file=tmp_path / "trusted-target.json",
        bundle_install_policy=tmp_path / "trusted-policy.json",
        machine_id_path=machine_id_file(tmp_path),
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
             artifact_sha256=digest,
            target_profile=TARGET, api_transaction_id=request["api_transaction_id"],
            mode=request["mode"], fpga_load=request["fpga_load"],
        )
        return co.execute_bundle_v3_install(real)
    srv.bundle_install_runner = runner
    # Without B2, B3 is forbidden and cannot stage software.
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_MATCHING_B2_ADMISSION_REQUIRED"):
        srv.start_deployment({"kind": "bundle", "upload_id": "a" * 32,
                              "mode": "stage_only", "fpga_load": False,
                              "authorization": {}})
    raw = archive.read_bytes()
    upload = bootstrap.create_upload(paths, size=len(raw), sha256=digest)
    upload_id = upload["upload_id"]
    bootstrap.append_chunk(
        paths, upload_id, offset=0,
        data_base64=base64.b64encode(raw).decode("ascii"),
        sha256=hashlib.sha256(raw).hexdigest(),
    )
    bootstrap.commit_upload(paths, upload_id)
    b2 = srv.start_deployment(admit_body(paths, "bundle", upload_id))
    assert b2["state"] == "admitted"
    assert b2["result"]["plan"]["bundle_schema"] == contract.BUNDLE_SCHEMA
    assert b2["result"]["install_qualified"] is False
    assert not paths.product_root.exists()

    # Policy is supplied from the factory root, never an HTTP caller field.
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_INSTALL_REQUEST_FIELDS_DENIED"):
        srv.start_deployment({**install_body(paths, b2, fpga_load=False),
                              "publisher": "caller"})
    new = dict(source_policy, mode="untrusted")
    paths.bundle_install_policy.write_text(json.dumps(new))
    with pytest.raises(bootstrap.BootstrapServiceError, match="B3_INSTALL_POLICY_INVALID"):
        srv.start_deployment(install_body(paths, b2, fpga_load=False))
    paths.bundle_install_policy.write_text(json.dumps(source_policy))

    # B3 never treats the B2 receipt as install authority: the B2 admit
    # authorization cannot be replayed as a B3 install authorization.
    replay = install_body(paths, b2, fpga_load=False)
    replay["authorization"] = admit_body(paths, "bundle", upload_id)["authorization"]
    with pytest.raises(bootstrap.BootstrapServiceError,
                       match="OWNER_AUTHORIZATION_ACTION_MISMATCH"):
        srv.start_deployment(replay)

    srv.start_deployment(install_body(paths, b2, fpga_load=False))
    assert srv.deployment_thread is not None
    srv.deployment_thread.join(timeout=10)
    assert not srv.deployment_thread.is_alive()
    result = bootstrap._deployment_api_record(paths)
    assert result["state"] == "succeeded", result.get("error_code")
    assert result["result"]["stage"] == "bundle_staged_only"
    assert result["result"]["coordinator_receipt"]["coordinator_state"] == "bundle_installed"
    assert result["result"]["runtime_activation_executed"] is False
    assert not (paths.product_root / "current").exists()


def build_generic_assets(tmp_path, *, bitstream=b"fpga-image-v1", fpga_manifest=None):
    """Canonical, nonexecuting multi-kind Bundle; unrelated to smoke fixture."""
    tmp_path.mkdir(parents=True, exist_ok=True)
    archive = tmp_path / "assets.zip"
    package_specs = [
        ("swd-parser", "python", (), {"python/parse.py": b"raise RuntimeError('NOT_EXECUTED')\\n"}),
        ("custom-swd", "fpga-image", (), {
            "fpga/swd.bin": bitstream, "fpga/swd.hwh": b"<hwh/>",
            "fpga/image.json": (
                fpga_manifest if fpga_manifest is not None
                else b'{"image_id":"custom-swd"}'
            ),
        }),
        ("stm32-profile", "programming-profile", ("custom-swd", "swd-parser"), {
            "data/profile.json": b'{"icpn":"STM32F103C8T6"}',
        }),
    ]
    files = {}
    packages = []
    for package_id, kind, requires, members in package_specs:
        entries = []
        for suffix, raw in members.items():
            name = f"payload/packages/{package_id}/{suffix}"
            entries.append({
                "path": name, "sha256": hashlib.sha256(raw).hexdigest(),
                "size": len(raw), "executable": False,
            })
            files[name] = raw
        packages.append({
            "id": package_id, "kind": kind, "version": "1.0.0",
            "requires": list(requires), "files": entries,
        })
    manifest = {
        "schema": "plasma.ppu.bundle.v3", "name": "general-assets",
        "version": "1.0.0", "purpose": "programming", "source_commit": SOURCE,
        "target": dict(TARGET), "actions": ["install", "verify"],
        "packages": packages,
    }
    files["manifest.json"] = json.dumps(manifest, sort_keys=True).encode()
    with zipfile.ZipFile(archive, "w") as dest:
        for name, raw in sorted(files.items()):
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.create_system = 3
            info.external_attr = (stat.S_IFREG | 0o644) << 16
            info.compress_type = zipfile.ZIP_STORED
            dest.writestr(info, raw)
    return archive, hashlib.sha256(archive.read_bytes()).hexdigest()


def test_generic_b3_installs_python_fpga_profile_without_execution(tmp_path):
    archive, sha = build_generic_assets(tmp_path / "new-archive")
    co = make_coordinator(tmp_path)
    evidence = co.execute_bundle_v3_install(b3_request(archive, sha))
    assert evidence["result"] == "PASS"
    assert evidence["package_order"] == ["swd-parser", "custom-swd", "stm32-profile"]
    assert evidence["files_verified"] == 5  # Parser + BIN/HWH/JSON + Profile
    assert evidence["runtime_activation_executed"] is False
    assert evidence["fpga"] == "NOT_RUN" and evidence["dut"] == "NOT_RUN"
    root = Path(evidence["install_path"])
    assert root == co.paths.product_root / "assets" / "staged" / sha
    assert (root / "payload/packages/custom-swd/fpga/swd.bin").read_bytes() == b"fpga-image-v1"
    assert (root / "payload/packages/swd-parser/python/parse.py").is_file()
    assert not (co.paths.product_root / "current").exists()
    assert not (co.paths.product_root / "assets" / "active").exists()
    assert not co.paths.systemd_root.exists()


def test_generic_b3_same_bundle_name_different_content_stages_independently(tmp_path):
    a, sa = build_generic_assets(tmp_path / "a")
    b, sb = build_generic_assets(tmp_path / "b", bitstream=b"fpga-image-v2")
    assert sa != sb
    co = make_coordinator(tmp_path)
    pa = Path(co.execute_bundle_v3_install(b3_request(a, sa))["install_path"])
    pb = Path(co.execute_bundle_v3_install(b3_request(b, sb))["install_path"])
    assert pa != pb and pa.is_dir() and pb.is_dir()
    assert (pa / "payload/packages/custom-swd/fpga/swd.bin").read_bytes() == b"fpga-image-v1"
    assert (pb / "payload/packages/custom-swd/fpga/swd.bin").read_bytes() == b"fpga-image-v2"


def test_generic_b3_rejects_corrupted_existing_digest_stage(tmp_path):
    archive, sha = build_generic_assets(tmp_path / "archive")
    co = make_coordinator(tmp_path)
    path = Path(co.execute_bundle_v3_install(b3_request(archive, sha))["install_path"])
    damaged = path / "payload/packages/custom-swd/fpga/swd.bin"
    damaged.chmod(0o600)
    damaged.write_bytes(b"bad")
    with pytest.raises(engine.DeploymentError, match="B3_INSTALL_REQUIRES_RECOVERY"):
        co.execute_bundle_v3_install(b3_request(archive, sha))
    assert damaged.read_bytes() == b"bad"
    assert co.journal.read().state == "recovery_required"


def test_generic_b3_rejects_symlinked_asset_root_without_external_write(tmp_path):
    archive, digest = build_generic_assets(tmp_path / "archive")
    co = make_coordinator(tmp_path)
    external = tmp_path / "external"
    external.mkdir()
    co.paths.product_root.mkdir()
    (co.paths.product_root / "assets").symlink_to(external, target_is_directory=True)
    with pytest.raises(engine.DeploymentError, match="B3_INSTALL_REQUIRES_RECOVERY"):
        co.execute_bundle_v3_install(b3_request(archive, digest))
    assert not list(external.iterdir())
    assert co.journal.read().state == "recovery_required"


def test_b3_standard_no_fpga_activates_once_with_held_runtime_lease(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    co = make_coordinator(tmp_path)
    events = []

    @contextmanager
    def lease():
        events.append("acquired")
        try:
            yield {"lease_kind": "connection_held", "active_job_count": 0}
        finally:
            events.append("released")

    co.quiescence_lease = lease
    first = co.execute_bundle_v3_install(b3_request(archive, digest, mode="activate"))
    second = co.execute_bundle_v3_install(b3_request(archive, digest, mode="activate"))
    assert events == ["acquired", "released", "acquired", "released"]
    assert first["stage"] == "bundle_install_and_activate"
    assert first["mode"] == second["mode"] == "activate"
    assert first["ready"] is second["ready"] is False
    assert first["fpga"] == second["fpga"] == "NOT_RUN"
    assert first["active_asset_set"] == {
        "asset_set_sha256": digest, "generation": 1, "already_active": False,
    }
    assert second["active_asset_set"] == {
        "asset_set_sha256": digest, "generation": 1, "already_active": True,
    }
    assert second["transaction"]["state"] == "asset_set_active"
    active = json.loads((co.paths.product_root / "assets" / "active.json").read_text())
    assert active["asset_set_sha256"] == digest
    assert active["generation"] == 1


def test_b3_no_fpga_quiescence_denial_does_not_change_active(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    co = make_coordinator(tmp_path)

    @contextmanager
    def denied_lease():
        raise RuntimeError("RUNNING_OR_QUEUED_JOB")
        yield

    co.quiescence_lease = denied_lease
    with pytest.raises(engine.DeploymentError, match="B3_RUNTIME_QUIESCE_DENIED"):
        co.execute_bundle_v3_install(b3_request(archive, digest, mode="activate"))
    assert co.journal.read().state == "verify_failed"
    assert co.journal.read().error_code == "b3_runtime_quiesce_denied"
    assert not (co.paths.product_root / "assets" / "active.json").exists()
    assert (co.paths.product_root / "assets" / "staged" / digest).exists()


def test_b3_no_fpga_unknown_active_publish_requires_recovery(tmp_path):
    archive, digest = build_smoke(tmp_path / "bundle")
    co = make_coordinator(tmp_path)

    @contextmanager
    def held():
        yield {"lease_kind": "connection_held", "active_job_count": 0}

    co.quiescence_lease = held
    helper = co._asset_helper()
    def failed_publish(*_args, **_kwargs):
        raise OSError("INJECTED_UNCERTAIN_FSYNC")
    helper.activate_verified = failed_publish
    co._asset_helper = lambda: helper
    with pytest.raises(engine.DeploymentError, match="B3_ACTIVE_SET_PUBLISH_REQUIRES_RECOVERY"):
        co.execute_bundle_v3_install(b3_request(archive, digest, mode="activate"))
    assert co.journal.read().state == "recovery_required"
    with pytest.raises(engine.DeploymentError, match="requires recovery"):
        co.execute_bundle_v3_install(b3_request(archive, digest, mode="stage_only"))
    # Only an activation path may recover the pointer under the same lease.
    with co._deployment_lock(recover_assets=True):
        assert co.journal.read().state == "rolled_back"
    assert not (co.paths.product_root / "assets" / "active.json").exists()


@pytest.mark.parametrize("mode,load", [
    ("", False), ("install_only", False), ("stage_only", True),
])
def test_b3_rejects_ambiguous_mode_without_install(tmp_path, mode, load):
    archive, digest = build_smoke(tmp_path / "bundle")
    request = engine.BundleV3InstallRequest(
        archive=archive,  artifact_sha256=digest,
        target_profile=dict(TARGET), api_transaction_id="b" * 32,
        mode=mode, fpga_load=load,
    )
    co = make_coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match="B3_MODE_INVALID|B3_STAGE_ONLY_FPGA_LOAD_DENIED"):
        co.execute_bundle_v3_install(request)
    assert not co.paths.product_root.exists()

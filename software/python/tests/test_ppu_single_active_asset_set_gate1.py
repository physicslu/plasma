"""P1 Single Active Asset Set: Host-only filesystem and Coordinator tests.

Never operate real Z2, PS/PL, FPGA Manager, network, root or DUT.
"""
from __future__ import annotations

import json
import threading
import urllib.request
from contextlib import contextmanager, nullcontext
from pathlib import Path
from types import SimpleNamespace

import pytest

from .test_ppu_bundle_v3_packages_contract import load
from .test_ppu_b3_z2_install_gate1 import (
    b3_request, build_generic_assets, make_coordinator, bootstrap,
)

assets = load("ppu_single_active_asset_set_gate1", "ppu_asset_set.py")


@pytest.mark.parametrize("state", ["received", "verifying", "verified"])
def test_p4_restart_before_asset_mutation_is_safe_to_retry(tmp_path, state):
    co, _, _ = stage(tmp_path)
    co.journal.write(co.journal.read(), state)
    with co._deployment_lock():
        assert co.journal.read().state == "verify_failed"
    assert co.asset_status()["state"] == "EMPTY"


def test_p4_api_restart_reuses_coordinator_rollback_and_reports_failure(tmp_path, monkeypatch):
    co, candidate, _ = stage(tmp_path)
    co.quiescence_lease = nullcontext
    previous = assets.read_active(co.paths.product_root)
    record = co.journal.read()
    co.journal.write(record, "activating", asset_activation_previous=previous,
                     asset_activation_fpga=False)
    assets.activate_verified(co.paths.product_root, candidate, runtime_quiesced=True)
    paths = bootstrap.ServicePaths(product_root=co.paths.product_root,
                                   state_root=co.paths.bootstrap_state_root)
    bootstrap._atomic_json(paths.deployment_record, {
        "schema_version": 1, "upload_id": "a" * 32,
        "transaction_id": record.api_transaction_id, "state": "running",
    })
    original_load = bootstrap._load_script
    def load_engine(path, name):
        module = original_load(path, name)
        # Only inject the host lease. Recovery still uses the real filesystem,
        # Coordinator, lock, journal and publisher.
        module.DeploymentCoordinator = lambda **kwargs: co
        return module
    monkeypatch.setattr(bootstrap, "_load_script", load_engine)
    result = bootstrap._recover_interrupted_api_deployment(paths)
    assert result["state"] == "failed"
    assert result["error_code"] == "asset_activation_rolled_back"
    assert co.journal.read().state == "rolled_back"
    assert assets.read_active(co.paths.product_root)["state"] == "EMPTY"


def test_p4_assets_get_exposes_recovery_without_socket_or_ready_claim(tmp_path):
    from .bootstrap_request_auth_fixture import auth as request_auth
    co, candidate, _ = stage(tmp_path)
    co.journal.write(co.journal.read(), "recovery_required")
    handler = bootstrap.BootstrapHandler.__new__(bootstrap.BootstrapHandler)
    # BaseHTTPRequestHandler.server owns the existing Bootstrap owner property.
    handler.server = SimpleNamespace(bootstrap_paths=bootstrap.ServicePaths(
        product_root=co.paths.product_root, state_root=co.paths.bootstrap_state_root),
        base_module=object(), request_auth=request_auth)
    handler.path = "/v1/assets"
    handler.headers = {}  # anonymous read-only discovery
    replies = []
    handler._json = lambda status, payload: replies.append((status, payload))
    handler.do_GET()
    assert replies[0][0] == 200
    assert replies[0][1]["assets"]["state"] == "RECOVERY_REQUIRED"
    assert replies[0][1]["assets"]["ready"] is False


@pytest.mark.parametrize("published", [False, True])
@pytest.mark.parametrize("has_previous", [False, True])
def test_p4_restart_recovers_pointer_publication_and_previous_set(tmp_path, published, has_previous):
    co, first, _ = stage(tmp_path, folder="first")
    co.quiescence_lease = nullcontext
    if has_previous:
        co.activate_staged_asset_set(first, quiescence_lease=nullcontext)
    co, candidate, _ = stage(tmp_path, folder="candidate", fpga=b"new")
    co.quiescence_lease = nullcontext
    previous = assets.read_active(co.paths.product_root)
    record = co.journal.read()
    co.journal.write(record, "activating", asset_activation_previous=previous,
                     artifact_sha256=candidate)
    if published:
        assets.activate_verified(co.paths.product_root, candidate, runtime_quiesced=True)
    assert co.asset_status()["state"] == "RECOVERY_REQUIRED"
    assert co.asset_status()["ready"] is False
    # New process, same lock/journal/pointer, no alternate recovery store.
    fresh = make_coordinator(tmp_path)
    fresh.quiescence_lease = nullcontext
    with fresh._deployment_lock(recover_assets=True):
        assert fresh.journal.read().state == "rolled_back"
    current = assets.read_active(co.paths.product_root)
    assert current["asset_set_sha256"] == previous["asset_set_sha256"]
    assert current["ready"] is False
    assert fresh.asset_status()["state"] == previous["state"]
    # Repeated recovery after rollback publication but before journal commit.
    fresh.journal.write(record, "activating")
    with fresh._deployment_lock(recover_assets=True):
        assert fresh.journal.read().state == "rolled_back"


@pytest.mark.parametrize("failure", ["busy", "corrupt_previous", "pointer_drift", "fpga"])
def test_p4_rollback_failures_remain_fenced(tmp_path, failure):
    co, first, stored = stage(tmp_path, folder="first")
    co.activate_staged_asset_set(first, quiescence_lease=nullcontext)
    previous = assets.read_active(co.paths.product_root)
    co, candidate, _ = stage(tmp_path, folder="candidate", fpga=b"new")
    record = co.journal.read()
    co.journal.write(record, "activating", asset_activation_previous=previous,
                     asset_activation_fpga=failure == "fpga")
    assets.activate_verified(co.paths.product_root, candidate, runtime_quiesced=True)
    if failure == "corrupt_previous":
        parser = stored / "payload/packages/swd-parser/python/parse.py"
        parser.chmod(0o600)
        parser.write_text("corrupt")
    if failure == "pointer_drift":
        pointer = co.paths.product_root / "assets/active.json"
        value = json.loads(pointer.read_text())
        value["generation"] += 10
        pointer.chmod(0o600)
        pointer.write_text(json.dumps(value))
    @contextmanager
    def busy():
        raise RuntimeError("ACTIVE_JOB")
        yield
    co.quiescence_lease = busy if failure == "busy" else nullcontext
    before = (co.paths.product_root / "assets/active.json").read_bytes()
    with pytest.raises(Exception, match="RECOVERY|recovery"):
        with co._deployment_lock(recover_assets=True):
            pytest.fail("must not admit a new transaction")
    assert co.journal.read().state == "recovery_required"
    assert (co.paths.product_root / "assets/active.json").read_bytes() == before


def stage(tmp_path, *, fpga=b"image-1", folder="a"):
    archive, sha = build_generic_assets(tmp_path / folder, bitstream=fpga)
    coordinator = make_coordinator(tmp_path)
    receipt = coordinator.execute_bundle_v3_install(b3_request(archive, sha))
    assert receipt["stage"] == "bundle_staged_only"
    return coordinator, sha, Path(receipt["install_path"])


def test_b3_never_activates_even_when_complete_and_verified(tmp_path):
    co, sha, stored = stage(tmp_path)
    current = assets.read_active(co.paths.product_root)
    assert current["state"] == "EMPTY" and current["asset_set_sha256"] is None
    assert assets.verify_staged(co.paths.product_root, sha)["state"] == "VERIFIED"
    assert (stored / "manifest.json").is_file()
    assert not (co.paths.product_root / "assets" / "active.json").exists()
    assert not (co.paths.product_root / "current").exists()


def test_p1_refuses_activation_when_authoritative_runtime_socket_is_missing(tmp_path):
    co, sha, _ = stage(tmp_path)
    with pytest.raises(Exception, match="ASSET_SET_QUIESCE_DENIED"):
        co.activate_staged_asset_set(sha)
    assert assets.read_active(co.paths.product_root)["state"] == "EMPTY"
    assert co.journal.read().state == "verify_failed"


def test_p1_guarded_atomic_activation_keeps_runtime_and_fpga_unmodified(tmp_path):
    co, sha, _ = stage(tmp_path)
    result = co.activate_staged_asset_set(sha, quiescence_lease=nullcontext)
    assert result["result"] == "PASS" and result["stage"] == "asset_set_active"
    assert result["asset_set_sha256"] == sha and result["fpga"] == "NOT_RUN"
    assert result["ready"] is False and result["dut"] == "NOT_RUN"
    assert result["generation"] == 1
    assert result["transaction"]["kind"] == "asset-set"
    assert result["transaction"]["state"] == "asset_set_active"
    current = assets.read_active(co.paths.product_root)
    assert current["state"] == "ACTIVE" and current["asset_set_sha256"] == sha
    assert current["ready"] is False and current["fpga"] == "NOT_VERIFIED"
    assert (co.paths.product_root / "assets" / "active.json").stat().st_mode & 0o777 == 0o444
    assert not (co.paths.product_root / "current").exists()
    assert not co.paths.systemd_root.exists()


def test_p1_new_staged_set_does_not_replace_active_until_explicit_commit(tmp_path):
    co, first, original = stage(tmp_path, folder="one")
    co.activate_staged_asset_set(first, quiescence_lease=nullcontext)
    newer, second, later = stage(tmp_path, folder="two", fpga=b"image-2")
    assert first != second and original.is_dir() and later.is_dir()
    assert assets.read_active(co.paths.product_root)["asset_set_sha256"] == first
    updated = newer.activate_staged_asset_set(second, quiescence_lease=nullcontext)
    assert updated["generation"] == 2
    pointer = assets.read_active(co.paths.product_root)
    assert pointer["asset_set_sha256"] == second
    assert original.is_dir() and later.is_dir()


def test_p1_repeat_selected_set_is_idempotent_no_generation_advance(tmp_path):
    co, sha, _ = stage(tmp_path)
    co.activate_staged_asset_set(sha, quiescence_lease=nullcontext)
    same = co.activate_staged_asset_set(sha, quiescence_lease=nullcontext)
    assert same["already_active"] is True and same["generation"] == 1
    assert assets.read_active(co.paths.product_root)["generation"] == 1


def test_p1_active_job_denies_switch_without_changing_previous(tmp_path):
    co, first, _ = stage(tmp_path, folder="first")
    co.activate_staged_asset_set(first, quiescence_lease=nullcontext)
    newer, second, _ = stage(tmp_path, folder="second", fpga=b"custom-swd")
    @contextmanager
    def busy_execution():
        raise RuntimeError("JOB_ACTIVE_OR_CANCELLING")
        yield
    with pytest.raises(Exception, match="ASSET_SET_QUIESCE_DENIED"):
        newer.activate_staged_asset_set(second, quiescence_lease=busy_execution)
    assert assets.read_active(co.paths.product_root)["asset_set_sha256"] == first
    assert newer.journal.read().state == "verify_failed"


def test_p1_corrupted_staged_package_denied_before_active_change(tmp_path):
    co, first, _ = stage(tmp_path, folder="first")
    co.activate_staged_asset_set(first, quiescence_lease=nullcontext)
    newer, second, later = stage(tmp_path, folder="second", fpga=b"next-image")
    image = later / "payload/packages/custom-swd/fpga/swd.bin"
    image.chmod(0o600)
    image.write_bytes(b"tampered")
    with pytest.raises(Exception, match="ASSET_SET_NOT_VERIFIED"):
        newer.activate_staged_asset_set(second, quiescence_lease=nullcontext)
    assert assets.read_active(co.paths.product_root)["asset_set_sha256"] == first
    assert newer.journal.read().state == "verify_failed"


def test_p1_existing_active_corruption_cannot_report_matching_digest(tmp_path):
    co, first, current = stage(tmp_path)
    co.activate_staged_asset_set(first, quiescence_lease=nullcontext)
    parser = current / "payload/packages/swd-parser/python/parse.py"
    parser.chmod(0o600)
    parser.write_text("tampered\n")
    with pytest.raises(assets.AssetSetError, match="ASSET_SET_FILE_MISMATCH"):
        assets.read_active(co.paths.product_root)


def test_p1_malicious_active_pointer_cannot_be_followed(tmp_path):
    co, first, _ = stage(tmp_path)
    link = co.paths.product_root / "assets" / "active.json"
    outside = tmp_path / "external.json"
    outside.write_text(json.dumps({"schema":"malicious"}))
    link.symlink_to(outside)
    with pytest.raises(assets.AssetSetError, match="ACTIVE_SYMLINK"):
        assets.read_active(co.paths.product_root)
    assert outside.read_text() == json.dumps({"schema":"malicious"})


def test_p1_nonexistent_digest_and_malformed_identity_rejected(tmp_path):
    co, first, _ = stage(tmp_path)
    for digest in ("", "A"*64, "../" + first, "a"*64):
        with pytest.raises(Exception):
            co.activate_staged_asset_set(digest, quiescence_lease=nullcontext)
    assert assets.read_active(co.paths.product_root)["state"] == "EMPTY"


def test_p1_failed_quiescence_does_not_overwrite_previous_active(tmp_path):
    co, sha, _ = stage(tmp_path)
    @contextmanager
    def refuse():
        raise RuntimeError("busy")
        yield
    with pytest.raises(Exception, match="ASSET_SET_QUIESCE_DENIED"):
        co.activate_staged_asset_set(sha, quiescence_lease=refuse)
    assert assets.read_active(co.paths.product_root)["state"] == "EMPTY"
    assert co.journal.read().state == "verify_failed"


def test_p1_symlinked_nested_package_directory_denied_before_read(tmp_path):
    co, sha, stage_root = stage(tmp_path)
    package = stage_root / "payload/packages/custom-swd"
    original = stage_root / "original"
    package.rename(original)
    package.symlink_to(original, target_is_directory=True)
    with pytest.raises(assets.AssetSetError, match="ASSET_SET_PARENT_UNTRUSTED"):
        assets.verify_staged(co.paths.product_root, sha)
    assert assets.read_active(co.paths.product_root)["state"] == "EMPTY"


def test_p1_existing_bootstrap_serves_verified_asset_identity_over_local_get(tmp_path):
    co, sha, _ = stage(tmp_path)
    paths = bootstrap.ServicePaths(
        product_root=co.paths.product_root,
        state_root=co.paths.bootstrap_state_root,
    )
    server = bootstrap.BootstrapHTTPServer(
        ("127.0.0.1", 0), paths=paths, base_module=object(),
    )
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        base = "http://127.0.0.1:" + str(server.server_address[1]) + "/v1/assets"
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(base, timeout=5) as response:
            empty = json.load(response)
        assert empty["assets"]["state"] == "EMPTY"
        co.activate_staged_asset_set(sha, quiescence_lease=nullcontext)
        with opener.open(base, timeout=5) as response:
            activated = json.load(response)
        assert activated["ok"] is True
        assert activated["assets"]["asset_set_sha256"] == sha
        assert activated["assets"]["ready"] is False
        assert activated["assets"]["fpga"] == "NOT_VERIFIED"
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=5)

"""P1 Single Active Asset Set: Host-only filesystem and Coordinator tests.

Never operate real Z2, PS/PL, FPGA Manager, network, root or DUT.
"""
from __future__ import annotations

import json
from contextlib import contextmanager, nullcontext
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import load
from .test_ppu_b3_z2_install_gate1 import (
    b3_request, build_generic_assets, make_coordinator,
)

assets = load("ppu_single_active_asset_set_gate1", "ppu_asset_set.py")


def stage(tmp_path, *, fpga=b"image-1", folder="a"):
    archive, sha = build_generic_assets(tmp_path / folder, bitstream=fpga)
    coordinator = make_coordinator(tmp_path)
    receipt = coordinator.execute_bundle_v3_install(b3_request(archive, sha))
    assert receipt["stage"] == "bundle_install_only"
    return coordinator, sha, Path(receipt["install_path"])


def test_b3_never_activates_even_when_complete_and_verified(tmp_path):
    co, sha, stored = stage(tmp_path)
    current = assets.read_active(co.paths.product_root)
    assert current["state"] == "EMPTY" and current["asset_set_sha256"] is None
    assert assets.verify_staged(co.paths.product_root, sha)["state"] == "VERIFIED"
    assert (stored / "manifest.json").is_file()
    assert not (co.paths.product_root / "assets" / "active.json").exists()
    assert not (co.paths.product_root / "current").exists()


def test_p1_refuses_activation_without_trusted_runtime_job_lease(tmp_path):
    co, sha, _ = stage(tmp_path)
    with pytest.raises(Exception, match="ASSET_SET_RUNTIME_QUIESCE_NOT_QUALIFIED"):
        co.activate_staged_asset_set(sha)
    assert assets.read_active(co.paths.product_root)["state"] == "EMPTY"
    assert co.journal.read().state == "bundle_installed"


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
    assert (co.paths.product_root / "assets" / "active.json").stat().st_mode & 0o777 == 0o600
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

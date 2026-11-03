"""Canonical three-package v3 B3 smoke: build, stage and explicit host execution.

No SWPC, Z2, privileges, systemd, FPGA, hardware or DUT. The staged payload is
NEVER executed by the installer: the test harness explicitly runs a REVIEWED
repository fixture using the local host Python interpreter after verification.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import (
    ROOT, SOURCE, TARGET, contract, coordinator, engine, request,
)

BUILDER = ROOT / "scripts" / "ppu-bundle-v3-smoke.py"
SMOKE = "payload/packages/python-smoke/python/smoke.py"
GEOMETRY = "payload/packages/programming-profile/data/geometry.json"
DEVICE = "payload/packages/ic-catalog/data/device.json"


def build_smoke(tmp_path: Path) -> tuple[Path, str]:
    target = tmp_path / "smoke.zip"
    result = subprocess.run(
        [sys.executable, str(BUILDER), "--output", str(target),
         "--source-commit", SOURCE],
        check=True, capture_output=True, text=True, timeout=20,
    )
    receipt = json.loads(result.stdout)
    assert receipt["schema"] == "plasma.ppu.bundle.v3"
    assert receipt["install_qualified"] is False
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    assert receipt["artifact_sha256"] == digest
    return target, digest


def policy_for(digest: str) -> dict:
    return {"schema": "plasma.ppu.bundle-authority.v2",
            "generation": 1, "approved_bundle_sha256": [digest]}


def stage_smoke(tmp_path: Path):
    archive, digest = build_smoke(tmp_path / "archive")
    co = coordinator(tmp_path)
    receipt = co.execute_authorized_bundle_host_only(
        request(archive, digest), trusted_policy=policy_for(digest),
        trusted_inventory={}, now_epoch_s=123,
    )
    root = (co.paths.bootstrap_state_root / "host-only-packages"
            / "releases" / "ppu-b3-smoke" / receipt["release_id"])
    return co, receipt, root


def run_fixture(root: Path) -> subprocess.CompletedProcess[str]:
    # Separate conscious test action; NOT an installer invocation.
    return subprocess.run(
        [sys.executable, str(root / SMOKE), "--root", str(root)],
        capture_output=True, text=True, timeout=10, check=False,
    )


def test_smoke_archive_deterministic_and_canonical(tmp_path):
    a, digest_a = build_smoke(tmp_path / "a")
    b, digest_b = build_smoke(tmp_path / "b")
    assert digest_a == digest_b
    with zipfile.ZipFile(a) as bundle:
        manifest = json.loads(bundle.read("manifest.json"))
        assert manifest["actions"] == ["install", "verify"]
        assert manifest["packages"][0]["id"] == "python-smoke"
        assert set(bundle.namelist()) == {"manifest.json", DEVICE, GEOMETRY, SMOKE}
    verified = contract.verify_host_only_artifact(
        a, expected_sha256=digest_a, source_commit=SOURCE, target_profile=TARGET,
    )
    assert len(verified.packages) == 3
    assert verified.install_qualified is False
    assert [p.id for p in verified.packages] == [
        "python-smoke", "programming-profile", "ic-catalog",
    ]
    resolution = contract.resolve_host_only_bundle(verified, trusted_inventory={})
    assert resolution["package_order"] == [
        "ic-catalog", "programming-profile", "python-smoke",
    ]


def test_b3_authorized_staging_then_explicit_python_smoke_pass(tmp_path):
    co, receipt, root = stage_smoke(tmp_path)
    assert receipt["result"] == "PASS"
    assert receipt["operation"] == "install_only"
    assert receipt["transaction"]["state"] == "installed"
    assert receipt["b3_install"]["status"] == "HOST_ONLY_VERIFIED"
    assert receipt["b4_activate"]["runtime_activation_executed"] is False
    assert receipt["package_order"] == [
        "ic-catalog", "programming-profile", "python-smoke",
    ]
    assert root.is_dir()
    assert (root / SMOKE).is_file()
    assert (root / DEVICE).is_file()
    assert (root / GEOMETRY).is_file()
    actual = run_fixture(root)
    assert actual.returncode == 0, actual.stderr
    assert actual.stdout.splitlines() == [
        "SMOKE_VERSION=0.1.0",
        "ICPN=STM32F103C8T6",
        "FLASH_BYTES=65536",
        "PASS",
    ]
    assert not (co.paths.bootstrap_state_root / "host-only-packages"
                / "active" / "ppu-b3-smoke.json").exists()
    assert not co.paths.product_root.exists()
    assert not co.paths.systemd_root.exists()


def test_b3_smoke_repeated_install_is_idempotent(tmp_path):
    archive, digest = build_smoke(tmp_path / "archive")
    co = coordinator(tmp_path)
    first = co.execute_package_host_only(request(archive, digest), install_only=True)
    second = co.execute_package_host_only(request(archive, digest), install_only=True)
    assert first["release_id"] == second["release_id"]
    assert first["transaction"]["state"] == second["transaction"]["state"] == "installed"
    assert second["active_pointer_unchanged"] is True


@pytest.mark.parametrize("corruption", ["missing", "wrong_geometry", "wrong_device"])
def test_b3_smoke_detects_corrupted_staged_data(tmp_path, corruption):
    _, _, root = stage_smoke(tmp_path)
    if corruption == "missing":
        (root / DEVICE).unlink()
    elif corruption == "wrong_geometry":
        file = root / GEOMETRY
        file.chmod(0o600)
        altered = json.loads(file.read_text(encoding="utf-8"))
        altered["flash_bytes"] = 131072
        file.write_text(json.dumps(altered), encoding="utf-8")
    else:
        file = root / DEVICE
        file.chmod(0o600)
        altered = json.loads(file.read_text(encoding="utf-8"))
        altered["icpn"] = "NOT_REAL"
        file.write_text(json.dumps(altered), encoding="utf-8")
    observed = run_fixture(root)
    assert observed.returncode != 0
    assert "PASS" not in observed.stdout


def test_b3_smoke_archive_hash_mismatch_rejected_before_staging(tmp_path):
    archive, digest = build_smoke(tmp_path / "archive")
    co = coordinator(tmp_path)
    with pytest.raises(engine.DeploymentError, match="BUNDLE_ARCHIVE_SHA256_MISMATCH"):
        co.execute_package_host_only(request(archive, "0" * 64), install_only=True)
    assert co.journal.read().state == "verify_failed"
    assert not co.paths.product_root.exists()


def test_b3_installed_state_is_not_global_restart_permission(tmp_path):
    archive, digest = build_smoke(tmp_path / "archive")
    co = coordinator(tmp_path)
    co.execute_package_host_only(request(archive, digest), install_only=True)
    journal_path = co.paths.journal
    previous = json.loads(journal_path.read_text(encoding="utf-8"))
    previous["kind"] = "ppu-runtime"
    journal_path.write_text(json.dumps(previous), encoding="utf-8")
    with pytest.raises(engine.DeploymentError, match="interrupted in state installed"):
        co.execute_package_host_only(request(archive, digest), install_only=True)
    assert co.journal.read().state == "recovery_required"

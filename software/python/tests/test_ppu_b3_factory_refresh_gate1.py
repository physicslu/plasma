"""Incremental B3 factory script refresh: preserve existing Factory environment.

This tests the EXISTING installer in refresh-only mode, not a new installer
path. No device, service, unit, credential or hardware calls are performed.
"""
from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT, SOURCE, TARGET, load
from .test_ppu_bundle_v3_smoke_execution_gate1 import build_smoke

installer = load("ppu_b3_factory_refresh_test", "ppu-bootstrap-installer.py")


def provision(tmp_path):
    root = tmp_path / "opt/plasma/bootstrap"
    state = tmp_path / "var/lib/plasma-bootstrap"
    unit = tmp_path / "etc/systemd/system/plasma-bootstrap.service"
    paths = installer.InstallPaths(root, state, unit)
    first = installer.install_bootstrap(
        source_root=ROOT / "scripts", host="192.168.2.99", port=18081,
        python_executable="/usr/bin/python3", paths=paths,
    )
    assert first["result"] == "PASS"
    token = state / "control-token"
    token.write_text("private-existing-enrollment-not-regenerated")
    token.chmod(0o600)
    runtime = tmp_path / "opt/plasma/current"
    runtime.mkdir()
    (runtime / "keep").write_text("existing runtime unchanged")
    return paths, token, runtime


def b3_sources(tmp_path):
    source = tmp_path / "factory-source"
    source.mkdir(parents=True)
    for name in (*installer.REQUIRED_SCRIPTS, "ppu-z2-installer.py",
                 "ppu-z2-installer-core.py"):
        shutil.copyfile(ROOT / "scripts" / name, source / name)
    archive, digest = build_smoke(tmp_path / "bundle")
    policy = {
        "schema": "plasma.ppu.b3-factory-policy.v1",
        "bundle_name": "ppu-b3-smoke",
        "source_commit": SOURCE,
        "archive_sha256": digest,
        "target": dict(TARGET),
        "actions": ["install", "verify"],
    }
    (source / "ppu-b3-smoke-policy.json").write_text(json.dumps(policy))
    return source, digest


def test_b3_refresh_preserves_factory_unit_token_state_and_runtime(tmp_path):
    paths, token, runtime = provision(tmp_path)
    existing_unit = paths.systemd_unit.read_bytes()
    existing_token = token.read_bytes()
    source, digest = b3_sources(tmp_path)
    # Explicitly add a harmless source change so refresh must really copy.
    service_file = source / "ppu-bootstrap-service.py"
    service_file.write_bytes(service_file.read_bytes() + b"\n# B3 incremental refresh fixture\n")
    result = installer.install_bootstrap(
        source_root=source, host="DIFFERENT_HOST_IGNORED", port=9999,
        python_executable="/bad/python", paths=paths,
        refresh_only=True,
        runner=lambda *_a, **_k: pytest.fail("refresh must not call systemctl"),
    )
    assert result["result"] == "PASS"
    assert result["operation"] == "refresh_only"
    assert result["unit_changed"] is False
    assert result["service_restarted"] is False
    assert result["control_token_provisioned"] is False
    assert paths.systemd_unit.read_bytes() == existing_unit
    assert token.read_bytes() == existing_token
    assert token.stat().st_mode & 0o777 == 0o600
    assert (runtime / "keep").read_text() == "existing runtime unchanged"
    assert (paths.install_root / "ppu-bootstrap-service.py").read_bytes() == service_file.read_bytes()
    assert (paths.install_root / "ppu-z2-installer-core.py").is_file()
    installed_policy = paths.install_root / "ppu-b3-smoke-policy.json"
    assert installed_policy.stat().st_mode & 0o777 == 0o600
    assert json.loads(installed_policy.read_text())["archive_sha256"] == digest


def test_b3_refresh_requires_existing_factory_before_mutation(tmp_path):
    source, _ = b3_sources(tmp_path)
    paths = installer.InstallPaths(tmp_path / "absent", tmp_path / "state",
                                    tmp_path / "unit")
    with pytest.raises(installer.BootstrapInstallError,
                       match="B3_REFRESH_REQUIRES_EXISTING_FACTORY"):
        installer.install_bootstrap(
            source_root=source, host="192.168.2.99", port=18081,
            python_executable="/usr/bin/python3", paths=paths,
            refresh_only=True,
        )
    assert not paths.install_root.exists() and not paths.systemd_unit.exists()


def test_b3_refresh_missing_policy_fail_closed_and_keeps_old_service(tmp_path):
    paths, _, _ = provision(tmp_path)
    old = (paths.install_root / "ppu-bootstrap-service.py").read_bytes()
    source, _ = b3_sources(tmp_path)
    (source / "ppu-b3-smoke-policy.json").unlink()
    with pytest.raises(installer.BootstrapInstallError,
                       match="B3_REFRESH_SOURCE_POLICY_REQUIRED"):
        installer.install_bootstrap(
            source_root=source, host="192.168.2.99", port=18081,
            python_executable="/usr/bin/python3", paths=paths,
            refresh_only=True,
        )
    assert (paths.install_root / "ppu-bootstrap-service.py").read_bytes() == old


def test_b3_refresh_refuses_enable_now_and_partial_source(tmp_path):
    paths, _, _ = provision(tmp_path)
    source, _ = b3_sources(tmp_path)
    with pytest.raises(installer.BootstrapInstallError,
                       match="B3_REFRESH_CANNOT_ENABLE_SERVICE"):
        installer.install_bootstrap(
            source_root=source, host="192.168.2.99", port=18081,
            python_executable="/usr/bin/python3", paths=paths,
            refresh_only=True, enable_now=True,
        )
    old = (paths.install_root / "ppu-bootstrap-service.py").read_bytes()
    (source / "ppu-z2-installer-core.py").unlink()
    with pytest.raises(installer.BootstrapInstallError,
                       match="factory B3 source set is incomplete"):
        installer.install_bootstrap(
            source_root=source, host="192.168.2.99", port=18081,
            python_executable="/usr/bin/python3", paths=paths,
            refresh_only=True,
        )
    assert (paths.install_root / "ppu-bootstrap-service.py").read_bytes() == old

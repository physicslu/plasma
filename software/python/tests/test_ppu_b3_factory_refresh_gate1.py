"""Generic B3 Bootstrap capability: refresh without changing enrollment or runtime.

No Z2, FPGA, DUT, service or credential operations.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from .test_ppu_bundle_v3_packages_contract import ROOT, load

installer = load("ppu_generic_b3_factory_test", "ppu-bootstrap-installer.py")
POLICY_FILE = "ppu-bundle-install-policy.json"


def provision(tmp_path):
    root = tmp_path / "opt/plasma/bootstrap"
    state = tmp_path / "var/lib/plasma-bootstrap"
    unit = tmp_path / "etc/systemd/system/plasma-bootstrap.service"
    paths = installer.InstallPaths(root, state, unit)
    receipt = installer.install_bootstrap(
        source_root=ROOT / "scripts", host="127.0.0.1", port=18081,
        python_executable="/usr/bin/python3", paths=paths,
    )
    assert receipt["result"] == "PASS"
    token = state / "control-token"
    token.write_text("existing-enrollment-kept")
    token.chmod(0o600)
    runtime = tmp_path / "opt/plasma/current"
    runtime.mkdir()
    (runtime / "keep").write_text("current-runtime-preserved")
    return paths, token, runtime


def generic_factory_sources(tmp_path):
    source = tmp_path / "source"
    source.mkdir(parents=True)
    for name in (*installer.REQUIRED_SCRIPTS, *installer.B3_FILES):
        shutil.copyfile(ROOT / "scripts" / name, source / name)
    return source


def test_generic_policy_has_no_bundle_name_or_fixed_archive_digest():
    data = json.loads((ROOT / "scripts" / POLICY_FILE).read_text())
    assert data == {
        "schema": "plasma.ppu.b3-install-policy.v1",
        "mode": "development", "install_only": True,
        "actions": ["install", "verify"],
    }
    assert "smoke" not in json.dumps(data).lower()


def test_generic_b3_factory_refresh_preserves_bootstrap_enrollment(tmp_path):
    paths, token, runtime = provision(tmp_path)
    original_unit = paths.systemd_unit.read_bytes()
    original_token = token.read_bytes()
    source = generic_factory_sources(tmp_path)
    service = source / "ppu-bootstrap-service.py"
    service.write_bytes(service.read_bytes() + b"\\n# reviewed generic factory refresh\\n")
    result = installer.install_bootstrap(
        source_root=source, host="different-host-ignored", port=9999,
        python_executable="/bad/python", paths=paths,
        refresh_only=True,
        runner=lambda *_a, **_k: pytest.fail("unexpected systemctl"),
    )
    assert result["result"] == "PASS" and result["operation"] == "refresh_only"
    assert result["unit_changed"] is False
    assert result["service_restarted"] is False
    assert result["control_token_provisioned"] is False
    assert paths.systemd_unit.read_bytes() == original_unit
    assert token.read_bytes() == original_token
    assert (runtime / "keep").read_text() == "current-runtime-preserved"
    assert (paths.install_root / "ppu-bootstrap-service.py").read_bytes() == service.read_bytes()
    assert (paths.install_root / POLICY_FILE).stat().st_mode & 0o777 == 0o600


def test_generic_b3_refresh_requires_existing_factory(tmp_path):
    paths = installer.InstallPaths(tmp_path / "missing", tmp_path / "state", tmp_path / "unit")
    with pytest.raises(installer.BootstrapInstallError, match="B3_REFRESH_REQUIRES_EXISTING_FACTORY"):
        installer.install_bootstrap(
            source_root=generic_factory_sources(tmp_path), host="ignored",
            port=18081, python_executable="/usr/bin/python3", paths=paths,
            refresh_only=True,
        )
    assert not paths.install_root.exists()


def test_generic_b3_refresh_rejects_missing_policy_without_mutation(tmp_path):
    paths, _, _ = provision(tmp_path)
    before = (paths.install_root / "ppu-bootstrap-service.py").read_bytes()
    source = generic_factory_sources(tmp_path)
    (source / POLICY_FILE).unlink()
    with pytest.raises(installer.BootstrapInstallError, match="B3_REFRESH_SOURCE_POLICY_REQUIRED"):
        installer.install_bootstrap(
            source_root=source, host="ignored", port=18081,
            python_executable="/usr/bin/python3", paths=paths,
            refresh_only=True,
        )
    assert (paths.install_root / "ppu-bootstrap-service.py").read_bytes() == before


def test_generic_b3_refresh_rejects_bad_policy_or_partial_scripts(tmp_path):
    paths, _, _ = provision(tmp_path)
    old = (paths.install_root / POLICY_FILE).read_bytes()
    source = generic_factory_sources(tmp_path)
    (source / POLICY_FILE).write_text('{"schema":"bad"}')
    with pytest.raises(installer.BootstrapInstallError, match="factory B3 policy invalid"):
        installer.install_bootstrap(
            source_root=source, host="ignored", port=18081,
            python_executable="/usr/bin/python3", paths=paths,
            refresh_only=True,
        )
    assert (paths.install_root / POLICY_FILE).read_bytes() == old
    shutil.copyfile(ROOT / "scripts" / POLICY_FILE, source / POLICY_FILE)
    (source / "ppu-z2-installer-core.py").unlink()
    with pytest.raises(installer.BootstrapInstallError, match="factory B3 source set is incomplete"):
        installer.install_bootstrap(
            source_root=source, host="ignored", port=18081,
            python_executable="/usr/bin/python3", paths=paths,
            refresh_only=True,
        )
    assert (paths.install_root / POLICY_FILE).read_bytes() == old

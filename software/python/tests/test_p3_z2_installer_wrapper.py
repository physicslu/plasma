from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ppu-z2-installer.py"
spec = importlib.util.spec_from_file_location("p3_z2_single_installer", SCRIPT)
assert spec is not None and spec.loader is not None
installer = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = installer
spec.loader.exec_module(installer)


def paths(tmp_path: Path):
    return installer.InstallPaths(
        product_root=tmp_path / "opt" / "plasma",
        config_root=tmp_path / "etc" / "plasma",
        state_root=tmp_path / "var" / "lib" / "plasma",
        log_root=tmp_path / "var" / "log" / "plasma",
        systemd_root=tmp_path / "etc" / "systemd" / "system",
    )


def runtime(install_paths):
    return installer.PythonRuntime(
        install_paths.product_root / "python" / "3.12.13" / "bin" / "python3",
        "3.12.13",
        "armv7l",
    )


def verified():
    return SimpleNamespace(
        release_id="1.0.0-" + "a" * 12,
        product_version="1.0.0",
        git_sha="a" * 40,
        archive_sha256="b" * 64,
        runtime_manifest={"schema_version": 1, "role": "ppu"},
    )


def mock_installer_io(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(installer, "_copy_release",
                        lambda verified, target: target.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(installer, "_chown_tree", lambda *args: None)
    monkeypatch.setattr(installer.os, "chown", lambda *args: None)
    monkeypatch.setattr(installer.pwd, "getpwnam",
                        lambda name: SimpleNamespace(pw_uid=1001, pw_gid=1001))
    monkeypatch.setattr(installer.grp, "getgrnam",
                        lambda name: SimpleNamespace(gr_gid=1001))


def deploy(install_paths, *, health_check, systemctl):
    return installer.install_release(
        verified(),
        python_runtime=runtime(install_paths),
        gateway_host="192.168.2.99",
        paths=install_paths,
        ppu_id="new-id-must-not-replace-canonical-config",
        facility_id="new-facility",
        display_name="new-name",
        systemctl=systemctl,
        health_check=health_check,
        ensure_service_account=lambda: None,
    )


def test_p3_units_make_helper_a_gateway_owned_dependency(tmp_path: Path) -> None:
    install_paths = paths(tmp_path)
    units = installer.render_systemd_units(
        paths=install_paths,
        python_runtime=runtime(install_paths),
        gateway_host="192.168.2.99",
    )
    server = units["plasma-server.service"]
    gateway = units["plasma-web.service"]
    helper = units[installer.RUNTIME_ACTIVATION_SERVICE]
    assert f"--runtime-control-socket {installer.SERVER_CONTROL_SOCKET}" in server
    assert f"Requires=plasma-server.service {installer.RUNTIME_ACTIVATION_SERVICE}" in gateway
    assert f"--runtime-activation-socket {installer.RUNTIME_ACTIVATION_SOCKET}" in gateway
    assert "PartOf=plasma-web.service" in helper
    assert "User=root" in helper
    assert "Group=plasma" in helper
    assert "RestrictAddressFamilies=AF_UNIX" in helper


def test_successful_upgrade_preserves_existing_canonical_site_desired_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_paths = paths(tmp_path)
    config = install_paths.config_root / "ppu.yaml"
    config.parent.mkdir(parents=True)
    existing = ("ppu:\n  id: preserved\nsites:\n  - id: 1\n"
                "    enabled: true\n    interface: mock\n    target: KEEP-ME\n")
    config.write_text(existing, encoding="utf-8")
    config.chmod(0o640)
    mock_installer_io(monkeypatch)
    calls = []
    evidence = deploy(install_paths, health_check=lambda host: {},
                      systemctl=lambda *args: calls.append(args))
    assert config.read_text(encoding="utf-8") == existing
    state = evidence["site_desired_state"]
    assert state["runtime_apply_supported"] is True
    assert state["upgrade_preserves_existing_config"] is True
    assert state["empty_sites_migrated_to_defaults"] is False
    assert evidence["runtime_activation"]["lifecycle_owner"] == "plasma-web.service"
    assert ("enable", "--now", installer.RUNTIME_ACTIVATION_SERVICE) not in calls
    persisted = json.loads((install_paths.install_root / "last-install.json").read_text())
    assert persisted["site_desired_state"]["upgrade_preserves_existing_config"] is True


def test_failed_activation_restores_previous_helper_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_paths = paths(tmp_path)
    previous = install_paths.releases_root / "previous"
    previous.mkdir(parents=True)
    install_paths.current.symlink_to(previous)
    helper = install_paths.systemd_root / installer.RUNTIME_ACTIVATION_SERVICE
    helper.parent.mkdir(parents=True)
    helper.write_text("old-helper-unit\n", encoding="utf-8")
    helper.chmod(0o644)
    mock_installer_io(monkeypatch)
    calls = []
    def failed_health(host):
        raise installer.Z2InstallerError("synthetic activation failure")
    with pytest.raises(installer.Z2InstallerError, match="synthetic activation failure"):
        deploy(install_paths, health_check=failed_health,
               systemctl=lambda *args: calls.append(args))
    assert helper.read_text(encoding="utf-8") == "old-helper-unit\n"
    assert install_paths.current.resolve() == previous.resolve()
    assert ("daemon-reload",) in calls
    assert ("restart", installer.RUNTIME_ACTIVATION_SERVICE) in calls


def test_failed_first_install_removes_candidate_helper_unit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_paths = paths(tmp_path)
    helper = install_paths.systemd_root / installer.RUNTIME_ACTIVATION_SERVICE
    mock_installer_io(monkeypatch)
    calls = []
    def failed_health(host):
        raise installer.Z2InstallerError("synthetic first-install failure")
    with pytest.raises(installer.Z2InstallerError, match="synthetic first-install failure"):
        deploy(install_paths, health_check=failed_health,
               systemctl=lambda *args: calls.append(args))
    assert not helper.exists()
    assert not install_paths.current.exists()
    assert ("daemon-reload",) in calls
    assert ("restart", installer.RUNTIME_ACTIVATION_SERVICE) not in calls

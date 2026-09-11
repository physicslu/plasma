from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ppu-z2-installer.py"
spec = importlib.util.spec_from_file_location("p3_z2_installer_wrapper", SCRIPT)
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
        runtime_manifest={
            "data": {
                "device_catalog_manifest": "data/device-catalog/production/icpn-v1-manifest.json"
            }
        }
    )


def test_p3_units_make_helper_a_gateway_owned_dependency(tmp_path: Path) -> None:
    install_paths = paths(tmp_path)
    units = installer.render_systemd_units(
        paths=install_paths,
        python_runtime=runtime(install_paths),
        gateway_host="192.168.2.99",
        catalog_relative="data/device-catalog/production/icpn-v1-manifest.json",
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
    assert "systemctl" not in helper


def test_successful_upgrade_preserves_existing_canonical_site_desired_state(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_paths = paths(tmp_path)
    config_path = install_paths.config_root / "ppu.yaml"
    config_path.parent.mkdir(parents=True)
    existing = "ppu:\n  id: preserved\nsites:\n  - id: 1\n    enabled: true\n    interface: mock\n    target: KEEP-ME\n"
    config_path.write_text(existing, encoding="utf-8")
    config_path.chmod(0o640)

    def fake_core_install(*args, **kwargs):
        installer._core._write_text_atomic(config_path, "sites: []\n", 0o640)
        return {"site_desired_state": {"runtime_apply_supported": False}}

    monkeypatch.setattr(installer, "_original_install_release", fake_core_install)
    calls: list[tuple[str, ...]] = []
    evidence = installer.install_release(
        verified(),
        python_runtime=runtime(install_paths),
        gateway_host="192.168.2.99",
        paths=install_paths,
        ppu_id="new-id-must-not-replace-canonical-config",
        facility_id="new-facility",
        display_name="new-name",
        systemctl=lambda *args: calls.append(args),
        health_check=lambda host: {},
        ensure_service_account=lambda: None,
    )

    assert config_path.read_text(encoding="utf-8") == existing
    assert evidence["site_desired_state"]["runtime_apply_supported"] is True
    assert evidence["site_desired_state"]["upgrade_preserves_existing_config"] is True
    assert evidence["runtime_activation"]["lifecycle_owner"] == "plasma-web.service"
    assert ("enable", "--now", installer.RUNTIME_ACTIVATION_SERVICE) not in calls
    persisted_evidence = json.loads((install_paths.install_root / "last-install.json").read_text())
    assert persisted_evidence["site_desired_state"]["upgrade_preserves_existing_config"] is True


def test_failed_activation_restores_previous_helper_unit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_paths = paths(tmp_path)
    helper_path = install_paths.systemd_root / installer.RUNTIME_ACTIVATION_SERVICE
    helper_path.parent.mkdir(parents=True)
    helper_path.write_text("old-helper-unit\n", encoding="utf-8")
    helper_path.chmod(0o644)

    def fail_core_install(*args, **kwargs):
        raise installer.Z2InstallerError("synthetic activation failure")

    monkeypatch.setattr(installer, "_original_install_release", fail_core_install)
    calls: list[tuple[str, ...]] = []
    with pytest.raises(installer.Z2InstallerError, match="synthetic activation failure"):
        installer.install_release(
            verified(),
            python_runtime=runtime(install_paths),
            gateway_host="192.168.2.99",
            paths=install_paths,
            ppu_id="ppu-a",
            facility_id="lab",
            display_name="PPU A",
            systemctl=lambda *args: calls.append(args),
            health_check=lambda host: {},
            ensure_service_account=lambda: None,
        )

    assert helper_path.read_text(encoding="utf-8") == "old-helper-unit\n"
    assert ("daemon-reload",) in calls
    assert ("restart", installer.RUNTIME_ACTIVATION_SERVICE) in calls


def test_failed_first_install_removes_candidate_helper_unit(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_paths = paths(tmp_path)
    helper_path = install_paths.systemd_root / installer.RUNTIME_ACTIVATION_SERVICE

    def fail_core_install(*args, **kwargs):
        raise installer.Z2InstallerError("synthetic first-install failure")

    monkeypatch.setattr(installer, "_original_install_release", fail_core_install)
    calls: list[tuple[str, ...]] = []
    with pytest.raises(installer.Z2InstallerError, match="synthetic first-install failure"):
        installer.install_release(
            verified(),
            python_runtime=runtime(install_paths),
            gateway_host="192.168.2.99",
            paths=install_paths,
            ppu_id="ppu-a",
            facility_id="lab",
            display_name="PPU A",
            systemctl=lambda *args: calls.append(args),
            health_check=lambda host: {},
            ensure_service_account=lambda: None,
        )

    assert not helper_path.exists()
    assert ("daemon-reload",) in calls
    assert ("restart", installer.RUNTIME_ACTIVATION_SERVICE) not in calls

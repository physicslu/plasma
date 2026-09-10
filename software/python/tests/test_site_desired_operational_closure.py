from __future__ import annotations

import importlib.util
import stat
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[3]
Z2_INSTALLER = ROOT / "scripts" / "ppu-z2-installer.py"
Z2_CONTROL = ROOT / "scripts" / "plasmactl-z2-ps"
PPU_RUNTIME = ROOT / "scripts" / "ppu-runtime.py"
SWPC_INSTALLER = ROOT / "scripts" / "swpc-z2like-ppu-install.sh"
SWPC_CONTROL = ROOT / "scripts" / "plasmactl-swpc-z2like"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


installer = _load("p2_ppu_z2_installer", Z2_INSTALLER)
runtime = _load("p2_ppu_runtime", PPU_RUNTIME)


def test_z2_server_and_gateway_share_one_explicit_canonical_config(tmp_path: Path) -> None:
    paths = installer.InstallPaths(
        product_root=tmp_path / "opt" / "plasma",
        config_root=tmp_path / "etc" / "plasma",
        state_root=tmp_path / "var" / "lib" / "plasma",
        log_root=tmp_path / "var" / "log" / "plasma",
        systemd_root=tmp_path / "etc" / "systemd" / "system",
    )
    python_path = paths.product_root / "python" / "3.11.9" / "bin" / "python3"
    units = installer.render_systemd_units(
        paths=paths,
        python_runtime=installer.PythonRuntime(python_path, "3.11.9", "armv7l"),
        gateway_host="192.168.2.99",
        catalog_relative="data/device-catalog/production/icpn-v1-manifest.json",
    )
    config = paths.config_root / "ppu.yaml"
    server = units["plasma-server.service"]
    gateway = units["plasma-web.service"]

    assert f"server --config {config}" in server
    assert f"gateway --ppu-config {config}" in gateway
    assert f"ReadWritePaths={paths.state_root} {paths.log_root} {paths.config_root}" in gateway
    server_write_line = next(line for line in server.splitlines() if line.startswith("ReadWritePaths="))
    assert str(paths.config_root) not in server_write_line
    assert "ProtectSystem=strict" in server
    assert "ProtectSystem=strict" in gateway


def test_z2_config_directory_permission_migration_is_rollback_safe(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    config_root = tmp_path / "etc" / "plasma"
    config_root.mkdir(parents=True)
    config_root.chmod(0o755)
    snapshot = installer._snapshot_directory(config_root)

    monkeypatch.setattr(installer.os, "chown", lambda *args: None)
    monkeypatch.setattr(
        installer.grp,
        "getgrnam",
        lambda name: types.SimpleNamespace(gr_gid=1001),
    )

    installer._prepare_config_directory(config_root)
    assert stat.S_IMODE(config_root.stat().st_mode) == 0o770
    installer._restore_directory(snapshot)
    assert stat.S_IMODE(config_root.stat().st_mode) == 0o755


def test_ppu_runtime_manifest_requires_gateway_and_server_config_identity() -> None:
    manifest = runtime._manifest(python_requirement=">=3.11", pyyaml_version="6.0.2")
    processes = manifest["processes"]
    assert processes["server"]["arguments"] == ["server", "--config", "<ppu-config>"]
    gateway_args = processes["gateway"]["arguments"]
    index = gateway_args.index("--ppu-config")
    assert gateway_args[index + 1] == "<ppu-config>"


def test_real_z2_verify_checks_p2_service_and_evidence_boundaries() -> None:
    source = Z2_CONTROL.read_text(encoding="utf-8")
    assert "verify_site_desired_operational_contract" in source
    assert "gateway --ppu-config $ppu_config" in source
    assert "server --config $ppu_config" in source
    assert "PPU config root must be mode 0770" in source
    assert "PPU config must be mode 0640" in source
    assert "Plasma Server must not receive canonical config write access" in source
    assert "site_desired_state.config_path" in source
    assert "site_desired_state.gateway_write_root" in source
    assert "site_desired_state.runtime_apply_supported" in source
    assert "Runtime apply" in source


def test_swpc_surrogate_matches_bounded_site_config_contract_and_rolls_permissions_back() -> None:
    installer_source = SWPC_INSTALLER.read_text(encoding="utf-8")
    control_source = SWPC_CONTROL.read_text(encoding="utf-8")

    assert 'install -d -m 0770 -o root -g plasma "$config_root"' in installer_source
    assert 'chmod 0640 "$config_path"' in installer_source
    assert 'chown plasma:plasma "$config_path"' in installer_source
    assert "gateway --ppu-config $config_path" in installer_source
    assert "ReadWritePaths=$state_root $log_root $config_root" in installer_source
    assert "ReadWritePaths=$state_root $log_root\n" in installer_source

    assert 'stat -c \'%a %u %g\' "$config_root" >"$snapshot/config-root.stat"' in control_source
    assert 'restore_config_root_metadata "$mode" "$uid" "$gid"' in control_source
    assert "verify_site_desired_operational_contract" in control_source
    assert "restricted ingress unexpectedly exposed /api/settings/sites" in control_source

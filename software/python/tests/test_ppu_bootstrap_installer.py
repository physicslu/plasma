from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
SCRIPT = ROOT / "scripts" / "ppu-bootstrap-installer.py"
SPEC = importlib.util.spec_from_file_location("ppu_bootstrap_installer", SCRIPT)
assert SPEC and SPEC.loader
installer = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = installer
SPEC.loader.exec_module(installer)


def _source(tmp_path: Path):
    source = tmp_path / "bundle" / "scripts"
    source.mkdir(parents=True)
    for name in installer.REQUIRED_SCRIPTS:
        if name == "ppu-bootstrap.py":
            content = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        else:
            content = f"#!/usr/bin/env python3\n# {name}\n"
        (source / name).write_text(content, encoding="utf-8")
    return source


def _paths(tmp_path: Path):
    return installer.InstallPaths(
        install_root=tmp_path / "opt" / "plasma" / "bootstrap",
        state_root=tmp_path / "var" / "lib" / "plasma-bootstrap",
        systemd_unit=tmp_path / "etc" / "systemd" / "system" / "plasma-bootstrap.service",
    )


def test_factory_install_is_runtime_and_fpga_independent(tmp_path: Path):
    paths = _paths(tmp_path)
    result = installer.install_bootstrap(
        source_root=_source(tmp_path),
        host="192.168.2.99",
        port=18081,
        python_executable="/usr/bin/python3",
        paths=paths,
    )

    assert result["result"] == "PASS"
    assert result["control_token_provisioned"] is False
    assert result["runtime_installed"] is False
    assert result["fpga_update"] is False
    assert paths.state_root.stat().st_mode & 0o777 == 0o700
    for name in installer.REQUIRED_SCRIPTS:
        installed = paths.install_root / name
        assert installed.is_file()
        assert installed.stat().st_mode & 0o777 == 0o755

    unit = paths.systemd_unit.read_text(encoding="utf-8")
    assert "ppu-bootstrap-service.py serve --host 192.168.2.99 --port 18081" in unit
    assert "plasma-server.service" not in unit
    assert "plasma-web.service" not in unit
    assert not (tmp_path / "opt" / "plasma" / "current").exists()


def test_factory_install_fails_if_bundle_is_incomplete(tmp_path: Path):
    source = _source(tmp_path)
    (source / "ppu-bootstrap-service.py").unlink()
    with pytest.raises(installer.BootstrapInstallError, match="missing required script"):
        installer.install_bootstrap(
            source_root=source,
            host="192.168.2.99",
            port=18081,
            python_executable="/usr/bin/python3",
            paths=_paths(tmp_path),
        )


def test_enable_now_uses_only_bootstrap_systemd_service(tmp_path: Path):
    calls = []

    def fake_runner(argv, **kwargs):
        calls.append(list(argv))
        return subprocess.CompletedProcess(argv, 0, stdout="")

    result = installer.install_bootstrap(
        source_root=_source(tmp_path),
        host="192.168.2.99",
        port=18081,
        python_executable="/usr/bin/python3",
        paths=_paths(tmp_path),
        enable_now=True,
        runner=fake_runner,
    )

    assert result["enabled_now"] is True
    assert calls == [
        ["systemctl", "daemon-reload"],
        ["systemctl", "enable", "--now", "plasma-bootstrap.service"],
    ]


def test_enable_now_fails_closed_on_systemd_error(tmp_path: Path):
    def fake_runner(argv, **kwargs):
        return subprocess.CompletedProcess(argv, 1, stdout="systemd failure")

    with pytest.raises(installer.BootstrapInstallError, match="systemd activation failed"):
        installer.install_bootstrap(
            source_root=_source(tmp_path),
            host="192.168.2.99",
            port=18081,
            python_executable="/usr/bin/python3",
            paths=_paths(tmp_path),
            enable_now=True,
            runner=fake_runner,
        )

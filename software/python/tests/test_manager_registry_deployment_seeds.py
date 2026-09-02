from __future__ import annotations

from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]


def test_macos_installer_seeds_operator_local_mutable_registry_state() -> None:
    source = (REPO_ROOT / "packaging" / "macos" / "postinstall.sh").read_text(encoding="utf-8")

    assert "registry_state_path: $USER_STATE_ROOT/manager-registry.json" in source
    assert "observation_db_path: $USER_STATE_ROOT/manager-observations.sqlite3" in source


def test_windows_installer_seeds_programdata_mutable_registry_state() -> None:
    source = (REPO_ROOT / "scripts" / "windows-control-station-msi.py").read_text(encoding="utf-8")

    assert r"registry_state_path: C:\\ProgramData\\Plasma\\state\\manager-registry.json" in source
    assert r"observation_db_path: C:\\ProgramData\\Plasma\\state\\manager-observations.sqlite3" in source

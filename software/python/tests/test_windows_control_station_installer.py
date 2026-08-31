from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "windows-control-station-msi.py"


def _load():
    spec = importlib.util.spec_from_file_location("plasma_windows_installer", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_windows_installer_contract_constants_are_pinned() -> None:
    module = _load()
    assert module.WINSW_VERSION == "2.12.0"
    assert module.WINSW_X64_SHA256 == "05b82d46ad331cc16bdc00de5c6332c1ef818df8ceefcd49c726553209b3a0da"
    assert module.WIX_TOOLSET_VERSION == "5.0.2"
    assert module.normalize_architecture("AMD64") == "x86_64"
    with pytest.raises(module.WindowsInstallerError):
        module.normalize_architecture("arm64")


def test_msi_version_rejects_non_semver_and_accepts_prerelease() -> None:
    module = _load()
    assert module._msi_version("1.2.3") == "1.2.3"
    assert module._msi_version("1.2.3-rc.1") == "1.2.3"
    with pytest.raises(module.WindowsInstallerError):
        module._msi_version("1.2")


def test_winsw_hash_fails_closed(tmp_path: Path) -> None:
    module = _load()
    winsw = tmp_path / "WinSW-x64.exe"
    winsw.write_bytes(b"not-winsw")
    with pytest.raises(module.WindowsInstallerError, match="SHA-256 mismatch"):
        module.verify_winsw(winsw)


def test_windows_service_launchers_cover_empty_alias_and_python_probe_regressions() -> None:
    manager = (REPO_ROOT / "packaging" / "windows" / "run-manager.ps1").read_text(encoding="utf-8")
    console = (REPO_ROOT / "packaging" / "windows" / "run-console.ps1").read_text(encoding="utf-8")
    assert "& $candidate --version" in manager
    assert "-replace '^Python\\s+', ''" in manager
    assert "-c 'import sys;" not in manager
    assert "$null -ne $aliasContent" in console
    assert "([string]$aliasContent).Trim()" in console


def test_stage_and_wix_source_keep_scm_and_mutable_config_boundaries(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module = _load()
    repo = tmp_path / "repo"
    packaging = repo / "packaging" / "windows"
    packaging.mkdir(parents=True)
    for name in (
        "run-manager.ps1",
        "run-console.ps1",
        "plasma-manager-service.xml",
        "plasma-console-service.xml",
        "LICENSE-WINSW.txt",
    ):
        (packaging / name).write_text(name + "\n", encoding="utf-8")

    runtime = tmp_path / "runtime"
    (runtime / "console").mkdir(parents=True)
    (runtime / "manager").mkdir(parents=True)
    (runtime / "console" / "server.js").write_text("console\n", encoding="utf-8")
    (runtime / "manager" / "manager.pyz").write_bytes(b"manager")
    winsw = tmp_path / "WinSW-x64.exe"
    winsw.write_bytes(b"winsw-test")
    monkeypatch.setattr(module, "WINSW_X64_SHA256", hashlib.sha256(winsw.read_bytes()).hexdigest())

    release_root, seed = module.stage_payload(
        repo_root=repo,
        runtime_dir=runtime,
        staging_root=tmp_path / "stage",
        version="1.2.3",
        source_release={"git_sha": "abc", "target": "windows-x86_64"},
        winsw_exe=winsw,
    )
    assert (release_root / "bin" / "plasma-manager-service.exe").is_file()
    assert (release_root / "bin" / "plasma-console-service.exe").is_file()
    assert (release_root / "THIRD_PARTY_LICENSES" / "WinSW.txt").is_file()
    assert "ppus: []" in (seed / "manager.yaml").read_text(encoding="utf-8")

    wxs = tmp_path / "installer.wxs"
    module.generate_wix_source(
        release_root=release_root,
        program_data_seed=seed,
        version="1.2.3",
        output_path=wxs,
    )
    text = wxs.read_text(encoding="utf-8")
    assert '<Files Directory="PlasmaVersion"' in text
    assert 'Name="PlasmaManager"' in text
    assert 'Name="PlasmaControlStationConsole"' in text
    assert 'ServiceDependency Id="PlasmaManager"' in text
    assert 'Start="install"' in text
    assert 'Remove="uninstall"' in text
    assert 'Permanent="yes"' in text
    assert 'NeverOverwrite="yes"' in text
    assert "Task Scheduler" not in text

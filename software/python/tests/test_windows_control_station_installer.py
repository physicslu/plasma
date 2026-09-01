from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "windows-control-station-msi.py"
ACCEPTANCE_SCRIPT = REPO_ROOT / "scripts" / "windows-control-station-installer-acceptance.py"
PRODUCT_BUILD_SCRIPT = REPO_ROOT / "software" / "web" / "scripts" / "build-product.mjs"
VINEXT_PATCH_SCRIPT = REPO_ROOT / "software" / "web" / "scripts" / "patch-vinext-windows-static-assets.mjs"


def _load():
    spec = importlib.util.spec_from_file_location("plasma_windows_installer", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_acceptance():
    spec = importlib.util.spec_from_file_location("plasma_windows_installer_acceptance", ACCEPTANCE_SCRIPT)
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
    assert module.BUNDLED_PYTHON_VERSION == "3.12.10"
    assert module.BUNDLED_PYTHON_ARCHIVE_SHA256 == "4acbed6dd1c744b0376e3b1cf57ce906f9dc9e95e68824584c8099a63025a3c3"
    assert module.BUNDLED_NODE_VERSION == "22.23.0"
    assert module.BUNDLED_NODE_ARCHIVE_SHA256 == "425a5bd68cc95e8eb16bcccd0a75081b48983fc6a26f67126bd4d6c7198231e8"
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


def test_windows_service_launchers_only_use_bundled_runtimes() -> None:
    manager = (REPO_ROOT / "packaging" / "windows" / "run-manager.ps1").read_text(encoding="utf-8")
    console = (REPO_ROOT / "packaging" / "windows" / "run-console.ps1").read_text(encoding="utf-8")

    assert "Resolve-BundledPython" in manager
    assert "..\\host-runtime\\python\\python.exe" in manager
    assert "Get-MachineRegisteredPythonCandidates" not in manager
    assert "GetEnvironmentVariable('Path', 'Machine')" not in manager
    assert "Get-Command python.exe" not in manager
    assert "HKLM:" not in manager
    assert "Plasma Manager bundled Python runtime:" in manager
    assert "[switch]$PreflightOnly" in manager

    assert "Resolve-BundledNode" in console
    assert "..\\host-runtime\\node\\node.exe" in console
    assert "GetEnvironmentVariable('Path', 'Machine')" not in console
    assert "Get-Command node.exe" not in console
    assert "Plasma Console bundled Node.js runtime:" in console
    assert "[switch]$PreflightOnly" in console
    assert "$null -ne $aliasContent" in console
    assert "([string]$aliasContent).Trim()" in console
    assert "$env:PLASMA_FLEET_UI_ENABLED = '1'" in console


def test_product_build_applies_version_pinned_vinext_windows_asset_patch() -> None:
    package = json.loads((REPO_ROOT / "software" / "web" / "package.json").read_text(encoding="utf-8"))
    build_source = PRODUCT_BUILD_SCRIPT.read_text(encoding="utf-8")
    patch_source = VINEXT_PATCH_SCRIPT.read_text(encoding="utf-8")

    assert package["devDependencies"]["vinext"] == "0.0.50"
    assert 'PINNED_VINEXT_VERSION = "0.0.50"' in patch_source
    assert 'path.relative(base, batch[j]).split(path.sep).join("/")' in patch_source
    assert "matches.length !== 1" in patch_source
    assert "patchVinextWindowsStaticAssets" in build_source
    assert "Applied pinned vinext Windows static-asset compatibility patch" in build_source


def test_windows_acceptance_requires_packaged_css_and_javascript_assets() -> None:
    module = _load_acceptance()
    html = """
    <html>
      <head><link rel="stylesheet" href="/assets/app-123.css"></head>
      <body><script type="module" src="/assets/app-456.js"></script></body>
    </html>
    """
    assert module._console_asset_paths(html) == (
        "/assets/app-123.css",
        "/assets/app-456.js",
    )

    source = ACCEPTANCE_SCRIPT.read_text(encoding="utf-8")
    assert "Console HTML does not reference any packaged CSS assets" in source
    assert "Console HTML does not reference any packaged JavaScript assets" in source
    assert "Windows installer Control Station entry/assets after SCM restart: PASS" in source


def _fake_python_runtime(root: Path) -> Path:
    root.mkdir(parents=True)
    for name in ("python.exe", "python3.dll", "python312.dll", "python312.zip", "LICENSE.txt"):
        (root / name).write_bytes((name + "\n").encode())
    (root / "python312._pth").write_text("python312.zip\n.\n#import site\n", encoding="utf-8")
    return root


def _fake_node_runtime(root: Path) -> Path:
    root.mkdir(parents=True)
    (root / "node.exe").write_bytes(b"node\n")
    (root / "LICENSE").write_text("node license\n", encoding="utf-8")
    return root


def test_stage_and_wix_source_keep_scm_mutable_config_and_bundled_runtime_boundaries(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
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
    python_runtime = _fake_python_runtime(tmp_path / "python-runtime")
    node_runtime = _fake_node_runtime(tmp_path / "node-runtime")
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
        python_runtime_dir=python_runtime,
        node_runtime_dir=node_runtime,
    )
    assert (release_root / "bin" / "plasma-manager-service.exe").is_file()
    assert (release_root / "bin" / "plasma-console-service.exe").is_file()
    assert (release_root / "THIRD_PARTY_LICENSES" / "WinSW.txt").is_file()
    assert (release_root / "host-runtime" / "python" / "python.exe").is_file()
    assert (release_root / "host-runtime" / "node" / "node.exe").is_file()
    assert (release_root / "host-runtime" / "python" / "LICENSE.txt").is_file()
    assert (release_root / "host-runtime" / "node" / "LICENSE.txt").is_file()
    pth = (release_root / "host-runtime" / "python" / "python312._pth").read_text(encoding="utf-8")
    assert "..\\..\\runtime\\manager\\manager.pyz" in pth
    assert "ppus: []" in (seed / "manager.yaml").read_text(encoding="utf-8")

    manifest = json.loads((release_root / "windows-installer.json").read_text(encoding="utf-8"))
    assert manifest["schema_version"] == 2
    assert manifest["runtime_ownership"] == "bundled"
    assert "external_prerequisites" not in manifest
    assert manifest["bundled_runtimes"]["python"]["version"] == "3.12.10"
    assert manifest["bundled_runtimes"]["node"]["version"] == "22.23.0"

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

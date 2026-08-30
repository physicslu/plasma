from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "macos-control-station-pkg.py"


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


pkg = _load(SCRIPT, "macos_control_station_pkg")
runtime_tool = _load(
    REPO_ROOT / "scripts" / "control-station-runtime.py",
    "macos_installer_test_runtime",
)
release_tool = _load(
    REPO_ROOT / "scripts" / "control-station-release.py",
    "macos_installer_test_release",
)


def _minimal_runtime(root: Path) -> Path:
    runtime = root / "runtime"
    (runtime / "console").mkdir(parents=True)
    (runtime / "manager").mkdir()
    (runtime / "console" / "server.js").write_text("console.log('ok')\n", encoding="utf-8")
    (runtime / "manager" / "manager.pyz").write_bytes(b"placeholder")
    (runtime / "control-station-runtime.json").write_text("{}\n", encoding="utf-8")
    return runtime


def _standalone(root: Path) -> Path:
    standalone = root / "standalone"
    standalone.mkdir()
    (standalone / "server.js").write_text("console.log('standalone');\n", encoding="utf-8")
    (standalone / "package.json").write_text('{"private":true,"type":"module"}\n', encoding="utf-8")
    modules = standalone / "node_modules" / "vinext"
    modules.mkdir(parents=True)
    (modules / "package.json").write_text('{"name":"vinext"}\n', encoding="utf-8")
    return standalone


def _canonical_release(root: Path, architecture: str = "arm64") -> Path:
    runtime = root / "control-runtime"
    runtime_tool.build_runtime(
        repo_root=REPO_ROOT,
        standalone_console=_standalone(root),
        output_dir=runtime,
    )
    return release_tool.build_control_station_release(
        repo_root=REPO_ROOT,
        runtime_dir=runtime,
        output_dir=root / "release-output",
        platform_name="macos",
        architecture=architecture,
        git_sha="a" * 40,
        build_timestamp="2026-08-30T00:00:00Z",
    )


def test_normalize_architecture_supports_macos_targets() -> None:
    assert pkg.normalize_architecture("arm64") == "arm64"
    assert pkg.normalize_architecture("aarch64") == "arm64"
    assert pkg.normalize_architecture("x86_64") == "x86_64"


def test_stage_payload_separates_immutable_runtime_from_user_state(tmp_path: Path) -> None:
    runtime = _minimal_runtime(tmp_path)
    stage = tmp_path / "stage"
    source_release = {
        "artifact_sha256": "b" * 64,
        "git_sha": "a" * 40,
        "target": "macos-arm64",
        "contracts": {"web_rest_api": "3"},
    }
    release = pkg.stage_payload(
        repo_root=REPO_ROOT,
        runtime_dir=runtime,
        staging_root=stage,
        version="9.8.7",
        architecture="arm64",
        source_release=source_release,
    )
    assert release == stage / "Library" / "Application Support" / "Plasma" / "releases" / "9.8.7"
    assert (release / "runtime" / "console" / "server.js").is_file()
    assert (release / "bin" / "run-manager.sh").stat().st_mode & 0o111
    assert (release / "bin" / "run-console.sh").stat().st_mode & 0o111
    assert (release / "bin" / "service-control.sh").stat().st_mode & 0o111
    assert (release / "bin" / "uninstall-pilot.sh").stat().st_mode & 0o111
    assert (release / "launchd" / "com.plasma.manager.plist").is_file()
    assert (release / "launchd" / "com.plasma.console.plist").is_file()
    manifest = json.loads((release / "macos-installer.json").read_text(encoding="utf-8"))
    assert manifest["service_manager"] == "launchd-launchagent"
    assert manifest["external_prerequisites"] == {"node": ">=22.13", "python": ">=3.11"}
    assert manifest["console"] == {"host": "127.0.0.1", "port": 18000}
    assert manifest["manager"] == {"host": "127.0.0.1", "port": 18180}
    assert manifest["architecture"] == "arm64"
    assert manifest["source_release"] == source_release
    assert manifest["signed"] is False
    assert manifest["notarized"] is False
    assert not (stage / "Users").exists()


def test_installer_input_must_pass_common_release_verification(tmp_path: Path) -> None:
    artifact = _canonical_release(tmp_path)
    manifest, release_root = pkg.verify_release_input(
        repo_root=REPO_ROOT,
        release_artifact=artifact,
        extract_to=tmp_path / "verified",
        architecture="arm64",
    )
    assert manifest["role"] == "control-station"
    assert manifest["platform"] == "macos"
    assert manifest["architecture"] == "arm64"
    assert manifest["artifact_sha256"]
    assert (release_root / "runtime" / "console" / "server.js").is_file()
    assert (release_root / "runtime" / "manager" / "manager.pyz").is_file()


def test_installer_rejects_tampered_release_sidecar(tmp_path: Path) -> None:
    artifact = _canonical_release(tmp_path)
    Path(str(artifact) + ".sha256").write_text(f"{'0' * 64}  {artifact.name}\n", encoding="utf-8")
    with pytest.raises(pkg.MacOSInstallerError, match="release verification failed"):
        pkg.verify_release_input(
            repo_root=REPO_ROOT,
            release_artifact=artifact,
            extract_to=tmp_path / "verified",
            architecture="arm64",
        )


def test_installer_rejects_release_for_other_architecture(tmp_path: Path) -> None:
    artifact = _canonical_release(tmp_path, architecture="arm64")
    with pytest.raises(pkg.MacOSInstallerError, match="release verification failed"):
        pkg.verify_release_input(
            repo_root=REPO_ROOT,
            release_artifact=artifact,
            extract_to=tmp_path / "verified",
            architecture="x86_64",
        )


def test_public_pkg_cli_requires_release_artifact_not_raw_runtime() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert 'parser.add_argument("--release-artifact", required=True' in source
    assert 'parser.add_argument("--runtime-dir"' not in source
    assert "verify_release(" in source
    assert "expect_role=release_tool.ROLE_CONTROL_STATION" in source
    assert 'expect_platform="macos"' in source


def test_launch_wrappers_use_recorded_absolute_runtime_paths_not_shell_path() -> None:
    manager = (REPO_ROOT / "packaging" / "macos" / "run-manager.sh").read_text(encoding="utf-8")
    console = (REPO_ROOT / "packaging" / "macos" / "run-console.sh").read_text(encoding="utf-8")
    postinstall = (REPO_ROOT / "packaging" / "macos" / "postinstall.sh").read_text(encoding="utf-8")
    assert 'PYTHON_PATH_FILE="$INSTALL_ROOT/python-path"' in manager
    assert 'NODE_PATH_FILE="$INSTALL_ROOT/node-path"' in console
    assert 'exec "$PYTHON_PATH"' in manager
    assert 'exec "$NODE_PATH"' in console
    assert ".nvm/versions/node/*/bin/node" in postinstall
    assert ".pyenv/versions/*/bin/python3" in postinstall
    assert "Python >= 3.11" in postinstall
    assert "Node.js >= 22.13" in postinstall
    assert "source " not in manager
    assert "source " not in console


def test_launchagents_are_per_user_and_product_services_are_loopback_only() -> None:
    manager = (REPO_ROOT / "packaging" / "macos" / "com.plasma.manager.plist").read_text(encoding="utf-8")
    console = (REPO_ROOT / "packaging" / "macos" / "com.plasma.console.plist").read_text(encoding="utf-8")
    run_console = (REPO_ROOT / "packaging" / "macos" / "run-console.sh").read_text(encoding="utf-8")
    postinstall = (REPO_ROOT / "packaging" / "macos" / "postinstall.sh").read_text(encoding="utf-8")
    assert "com.plasma.manager" in manager
    assert "com.plasma.console" in console
    assert 'export HOST="127.0.0.1"' in run_console
    assert 'PLASMA_MANAGER_API_URL="http://127.0.0.1:18180"' in run_console
    assert 'USER_LAUNCH_ROOT="$INSTALL_HOME/Library/LaunchAgents"' in postinstall
    assert 'DOMAIN="gui/$INSTALL_UID"' in postinstall
    assert "/Library/LaunchDaemons" not in postinstall


def test_pilot_uninstall_preserves_user_mutable_data_by_contract() -> None:
    uninstall = (REPO_ROOT / "packaging" / "macos" / "uninstall-pilot.sh").read_text(encoding="utf-8")
    assert 'rm -rf "$PRODUCT_ROOT/releases" "$PRODUCT_ROOT/current" "$PRODUCT_ROOT/install"' in uninstall
    assert "Application Support/Plasma/config" not in uninstall
    assert "Library/Logs/Plasma" not in uninstall
    assert "pkgutil --forget" in uninstall

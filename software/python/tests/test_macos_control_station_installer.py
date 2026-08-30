from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "macos-control-station-pkg.py"
spec = importlib.util.spec_from_file_location("macos_control_station_pkg", SCRIPT)
assert spec is not None and spec.loader is not None
pkg = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = pkg
spec.loader.exec_module(pkg)


def _minimal_runtime(root: Path) -> Path:
    runtime = root / "runtime"
    (runtime / "console").mkdir(parents=True)
    (runtime / "manager").mkdir()
    (runtime / "console" / "server.js").write_text("console.log('ok')\n", encoding="utf-8")
    (runtime / "manager" / "manager.pyz").write_bytes(b"placeholder")
    (runtime / "control-station-runtime.json").write_text("{}\n", encoding="utf-8")
    return runtime


def test_normalize_architecture_supports_macos_targets() -> None:
    assert pkg.normalize_architecture("arm64") == "arm64"
    assert pkg.normalize_architecture("aarch64") == "arm64"
    assert pkg.normalize_architecture("x86_64") == "x86_64"


def test_stage_payload_separates_immutable_runtime_from_user_state(tmp_path: Path) -> None:
    runtime = _minimal_runtime(tmp_path)
    stage = tmp_path / "stage"
    release = pkg.stage_payload(repo_root=REPO_ROOT, runtime_dir=runtime, staging_root=stage, version="9.8.7", validate_runtime=False)
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
    assert manifest["signed"] is False
    assert manifest["notarized"] is False
    assert not (stage / "Users").exists()


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

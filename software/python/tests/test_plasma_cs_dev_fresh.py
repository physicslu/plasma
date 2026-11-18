"""Host-only mock of developer fresh-State CLI cutover (never touches real systemd)."""
from __future__ import annotations

import json
from pathlib import Path
import subprocess

from plasma_manager.bootstrap import BootstrapCredentialStore
from plasma_manager.registry import PPURegistryStore


ROOT = Path(__file__).resolve().parents[3]
BACKEND = ROOT / "utilities/plasmactl/backends/plasmactl-local-control-station"
HARNESS = r"""
set -Eeuo pipefail
source "$1" help >/dev/null
root="$2"
state_home="$root/statehome"
state_dir="$state_home/plasma/local-control-station"
config_home="$root/config"
config_dir="$config_home/plasma/local-control-station"
config_file="$config_dir/profile.env"
manager_config="$config_dir/manager.yaml"
unit_dir="$config_home/systemd/user"
manager_unit="$unit_dir/plasma-local-manager.service"
console_unit="$unit_dir/plasma-control-station.service"
evidence="$state_dir/install.json"
release_root="$root/releases"
current_link="$root/current"
mkdir -p "$state_dir" "$config_dir" "$unit_dir" "$release_root/old" "$release_root/new"
printf 'ORIGINAL_HISTORY\n' > "$state_dir/old-journal.json"
printf 'OLD_INSTALL\n' > "$evidence"
printf 'OLD_PROFILE\n' > "$config_file"
printf 'OLD_MANAGER_CONFIG\n' > "$manager_config"
printf 'OLD_MANAGER_UNIT\n' > "$manager_unit"
printf 'OLD_CONSOLE_UNIT\n' > "$console_unit"
if [[ "${PAIRING:-0}" == 1 ]]; then
  printf '%s\n' '{"schema_version":1,"ppus":[{"endpoint":"http://z2.local:18080","alias":"z2","lifecycle":"commissioned","registered_at":"2026-01-01T00:00:00Z","updated_at":"2026-01-01T00:00:00Z"}]}' > "$state_dir/registry.json"
  printf '%s\n' '{"schema_version":2,"credentials":{"z2":{"device_id":"ppu-device-z2-0001","token":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","updated_at":"2026-01-01T00:00:00Z","generation":7,"controller_id":"controller-1"}}}' > "$state_dir/bootstrap-credentials.json"
  chmod 600 "$state_dir/bootstrap-credentials.json"
fi
if [[ "${MODE:-success}" == "symlink" ]]; then
  ln -sfn "$state_dir/old-journal.json" "$state_dir/registry.json"
fi
ln -s "$release_root/old" "$current_link"
dev_fresh_state="${FRESH:-1}"
current_sha() { printf '%040d\n' 0; }
prepare_release() { prepared_release="$release_root/new"; }
require_linux_user_runtime() { :; }
require_command() { :; }
resolve_base_python() { :; }
validate_settings() { :; }
require_clean_source() { :; }
require_owned_installation() { :; }
systemctl() {
  printf 'SYSTEMCTL %s\n' "$*" >> "$root/events"
  return 0
}
check_development_ppu_idle() {
  printf 'PPU_IDLE_CHECK\n' >> "$root/events"
  [[ "${MODE:-success}" != "busy" ]]
}
run_deployment_preflight() {
  printf 'PREFLIGHT_CHECK\n' >> "$root/events"
  [[ "${MODE:-success}" == "ordinary" ]]
}
write_profile_config() { printf 'NEW_PROFILE\n' > "$config_file"; }
write_manager_config() {
  printf 'NEW_MANAGER_CONFIG\n' > "$manager_config"
  [[ "${MODE:-success}" != "rollback" ]]
}
write_units() {
  printf 'NEW_MANAGER_UNIT\n' > "$manager_unit"
  printf 'NEW_CONSOLE_UNIT\n' > "$console_unit"
}
write_evidence() { printf 'NEW_INSTALL\n' > "$evidence"; }
wait_for_http() { :; }
verify_profile() { printf 'VERIFY_OK\n' >> "$root/events"; }
deploy_profile
"""


def invoke(tmp_path: Path, mode: str, *, paired: bool = False, fresh: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", "-c", HARNESS, "test-fresh", str(BACKEND), str(tmp_path)],
        capture_output=True, text=True, timeout=30,
        env={"MODE": mode, "PAIRING": "1" if paired else "0", "FRESH": "1" if fresh else "0",
             "PATH": "/usr/bin:/bin", "HOME": str(tmp_path)},
        check=False,
    )


def test_backend_shell_syntax() -> None:
    p = subprocess.run(["bash", "-n", str(BACKEND)], capture_output=True, text=True)
    assert p.returncode == 0, p.stderr


def test_development_fresh_state_archives_and_activates_without_journal_migration(tmp_path: Path) -> None:
    result = invoke(tmp_path, "success")
    assert result.returncode == 0, result.stdout + result.stderr
    state = tmp_path / "statehome/plasma/local-control-station"
    assert (state / "install.json").read_text() == "NEW_INSTALL\n"
    assert not (state / "old-journal.json").exists()
    archive = list(state.parent.glob("local-control-station.archive.*"))
    assert len(archive) == 1
    assert (archive[0] / "old-journal.json").read_text() == "ORIGINAL_HISTORY\n"
    assert (archive[0] / "install.json").read_text() == "OLD_INSTALL\n"
    assert not (state / "registry.json").exists()
    assert not (state / "bootstrap-credentials.json").exists()
    assert (tmp_path / "current").resolve() == tmp_path / "releases/new"
    events = (tmp_path / "events").read_text()
    assert events.count("PPU_IDLE_CHECK") == 3
    assert events.index("SYSTEMCTL --user stop plasma-control-station.service") < (
        events.index("SYSTEMCTL --user stop plasma-local-manager.service"))
    assert "SYSTEMCTL --user restart plasma-local-manager.service" in events
    assert "SYSTEMCTL --user restart plasma-control-station.service" in events
    assert "PREFLIGHT_CHECK" not in events
    assert "VERIFY_OK" in events
    assert "dev-fresh PASS" in result.stdout


def test_development_fresh_state_preserves_pairing_identity(tmp_path: Path) -> None:
    result = invoke(tmp_path, "success", paired=True)
    assert result.returncode == 0, result.stdout + result.stderr
    state = tmp_path / "statehome/plasma/local-control-station"
    archive = next(state.parent.glob("local-control-station.archive.*"))
    for name in ("registry.json", "bootstrap-credentials.json"):
        assert (state / name).read_bytes() == (archive / name).read_bytes()
    credential = json.loads((state / "bootstrap-credentials.json").read_text())["credentials"]["z2"]
    assert credential["device_id"] == "ppu-device-z2-0001"
    assert credential["token"] == "a" * 32
    assert credential["generation"] == 7
    assert credential["controller_id"] == "controller-1"
    assert PPURegistryStore((), state / "registry.json").record_by_alias("z2") is not None
    loaded = BootstrapCredentialStore(state / "bootstrap-credentials.json").record_for("z2")
    assert (loaded.device_id, loaded.token, loaded.generation, loaded.controller_id) == (
        "ppu-device-z2-0001", "a" * 32, 7, "controller-1")
    assert (state / "bootstrap-credentials.json").stat().st_mode & 0o777 == 0o600
    assert not (state / "old-journal.json").exists()


def test_ordinary_deploy_keeps_existing_state_and_preflight(tmp_path: Path) -> None:
    result = invoke(tmp_path, "ordinary", paired=True, fresh=False)
    assert result.returncode == 0, result.stdout + result.stderr
    state = tmp_path / "statehome/plasma/local-control-station"
    assert (state / "old-journal.json").read_text() == "ORIGINAL_HISTORY\n"
    assert (state / "registry.json").exists()
    assert (state / "bootstrap-credentials.json").exists()
    assert not list(state.parent.glob("local-control-station.archive.*"))
    events = (tmp_path / "events").read_text()
    assert events.count("PREFLIGHT_CHECK") == 2
    assert "PPU_IDLE_CHECK" not in events


def test_failed_development_cutover_restores_old_state_and_release(tmp_path: Path) -> None:
    result = invoke(tmp_path, "rollback", paired=True)
    assert result.returncode != 0
    assert "activation failed" in result.stdout
    state = tmp_path / "statehome/plasma/local-control-station"
    assert (state / "old-journal.json").read_text() == "ORIGINAL_HISTORY\n"
    assert (state / "install.json").read_text() == "OLD_INSTALL\n"
    assert (state / "registry.json").exists()
    assert (state / "bootstrap-credentials.json").exists()
    assert (tmp_path / "current").resolve() == tmp_path / "releases/old"
    assert (tmp_path / "config/plasma/local-control-station/manager.yaml").read_text() == (
        "OLD_MANAGER_CONFIG\n")
    events = (tmp_path / "events").read_text()
    assert "SYSTEMCTL --user restart plasma-local-manager.service" in events
    assert "SYSTEMCTL --user restart plasma-control-station.service" in events
    assert not list(state.parent.glob("local-control-station.archive.*"))
    assert len(list(state.parent.glob("local-control-station.failed.*"))) == 1


def test_development_fresh_state_rejects_symlink_pairing_file_and_restores_state(tmp_path: Path) -> None:
    result = invoke(tmp_path, "symlink", paired=True)
    assert result.returncode != 0
    assert "pairing state is not a regular file: registry.json" in result.stdout
    state = tmp_path / "statehome/plasma/local-control-station"
    assert (state / "registry.json").is_symlink()
    assert (state / "bootstrap-credentials.json").exists()
    assert (tmp_path / "current").resolve() == tmp_path / "releases/old"
    assert not list(state.parent.glob("local-control-station.archive.*"))


def test_busy_ppu_refuses_cutover_before_services_stop(tmp_path: Path) -> None:
    result = invoke(tmp_path, "busy")
    assert result.returncode != 0
    state = tmp_path / "statehome/plasma/local-control-station"
    assert (state / "old-journal.json").read_text() == "ORIGINAL_HISTORY\n"
    assert (tmp_path / "current").resolve() == tmp_path / "releases/old"
    assert not list(state.parent.glob("local-control-station.archive.*"))
    assert "SYSTEMCTL --user stop" not in (tmp_path / "events").read_text()

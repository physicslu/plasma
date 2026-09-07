from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLASMACTL = REPO_ROOT / "scripts" / "plasmactl"
INTEGRATION = REPO_ROOT / "scripts" / "plasmactl-integration"
LOCAL_CONTROL_STATION = REPO_ROOT / "scripts" / "plasmactl-local-control-station"
SWPC_Z2LIKE = REPO_ROOT / "scripts" / "plasmactl-swpc-z2like"


def run(*args: str, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    merged = os.environ.copy()
    merged.update(env or {})
    return subprocess.run(
        ["bash", str(PLASMACTL), *args],
        cwd=REPO_ROOT,
        env=merged,
        text=True,
        capture_output=True,
        check=False,
    )


def test_profile_scripts_are_valid_bash() -> None:
    for path in (PLASMACTL, INTEGRATION, LOCAL_CONTROL_STATION, SWPC_Z2LIKE):
        result = subprocess.run(
            ["bash", "-n", str(path)],
            cwd=REPO_ROOT,
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, f"{path}: {result.stderr}"


def test_library_mode_preserves_legacy_integration_functions_but_reexecs_through_router(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "PLASMACTL_LIB_ONLY": "1",
            "PLASMACTL_CONFIG": str(tmp_path / "no-config.env"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
            "PLASMA_PYTHON": sys.executable,
        }
    )
    result = subprocess.run(
        [
            "bash",
            "-c",
            'source "$1"; declare -F deploy >/dev/null; declare -F write_units >/dev/null; '
            '[[ "$script_path" == "$(readlink -f "$1")" ]]',
            "_",
            str(PLASMACTL),
        ],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr


def test_legacy_default_and_explicit_integration_profiles_are_declared() -> None:
    source = PLASMACTL.read_text(encoding="utf-8")
    assert '""|integration) printf' in source
    assert "Legacy integration-host install (default; backward compatible)" in source
    assert "update-and-restart" in source
    assert "plasmactl-integration" in source


def test_local_control_station_profile_delegates_to_dedicated_backend(tmp_path: Path) -> None:
    log = tmp_path / "local-backend.log"
    fake = tmp_path / "fake-local-backend.sh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        f"printf '%s\\n' \"$*\" >> {log!s}\n",
        encoding="utf-8",
    )
    env = {"PLASMA_LOCAL_CONTROL_STATION_BACKEND": str(fake)}

    cases = (
        (
            ("install", "local-control-station", "--ppu-endpoint", "http://127.0.0.1:18081"),
            "install --ppu-endpoint http://127.0.0.1:18081",
        ),
        (
            ("deploy", "local-control-station", "--ppu-alias", "z2-lab"),
            "deploy --ppu-alias z2-lab",
        ),
        (("verify", "local-control-station"), "verify"),
        (("status", "local-control-station"), "status"),
    )
    for args, _ in cases:
        result = run(*args, env=env)
        assert result.returncode == 0, result.stderr

    assert log.read_text(encoding="utf-8").splitlines() == [expected for _, expected in cases]


def test_local_control_station_is_console_manager_only_and_loopback_bound() -> None:
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    assert 'console_host="127.0.0.1"' in source
    assert 'manager_host="127.0.0.1"' in source
    assert "plasma-local-manager.service" in source
    assert "plasma-control-station.service" in source
    assert "PLASMA_CONTROL_STATION_MODE=managed" in source
    assert "PLASMA_MANAGER_API_URL=http://$manager_host:$manager_port" in source
    assert "PLASMA_MANAGER_PPU_ALIAS=$ppu_alias" in source
    assert "plasma-server.service" not in source
    assert "plasma-web.service" not in source
    assert "hardware_claim\": \"none\"" in source
    assert "PPU/PS/PL/Site/IC readiness is separate" in source


def test_local_control_station_target_is_configurable_and_not_swpc_hardcoded() -> None:
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    assert "--ppu-endpoint" in source
    assert 'parsed.scheme not in {"http", "https"}' in source
    assert "PPU endpoint must not embed credentials" in source
    assert "PPU endpoint must not contain query or fragment" in source
    assert "PPU endpoint must identify the Plasma Gateway root" in source
    assert "ppu-lab.open4th.com" not in source
    assert "plasma.open4th.com" not in source
    assert "swpc-z2like-01" not in source


def test_local_control_station_uses_immutable_release_and_activation_rollback() -> None:
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    assert 'release_root="$data_home/plasma/local-control-station/releases"' in source
    assert 'current_link="$data_home/plasma/local-control-station/current"' in source
    assert "repository must be clean before local Control Station activation" in source
    assert "building immutable local Control Station release" in source
    assert "activation failed; restoring previous local Control Station release/configuration" in source
    assert "install evidence/current release mismatch" in source
    for forbidden in ("git pull", "git merge", "git reset", "git checkout"):
        assert forbidden not in source


def test_local_control_station_linux_reference_does_not_claim_cross_platform_installer() -> None:
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    assert "Linux user-systemd only" in source
    assert "macOS/Windows require their platform package" in source
    assert "macOS and Windows" in source
    assert "platform-native" in source


def test_swpc_z2like_profile_delegates_to_backend_without_browser_selected_target(tmp_path: Path) -> None:
    log = tmp_path / "backend.log"
    fake = tmp_path / "fake-backend.sh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        f"printf '%s\\n' \"$*\" >> {log!s}\n",
        encoding="utf-8",
    )
    env = {"PLASMA_SWPC_Z2LIKE_BACKEND": str(fake)}

    cases = (
        (("install", "swpc-z2like", "--ppu-id", "lab-ppu"), "install --ppu-id lab-ppu"),
        (("deploy", "swpc-z2like", "--proxy-port", "19081"), "deploy --proxy-port 19081"),
        (("verify", "swpc-z2like"), "verify"),
        (("status", "swpc-z2like"), "status"),
    )
    for args, _ in cases:
        result = run(*args, env=env)
        assert result.returncode == 0, result.stderr

    assert log.read_text(encoding="utf-8").splitlines() == [expected for _, expected in cases]
    source = PLASMACTL.read_text(encoding="utf-8")
    assert "ppu-lab.open4th.com" not in source
    assert "target_url" not in source


def test_unknown_profile_fails_closed() -> None:
    result = run("deploy", "future-hardware")
    assert result.returncode != 0
    assert "unknown deployment profile" in result.stderr


def test_real_z2_profiles_remain_reserved_not_aliases() -> None:
    source = PLASMACTL.read_text(encoding="utf-8")
    assert "z2-ps and z2-full remain reserved" in source
    assert "`z2` is intentionally not accepted yet" in source
    for profile in ("z2", "z2-ps", "z2-full"):
        result = run("deploy", profile)
        assert result.returncode != 0
        assert "unknown deployment profile" in result.stderr


def test_update_and_restart_remains_integration_only(tmp_path: Path) -> None:
    log = tmp_path / "backend.log"
    fake = tmp_path / "fake-backend.sh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        f"printf '%s\\n' \"$*\" >> {log!s}\n",
        encoding="utf-8",
    )
    result = run(
        "update-and-restart",
        "swpc-z2like",
        env={"PLASMA_SWPC_Z2LIKE_BACKEND": str(fake)},
    )
    assert result.returncode != 0
    assert "integration-only alias" in result.stderr
    assert not log.exists()


def test_swpc_backend_keeps_system_profile_separate_from_integration_user_services() -> None:
    source = SWPC_Z2LIKE.read_text(encoding="utf-8")
    assert "/opt/plasma/install/last-swpc-z2like-install.json" in source
    assert "/etc/systemd/system/plasma-server.service" in source
    assert "/etc/systemd/system/plasma-web.service" in source
    assert "systemctl --user stop" not in source
    assert "integration-host user services are never stopped implicitly" in source
    assert '"z2_equivalent": False' in source
    assert '"hardware_boundary": "closed"' in source
    assert '"configured_site_count": 0' in source
    assert '"max_supported_sites": 8' in source


def test_swpc_backend_verifies_restricted_ingress_and_ps_only_boundary() -> None:
    source = SWPC_Z2LIKE.read_text(encoding="utf-8")
    assert "/api/settings/sites" in source
    assert '[[ "$blocked_status" == "404" ]]' in source
    assert "/api/engineering/diagnostics/loopback" in source
    assert 'loopback.get("endpoint") != "ps"' in source
    assert 'loopback.get("source") != "ps"' in source
    assert "no Z2/ARMv7/PL/FPGA/Site/IC claim" in source


def test_swpc_activation_requires_evidence_current_and_system_ownership_consistency() -> None:
    source = SWPC_Z2LIKE.read_text(encoding="utf-8")
    assert "PPU configuration is missing" in source
    assert "install evidence/current release mismatch" in source
    assert "plasma-server.service is not owned by the Plasma system runtime" in source
    assert "restricted Nginx ingress is not Plasma-owned" in source


def test_swpc_deploy_has_explicit_rollback_retry_cleanup_and_does_not_mutate_git() -> None:
    source = SWPC_Z2LIKE.read_text(encoding="utf-8")
    assert "repository must be clean" in source
    assert "deployment failed; restoring previous qualified SWPC Z2-like activation" in source
    assert "rollback restored" in source
    assert "stale unqualified target exists from a prior failed activation" in source
    assert "removing unqualified inactive release" in source
    assert "rm -rf --one-file-system" in source
    assert "git -C \"$repo_root\" rev-parse HEAD" in source
    for forbidden in ("git pull", "git merge", "git reset", "git checkout"):
        assert forbidden not in source


def test_swpc_first_install_is_fail_closed_and_cleans_only_a_prechecked_clean_boundary() -> None:
    source = SWPC_Z2LIKE.read_text(encoding="utf-8")
    assert "first install found unmanaged/pre-existing appliance artifact without install evidence" in source
    assert "first install failed; removing only artifacts created inside the clean SWPC Z2-like boundary" in source
    assert "require_clean_first_install_boundary" in source

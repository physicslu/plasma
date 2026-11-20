from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLASMACTL = REPO_ROOT / "scripts" / "plasmactl"
INTEGRATION = REPO_ROOT / "utilities" / "plasmactl" / "backends" / "plasmactl-integration"
LOCAL_CONTROL_STATION = REPO_ROOT / "utilities" / "plasmactl" / "backends" / "plasmactl-local-control-station"
SWPC_Z2LIKE = REPO_ROOT / "utilities" / "plasmactl" / "backends" / "plasmactl-swpc-z2like"
Z2_PS = REPO_ROOT / "utilities" / "plasmactl" / "backends" / "plasmactl-z2-ps"
CLI_MAIN = REPO_ROOT / "utilities" / "plasmactl" / "src" / "plasma_cli" / "main.py"
CLI_OPERATIONS = REPO_ROOT / "utilities" / "plasmactl" / "src" / "plasma_cli" / "operations.py"


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
    for path in (
        PLASMACTL,
        INTEGRATION,
        LOCAL_CONTROL_STATION,
        SWPC_Z2LIKE,
        Z2_PS,
    ):
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
    # One canonical router (Python); integration stays the default profile.
    operations_source = CLI_OPERATIONS.read_text(encoding="utf-8")
    main_source = CLI_MAIN.read_text(encoding="utf-8")
    assert 'add_argument("target", nargs="?", default="integration"' in main_source
    assert "SWPC development/integration host (default; user systemd)" in main_source
    assert '"update-and-restart": "deploy"' in operations_source
    assert '"plasmactl-integration"' in operations_source
    assert "exec python3 -m plasma_cli.main" in PLASMACTL.read_text(encoding="utf-8")


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
            ("install", "local-control-station", "--ppu-endpoint", "http://127.0.0.1:18080"),
            "install --ppu-endpoint http://127.0.0.1:18080",
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



def _resolve_local_python_from_fixture(root: Path, configured: str = "") -> subprocess.CompletedProcess[str]:
    """Execute only the pinned Bash resolver using temporary fake executables."""
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    resolver = "python_is_supported() {" + source.split("python_is_supported() {", 1)[1].split("\nrequire_clean_source() {", 1)[0]
    harness = (
        "set -euo pipefail\n"
        'die() { printf "%s\\n" "$*" >&2; exit 77; }\n'
        f"plasma_python_root={shlex.quote(str(root))}\n"
        f"base_python={shlex.quote(configured)}\n"
        f"{resolver}\n"
        # Replace qualification with a safe executable check. This test checks
        # path identity; real version gating remains in python_is_supported().
        'python_is_supported() { [[ -x "$1" ]]; }\n'
        'resolve_base_python\nprintf "%s\\n" "$base_python"\n'
    )
    return subprocess.run(
        ["bash", "-c", harness], capture_output=True, text=True, check=False, timeout=10
    )


def test_local_control_station_runtime_aliases_are_one_canonical_interpreter(tmp_path: Path) -> None:
    base = tmp_path / "cpython-3.12.13-linux-x86_64-gnu"
    interpreter = base / "bin" / "python3"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("#!/bin/sh\\nexit 0\\n", encoding="utf-8")
    interpreter.chmod(0o755)

    (tmp_path / "cpython-3.12-linux-x86_64-gnu").symlink_to(base, target_is_directory=True)
    venv_alias = tmp_path / "3.12.13" / "bin" / "python3"
    venv_alias.parent.mkdir(parents=True)
    venv_alias.symlink_to(interpreter)
    (tmp_path / "broken").symlink_to(tmp_path / "missing-runtime", target_is_directory=True)

    result = _resolve_local_python_from_fixture(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(interpreter.resolve())
    # The saved explicit path must remain unchanged: do not silently change
    # the installed Control Station's selected venv or config.
    selected = _resolve_local_python_from_fixture(tmp_path, str(venv_alias))
    assert selected.returncode == 0
    assert selected.stdout.strip() == str(venv_alias)


def test_local_control_station_distinct_interpreters_still_fail_closed(tmp_path: Path) -> None:
    for name in ("cpython-3.12.13-linux-x86_64-gnu", "cpython-3.13.0-linux-x86_64-gnu"):
        python = tmp_path / name / "bin" / "python3"
        python.parent.mkdir(parents=True)
        python.write_text("#!/bin/sh\\nexit 0\\n", encoding="utf-8")
        python.chmod(0o755)
    result = _resolve_local_python_from_fixture(tmp_path)
    assert result.returncode == 77
    assert "multiple Plasma Python runtimes found" in result.stderr


def _run_local_node_path_resolver(home: Path, path: str = "/missing-node-tools") -> subprocess.CompletedProcess[str]:
    """Execute only the backend PATH resolver, never a deployment or service."""
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    resolver = (
        "ensure_nvm_node22_path() {"
        + source.split("ensure_nvm_node22_path() {", 1)[1]
        .split("\nprepare_release() {", 1)[0]
    )
    harness = (
        "set -euo pipefail\n"
        'die() { printf "%s\\n" "$*" >&2; exit 77; }\n'
        f"{resolver}\n"
        'ensure_nvm_node22_path\nprintf "%s\\n" "$PATH"\n'
    )
    return subprocess.run(
        ["/bin/bash", "-c", harness],
        env={"HOME": str(home), "PATH": path},
        capture_output=True, text=True, check=False, timeout=10,
    )


def test_local_control_station_resolves_single_existing_nvm_node22(tmp_path: Path) -> None:
    node_bin = tmp_path / ".nvm/versions/node/v22.23.2/bin"
    node_bin.mkdir(parents=True)
    for name in ("node", "npm"):
        tool = node_bin / name
        tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tool.chmod(0o755)
    old_bin = tmp_path / ".nvm/versions/node/v20.19.0/bin"
    old_bin.mkdir(parents=True)
    (old_bin / "node").write_text("not executable\n")

    result = _run_local_node_path_resolver(tmp_path)
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == f"{node_bin}:/missing-node-tools"
    # A qualified tool pair already on PATH must remain the caller's choice.
    existing = _run_local_node_path_resolver(tmp_path, str(node_bin))
    assert existing.returncode == 0, existing.stderr
    assert existing.stdout.strip() == str(node_bin)


def test_local_control_station_nvm_path_fails_closed_on_ambiguity(tmp_path: Path) -> None:
    for version in ("v22.22.0", "v22.23.2"):
        bin_dir = tmp_path / ".nvm/versions/node" / version / "bin"
        bin_dir.mkdir(parents=True)
        for name in ("node", "npm"):
            tool = bin_dir / name
            tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            tool.chmod(0o755)
    result = _run_local_node_path_resolver(tmp_path)
    assert result.returncode == 77
    assert "multiple NVM Node.js 22 runtimes found" in result.stderr


def test_local_control_station_does_not_select_incomplete_nvm_install(tmp_path: Path) -> None:
    bin_dir = tmp_path / ".nvm/versions/node/v22.23.2/bin"
    bin_dir.mkdir(parents=True)
    tool = bin_dir / "node"
    tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    tool.chmod(0o755)
    result = _run_local_node_path_resolver(tmp_path)
    assert result.returncode == 0
    assert result.stdout.strip() == "/missing-node-tools"


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
        (("deploy", "swpc-z2like", "--facility-id", "lab"), "deploy --facility-id lab"),
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


def test_z2_ps_profile_delegates_without_aliasing_swpc_surrogate(tmp_path: Path) -> None:
    log = tmp_path / "z2-backend.log"
    fake = tmp_path / "fake-z2-backend.sh"
    fake.write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        f"printf '%s\\n' \"$*\" >> {log!s}\n",
        encoding="utf-8",
    )
    env = {"PLASMA_Z2_PS_BACKEND": str(fake)}
    cases = (
        (("install", "z2-ps", "--gateway-host", "192.168.2.99"), "install --gateway-host 192.168.2.99"),
        (("deploy", "z2-ps", "--gateway-host", "192.168.2.99"), "deploy --gateway-host 192.168.2.99"),
        (("verify", "z2-ps"), "verify"),
        (("status", "z2-ps"), "status"),
    )
    for args, _ in cases:
        result = run(*args, env=env)
        assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [expected for _, expected in cases]
    assert "Real PYNQ-Z2 ARMv7 PS-only" in run("help").stdout
    source = CLI_OPERATIONS.read_text(encoding="utf-8")
    assert '"z2-ps": ("PLASMA_Z2_PS_BACKEND", "plasmactl-z2-ps")' in source
    assert '"z2-ps": ("PLASMA_SWPC_Z2LIKE_BACKEND"' not in source


def test_z2_ps_backend_keeps_pynq_python_and_hardware_boundary_closed() -> None:
    source = Z2_PS.read_text(encoding="utf-8")
    assert "--python-artifact" in source
    assert "$product_root/python" in source
    assert "--openocd-artifact" in source
    assert "PLASMA_Z2_OPENOCD_RUNTIME_TOOL" in source
    assert "$product_root/programming-engines/openocd" in source
    assert "hardware_runtime_ready=false" in source
    assert "starts_openocd_service" in source
    assert "/usr/bin/python3" not in source
    assert "PS-only" in source
    assert "PL/FPGA/Site/power/real-IC readiness is separate" in source
    # LOM-P2A-2 P0: the kit sends no Gateway write; read-only G13 readiness only.
    assert "/api/engineering/diagnostics/loopback" not in source
    assert '"$readiness_tool" --gateway "$base"' in source


def test_unknown_profile_fails_closed() -> None:
    result = run("deploy", "future-hardware")
    assert result.returncode != 0
    assert "unknown deployment profile" in result.stderr


def test_unqualified_real_z2_profiles_remain_reserved_not_aliases() -> None:
    source = run("help").stdout
    assert "z2-full remains reserved" in source
    assert "`z2` is intentionally not accepted" in source
    for profile in ("z2", "z2-full"):
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


def test_swpc_backend_verifies_host_18081_retirement_and_ps_only_boundary() -> None:
    source = SWPC_Z2LIKE.read_text(encoding="utf-8")
    assert "/api/settings/sites" in source
    assert "verify_legacy_ingress_retired" in source
    assert 'legacy_host_port="18081"' in source
    assert "retired SWPC host ingress is still listening" in source
    assert "/api/engineering/diagnostics/loopback" in source
    assert 'loopback.get("endpoint") != "ps"' in source
    assert 'loopback.get("source") != "ps"' in source
    assert "no Z2/ARMv7/PL/FPGA/Site/IC claim" in source


def test_swpc_activation_requires_evidence_current_and_system_ownership_consistency() -> None:
    source = SWPC_Z2LIKE.read_text(encoding="utf-8")
    assert "PPU configuration is missing" in source
    assert "install evidence/current release mismatch" in source
    assert "plasma-server.service is not owned by the Plasma system runtime" in source
    assert "retired SWPC Nginx ingress config still exists" in source


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


def test_local_control_station_manager_is_bootstrap_capable_with_release_catalog() -> None:
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    units = source.split("write_units()", 1)[1].split("write_evidence()", 1)[0]
    assert "-m plasma_manager.bootstrap_server --config $manager_config" in units
    assert "-m plasma_manager.server --config" not in units
    assert "Environment=PLASMA_DEVICE_CATALOG_MANIFEST=$current_link/$release_catalog_dir/$catalog_manifest_relative" in units
    assert "Environment=PLASMA_IC_SUPPORT_ROOT=$current_link/$release_catalog_dir/data/ic-support" in units
    assert "Environment=PLASMA_RUNTIME_EVIDENCE_ROOT=$current_link/$release_catalog_dir" in units
    assert 'catalog_manifest_relative="data/device-catalog/production/icpn-v1-manifest.json"' in source
    # Committed bytes only, exported from the clean HEAD being activated.
    assert "archive --format=tar HEAD -- data release" in source
    assert "-c core.autocrlf=false -c core.eol=lf" in source
    # L3 HIL receipts referenced by the reviewed manifests ship with the Catalog.
    export = source.split("export_release_catalog() {", 1)[1].split("prepare_release() {", 1)[0]
    assert '"$destination/release/physical-compatibility"' in export
    assert 'value.startswith("docs/evidence/")' in export
    assert 'archive --format=tar HEAD -- "${evidence_paths[@]}"' in export


def test_local_control_station_release_catalog_ships_l3_evidence(tmp_path: Path) -> None:
    """Execute export_release_catalog against this repository's HEAD."""
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    function = "export_release_catalog() {" + source.split("export_release_catalog() {", 1)[1].split("\nprepare_release() {", 1)[0]
    repo_root = REPO_ROOT
    script = (
        "set -euo pipefail\n"
        'die() { echo "$*" >&2; exit 1; }\n'
        f"repo_root={shlex.quote(str(repo_root))}\n"
        f"base_python={shlex.quote(sys.executable)}\n"
        f"{function}\n"
        f"export_release_catalog {shlex.quote(str(tmp_path / 'catalog'))}\n"
    )
    subprocess.run(["bash", "-c", script], check=True, timeout=300)
    catalog = tmp_path / "catalog"
    manifest = json.loads((catalog / "release/physical-compatibility/l3-configurations-v1.json").read_text(encoding="utf-8"))
    referenced = {manifest_path for record in manifest["configurations"]
                  for manifest_path in [record["provenance"]["manager_journal"], record["provenance"]["bootstrap_status"],
                                        *(receipt["path"] for receipt in record["evidence"])]}
    assert referenced
    for rel in referenced:
        assert (catalog / rel).is_file(), rel
    shipped = {str(p.relative_to(catalog)) for p in (catalog / "docs").rglob("*") if p.is_file()}
    assert shipped == referenced


def test_local_control_station_release_build_self_tests_manager_selector() -> None:
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    prepare = source.split("prepare_release() {", 1)[1].split("write_profile_config()", 1)[0]
    assert 'export_release_catalog "$staging/$release_catalog_dir"' in prepare
    assert 'validate_release_selector "$staging" || die' in prepare
    # A reused release without a working Selector Catalog is refused.
    assert 'validate_release_selector "$release" ||' in prepare
    selector = source.split("validate_release_selector() {", 1)[1].split("export_release_catalog()", 1)[0]
    assert '"$release/venv/bin/python" -I -B' in selector
    assert "import plasma_manager.bootstrap_server" in selector
    assert "legacy_device_selector.search_response" in selector
    assert "status != 200" in selector


def test_local_control_station_manager_registry_is_durable_profile_state() -> None:
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    assert 'registry_state="$state_dir/registry.json"' in source
    config = source.split("write_manager_config()", 1)[1].split("write_units()", 1)[0]
    assert 'f"  registry_state_path: {q(registry_state)}\\n"' in config
    rollback = source.split("rollback() {", 1)[1].split("trap rollback ERR", 1)[0]
    assert "registry.json" not in rollback
    assert "bootstrap-credentials" not in rollback
    assert "registry_state" not in rollback


def test_local_control_station_verify_requires_manager_selector_and_bootstrap_unit() -> None:
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    verify = source.split("verify_profile() {", 1)[1].split("status_profile()", 1)[0]
    assert 'plasma_manager.bootstrap_server --config $manager_config" "$manager_unit"' in verify
    assert "registry_state_path" in verify
    assert '/api/devices/search?$selector_probe_query" "Manager Device Selector"' in verify
    assert "Manager Device Selector is unavailable" in verify
    assert verify.index("Manager liveness failed") < verify.index("Manager Device Selector is unavailable")


def test_local_control_station_accepts_clean_linked_worktree_source() -> None:
    source = LOCAL_CONTROL_STATION.read_text(encoding="utf-8")
    clean = source.split("require_clean_source() {", 1)[1].split("current_sha()", 1)[0]
    assert '[[ -e "$repo_root/.git" ]]' in clean
    assert '[[ -d "$repo_root/.git" ]]' not in clean
    assert "rev-parse --show-toplevel" in clean
    assert "--untracked-files=normal" in clean

def test_portable_readonly_commands_are_available_through_existing_plasmactl() -> None:
    # Existing SWPC launcher must delegate to the one canonical Python source.
    # All cases stop at argparse; neither Manager nor hardware is accessed.
    env = {"PLASMACTL_INTEGRATION_BACKEND": "/not-a-real-deployment-backend"}
    for args, option in (
        (("diagnose", "--help"), "--target"),
        (("deploy", "status", "--help"), "--ppu"),
        (("program", "receipt", "--help"), "--batch-id"),
        (("program", "submit", "--help"), "--journal"),
    ):
        result = run(*args, env=env)
        assert result.returncode == 0, (args, result.stderr)
        assert option in result.stdout

    bad = run("diagnose", "--target", "z2:0", env=env)
    assert bad.returncode == 2
    assert "Site IDs must be unique positive integers" in bad.stderr


def test_unified_readonly_dispatch_does_not_replace_existing_deploy_or_test() -> None:
    operations_source = CLI_OPERATIONS.read_text(encoding="utf-8")
    main_source = CLI_MAIN.read_text(encoding="utf-8")
    assert '"plasmactl-local-control-station"' in operations_source
    assert '"test": "run_tests"' in operations_source
    assert 'subs.add_parser("diagnose"' in main_source
    assert 'argv[:2] == ["deploy", "status"]' in main_source
    assert 'psub.add_parser("receipt"' in main_source
    # The retired split read-only entry is not kept as a second name.
    assert run("test", "receipt").returncode != 0

def test_retired_z2like_demo_profile_is_rejected() -> None:
    for command in ("install", "deploy", "verify", "status", "update"):
        result = run(command, "z2like-demo")
        assert result.returncode != 0

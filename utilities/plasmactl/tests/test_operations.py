"""Deployment/maintenance routing and execution-path neutrality (host-only).

Backends are stand-in scripts that record their argv; no install, deploy,
restart, systemd, sudo, SSH, Z2 or GitHub interaction happens here.
"""
from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from plasma_cli import operations
from plasma_cli.main import main

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "plasma_cli"
REPO = Path(__file__).resolve().parents[3]

ENV_FOR = {
    "integration": "PLASMACTL_INTEGRATION_BACKEND",
    "integration-verify": "PLASMACTL_VERIFY_BACKEND",
    "local-control-station": "PLASMA_LOCAL_CONTROL_STATION_BACKEND",
    "swpc-z2like": "PLASMA_SWPC_Z2LIKE_BACKEND",
    "swpc-z2like-bootstrap": "PLASMA_SWPC_Z2LIKE_BOOTSTRAP_BACKEND",
    "z2-ps": "PLASMA_Z2_PS_BACKEND",
}


@pytest.fixture
def backends(tmp_path, monkeypatch):
    """Recording backends; integration also exposes library functions."""
    log = tmp_path / "calls.jsonl"
    for name, env in ENV_FOR.items():
        script = tmp_path / f"{name}.sh"
        body = (
            f'record() {{ python3 -c \'import json,sys;open("{log}","a").write('
            'json.dumps(sys.argv[1:])+"\\n")\' "$@"; }\n'
        )
        if name == "integration":
            body += "".join(
                f'{fn}() {{ record integration {fn} "$@"; }}\n'
                for fn in ("install_services", "deploy", "show_status", "restart_services",
                           "show_logs", "update_code", "run_tests", "restart_web_console",
                           "start_services", "stop_services", "show_ports"))
            body += 'repo=/nonexistent\nbash() { record integration bash "$@"; }\n'
            body += '[[ "${PLASMACTL_LIB_ONLY:-0}" == 1 ]] && return 0\n'
        body += f'record {name} "$@"\n'
        script.write_text(body)
        monkeypatch.setenv(env, str(script))
    monkeypatch.setenv("PLASMA_CLI_BACKEND_DIR", str(tmp_path))

    def calls():
        return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []
    return calls


@pytest.mark.parametrize(("argv", "expected"), [
    (["install", "local-control-station", "--ppu-endpoint", "http://10.0.0.2:18080"],
     ["local-control-station", "install", "--ppu-endpoint", "http://10.0.0.2:18080"]),
    (["deploy", "local-control-station"], ["local-control-station", "deploy"]),
    (["verify", "local-control-station"], ["local-control-station", "verify"]),
    (["status", "local-control-station"], ["local-control-station", "status"]),
    (["logs", "local-control-station"], ["local-control-station", "logs"]),
    (["restart", "local-control-station"], ["local-control-station", "restart"]),
    (["install", "z2-ps", "--release-artifact", "r.tgz", "--gateway-host", "192.168.2.99"],
     ["z2-ps", "install", "--release-artifact", "r.tgz", "--gateway-host", "192.168.2.99"]),
    (["deploy", "z2-ps", "--release-artifact", "r.tgz"], ["z2-ps", "deploy", "--release-artifact", "r.tgz"]),
    (["verify", "z2-ps"], ["z2-ps", "verify"]),
    (["status", "z2-ps"], ["z2-ps", "status"]),
    (["logs", "z2-ps"], ["z2-ps", "logs"]),
    (["verify", "swpc-z2like"], ["swpc-z2like", "verify"]),
    (["bootstrap-sites", "swpc-z2like"], ["swpc-z2like-bootstrap"]),
    (["install"], ["integration", "install_services"]),
    (["deploy"], ["integration", "deploy"]),
    (["status"], ["integration", "show_status"]),
    (["restart"], ["integration", "restart_services"]),
    (["logs"], ["integration", "show_logs", "all"]),
    (["logs", "web"], ["integration", "show_logs", "web"]),
    (["update"], ["integration", "update_code"]),
    (["verify", "fleet"], ["integration-verify", "fleet"]),
    (["verify"], ["integration-verify"]),
    (["test"], ["integration", "run_tests"]),
    (["restart-web"], ["integration", "restart_web_console"]),
    (["update-and-restart"], ["integration", "deploy"]),
])
def test_profile_commands_delegate_to_existing_backend(backends, argv, expected):
    assert main(argv) == 0
    assert backends() == [expected]


@pytest.mark.parametrize("argv", [
    ["restart", "z2-ps"],             # Coordinator-owned: no out-of-band restart
    ["restart", "swpc-z2like"],
    ["logs", "swpc-z2like"],
    ["install", "z2like-demo"],       # retired by #1481
    ["deploy", "z2"],                 # reserved, never an alias
    ["status", "z2-ps", "--extra"],
    ["install", "integration", "--x"],
    ["bootstrap-sites", "z2-ps"],
    ["update", "integration"],
])
def test_unsupported_or_unsafe_operations_fail_closed_without_backend(backends, argv):
    assert main(argv) == 1
    assert backends() == []


def test_standalone_install_without_checkout_refuses_deployment(monkeypatch, capsys):
    for env in [*ENV_FOR.values(), "PLASMA_CLI_BACKEND_DIR"]:
        monkeypatch.delenv(env, raising=False)
    assert main(["deploy", "local-control-station"]) == 1
    assert "not available on this host" in capsys.readouterr().err


def test_backend_failure_exit_code_is_preserved(backends, tmp_path, monkeypatch):
    failing = tmp_path / "fail.sh"
    failing.write_text("exit 7\n")
    monkeypatch.setenv("PLASMA_Z2_PS_BACKEND", str(failing))
    assert main(["verify", "z2-ps"]) == 7


# --- execution-path neutrality ------------------------------------------------

FORBIDDEN = ("path2", "path3", "GITHUB_", "RUNNER_", "P2HW", "systemctl", "sudo",
             "journalctl", "ssh", "192.168.", "plasma-engineering-claims")


def test_cli_core_has_no_execution_path_runner_or_platform_coupling():
    for source in PACKAGE.glob("*.py"):
        text = source.read_text()
        tree = ast.parse(text)
        for node in ast.walk(tree):  # judge executable code, not prose
            body = getattr(node, "body", None)
            if isinstance(body, list) and body and isinstance(body[0], ast.Expr) \
                    and isinstance(body[0].value, ast.Constant):
                body.pop(0)
        code = ast.unparse(tree).lower()
        for token in FORBIDDEN:
            assert token.lower() not in code, (source.name, token)
        imports = {alias.name.split(".")[0]
                   for node in ast.walk(ast.parse(text))
                   if isinstance(node, (ast.Import, ast.ImportFrom))
                   for alias in getattr(node, "names", [])}
        modules = {node.module.split(".")[0] for node in ast.walk(ast.parse(text))
                   if isinstance(node, ast.ImportFrom) and node.module}
        assert not ({"ppu_path2_hardware_baseline", "plasma_development_dispatch",
                     "plasma_engineering_hil"} & (imports | modules)), source.name


@pytest.mark.parametrize("environment", [
    {},
    {"GITHUB_ACTIONS": "true", "GITHUB_RUN_ATTEMPT": "2", "RUNNER_TEMP": "/tmp"},
    {"PLASMA_EXECUTION_PATH": "path3-codex", "CODEX_SANDBOX": "workspace-write"},
])
def test_same_cli_behaviour_under_any_execution_environment(environment, tmp_path):
    """Path 2, Path 3 and a plain Controller run the identical code path."""
    env = {"PATH": os.environ["PATH"], "PYTHONPATH": str(PACKAGE.parent), **environment}
    image = tmp_path / "fw.bin"
    image.write_bytes(b"x")
    run = subprocess.run(
        [sys.executable, "-m", "plasma_cli.main", "program", "submit", "--manager-url",
         "http://127.0.0.1:9", "--timeout", "1", "--icpn", "X", "--target", "z2:1",
         "--image", str(image), "--journal", str(tmp_path / "j.json")],
        env=env, capture_output=True, text=True, check=False)
    assert run.returncode == 4, run.stderr
    assert json.loads(run.stdout)["submission"] == "NOT_SUBMITTED"


def test_programming_commissioning_tool_no_longer_imports_path2_module():
    source = (REPO / "scripts/plasma_program.py").read_text()
    assert "ppu_path2_hardware_baseline" not in source
    assert "import ppu_bootstrap_transport" in source
    neutral = (REPO / "scripts/ppu_bootstrap_transport.py").read_text()
    assert "path2" not in neutral.lower() and "GITHUB_" not in neutral


# Source ownership: nine canonical backends and zero legacy entry paths.
@pytest.mark.parametrize("name", [
    "plasmactl-integration",
    "plasmactl-local-control-station",
    "plasmactl-swpc-z2like",
    "plasmactl-swpc-z2like-bootstrap-sites",
    "plasmactl-swpc-z2like-managed-ingress",
    "plasmactl-swpc-z2like-orchestrator",
    "plasmactl-swpc-z2like-programming",
    "plasmactl-verify",
    "plasmactl-z2-ps",
])
def test_no_legacy_backend_path_after_migration(name):
    canonical = REPO / "utilities" / "plasmactl" / "backends" / name
    legacy = REPO / "scripts" / name
    assert canonical.is_file()
    assert not legacy.exists()
    assert not legacy.is_symlink()


def test_launcher_points_at_canonical_backend_directory():
    launcher = (REPO / "scripts/plasmactl").read_text()
    assert 'backend_root="$repo_root/utilities/plasmactl/backends"' in launcher
    assert 'PLASMA_CLI_BACKEND_DIR="$backend_root"' in launcher


def test_integration_install_uses_operator_launcher_not_backend():
    integration = (REPO / "utilities/plasmactl/backends/plasmactl-integration").read_text()
    assert 'ln -sfn "$repo/scripts/plasmactl" "$bin_dir/plasmactl"' in integration
    assert 'PLASMACTL_DEPLOY_REEXEC=1 exec "$repo/scripts/plasmactl" deploy' in integration


def test_hil_programming_execs_harness_next_to_launcher(tmp_path, monkeypatch):
    (tmp_path / "plasma_engineering_hil.py").write_text("")
    monkeypatch.setenv("PLASMACTL_WRAPPER", str(tmp_path / "plasmactl"))
    monkeypatch.setenv("PLASMA_CLI_BACKEND_DIR", str(tmp_path / "backends"))
    seen = []
    monkeypatch.setattr(operations.os, "execvp", lambda *call: seen.append(call))
    main(["hil", "programming", "--profile", "bluepill-ab"])
    assert seen == [("python3", ["python3", str(tmp_path / "plasma_engineering_hil.py"),
                                 "--profile", "bluepill-ab"])]


@pytest.mark.parametrize("launcher", [None, "kit"])
def test_hil_programming_refuses_without_launcher_or_harness(launcher, tmp_path, monkeypatch,
                                                             capsys):
    """A wheel has no launcher; a Z2 kit's scripts/ does not ship the SWPC harness."""
    monkeypatch.delenv("PLASMACTL_WRAPPER", raising=False)
    if launcher:
        monkeypatch.setenv("PLASMACTL_WRAPPER", str(tmp_path / "plasmactl"))
    monkeypatch.setattr(operations.os, "execvp", lambda *call: pytest.fail("must not exec"))
    assert main(["hil", "programming"]) != 0
    assert "hil programming" in capsys.readouterr().err


def test_launcher_resolves_existing_hil_harness():
    run = subprocess.run([str(REPO / "scripts/plasmactl"), "hil", "programming", "--help"],
                         capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stderr
    assert "--execute" in run.stdout

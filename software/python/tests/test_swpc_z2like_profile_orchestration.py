from __future__ import annotations

import os
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
ORCHESTRATOR = REPO_ROOT / "scripts" / "plasmactl-swpc-z2like-orchestrator"
ROUTER = REPO_ROOT / "scripts" / "plasmactl"
PROGRAMMING_MARKER = "# Managed by Plasma SWPC Z2-like configured Mock Programming activation"
MANAGED_MARKER = "# Managed by Plasma SWPC Z2-like managed programming ingress"


def _fake_backend(path: Path, label: str) -> None:
    path.write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        f"printf '{label} %s\\n' \"$*\" >> \"$PLASMA_TEST_LOG\"\n",
        encoding="utf-8",
    )


def _environment(tmp_path: Path) -> tuple[dict[str, str], Path, Path, Path, Path]:
    log = tmp_path / "calls.log"
    base = tmp_path / "base.sh"
    programming = tmp_path / "programming.sh"
    managed = tmp_path / "managed.sh"
    _fake_backend(base, "base")
    _fake_backend(programming, "programming")
    _fake_backend(managed, "managed")

    dropin = tmp_path / "30-programming.conf"
    managed_conf = tmp_path / "managed.conf"
    managed_evidence = tmp_path / "managed.json"
    env = os.environ.copy()
    env.update(
        {
            "PLASMA_TEST_LOG": str(log),
            "PLASMA_SWPC_Z2LIKE_BASE_BACKEND": str(base),
            "PLASMA_SWPC_Z2LIKE_PROGRAMMING_BACKEND": str(programming),
            "PLASMA_SWPC_Z2LIKE_MANAGED_BACKEND": str(managed),
            "PLASMA_SWPC_Z2LIKE_PROGRAMMING_DROPIN": str(dropin),
            "PLASMA_SWPC_Z2LIKE_MANAGED_NGINX_CONF": str(managed_conf),
            "PLASMA_SWPC_Z2LIKE_MANAGED_EVIDENCE": str(managed_evidence),
        }
    )
    return env, log, dropin, managed_conf, managed_evidence


def _run(tmp_path: Path, *args: str) -> tuple[subprocess.CompletedProcess[str], Path, Path, Path, Path]:
    env, log, dropin, managed_conf, managed_evidence = _environment(tmp_path)
    result = subprocess.run(
        ["bash", str(ORCHESTRATOR), *args],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    return result, log, dropin, managed_conf, managed_evidence


def test_orchestrator_is_valid_bash_and_router_uses_it_by_default() -> None:
    result = subprocess.run(
        ["bash", "-n", str(ORCHESTRATOR)],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    source = ROUTER.read_text(encoding="utf-8")
    assert "plasmactl-swpc-z2like-orchestrator" in source
    assert "PLASMA_SWPC_Z2LIKE_BACKEND" in source


def test_base_only_deploy_remains_one_base_deploy_plus_verify(tmp_path: Path) -> None:
    result, log, _, _, _ = _run(tmp_path, "deploy", "--proxy-port", "19081")
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "base deploy --proxy-port 19081",
        "base verify --proxy-port 19081",
    ]
    assert "Programming=0 ManagedIngress=0" in result.stdout


def test_deploy_reconciles_previously_enabled_programming_and_managed_ingress(tmp_path: Path) -> None:
    env, log, dropin, managed_conf, managed_evidence = _environment(tmp_path)
    dropin.write_text(PROGRAMMING_MARKER + "\n", encoding="utf-8")
    managed_conf.write_text(MANAGED_MARKER + "\n", encoding="utf-8")
    managed_evidence.write_text("{}\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(ORCHESTRATOR), "deploy", "--proxy-port", "19081"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "base deploy --proxy-port 19081",
        "programming install",
        "programming verify",
        "managed install",
        "managed verify",
        "base verify --proxy-port 19081",
        "programming verify",
        "managed verify",
    ]
    assert "Programming=1 ManagedIngress=1" in result.stdout
    assert "previously enabled add-ons were reconciled in one operation" in result.stdout


def test_managed_ingress_can_be_declared_without_programming(tmp_path: Path) -> None:
    env, log, _, managed_conf, managed_evidence = _environment(tmp_path)
    managed_conf.write_text(MANAGED_MARKER + "\n", encoding="utf-8")
    managed_evidence.write_text("{}\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(ORCHESTRATOR), "deploy"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "base deploy",
        "managed install",
        "managed verify",
        "base verify",
        "managed verify",
    ]
    assert "Programming=0 ManagedIngress=1" in result.stdout


def test_programming_can_be_declared_without_managed_ingress(tmp_path: Path) -> None:
    env, log, dropin, _, _ = _environment(tmp_path)
    dropin.write_text(PROGRAMMING_MARKER + "\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(ORCHESTRATOR), "deploy"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == [
        "base deploy",
        "programming install",
        "programming verify",
        "base verify",
        "programming verify",
    ]
    assert "Programming=1 ManagedIngress=0" in result.stdout


def test_incomplete_managed_state_fails_closed(tmp_path: Path) -> None:
    env, log, dropin, managed_conf, _ = _environment(tmp_path)
    dropin.write_text(PROGRAMMING_MARKER + "\n", encoding="utf-8")
    managed_conf.write_text(MANAGED_MARKER + "\n", encoding="utf-8")

    result = subprocess.run(
        ["bash", str(ORCHESTRATOR), "deploy"],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert "managed Programming ingress state is incomplete" in result.stderr
    assert not log.exists()


def test_fresh_install_does_not_implicitly_enable_optional_programming(tmp_path: Path) -> None:
    result, log, _, _, _ = _run(tmp_path, "install", "--ppu-id", "lab-ppu")
    assert result.returncode == 0, result.stderr
    assert log.read_text(encoding="utf-8").splitlines() == ["base install --ppu-id lab-ppu"]

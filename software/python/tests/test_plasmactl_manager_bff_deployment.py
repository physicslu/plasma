from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLASMACTL = REPO_ROOT / "scripts" / "plasmactl"
PYTHON_ROOT = REPO_ROOT / "software" / "python"


def write_manager_config(path: Path, *, host: str = "127.0.0.1", alias: str = "ppu-a") -> None:
    path.write_text(
        "\n".join(
            [
                "manager:",
                f'  host: "{host}"',
                "  port: 19180",
                "  request_timeout_s: 2.0",
                "ppus:",
                "  - endpoint: http://127.0.0.1:18080",
                f"    alias: {alias}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def run_plasmactl_lib(
    tmp_path: Path,
    manager_config: Path,
    *,
    alias: str,
    script: str,
) -> subprocess.CompletedProcess[str]:
    deployment_config = tmp_path / "plasmactl.env"
    deployment_config.write_text(
        "\n".join(
            [
                "PLASMA_CONFIG_VERSION=5",
                "PLASMA_MANAGER_ENABLED=1",
                f"PLASMA_MANAGER_CONFIG={manager_config}",
                f"PLASMA_MANAGER_PPU_ALIAS={alias}",
                "",
            ]
        ),
        encoding="utf-8",
    )
    env = os.environ.copy()
    env.update(
        {
            "PLASMACTL_LIB_ONLY": "1",
            "PLASMACTL_CONFIG": str(deployment_config),
            "PLASMA_PYTHON": sys.executable,
            "PYTHONPATH": str(PYTHON_ROOT),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
        }
    )
    return subprocess.run(
        ["bash", "-c", f'source "$1"; {script}', "_", str(PLASMACTL)],
        cwd=REPO_ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_manager_bff_deployment_accepts_registered_alias_and_derives_loopback_url(tmp_path: Path) -> None:
    manager_config = tmp_path / "manager.yaml"
    write_manager_config(manager_config)

    result = run_plasmactl_lib(
        tmp_path,
        manager_config,
        alias="ppu-a",
        script="require_manager_config; manager_bff_url",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("http://127.0.0.1:19180")


def test_manager_bff_deployment_rejects_alias_missing_from_registry(tmp_path: Path) -> None:
    manager_config = tmp_path / "manager.yaml"
    write_manager_config(manager_config, alias="ppu-a")

    result = run_plasmactl_lib(
        tmp_path,
        manager_config,
        alias="ppu-missing",
        script="require_manager_config",
    )

    assert result.returncode != 0
    assert "PLASMA_MANAGER_PPU_ALIAS 未登錄於 Manager registry" in result.stderr


def test_manager_bff_deployment_rejects_nonlocal_manager_bind(tmp_path: Path) -> None:
    manager_config = tmp_path / "manager.yaml"
    write_manager_config(manager_config, host="192.0.2.10")

    result = run_plasmactl_lib(
        tmp_path,
        manager_config,
        alias="ppu-a",
        script="require_manager_config",
    )

    assert result.returncode != 0
    assert "Manager BFF 只支援本機 loopback/wildcard bind" in result.stderr


def test_manager_bff_deployment_normalizes_wildcard_ipv4_to_loopback(tmp_path: Path) -> None:
    manager_config = tmp_path / "manager.yaml"
    write_manager_config(manager_config, host="0.0.0.0")

    result = run_plasmactl_lib(
        tmp_path,
        manager_config,
        alias="ppu-a",
        script="require_manager_config; manager_bff_url",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("http://127.0.0.1:19180")


def test_manager_bff_deployment_normalizes_wildcard_ipv6_to_loopback(tmp_path: Path) -> None:
    manager_config = tmp_path / "manager.yaml"
    write_manager_config(manager_config, host="::")

    result = run_plasmactl_lib(
        tmp_path,
        manager_config,
        alias="ppu-a",
        script="require_manager_config; manager_bff_url",
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip().endswith("http://[::1]:19180")

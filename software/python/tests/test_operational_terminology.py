from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[3]
PLASMACTL = REPO_ROOT / "scripts" / "plasmactl"


def test_plasmactl_generates_canonical_systemd_descriptions(tmp_path: Path) -> None:
    env = os.environ.copy()
    env.update(
        {
            "PLASMACTL_LIB_ONLY": "1",
            "PLASMACTL_CONFIG": str(tmp_path / "no-config.env"),
            "XDG_CONFIG_HOME": str(tmp_path / "xdg"),
            "PLASMA_PYTHON": sys.executable,
            "PLASMA_NPM": "/usr/bin/true",
        }
    )

    subprocess.run(
        ["bash", "-c", 'source "$1"; write_units', "_", str(PLASMACTL)],
        check=True,
        env=env,
    )

    unit_dir = tmp_path / "xdg" / "systemd" / "user"
    server_unit = (unit_dir / "plasma-server.service").read_text(encoding="utf-8")
    gateway_unit = (unit_dir / "plasma-web.service").read_text(encoding="utf-8")

    assert "Description=Plasma PPU Programming Server" in server_unit
    assert "Description=Plasma Web REST Gateway" in gateway_unit


def test_plasmactl_operator_text_uses_canonical_gateway_name() -> None:
    source = PLASMACTL.read_text(encoding="utf-8")

    assert '"Plasma Web REST Gateway"' in source
    assert "default Plasma Web REST Gateway" in source

    for legacy_text in (
        "Plasma multi-channel programming server",
        "Plasma Python Web Gateway",
        "Python Gateway API",
        "default Python API",
    ):
        assert legacy_text not in source

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

import yaml


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPOSITORY_ROOT / "scripts" / "plasma-security-deploy"


def test_security_deploy_enable_and_disable_are_reversible(tmp_path: Path) -> None:
    home = tmp_path / "home"
    config_home = home / ".config"
    state_home = home / ".local" / "state"
    unit_dir = config_home / "systemd" / "user"
    unit_dir.mkdir(parents=True)
    (unit_dir / "plasma-web.service").write_text("[Service]\nExecStart=/canonical/gateway\n", encoding="utf-8")

    configured_repo = tmp_path / "configured-repo"
    (configured_repo / "software" / "python").mkdir(parents=True)
    plasmactl_config = config_home / "plasma" / "plasmactl.env"
    plasmactl_config.parent.mkdir(parents=True)
    plasmactl_config.write_text(
        "\n".join(
            [
                f"PLASMA_REPO={configured_repo}",
                f"PLASMA_PYTHON={sys.executable}",
                "PLASMA_GATEWAY_HOST=127.0.0.1",
                "PLASMA_GATEWAY_PORT=18080",
                "PLASMA_CORS_ORIGIN=https://console.example",
                "PLASMA_ENGINEERING_MOCK_ENABLED=0",
                "",
            ]
        ),
        encoding="utf-8",
    )

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    systemctl_log = tmp_path / "systemctl.log"
    fake_systemctl = fake_bin / "systemctl"
    fake_systemctl.write_text(
        "#!/usr/bin/env bash\n"
        "printf '%s\\n' \"$*\" >> \"$SYSTEMCTL_LOG\"\n"
        "exit 0\n",
        encoding="utf-8",
    )
    fake_systemctl.chmod(0o755)

    env = {
        **os.environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(config_home),
        "XDG_STATE_HOME": str(state_home),
        "PATH": f"{fake_bin}:{os.environ.get('PATH', '')}",
        "SYSTEMCTL_LOG": str(systemctl_log),
    }

    enabled = subprocess.run(
        ["bash", str(SCRIPT), "enable"],
        cwd=REPOSITORY_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    token_match = re.search(
        r"Bearer token（只顯示這一次；未寫入磁碟）===\n([^\n]+)\n=+",
        enabled.stdout,
    )
    assert token_match is not None
    token = token_match.group(1)
    assert len(token) >= 32

    security_config = config_home / "plasma" / "security.yaml"
    assert stat.S_IMODE(security_config.stat().st_mode) == 0o600
    config = yaml.safe_load(security_config.read_text(encoding="utf-8"))
    principal = config["principals"][0]
    assert principal["id"] == "local-admin"
    assert principal["token_sha256"] == hashlib.sha256(token.encode()).hexdigest()
    assert token not in security_config.read_text(encoding="utf-8")

    state_dir = state_home / "plasma"
    assert stat.S_IMODE(state_dir.stat().st_mode) == 0o700

    dropin = unit_dir / "plasma-web.service.d" / "security.conf"
    dropin_source = dropin.read_text(encoding="utf-8")
    assert "-m plasma_web.secure_gateway_app" in dropin_source
    assert f"--output-root {configured_repo}/software/python/output" in dropin_source
    assert f"Environment=PLASMA_SECURITY_CONFIG={security_config}" in dropin_source
    assert f"Environment=PLASMA_SECURITY_STATE={state_home}/plasma/security-state.sqlite3" in dropin_source
    assert "--cors-origin https://console.example" in dropin_source

    calls = systemctl_log.read_text(encoding="utf-8")
    assert "--user daemon-reload" in calls
    assert "--user restart plasma-web.service" in calls
    assert "--user is-active --quiet plasma-web.service" in calls

    subprocess.run(
        ["bash", str(SCRIPT), "disable"],
        cwd=REPOSITORY_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
    assert not dropin.exists()
    assert security_config.exists()

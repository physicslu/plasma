from __future__ import annotations

import os
from pathlib import Path
import subprocess


REPO_ROOT = Path(__file__).resolve().parents[3]
PLASMACTL = REPO_ROOT / "scripts" / "plasmactl"


def _run_render_deploy(tmp_path: Path, hook: str | None) -> subprocess.CompletedProcess[str]:
    fake_bin = tmp_path / "bin"
    fake_bin.mkdir(exist_ok=True)
    curl_args = tmp_path / "curl-args.txt"
    fake_curl = fake_bin / "curl"
    fake_curl.write_text(
        "#!/usr/bin/env bash\n"
        "set -Eeuo pipefail\n"
        'printf \'%s\\n\' "$@" > "$PLASMA_TEST_CURL_ARGS"\n',
        encoding="utf-8",
    )
    fake_curl.chmod(0o755)

    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{fake_bin}:{env['PATH']}",
            "PLASMACTL_LIB_ONLY": "1",
            "PLASMACTL_CONFIG": str(tmp_path / "no-config.env"),
            "PLASMA_TEST_CURL_ARGS": str(curl_args),
            "XDG_CONFIG_HOME": str(tmp_path / "config"),
            "XDG_STATE_HOME": str(tmp_path / "state"),
        }
    )
    if hook is None:
        env.pop("PLASMA_RENDER_DEPLOY_HOOK_URL", None)
    else:
        env["PLASMA_RENDER_DEPLOY_HOOK_URL"] = hook

    return subprocess.run(
        [
            "bash",
            "-c",
            'set -Eeuo pipefail; source "$1"; render_deploy',
            "_",
            str(PLASMACTL),
        ],
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_render_deploy_posts_secret_hook_without_logging_it(tmp_path: Path) -> None:
    hook = "https://api.render.com/deploy/srv-test?key=super-secret-hook-key"
    result = _run_render_deploy(tmp_path, hook)

    assert result.returncode == 0, result.stderr
    assert "Render 部署已觸發" in result.stdout
    assert hook not in result.stdout
    assert "super-secret-hook-key" not in result.stdout
    assert hook not in result.stderr

    curl_args = (tmp_path / "curl-args.txt").read_text(encoding="utf-8").splitlines()
    assert "--request" in curl_args
    assert "POST" in curl_args
    assert "--fail" in curl_args
    assert "--silent" in curl_args
    assert "--show-error" in curl_args
    assert hook in curl_args


def test_render_deploy_requires_hook(tmp_path: Path) -> None:
    result = _run_render_deploy(tmp_path, None)

    assert result.returncode != 0
    assert "PLASMA_RENDER_DEPLOY_HOOK_URL" in result.stderr


def test_render_deploy_rejects_non_render_hook(tmp_path: Path) -> None:
    result = _run_render_deploy(tmp_path, "https://example.invalid/deploy?key=secret")

    assert result.returncode != 0
    assert "api.render.com" in result.stderr


def test_render_deploy_rejects_specific_commit_ref(tmp_path: Path) -> None:
    result = _run_render_deploy(
        tmp_path,
        "https://api.render.com/deploy/srv-test?key=secret&ref=deadbeef",
    )

    assert result.returncode != 0
    assert "ref" in result.stderr.lower()

#!/usr/bin/env python3
"""Run candidate Dispatcher CLI regression inside trusted Path 2 CPU sandbox.

This script must be launched ONLY as a candidate Path 2 CPU-only fixture using
trusted main's bubblewrap sandbox (unshared user/network, synthetic /dev,
read-only /work, empty environment). It runs a stub Codex, not real Codex.
"""
from __future__ import annotations

import contextlib
from io import StringIO
import os
from pathlib import Path
import runpy
import subprocess

ROOT = Path("/work")
TEST = ROOT / "scripts/tests/test_plasma_candidate_dispatcher_premerge.py"
STAMP = "CANDIDATE_DISPATCHER_PREMERGE_SWPC_BWRAP_STUB_PASS"

def check_isolation(*, environ=None, exists=None) -> None:
    """Fail closed if the CPU-only sandbox can observe host credentials/devices.

    These checks supplement, not replace, trusted main's bwrap --unshare-all,
    --clearenv, --dev and read-only /work flags. This mode has no real Codex
    authentication or external network connectivity by design.
    """
    env = os.environ if environ is None else environ
    path_exists = os.path.lexists if exists is None else exists
    assert env.get("HOME") == "/tmp", "SANDBOX_HOME_DENIED"
    assert env.get("PYTHONNOUSERSITE") == "1", "SANDBOX_PYTHON_DENIED"
    forbidden_env_fragments = ("TOKEN", "SECRET", "CREDENTIAL", "AUTH", "API_KEY")
    for key in env:
        upper = key.upper()
        credential_key = (
            any(marker in upper for marker in forbidden_env_fragments)
            or upper.startswith(("SSH_", "AWS_", "AZURE_", "GOOGLE_"))
            or upper in ("CODEX_HOME", "GITHUB_TOKEN", "GH_TOKEN")
        )
        assert not credential_key, "HOST_CREDENTIAL_ENV_EXPOSED"
    assert not path_exists("/sys"), "HOST_SYSFS_MOUNT_DENIED"
    assert not path_exists("/run/udev"), "HOST_UDEV_MOUNT_DENIED"
    forbidden_paths = (
        "/home", "/root", "/dev/mem",
        "/dev/gpiomem", "/dev/uio0", "/dev/uio1",
        "/dev/ttyUSB0", "/dev/ttyACM0", "/dev/serial",
        "/dev/bus/usb", "/dev/i2c-0", "/dev/spidev0.0",
    )
    for path in forbidden_paths:
        assert not path_exists(path), "HOST_PATH_EXPOSED"


def main() -> None:
    # Fail closed if invoked outside the trusted bubblewrap RO worktree.
    assert Path.cwd().resolve() == ROOT, "WORKSPACE_SANDBOX_DENIED"
    assert TEST.is_file() and not TEST.is_symlink(), "TEST_PATH_DENIED"
    assert not os.access(ROOT, os.W_OK), "WORKTREE_MUST_BE_READ_ONLY"
    check_isolation()
    candidate_sha = subprocess.check_output(
        ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
        text=True, timeout=5).strip()
    assert len(candidate_sha) == 40, "CANDIDATE_HEAD_DENIED"
    # The inside-only simulated Owner/Runner context does NOT grant host
    # privileges: bubblewrap already removed host network/devices/credentials.
    os.environ.update({
        "RUNNER_ENVIRONMENT": "github-hosted",  # Fixture, NOT the real SWPC environment.
        "GITHUB_EVENT_NAME": "pull_request",   # Fixture, NOT a GitHub event.
        "GITHUB_REPOSITORY": "physicslu/plasma",
        "PLASMA_TRUSTED_SHA": "a" * 40,         # Synthetic main identity.
        "PLASMA_CANDIDATE_SHA": candidate_sha, # Real checked-out source identity.
        "PLASMA_PR_NUMBER": "1083",
    })
    namespace = runpy.run_path(str(TEST), run_name="candidate_dispatcher_fixture")
    captured = StringIO()
    with contextlib.redirect_stdout(captured):
        namespace["smoke"]()
    assert "CANDIDATE_DISPATCHER_PREMERGE_HOSTED_SIMULATION_PASS" in captured.getvalue()
    print(STAMP)

if __name__ == "__main__":
    main()

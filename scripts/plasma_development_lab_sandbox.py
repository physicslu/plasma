#!/usr/bin/env python3
"""Rootless USB/TTY visibility for an explicitly approved Path 3 lab session.

The host worker's DAC permissions still apply. This is NOT a privileged
executor, a per-DUT stage, or a device-command allowlist. The outer bwrap
namespace hides host block/privileged device nodes while sharing the SWPC
USB bus and current ACM/USB serial devices.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import re
import shutil


class LabSandboxDenied(ValueError):
    """Fixed reason code only; never include private filesystem paths."""


def _require(ok: bool, code: str) -> None:
    if not ok:
        raise LabSandboxDenied(code)


def command(
    workspace: Path,
    *,
    home: Path | None = None,
    usb_root: Path = Path("/dev/bus/usb"),
    tty_root: Path = Path("/dev"),
) -> list[str]:
    """Build the reviewed command; launching remains the trusted Dispatcher job.

    Codex's inner danger-full-access is confined by this ROOTLESS mount
    namespace. No arbitrary host /dev, /dev/mem, UIO or sudo is granted.
    Existing /dev/bus/usb nodes are all visible, intentionally without a
    VID/PID allowlist. Access is still determined by Linux DAC/ACL and ownership.
    """
    _require(os.geteuid() != 0, "LAB_ROOT_WORKER_DENIED")
    wrapper = shutil.which("bwrap")
    _require(bool(wrapper) and Path(wrapper).is_file(), "LAB_BWRAP_UNAVAILABLE")
    workspace = Path(workspace)
    _require(workspace.is_dir() and not workspace.is_symlink(),
             "LAB_WORKSPACE_DENIED")
    workspace = workspace.resolve(strict=True)
    if home is None:
        home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
    home = Path(home)
    _require(home.is_dir() and not home.is_symlink(),
             "LAB_HOME_DENIED")
    auth = home / ".codex"
    _require(auth.is_dir() and not auth.is_symlink(),
             "LAB_CODEX_AUTH_DENIED")
    _require(usb_root.is_dir() and not usb_root.is_symlink() and
             tty_root.is_dir() and not tty_root.is_symlink(),
             "LAB_USB_ROOT_UNAVAILABLE")

    argv = [
        wrapper, "--die-with-parent", "--new-session", "--unshare-pid",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/tmp", "--dir", "/dev/bus",
        "--dev-bind", str(usb_root), "/dev/bus/usb",
    ]
    # Character devices may be re-enumerated. Never trust an old node name
    # across distinct sessions. Missing serial devices are not errors.
    for node in sorted(tty_root.iterdir()):
        if not re.fullmatch(r"tty(?:ACM|USB)[0-9]+", node.name):
            continue
        _require(node.is_char_device() and not node.is_symlink(),
                 "LAB_TTY_NODE_DENIED")
        argv += ["--dev-bind", str(node), "/dev/" + node.name]

    # Read-only host files; only the selected candidate workspace, dedicated
    # /tmp and Codex's existing login state may be written.
    argv += ["--bind", str(workspace), str(workspace)]
    # Rootless Codex must not inherit unrelated private host credentials.
    for name in (".ssh", ".aws", ".gnupg", ".kube", ".config/plasma",
                 ".config/gh"):
        private = home / name
        if private.exists() or private.is_symlink():
            _require(private.is_dir() and not private.is_symlink(),
                     "LAB_PRIVATE_PATH_DENIED")
            argv += ["--tmpfs", str(private)]
    argv += ["--bind", str(auth), str(auth)]
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GITHUB_PAT", "SSH_AUTH_SOCK",
                "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN", "PLASMA_Z2_AUTH"):
        argv += ["--unsetenv", key]
    argv += [
        "--chdir", str(workspace), "--",
        "codex", "--ask-for-approval", "never",
        "exec", "--json", "--sandbox", "danger-full-access", "-",
    ]
    return argv

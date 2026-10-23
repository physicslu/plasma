#!/usr/bin/env python3
"""Device-visible rootless Codex sandbox for the existing Development Path 3.

No new execution mode, session type, Work Order field or Runner. Every
existing Path 3 Codex run uses this outer OS namespace. The owner authorizes
physical effects through the existing Gate 1 Work Order, not through a new
hardware-capability field. The lab worker's normal DAC/ACL still applies.
"""
from __future__ import annotations

import os
from pathlib import Path
import pwd
import re
import shutil


class CodexSandboxDenied(ValueError):
    """Only fixed code strings are safe for published diagnostics."""


def require(ok: bool, code: str) -> None:
    if not ok:
        raise CodexSandboxDenied(code)


def codex_command(
    workspace: Path,
    *,
    home: Path | None = None,
    usb_root: Path = Path("/dev/bus/usb"),
    dev_root: Path = Path("/dev"),
    resolv_conf: Path = Path("/etc/resolv.conf"),
) -> list[str]:
    """Return rootless bubblewrap + Codex argv, with USB/TTY device visibility.

    Other /dev nodes are hidden by --dev. Do not infer that this can prevent
    every dangerous USB command: the underlying device driver/API still grants
    what the worker's effective privileges permit. Keep this host account
    dedicated to owner-operated prototype development.
    """
    require(os.geteuid() != 0, "CODEX_SANDBOX_ROOT_DENIED")
    bwrap = shutil.which("bwrap")
    require(bool(bwrap) and Path(bwrap).is_file(),
            "CODEX_SANDBOX_BWRAP_UNAVAILABLE")
    workspace = Path(workspace)
    require(workspace.is_dir() and not workspace.is_symlink(),
            "CODEX_SANDBOX_WORKSPACE_DENIED")
    workspace = workspace.resolve(strict=True)
    if home is None:
        home = Path(pwd.getpwuid(os.geteuid()).pw_dir)
    home = Path(home)
    require(home.is_dir() and not home.is_symlink(),
            "CODEX_SANDBOX_HOME_DENIED")
    auth = home / ".codex"
    require(auth.is_dir() and not auth.is_symlink(),
            "CODEX_SANDBOX_AUTH_DENIED")
    require(usb_root.is_dir() and not usb_root.is_symlink() and
            dev_root.is_dir() and not dev_root.is_symlink(),
            "CODEX_SANDBOX_USB_ROOT_DENIED")

    # Mask host runtime sockets (/run, /var/run) even if their parent is
    # read-only. A read-only Unix socket pathname can still allow IPC writes.
    # Keep the proven SWPC systemd-resolved stub accessible for Codex API DNS.
    try:
        resolved = Path(resolv_conf).resolve(strict=True)
    except (OSError, RuntimeError):
        raise CodexSandboxDenied("CODEX_SANDBOX_DNS_CONFIG_DENIED") from None
    require(resolved.is_file() and os.access(resolved, os.R_OK),
            "CODEX_SANDBOX_DNS_CONFIG_DENIED")
    resolved_in_run = resolved == Path("/run") or Path("/run") in resolved.parents
    if resolved_in_run:
        require(resolved in {
            Path("/run/systemd/resolve/stub-resolv.conf"),
            Path("/run/systemd/resolve/resolv.conf"),
        }, "CODEX_SANDBOX_DNS_RUN_TARGET_DENIED")

    argv = [
        bwrap, "--die-with-parent", "--new-session", "--unshare-pid",
        "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc",
        "--tmpfs", "/run", "--tmpfs", "/tmp", "--dir", "/dev/bus",
        "--dev-bind", str(usb_root), "/dev/bus/usb",
    ]
    if resolved_in_run:
        argv += ["--dir", "/run/systemd", "--dir", "/run/systemd/resolve",
                 "--ro-bind", str(resolved), str(resolved)]
    # No VID/PID filter. Available USB serial devices are exposed at the
    # start of each Codex invocation; re-enumeration needs fresh discovery.
    for node in sorted(dev_root.iterdir()):
        if not re.fullmatch(r"tty(?:ACM|USB)[0-9]+", node.name):
            continue
        require(node.is_char_device() and not node.is_symlink(),
                "CODEX_SANDBOX_TTY_NODE_DENIED")
        argv += ["--dev-bind", str(node), "/dev/" + node.name]

    argv += ["--bind", str(workspace), str(workspace)]
    # Preserve only Codex's API login; hide unrelated private credential dirs.
    for name in (".ssh", ".aws", ".gnupg", ".kube", ".config/plasma",
                 ".config/gh"):
        private = home / name
        if private.exists() or private.is_symlink():
            require(private.is_dir() and not private.is_symlink(),
                    "CODEX_SANDBOX_PRIVATE_PATH_DENIED")
            argv += ["--tmpfs", str(private)]
    argv += ["--bind", str(auth), str(auth)]
    for key in ("GH_TOKEN", "GITHUB_TOKEN", "GITHUB_PAT", "SSH_AUTH_SOCK",
                "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY",
                "AWS_SESSION_TOKEN", "PLASMA_Z2_AUTH"):
        argv += ["--unsetenv", key]
    argv += [
        "--chdir", str(workspace), "--",
        "codex", "--ask-for-approval", "never", "exec", "--json",
        "--sandbox", "danger-full-access", "-",
    ]
    return argv

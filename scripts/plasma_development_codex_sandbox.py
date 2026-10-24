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
import stat


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
    # Keep only the enrolled Z2 login sources visible, read-only. Do not expose
    # the whole SSH directory, agent socket or unrelated Plasma credentials.
    plasma = home / ".config/plasma"
    z2_sources = []
    if plasma.exists() or plasma.is_symlink():
        meta = plasma.lstat()
        require(stat.S_ISDIR(meta.st_mode) and meta.st_uid == os.geteuid()
                and stat.S_IMODE(meta.st_mode) == 0o700,
                "CODEX_SANDBOX_Z2_DIRECTORY_DENIED")
        for name in ("z2-login-smoke.json", "z2-login-known_hosts"):
            source = plasma / name
            if not source.exists() and not source.is_symlink():
                continue
            meta = source.lstat()
            require(stat.S_ISREG(meta.st_mode) and meta.st_uid == os.geteuid()
                    and stat.S_IMODE(meta.st_mode) == 0o600,
                    "CODEX_SANDBOX_Z2_SOURCE_DENIED")
            z2_sources.append(source)
    # Hide private directories before restoring the selected file mounts.
    for name in (".ssh", ".aws", ".gnupg", ".kube", ".config/plasma",
                 ".config/gh"):
        private = home / name
        if private.exists() or private.is_symlink():
            require(private.is_dir() and not private.is_symlink(),
                    "CODEX_SANDBOX_PRIVATE_PATH_DENIED")
            # Bubblewrap defaults tmpfs to 0755; Stage Transport enrollment
            # requires this credential parent to remain private (0700).
            # --perms applies only to the immediately following tmpfs.
            if name == ".config/plasma":
                argv += ["--perms", "0700"]
            argv += ["--tmpfs", str(private)]
    for source in z2_sources:
        argv += ["--ro-bind", str(source), str(source)]
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


def readonly_probe(workspace: Path) -> dict:
    """Real outer-namespace smoke check; no Codex, no device opens or writes.

    Intended for manual owner-controlled pre-merge execution as the actual
    non-root SWPC runner user on an exact candidate checkout. The operation
    cannot prove Linux DAC, device IO, model API or HIL acceptance.
    """
    import subprocess
    import sys

    try:
        cmd = codex_command(workspace)
        # Preserve the exact reviewed OS namespace/mount configuration, but
        # replace Codex with a deterministic, non-actuating Python assertion.
        marker = cmd.index("--")
        expr = (
            "from pathlib import Path; "
            "usb=Path('/dev/bus/usb'); "
            "assert usb.is_dir(); "
            "assert all(p.is_char_device() for p in usb.glob('*/*')); "
            "assert all(p.is_char_device() for stem in ('ttyACM','ttyUSB') "
            "for p in Path('/dev').glob(stem+'*')); "
            "assert not Path('/dev/mem').exists(); "
            "assert not Path('/dev/uio0').exists(); "
            "assert not Path('/run/plasma-codex').exists(); "
            "assert not Path('/run/docker.sock').exists(); "
            "assert Path('/etc/resolv.conf').is_file(); "
            "print('PATH3_NAMESPACE_VISIBLE')"
        )
        check = subprocess.run(
            [*cmd[:marker], "--", sys.executable, "-I", "-c", expr],
            cwd=workspace, stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            timeout=20, check=False,
        )
        if check.returncode != 0 or check.stdout != b"PATH3_NAMESPACE_VISIBLE\n":
            return {"schema": "plasma.path3.namespace_probe.v1",
                    "status": "NOT_RUN_OR_FAIL",
                    "reason": "CODEX_SANDBOX_PROBE_FAILED"}
        return {"schema": "plasma.path3.namespace_probe.v1",
                "status": "NAMESPACE_VISIBLE_ONLY",
                "hardware_io": "NOT_RUN",
                "codex_model": "NOT_RUN"}
    except (CodexSandboxDenied, OSError, ValueError,
            subprocess.SubprocessError) as exc:
        if (isinstance(exc, CodexSandboxDenied) and
                re.fullmatch(r"CODEX_SANDBOX_[A-Z0-9_]{3,80}", str(exc))):
            code = str(exc)
        else:
            code = "CODEX_SANDBOX_PROBE_ERROR"
        return {"schema": "plasma.path3.namespace_probe.v1",
                "status": "NOT_RUN_OR_FAIL", "reason": code}


def main(argv: list[str] | None = None) -> int:
    import json
    import sys

    args = sys.argv[1:] if argv is None else argv
    if args != ["--probe"]:
        return 2
    receipt = readonly_probe(Path.cwd())
    print(json.dumps(receipt, sort_keys=True))
    return 0 if receipt["status"] == "NAMESPACE_VISIBLE_ONLY" else 2


if __name__ == "__main__":
    raise SystemExit(main())

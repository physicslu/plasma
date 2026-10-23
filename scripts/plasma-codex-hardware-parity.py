#!/usr/bin/env python3
"""SWPC dedicated Codex hardware parity: inspect, stage, and verify host grants.

No remote SSH, USB transfers, serial/JTAG access, LA capture or power commands.
Root-only --apply adds only a narrowly scoped USB/FTDI device group and udev
rules. Existing identities and credentials remain distinct.
"""
from __future__ import annotations

import argparse
import grp
import hashlib
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import stat
import subprocess
import sys
import tempfile

HOST = "SWPC"
WORKER = "plasma-codex"
OPERATOR = "gordon"
GROUP = "plasma-codex-io"
RULE_FILE = Path("/etc/udev/rules.d/99-plasma-codex-io.rules")
LA_DIGEST = "b551cb26e8bd3261bb650fac98e62b70a6786f7f5521d62e86bc7e30cebf4475"
LA_BINARY = Path("/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage")
LA_WRAPPER = Path("/usr/local/bin/plasma-la2016-sigrok")

# Device group covers only already observed USB VID/PID and their FTDI serial
# children. Match DEVTYPE so USB interfaces do not appear as extra devices.
VID_PIDS = (
    ("0403", "6010"),  # Xilinx FT2232 USB/JTAG/UART
    ("8564", "4100"),  # Transcend USB2/USB3 companion Hub
    ("77a1", "01a2"),  # KINGST LA2016
    ("0483", "374f"),  # STLINK-V3SET
    ("cafe", "4001"),  # development Blue Pill USB CDC firmware
)
LEGACY_VID_PIDS = VID_PIDS[:3]


def render_rules(group: str = GROUP, *, legacy: bool = False) -> str:
    if not group or not all(c.isalnum() or c in "-_" for c in group):
        raise ValueError("invalid device group")
    items = [
        "# PLASMA SWPC prototype HIL: only owner-approved USB models",
        "# Both USB 2.x and 3.x companion hub identities intentionally match.",
    ]
    for vid, pid in (LEGACY_VID_PIDS if legacy else VID_PIDS):
        items.append(
            f'SUBSYSTEM=="usb", ENV{{DEVTYPE}}=="usb_device", '
            f'ATTR{{idVendor}}=="{vid}", ATTR{{idProduct}}=="{pid}", '
            f'GROUP="{group}", MODE="0660"'
        )
    items.append(
        'SUBSYSTEM=="tty", KERNEL=="ttyUSB[0-9]*", '
        'ATTRS{idVendor}=="0403", ATTRS{idProduct}=="6010", '
        f'GROUP="{group}", MODE="0660"'
    )
    if not legacy:
        items.append(
            'SUBSYSTEM=="tty", KERNEL=="ttyACM[0-9]*", '
            'ATTRS{idVendor}=="cafe", ATTRS{idProduct}=="4001", '
            f'GROUP="{group}", MODE="0660"'
        )
    return "\n".join(items) + "\n"


def render_wrapper() -> str:
    return (
        "#!/bin/sh\n"
        "# Pinned 2026-10-16 KINGST LA2016 sigrok AppImage CLI\n"
        'exec /opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage '
        '--appimage-extract-and-run "$@"\n'
    )


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def file_state(path: Path, content: str | None = None) -> str:
    if path.is_symlink():
        return "SYMLINK_REFUSED"
    if not path.exists():
        return "MISSING"
    if not path.is_file():
        return "NON_REGULAR_REFUSED"
    if content is not None and path.read_text(encoding="utf-8") != content:
        return "CONFLICT_REFUSED"
    return "EXACT" if content is not None else "PRESENT"


def managed_rule_state() -> str:
    current = file_state(RULE_FILE, render_rules())
    if current == "CONFLICT_REFUSED" and \
            file_state(RULE_FILE, render_rules(legacy=True)) == "EXACT":
        return "LEGACY_EXACT_UPGRADE_AVAILABLE"
    return current


def current_groups(user: str) -> list[str]:
    account = pwd.getpwnam(user)
    return sorted(grp.getgrgid(i).gr_name for i in os.getgrouplist(user, account.pw_gid))



def unix_mode_rw(meta: os.stat_result, uid: int, gids: set[int]) -> bool:
    """POSIX mode projection only; cannot account for ACLs or LSM controls."""
    mode = stat.S_IMODE(meta.st_mode)
    if uid == meta.st_uid:
        return (mode & 0o600) == 0o600
    if meta.st_gid in gids:
        return (mode & 0o060) == 0o060
    return (mode & 0o006) == 0o006


def device_dac_comparison() -> dict:
    """Compare operator and worker mode bits with no device opens or IDs leaked."""
    try:
        users = {}
        for name in (OPERATOR, WORKER):
            entry = pwd.getpwnam(name)
            users[name] = (entry.pw_uid, set(os.getgrouplist(name, entry.pw_gid)))
    except KeyError:
        return {"status": "ACCOUNT_UNAVAILABLE"}

    observed: dict[str, list[dict]] = {
        "z2_ft2232": [], "usb_hub_companions": [], "kingst_la2016": [],
        "stlink_v3": [], "blue_pill_cdc": [], "ft2232_tty": [],
        "blue_pill_tty": [],
    }

    def append_metadata(label: str, node: Path) -> None:
        try:
            metadata = node.stat()
            if not stat.S_ISCHR(metadata.st_mode):
                return
            observed[label].append({
                "operator_mode_rw": unix_mode_rw(metadata, *users[OPERATOR]),
                "worker_mode_rw": unix_mode_rw(metadata, *users[WORKER]),
            })
        except OSError:
            return

    root = Path("/sys/bus/usb/devices")
    try:
        entries = list(root.iterdir())
    except OSError:
        return {"status": "USB_SYSFS_UNAVAILABLE"}
    mapping = {
        ("0403", "6010"): "z2_ft2232",
        ("8564", "4100"): "usb_hub_companions",
        ("77a1", "01a2"): "kingst_la2016",
        ("0483", "374f"): "stlink_v3",
        ("cafe", "4001"): "blue_pill_cdc",
    }
    for entry in entries:
        try:
            key = (entry / "idVendor").read_text().strip().lower(), (
                entry / "idProduct"
            ).read_text().strip().lower()
            label = mapping.get(key)
            if label is None:
                continue
            bus = int((entry / "busnum").read_text())
            device = int((entry / "devnum").read_text())
            append_metadata(label, Path(f"/dev/bus/usb/{bus:03d}/{device:03d}"))
        except (OSError, ValueError):
            continue

    for tty in (*Path("/sys/class/tty").glob("ttyUSB*"),
                *Path("/sys/class/tty").glob("ttyACM*")):
        try:
            parent = (tty / "device").resolve(strict=True)
            for component in (parent, *parent.parents):
                if component == Path("/sys"):
                    break
                try:
                    vid = (component / "idVendor").read_text().strip().lower()
                    pid = (component / "idProduct").read_text().strip().lower()
                except OSError:
                    continue
                if (vid, pid) == ("0403", "6010"):
                    append_metadata("ft2232_tty", Path("/dev") / tty.name)
                elif (vid, pid) == ("cafe", "4001"):
                    append_metadata("blue_pill_tty", Path("/dev") / tty.name)
                break
        except OSError:
            continue

    return {
        label: {
            "node_count": len(results),
            "operator_rw_by_mode_only": sum(x["operator_mode_rw"] for x in results),
            "worker_rw_by_mode_only": sum(x["worker_mode_rw"] for x in results),
            "actual_open_or_acl": "NOT_CHECKED",
        }
        for label, results in observed.items()
    }


def check_credentials_metadata(user: str) -> str:
    # Does not open, parse or read secret contents or keys. Directory traversal
    # may be denied to the dedicated user; this is reported rather than escalated.
    try:
        account = pwd.getpwnam(user)
        base = Path(account.pw_dir)
        d = base / ".config/plasma"
        file = d / "z2-dev-credentials.json"
        if file.is_symlink() or d.is_symlink():
            return "SYMLINK_REFUSED"
        meta = file.stat()
        dm = d.stat()
        if not stat.S_ISREG(meta.st_mode):
            return "NOT_REGULAR"
        if (
            meta.st_uid == account.pw_uid
            and stat.S_IMODE(meta.st_mode) == 0o600
            and dm.st_uid == account.pw_uid
            and stat.S_IMODE(dm.st_mode) == 0o700
        ):
            return "PRESENT_OWNER_ONLY_NOT_READ"
        return "UNSAFE_METADATA"
    except PermissionError:
        return "UNREADABLE_METADATA"
    except FileNotFoundError:
        return "ABSENT"
    except (OSError, KeyError):
        return "UNAVAILABLE"


def audit() -> dict:
    try:
        groups = {user: current_groups(user) for user in (OPERATOR, WORKER)}
    except KeyError:
        groups = {OPERATOR: [], WORKER: []}
    return {
        "schema": "plasma.codex.hw-parity.v1",
        "host_swpc": socket.gethostname() == HOST,
        "effective_user_role": (
            "operator" if pwd.getpwuid(os.geteuid()).pw_name == OPERATOR else
            "worker" if pwd.getpwuid(os.geteuid()).pw_name == WORKER else
            "administrator" if os.geteuid() == 0 else "other"
        ),
        "groups": groups,
        "device_mode_comparison": device_dac_comparison(),
        "worker_io_group_present": GROUP in groups.get(WORKER, []),
        "operator_io_group_present": GROUP in groups.get(OPERATOR, []),
        "udev_rules": managed_rule_state(),
        "kingst_appimage": (
            "EXACT_PINNED" if LA_BINARY.is_file() and not LA_BINARY.is_symlink()
            and sha256(LA_BINARY) == LA_DIGEST else "NOT_EXACT_PINNED"
        ),
        "kingst_wrapper": file_state(LA_WRAPPER, render_wrapper()),
        "credential_store": {
            OPERATOR: check_credentials_metadata(OPERATOR),
            WORKER: check_credentials_metadata(WORKER),
        },
        "ssh_keys_or_passwords": "NOT_READ_OR_COPIED",
        "hardware_io": "NOT_RUN",
        "runner_restart": "NOT_PERFORMED",
    }


def require_safe_admin() -> None:
    if socket.gethostname() != HOST:
        raise RuntimeError("host identity mismatch")
    if os.geteuid() != 0:
        raise RuntimeError("root operator channel required")
    if os.environ.get("GITHUB_ACTIONS") or os.environ.get("RUNNER_NAME"):
        raise RuntimeError("cannot apply from GitHub Actions runner")
    for user in (OPERATOR, WORKER):
        account = pwd.getpwnam(user)
        if account.pw_uid == 0:
            raise RuntimeError("unexpected uid 0")
    if not shutil.which("groupadd") or not shutil.which("usermod"):
        raise RuntimeError("group management tools missing")
    if not shutil.which("udevadm"):
        raise RuntimeError("udevadm missing")


def run_admin(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, timeout=20)


def install_exact(path: Path, content: str, mode: int,
                  *, previous: str | None = None) -> str:
    state = file_state(path, content)
    upgrade = state == "CONFLICT_REFUSED" and previous is not None \
        and file_state(path, previous) == "EXACT"
    if state not in ("MISSING", "EXACT") and not upgrade:
        raise RuntimeError(f"conflicting existing managed file: {path.name}")
    if state == "EXACT":
        return "UNCHANGED"
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, prefix=".plasma-stage-",
        delete=False
    ) as temp:
        temp.write(content)
        temp.flush()
        os.fsync(temp.fileno())
        name = temp.name
    try:
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)
    return "UPDATED" if upgrade else "INSTALLED"


def install_appimage(source: Path) -> str:
    if not source.is_file() or source.is_symlink():
        raise RuntimeError("KINGST source must be a regular local file")
    if sha256(source) != LA_DIGEST:
        raise RuntimeError("KINGST AppImage SHA256 mismatch; refusing substitute")
    if LA_BINARY.is_symlink() or (LA_BINARY.exists() and
                                  sha256(LA_BINARY) != LA_DIGEST):
        raise RuntimeError("conflicting existing pinned LA binary")
    if not LA_BINARY.exists():
        LA_BINARY.parent.mkdir(parents=True, exist_ok=True)
        # Atomic copy, leaving the original operator installation unchanged.
        with tempfile.NamedTemporaryFile(dir=LA_BINARY.parent,
                                         prefix=".la-stage-", delete=False) as temp:
            staged = Path(temp.name)
            with source.open("rb") as stream:
                shutil.copyfileobj(stream, temp)
        try:
            if sha256(staged) != LA_DIGEST:
                raise RuntimeError("staged AppImage integrity check failed")
            staged.chmod(0o755)
            os.replace(staged, LA_BINARY)
        finally:
            staged.unlink(missing_ok=True)
    return install_exact(LA_WRAPPER, render_wrapper(), 0o755)


def apply(appimage: Path | None = None) -> None:
    require_safe_admin()
    # Reject unmanaged udev conflicts before making any group changes.
    if managed_rule_state() not in (
            "MISSING", "EXACT", "LEGACY_EXACT_UPGRADE_AVAILABLE"):
        raise RuntimeError("existing udev rule differs, no overwrite")
    if appimage is not None:
        if not appimage.is_file() or appimage.is_symlink() or sha256(appimage) != LA_DIGEST:
            raise RuntimeError("selected LA AppImage is not the pinned real-test binary")
        if file_state(LA_WRAPPER, render_wrapper()) not in ("MISSING", "EXACT"):
            raise RuntimeError("LA wrapper conflict")
        if LA_BINARY.is_symlink() or (LA_BINARY.exists() and
                                      sha256(LA_BINARY) != LA_DIGEST):
            raise RuntimeError("existing LA binary mismatch")

    try:
        grp.getgrnam(GROUP)
    except KeyError:
        run_admin(["groupadd", "--system", GROUP])
    for user in (OPERATOR, WORKER):
        if GROUP not in current_groups(user):
            run_admin(["usermod", "--append", "--groups", GROUP, user])
    print("udev_rules=" + install_exact(
        RULE_FILE, render_rules(), 0o644, previous=render_rules(legacy=True)))
    if appimage is not None:
        print("kingst_appimage=" + install_appimage(appimage))
    run_admin(["udevadm", "control", "--reload"])
    print("udev_reload=PASS")
    print("CURRENT_DEVICE_NODES=NOT_CHANGED: re-enumeration or operator-selected"
          " scoped udev trigger required")
    print("RUNNER_NEW_GROUPS=NOT_ACTIVE: restart dedicated runner while idle")
    print("SSH_CREDENTIALS=NOT_COPIED: reauthorize worker identity separately")
    print("HARDWARE_TESTS=NOT_RUN")


def self_test() -> None:
    rules = render_rules()
    assert rules.count('SUBSYSTEM=="usb"') == 5
    assert rules.count('SUBSYSTEM=="tty"') == 2
    for vid, pid in VID_PIDS:
        assert f'ATTR{{idVendor}}=="{vid}"' in rules
        assert f'ATTR{{idProduct}}=="{pid}"' in rules
    assert 'MODE="0660"' in rules
    assert 'MODE="0666"' not in rules
    assert 'ATTRS{idVendor}=="0403"' in rules
    assert 'ATTRS{idProduct}=="6010"' in rules
    assert 'ATTRS{idVendor}=="cafe"' in rules
    assert 'ATTRS{idProduct}=="4001"' in rules
    assert 'sudo' not in rules
    assert render_wrapper().count("--appimage-extract-and-run") == 1
    try:
        render_rules("evil\" GROUP=\"root")
        raise AssertionError("invalid group accepted")
    except ValueError:
        pass
    print("PLASMA Codex dedicated USB parity configuration self-test PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--audit", action="store_true")
    modes.add_argument("--apply", action="store_true")
    modes.add_argument("--self-test", action="store_true")
    parser.add_argument("--la-appimage", type=Path, default=None,
                        help="Optional local trusted AppImage path; never printed")
    args = parser.parse_args()
    if args.self_test:
        self_test()
    elif args.audit:
        print(json.dumps(audit(), indent=2, sort_keys=True))
    else:
        apply(args.la_appimage)


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, OSError, KeyError, subprocess.SubprocessError) as exc:
        # Never log private --la-appimage arguments or source paths.
        msg = str(exc)
        if "AppImage" in msg or "KINGST" in msg or "binary" in msg:
            print("PLASMA host parity blocked: AppImage validation failed", file=sys.stderr)
        else:
            print("PLASMA host parity blocked: " + msg, file=sys.stderr)
        raise SystemExit(2)

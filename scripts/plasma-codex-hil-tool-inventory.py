#!/usr/bin/env python3
"""Passive, sanitized SWPC HIL tool/permission inventory for plasma-codex.

Only PATH lookup, identity/group queries, sysfs text reads and stat/access of
device nodes. No SSH connections, serial opens, libusb transfers, USB power
commands, LA captures, JTAG operations, or subprocess invocation.
"""
from __future__ import annotations

import argparse
import grp
import json
import os
from pathlib import Path
import pwd
import shutil
import socket
import stat

WORKER = "plasma-codex"
RUNNER = "SWPC-plasma-codex"
PROHIBITED_GROUPS = frozenset(
    {"sudo", "docker", "adm", "dialout", "gpio", "i2c", "video", "plasma-hil"}
)
# Only public vendor/product IDs, never raw USB serials or changing bus/device IDs.
TARGETS = {
    "z2_ft2232": ("0403", "6010"),
    "usb_power_hub": ("8564", "4100"),
    "kingst_la2016": ("77a1", "01a2"),
}


def worker_groups() -> set[str]:
    entry = pwd.getpwuid(os.geteuid())
    return {
        grp.getgrgid(gid).gr_name
        for gid in os.getgrouplist(entry.pw_name, entry.pw_gid)
    }


def cli_status(executable: str) -> str:
    # A PATH hit is not proof the CLI works or has permission to use hardware.
    return "FOUND_UNEXECUTED" if shutil.which(executable) else "NOT_IN_PATH"


def device_access(path: Path) -> str:
    """Stat and permission check only; never open the node."""
    try:
        meta = path.stat()
        if not stat.S_ISCHR(meta.st_mode):
            return "NOT_CHAR_DEVICE"
        if os.access(path, os.R_OK | os.W_OK, effective_ids=True):
            return "RW_BY_DAC_NOT_OPENED"
        if os.access(path, os.R_OK, effective_ids=True):
            return "READ_BY_DAC_NOT_OPENED"
        return "DENIED_BY_DAC"
    except (OSError, ValueError):
        return "UNAVAILABLE"


def usb_inventory(root: Path = Path("/sys/bus/usb/devices")) -> dict:
    matches: dict[str, list[str]] = {name: [] for name in TARGETS}
    try:
        entries = list(root.iterdir())
    except OSError:
        return {name: {"enumeration": "SYSFS_UNAVAILABLE", "node_dac": "NOT_CHECKED"}
                for name in TARGETS}

    for entry in entries:
        try:
            vendor = (entry / "idVendor").read_text(encoding="ascii").strip().lower()
            product = (entry / "idProduct").read_text(encoding="ascii").strip().lower()
        except (OSError, UnicodeError):
            continue
        for name, identity in TARGETS.items():
            if (vendor, product) != identity:
                continue
            try:
                bus = int((entry / "busnum").read_text(encoding="ascii").strip())
                dev = int((entry / "devnum").read_text(encoding="ascii").strip())
                # The numeric location is used only internally; never serialized.
                node = Path("/dev/bus/usb") / f"{bus:03d}" / f"{dev:03d}"
                matches[name].append(device_access(node))
            except (OSError, ValueError):
                matches[name].append("NODE_UNRESOLVED")

    report = {}
    for name, accesses in matches.items():
        if not accesses:
            report[name] = {"enumeration": "NOT_ENUMERATED", "node_dac": "NOT_CHECKED"}
        elif len(accesses) != 1:
            report[name] = {"enumeration": "MULTIPLE_IDENTITIES", "node_dac": "AMBIGUOUS"}
        else:
            report[name] = {"enumeration": "FOUND_BY_VID_PID", "node_dac": accesses[0]}
    return report


def uart_inventory() -> dict:
    try:
        entries = list(Path("/dev").glob("ttyUSB*"))
    except OSError:
        entries = []
    # Does not claim any candidate belongs to Z2, and does not open a TTY.
    return {
        "generic_ttyusb_candidates": len(entries),
        "generic_ttyusb_rw_by_dac": sum(
            1 for node in entries if device_access(node) == "RW_BY_DAC_NOT_OPENED"
        ),
        "z2_uart_mapping": "NOT_CHECKED",
        "serial_open": "NOT_RUN",
    }


def appimage_cli_status() -> str:
    # Optional trusted local provisioning. Do not print the environment value.
    candidate = os.environ.get("PLASMA_HIL_LA_CLI", "")
    if not candidate:
        return "NOT_CONFIGURED"
    path = Path(candidate)
    if not path.is_absolute():
        return "INVALID_NONABSOLUTE"
    try:
        return "FOUND_UNEXECUTED" if path.is_file() and os.access(path, os.X_OK) else "NOT_EXECUTABLE"
    except OSError:
        return "UNAVAILABLE"


def inventory() -> dict:
    groups = worker_groups()
    expected_user = pwd.getpwuid(os.geteuid()).pw_name == WORKER
    identity = {
        "host_swpc": socket.gethostname() == "SWPC",
        "worker_account": expected_user,
        "non_root": os.geteuid() != 0,
        "runner_name": os.environ.get("RUNNER_NAME") == RUNNER,
        "no_prohibited_groups": PROHIBITED_GROUPS.isdisjoint(groups),
        # plugdev is informational only; device-specific node DAC is authoritative.
        "plugdev_member": "plugdev" in groups,
    }
    return {
        "schema": "plasma.codex.hil-direct-tool-inventory.v1",
        "scope": "PASSIVE_LOCAL_METADATA_ONLY",
        "identity": identity,
        "cli_presence": {
            "ssh": cli_status("ssh"),
            "uhubctl": cli_status("uhubctl"),
            "openocd": cli_status("openocd"),
            "xsdb": cli_status("xsdb"),
            "hw_server": cli_status("hw_server"),
            "picocom": cli_status("picocom"),
            "minicom": cli_status("minicom"),
            "sigrok_cli_system": cli_status("sigrok-cli"),
            "la_appimage_override": appimage_cli_status(),
        },
        "usb": usb_inventory(),
        "uart": uart_inventory(),
        "tests": {
            "z2_ssh_connect": "NOT_RUN",
            "z2_uart_open": "NOT_RUN",
            "z2_jtag_connect": "NOT_RUN",
            "hub_power_command": "NOT_RUN",
            "la_device_open_or_capture": "NOT_RUN",
            "hardware_access_qualified": False,
        },
        "inventory_completed": True,
        "identity_ready": all(identity[k] for k in
                              ("host_swpc", "worker_account", "non_root",
                               "runner_name", "no_prohibited_groups")),
        "note": "Presence/DAC checks never prove real SSH/USB/UART/JTAG/LA operation.",
    }


def self_test() -> None:
    assert PROHIBITED_GROUPS.isdisjoint({"plasma-codex", "plasma-monitor"})
    assert not PROHIBITED_GROUPS.isdisjoint({"sudo", "plasma-codex"})
    assert cli_status("a-tool-name-that-does-not-exist-__plasma__") == "NOT_IN_PATH"
    assert usb_inventory(Path("/definitely-not-a-real-sysfs-dir"))["z2_ft2232"]["enumeration"] == "SYSFS_UNAVAILABLE"
    assert all(len(v) == 2 for v in TARGETS.values())
    print("PLASMA passive HIL inventory self-test PASS")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-test", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        self_test()
        return
    result = inventory()
    print(json.dumps(result, sort_keys=True, indent=2))
    # Identity failure is a hard stop, but missing devices/tools are inventory facts.
    if not result["identity_ready"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Passive USB identity/topology observation from Linux's cached sysfs only.

No USB device is opened, no ioctl or control transfer is issued. This is not
proof of a KL25 target, SWD connection, or permission to run OpenOCD.
"""
from __future__ import annotations

import json
from pathlib import Path
import re

USB_ROOT = Path("/sys/bus/usb/devices")
HEX4 = re.compile(r"[0-9a-fA-F]{4}\Z")
TOPOLOGY = re.compile(r"[0-9]{1,3}-[0-9]{1,3}(?:\.[0-9]{1,3}){0,7}\Z")


def observe(root: Path = USB_ROOT) -> dict:
    devices = []
    try:
        entries = sorted(root.iterdir(), key=lambda p: p.name)
    except OSError:
        return {"status": "SYSFS_UNAVAILABLE", "devices": [],
                "usb_transfer": "NOT_RUN", "target_identity": "NOT_CHECKED"}
    for entry in entries:
        if not TOPOLOGY.fullmatch(entry.name):
            continue
        try:
            vid = (entry / "idVendor").read_text(encoding="ascii").strip()
            pid = (entry / "idProduct").read_text(encoding="ascii").strip()
        except (OSError, UnicodeError):
            continue
        if not HEX4.fullmatch(vid) or not HEX4.fullmatch(pid):
            continue
        # Product is an already cached, untrusted display name, not an
        # identity claim. Never read/export serial-number attributes.
        try:
            name = (entry / "product").read_text(encoding="utf-8").strip()
            name = "".join(ch for ch in name if ch.isprintable())[:80]
        except (OSError, UnicodeError):
            name = ""
        devices.append({"topology": entry.name,
                        "vid": vid.lower(), "pid": pid.lower(),
                        "device_name": name})
    return {"status": "PASSIVE_CACHE_READ", "devices": devices,
            "usb_transfer": "NOT_RUN", "target_identity": "NOT_CHECKED"}


if __name__ == "__main__":
    print(json.dumps(observe(), sort_keys=True))

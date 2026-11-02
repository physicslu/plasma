"""Host-only: devmem owner admission against the REAL Z2 sysfs layout.

Observed on Z2 (boot 4cefdc0c): /sys/class/uio/uio0/device ->
/sys/devices/soc0/43c00000.audio-codec-ctrl, and
/sys/bus/platform/devices/43c00000.audio-codec-ctrl is a symlink to it.
The earlier check (node.parent == bus/platform/devices) wrongly denied
this genuine platform device with UIO_NOT_PLATFORM_DEVICE.
"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from pl.hil import fpga_image_admission as admission  # noqa: E402
from pl.hil import fpga_image_guard as guard  # noqa: E402
from pl.hil import fpga_image_root as root  # noqa: E402

DEPLOY = ROOT / "pl/hil/releases/swd-independent-ab79b04e/plasma-image-manifest.json"
NODE = "43c00000.audio-codec-ctrl"


class Port:
    def __init__(self, release, facts):
        self.release, self._facts = release, facts

    def _require_locked(self):
        return None

    def current_facts(self):
        return self._facts


class RealSysfsLayoutTests(unittest.TestCase):
    def setUp(self):
        self.release = root.parse_image_manifest_bytes(DEPLOY.read_bytes())
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.sys = self.base / "sys"
        self.proc = self.base / "proc"
        boot = self.proc / "sys/kernel/random/boot_id"
        boot.parent.mkdir(parents=True)
        boot.write_text("boot-x")
        self.facts = {
            "observation_kind": "LIVE_ROOT_READ_ONLY", "root": True,
            "boot_id": "boot-x", "manager_state": "operating",
            "recovery_sha256": self.release.recovery_sha256,
            "candidate_sha256": self.release.firmware_sha256,
            "proc_complete": True, "proc_conflicts": [],
            "proc_scan_diagnostic": {"status": "COMPLETE"},
            "uio_overlaps": ["uio0"], "platform_overlaps": [NODE],
        }

    def build(self, *, bus_link: str | None = "self"):
        device = self.sys / "devices/soc0" / NODE
        (device / "power").mkdir(parents=True)
        (device / "power/runtime_status").write_text("suspended")
        drv = self.sys / "bus/platform/drivers/uio_pdrv_genirq"
        drv.mkdir(parents=True)
        (device / "driver").symlink_to(drv)
        bus = self.sys / "bus/platform/devices"
        bus.mkdir(parents=True)
        if bus_link == "self":
            (bus / NODE).symlink_to(device)
        elif bus_link == "other":
            other = self.sys / "devices/soc0/other"
            other.mkdir()
            (bus / NODE).symlink_to(other)
        uio = self.sys / "class/uio/uio0"
        (uio / "maps/map0").mkdir(parents=True)
        (uio / "maps/map0/addr").write_text("0x43c00000")
        (uio / "maps/map0/size").write_text("0x00010000")
        (uio / "device").symlink_to(device)

    def collect(self):
        load = "fpga_manager fpga0: writing " + self.release.firmware_name + " to x"
        with patch.object(guard, "PROC", self.proc), \
                patch.object(guard, "SYS", self.sys), \
                patch.object(guard, "manager_last_load", return_value=load), \
                patch.object(admission.os, "geteuid", return_value=0):
            return admission.collect_live(
                root_port=Port(self.release, self.facts), release=self.release,
                expected_firmware=self.release.firmware_name)

    def test_real_layout_platform_device_admitted_as_devmem(self):
        self.build()
        report = self.collect()
        self.assertEqual(report["mmio_backend"], "devmem")
        self.assertEqual(report["current_uio"]["platform_node"], NODE)

    def test_device_without_platform_bus_entry_denied(self):
        self.build(bus_link=None)
        with self.assertRaisesRegex(ValueError, "UIO_NOT_PLATFORM_DEVICE"):
            self.collect()

    def test_bus_entry_pointing_elsewhere_denied(self):
        self.build(bus_link="other")
        with self.assertRaisesRegex(ValueError, "UIO_NOT_PLATFORM_DEVICE"):
            self.collect()

    def test_competing_process_still_denied(self):
        self.build()
        self.facts["proc_conflicts"] = ["4242"]
        with self.assertRaisesRegex(ValueError, "PROC_RESOURCE_OWNER_CONFLICT"):
            self.collect()


if __name__ == "__main__":
    unittest.main()

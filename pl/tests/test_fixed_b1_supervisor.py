"""Host-only tests of zero automatic Z2 actuation and 64KiB inventory."""
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from pl.hil.fixed_b1_contract import B1Blocked
from pl.hil.fixed_b1_supervisor import (
    IsolatedIdentity, Inputs, check_ownership_full_64k, exact_pins,
)


class B1TargetOfflineContracts(unittest.TestCase):
    def test_no_real_admission_is_accepted(self):
        with tempfile.TemporaryDirectory() as root:
            p = Path(root)
            inputs = Inputs(*(p / f for f in (
                "candidate.bit", "candidate.hwh", "candidate.bin",
                "base.bin", "base.hwh", "out", "receipt.json", "admission.json")))
            with patch("pl.hil.fixed_b1_supervisor.os.geteuid", return_value=1000):
                with self.assertRaisesRegex(B1Blocked, "ROOT_REQUIRED"):
                    exact_pins(inputs)

    def test_absent_kernel_resource_inventory_fail_closed(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td)
            with self.assertRaisesRegex(B1Blocked, "INVENTORY_INCOMPLETE"):
                check_ownership_full_64k(sysroot=p, procroot=p)

    def test_bound_uio_at_tail_of_full_window_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            syspath, procpath = root / "sys", root / "proc"
            uio = syspath / "class/uio/uio0"
            mapping = uio / "maps/map0"
            mapping.mkdir(parents=True)
            (mapping / "addr").write_text("0x4000F000\n")
            (mapping / "size").write_text("0x1000\n")
            driver = uio / "device/driver"
            driver.mkdir(parents=True)
            (syspath / "bus/platform/devices").mkdir(parents=True)
            procpath.mkdir()
            with self.assertRaisesRegex(B1Blocked, "BOUND_UIO_DRIVER"):
                check_ownership_full_64k(sysroot=syspath, procroot=procpath)

    def test_open_dev_mem_consumer_is_refused(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            syspath, procpath = root / "sys", root / "proc"
            (syspath / "class/uio").mkdir(parents=True)
            (syspath / "bus/platform/devices").mkdir(parents=True)
            pid = procpath / "1234"
            (pid / "fd").mkdir(parents=True)
            (pid / "maps").write_text("")
            (pid / "fd/7").symlink_to("/dev/mem")
            with self.assertRaisesRegex(B1Blocked, "ACTIVE_PL_CONSUMER"):
                check_ownership_full_64k(sysroot=syspath, procroot=procpath)

    def test_unreaped_child_forbids_restoration(self):
        child = IsolatedIdentity()
        fake = type("Fake", (), {"poll": lambda self: None})()
        child.proc = fake
        with self.assertEqual if False else patch(
                "pl.hil.fixed_b1_supervisor.check_ownership_full_64k"
        ) as check:
            self.assertFalse(child.stopped_and_unmapped())
            check.assert_not_called()


if __name__ == "__main__":
    unittest.main()

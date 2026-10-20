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


    def test_unrelated_uio_owner_does_not_block_full_64k(self):
        """Audio UIO outside the aperture is not an F1-B owner."""
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            sysroot, procroot = base / "sys", base / "proc"
            mapping = sysroot / "class/uio/uio1/maps/map0"
            mapping.mkdir(parents=True)
            (mapping / "addr").write_text("0x43C00000\n")
            (mapping / "size").write_text("0x1000\n")
            (mapping.parent.parent / "device/driver").mkdir(parents=True)
            (sysroot / "bus/platform/devices").mkdir(parents=True)
            pid = procroot / "1234"
            (pid / "fd").mkdir(parents=True)
            (pid / "fd/3").symlink_to("/dev/uio1")
            (pid / "maps").write_text(
                "abcd0000-abcd1000 r--s 00000000 00:00 0 /dev/uio1\n")
            check_ownership_full_64k(sysroot=sysroot, procroot=procroot)

    def test_latest_manager_load_must_match_requested_name(self):
        from pl.hil.fixed_b1_supervisor import manager_write_firmware
        with tempfile.TemporaryDirectory() as td:
            manager = Path(td)
            (manager / "state").write_text("operating")
            with patch("pl.hil.fixed_b1_supervisor.MANAGER", manager), patch(
                "pl.hil.fixed_b1_supervisor.manager_last_load",
                return_value="fpga_manager fpga0: writing other.bin to xdevcfg",
            ):
                with self.assertRaisesRegex(B1Blocked, "LOAD_PROVENANCE_MISMATCH"):
                    manager_write_firmware("base.bin")
            with patch("pl.hil.fixed_b1_supervisor.MANAGER", manager), patch(
                "pl.hil.fixed_b1_supervisor.manager_last_load",
                return_value="fpga_manager fpga0: writing base.bin to xdevcfg",
            ):
                manager_write_firmware("base.bin")
                self.assertEqual((manager / "firmware").read_text(), "base.bin")

    def test_service_baseline_reuses_existing_swd05_contract(self):
        from pl.hil.fixed_b1_supervisor import service_snapshot
        from pl.hil.swd04.contract import REQUIRED_SERVICES
        assert "jupyter.service" in REQUIRED_SERVICES
        seen = []
        def fake_run(argv, **kwargs):
            seen.append(argv[-1])
            return type("Completed", (), {"returncode": 0})()
        with patch("pl.hil.fixed_b1_supervisor.subprocess.run",
                   side_effect=fake_run):
            self.assertTrue(all(service_snapshot().values()))
        self.assertEqual(tuple(seen), REQUIRED_SERVICES)

    def test_unreaped_child_forbids_restoration(self):
        child = IsolatedIdentity()
        fake = type("Fake", (), {"poll": lambda self: None})()
        child.proc = fake
        with patch("pl.hil.fixed_b1_supervisor.check_ownership_full_64k") as check:
            self.assertFalse(child.stopped_and_unmapped())
            check.assert_not_called()


if __name__ == "__main__":
    unittest.main()

#!/usr/bin/env python3
"""Path 2 root target passive safety contracts; never connect to real Z2."""
from __future__ import annotations

from pathlib import Path
import os
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
from pl.hil import path2_z2_target_guard as target
from pl.hil.swd04 import one_shot


def fixture(**overrides):
    record = {
        "root": True, "boot_id": "example-current-boot",
        "manager_state": "operating",
        "recovery_sha256": target.f1b.BASE_SHA,
        "candidate_sha256": target.f1b.BIN_SHA,
        "uio_overlaps": [], "platform_overlaps": [],
        "proc_complete": True, "proc_conflicts": [],
        "observation_kind": "LIVE_ROOT_READ_ONLY",
        "axi_isolation_evidence": "UNPROVEN",
        "active_image_attestation": "UNPROVEN",
    }
    record.update(overrides)
    return record


class PassiveSafety(unittest.TestCase):
    def test_even_root_and_no_consumers_cannot_claim_hardware_qualification(self):
        report = target.classify_passive_facts(fixture())
        self.assertEqual(report["decision"], "NO_GO")
        self.assertFalse(report["hardware_write_authorized"])
        self.assertEqual(report["scope"], "PASSIVE_OBSERVATION_ONLY")
        self.assertIn("AXI_ISOLATION_UNPROVEN", report["blockers"])
        self.assertIn("ACTIVE_FPGA_IMAGE_UNATTESTED", report["blockers"])

    def test_bound_uio_fabric_and_process_conflicts_are_explicit_blockers(self):
        r = target.classify_passive_facts(fixture(
            uio_overlaps=["uio1"], platform_overlaps=["40000000.fabric"],
            proc_conflicts=["123"]))
        self.assertIn("BOUND_UIO_IN_F1B_APERTURE", r["blockers"])
        self.assertIn("BOUND_PLATFORM_IN_F1B_APERTURE", r["blockers"])
        self.assertIn("RETAINED_MMIO_PROCESS_MAPPING", r["blockers"])

    def test_forged_claim_cannot_enable_hardware_operations(self):
        r = target.classify_passive_facts(fixture(
            axi_isolation_evidence="INDEPENDENT_HARDWARE_PROOF",
            active_image_attestation="INDEPENDENT_TARGET_PROOF"))
        self.assertEqual(r["decision"], "NO_GO")
        self.assertFalse(r["hardware_write_authorized"])
        self.assertEqual(r["blockers"], [
            "LIVE_PROVIDER_AND_PROOF_AUTHORITY_NOT_REGISTERED"])

    def test_untrusted_or_partial_observations_are_denied(self):
        cases = [
            dict(root=False), dict(boot_id=""),
            dict(manager_state="unknown"),
            dict(recovery_sha256="0"*64),
            dict(candidate_sha256="0"*64),
            dict(proc_complete=False),
            dict(observation_kind="HISTORICAL_ONE_SHOT"),
            dict(uio_overlaps="uio1"),
            dict(platform_overlaps=None),
            dict(proc_conflicts=[""]),
        ]
        for c in cases:
            with self.subTest(c=c), self.assertRaises(target.TargetSafetyDenied):
                target.classify_passive_facts(fixture(**c))
        with self.assertRaises(target.TargetSafetyDenied):
            target.classify_passive_facts({**fixture(), "i_say_safe": True})

    def test_uio_and_platform_mapping_overlap_scanner(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            uio = root / "class/uio/uio1"
            mapping = uio / "maps/map0"
            mapping.mkdir(parents=True)
            (mapping / "addr").write_text("0x40000000")
            (mapping / "size").write_text("0x10000")
            (uio / "device/driver").mkdir(parents=True)
            platform = root / "bus/platform/devices/40000000.fabric"
            platform.mkdir(parents=True)
            (platform / "driver").mkdir()
            (platform / "resource").write_text("40000000 4000ffff 00000200\n")
            a, b = target.scan_kernel_owners(sysroot=root)
            self.assertEqual(a, ["uio1"])
            self.assertEqual(b, ["40000000.fabric"])
            (uio / "device/driver").rmdir()
            (platform / "driver").rmdir()
            self.assertEqual(target.scan_kernel_owners(sysroot=root), ([], []))

    def test_proc_fd_overlap_denied_and_clean_snapshot_not_axi_proof(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pid = root / "1000"
            fd = pid / "fd"
            fd.mkdir(parents=True)
            (pid / "maps").write_text(
                "00100000-00101000 r--p 00000000 00:00 0 [anon]\n")
            clean, conflicts = target.scan_proc_consumers(procroot=root)
            self.assertTrue(clean)
            self.assertEqual(conflicts, [])
            (fd / "3").symlink_to("/dev/mem")
            clean, conflicts = target.scan_proc_consumers(procroot=root)
            self.assertTrue(clean)
            self.assertEqual(conflicts, ["1000"])

    def test_missing_kernel_or_uio_maps_cannot_be_clean_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            with self.assertRaisesRegex(target.TargetSafetyDenied, "KERNEL_OWNER_VISIBILITY"):
                target.scan_kernel_owners(sysroot=root)
            (root / "bus/platform/devices").mkdir(parents=True)
            uio = root / "class/uio/uio1"
            uio.mkdir(parents=True)
            for create_empty_maps in (False, True):
                if create_empty_maps:
                    (uio / "maps").mkdir()
                with self.assertRaisesRegex(target.TargetSafetyDenied, "UIO_MAP_VISIBILITY"):
                    target.scan_kernel_owners(sysroot=root)

    def test_invalid_uio_range_never_looks_nonoverlapping(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "bus/platform/devices").mkdir(parents=True)
            mapping = root / "class/uio/uio1/maps/map0"
            mapping.mkdir(parents=True)
            for address, size in (("0x40000000", "0"), ("-1", "4096"),
                                  ("0xffffffff", "4096")):
                (mapping / "addr").write_text(address)
                (mapping / "size").write_text(size)
                with self.assertRaisesRegex(target.TargetSafetyDenied, "UIO_MAP_RANGE"):
                    target.scan_kernel_owners(sysroot=root)

    def test_fd_disappearing_during_scan_is_incomplete(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            fd = root / "1000/fd"
            fd.mkdir(parents=True)
            (fd / "3").symlink_to("/dev/mem")
            (fd.parent / "maps").write_text("")
            with patch.object(target.os, "readlink", side_effect=FileNotFoundError):
                self.assertEqual(target.scan_proc_consumers(procroot=root), (False, ["1000"]))

    def test_disappearing_process_does_not_claim_complete_snapshot(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            # Process listed, but fd and maps disappear before inspection.
            (root / "1000").mkdir()
            complete, conflicts = target.scan_proc_consumers(procroot=root)
            self.assertFalse(complete)
            self.assertEqual(conflicts, ["1000"])

    def test_retained_vma_never_passes(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            pid = root / "1000"
            (pid / "fd").mkdir(parents=True)
            (pid / "maps").write_text(
                "00100000-00101000 rw-p 40000000 00:00 0 /dev/mem\n")
            complete, conflicts = target.scan_proc_consumers(procroot=root)
            self.assertTrue(complete)
            self.assertEqual(conflicts, ["1000"])


class RootTargetPortContracts(unittest.TestCase):
    def test_default_live_methods_have_no_hardware_capability(self):
        port = target.RootZ2TargetPort(
            candidate=Path("/lib/firmware/test.bin"),
            recovery=Path("/lib/firmware/base.bin"),
            ledger=Path("/run/plasma-z2-swd05/target.json"))
        with self.assertRaisesRegex(target.TargetSafetyDenied, "Z2_ROOT_REQUIRED"):
            with patch.object(os, "geteuid", return_value=1000):
                with port.exclusive():
                    self.fail("not authorized")
        with self.assertRaisesRegex(
                target.TargetSafetyDenied, "AXI_ISOLATION_UNPROVEN_NO_FPGA_WRITE"):
            port.load_candidate_once(target.f1b.BIN_SHA)
        with self.assertRaisesRegex(
                target.TargetSafetyDenied, "CURRENT_IMAGE_OR_CHILD_ADMISSION"):
            port.read_f1b_identity_child()
        with self.assertRaisesRegex(
                target.TargetSafetyDenied, "SAFE_RECOVERY_CONTEXT"):
            port.restore_original_once(target.f1b.BASE_SHA)
        self.assertEqual(target.GLOBAL_LOCK, one_shot.OWNER_LOCK)

    def test_missing_target_lock_rejects_passive_and_clock(self):
        port = target.RootZ2TargetPort(
            candidate=Path("/lib/firmware/test.bin"),
            recovery=Path("/lib/firmware/base.bin"),
            ledger=Path("/run/plasma-z2-swd05/target.json"))
        with self.assertRaisesRegex(target.TargetSafetyDenied,
                                    "FPGA_OWNER_LOCK_REQUIRED"):
            port.passive_report()
        with self.assertRaisesRegex(target.TargetSafetyDenied,
                                    "FPGA_OWNER_LOCK_REQUIRED"):
            port.now()

    def test_probe_never_promotes_previous_passive_uio_exception(self):
        port = target.RootZ2TargetPort(
            candidate=Path("/lib/firmware/test.bin"),
            recovery=Path("/lib/firmware/base.bin"),
            ledger=Path("/run/plasma-z2-swd05/target.json"))
        port._locked = True  # Explicit Host-only fixture, never live.
        port._lock_owner_pid = os.getpid()
        port._lock_owner_thread = threading.get_ident()
        with patch.object(target, "read_live_z2_facts",
                          return_value=fixture(uio_overlaps=["uio1"])):
            report = port.passive_report()
            self.assertIn("BOUND_UIO_IN_F1B_APERTURE", report["blockers"])
            with self.assertRaisesRegex(
                    target.TargetSafetyDenied, "TARGET_AXI_OR_IMAGE_ISOLATION_NO_GO"):
                port.qualification("download")

    def test_lock_claim_cannot_cross_thread_or_process(self):
        port = target.RootZ2TargetPort(
            candidate=Path("/lib/firmware/test.bin"),
            recovery=Path("/lib/firmware/base.bin"),
            ledger=Path("/run/plasma-z2-swd05/target.json"))
        port._locked = True  # Host-only fixture, without OS lock.
        port._lock_owner_pid = os.getpid()
        port._lock_owner_thread = threading.get_ident()
        self.assertIsInstance(port.now(), int)
        port._lock_owner_thread = -1
        with self.assertRaisesRegex(target.TargetSafetyDenied,
                                    "FPGA_OWNER_LOCK_REQUIRED"):
            port.now()
        port._lock_owner_thread = threading.get_ident()
        port._lock_owner_pid = -1
        with self.assertRaisesRegex(target.TargetSafetyDenied,
                                    "FPGA_OWNER_LOCK_REQUIRED"):
            port.now()

    def test_cross_trigger_checkpoint_rechecks_lease_boot_and_last_load(self):
        from scripts import plasma_path2_persistent_lease as lease
        import time
        now = int(time.time())
        port = target.RootZ2TargetPort(
            candidate=Path("/lib/firmware/plasma-f1b-owner-20261020-once.bin"),
            recovery=Path("/lib/firmware/base.bin"),
            ledger=Path("/run/plasma-z2-swd05/f1b-site1-lease.json"))
        # The local fixture models an acquired root owner, not a real lock.
        port._locked = True
        port._lock_owner_pid = os.getpid()
        port._lock_owner_thread = threading.get_ident()
        record = dict(
            status="LOADED_AND_HELD", load_attempts=1,
            restore_attempts=0, artifact_sha256=target.f1b.BIN_SHA,
            recovery_sha256=target.f1b.BASE_SHA, boot_id="boot-current",
            last_seen=now-2, lease_deadline=now+120, lease_id="lease-123")
        live = fixture(boot_id="boot-current")
        name = port.candidate.name
        manager_log = f"fpga_manager fpga0: writing {name} to fpga0"
        with patch.object(lease.LeaseLedger, "snapshot", return_value=record), \
             patch.object(target, "read_live_z2_facts", return_value=live), \
             patch.object(one_shot, "manager_last_load",
                          return_value=manager_log):
            result = port.inspect_cross_trigger("testing")
            self.assertEqual(result["status"],
                             "PASSIVE_CHECKPOINT_REVIEW_REQUIRED")
            self.assertFalse(result["hardware_write_authorized"])
            self.assertEqual(result["axi_isolation"], "UNPROVEN")
            self.assertIn("UNATTESTED", result["loaded_image_identity"])
            self.assertEqual(port.inspect_cross_trigger("restore")["stage"],
                             "restore")
            with patch.object(target, "read_live_z2_facts",
                              return_value=fixture(boot_id="different-boot")):
                with self.assertRaisesRegex(target.TargetSafetyDenied,
                                            "CROSS_TRIGGER_BOOT_OR_MMIO"):
                    port.inspect_cross_trigger("testing")
            with patch.object(one_shot, "manager_last_load",
                              return_value="fpga_manager fpga0: writing base.bin to fpga0"):
                with self.assertRaisesRegex(target.TargetSafetyDenied,
                                            "HELD_IMAGE_MANAGER"):
                    port.inspect_cross_trigger("testing")
            with patch.object(lease.LeaseLedger, "snapshot",
                              return_value={**record,
                                            "status": "UNKNOWN_MANUAL_RECOVERY"}):
                with self.assertRaisesRegex(target.TargetSafetyDenied,
                                            "CROSS_TRIGGER_LEASE_NOT_ACTIVE"):
                    port.inspect_cross_trigger("testing")
            with patch.object(lease.LeaseLedger, "snapshot",
                              return_value={**record, "lease_deadline": now-1}):
                with self.assertRaisesRegex(target.TargetSafetyDenied,
                                            "HELD_IMAGE_LEASE_EXPIRED"):
                    port.inspect_cross_trigger("restore")

    def test_no_auto_activation_or_arbitrary_shell(self):
        content = (ROOT / "pl/hil/path2_z2_target_guard.py").read_text()
        self.assertNotIn("subprocess", content)
        self.assertNotIn("manager_write(", content)
        self.assertNotIn("ssh ", content)
        self.assertNotIn("if __name__ ==", content)
        main = (ROOT / "scripts/plasma_development_dispatch.py").read_text()
        self.assertIn("return integration.registered_hardware_stage", main)


if __name__ == "__main__":
    unittest.main()

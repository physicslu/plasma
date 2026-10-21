#!/usr/bin/env python3
"""Offline-only stage lifecycle tests. No real Z2, root access or MMIO."""
from __future__ import annotations

from contextlib import nullcontext, ExitStack
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pl.hil import f1b, path2_f1b_minimal_stage as stage
from pl.hil import path2_f1b_dev_risk as risk
from pl.hil import path2_z2_target_guard as guard
from pl.hil.swd04 import one_shot
from scripts import plasma_path2_persistent_lease as lease


class FakeHardware:
    def __init__(self):
        self.boot_id = "reviewed-test-boot-id"
        self.current = "base.bin"
        self.clock = int(time.time())
        self.writes = []
        self.native_reads = 0
        self.raise_write = None
        self.raise_child = False

    def exclusive(self):
        return nullcontext()

    def now(self):
        self.clock += 1
        return self.clock

    def image_sha256(self, which):
        return {"candidate": f1b.BIN_SHA, "recovery": f1b.BASE_SHA}[which]

    def report(self, _port, image):
        if image != self.current:
            raise stage.LiveStageDenied("MANAGER_LAST_LOAD_CHANGED")
        return {
            "target_boot_id": self.boot_id,
            "site": 1,
            "source_sha": f1b.SOURCE,
            "bin_sha256": f1b.BIN_SHA,
            "recovery_sha256": f1b.BASE_SHA,
            "current_uio": risk.FIXED_UIO,
            "development_exception": risk.WAIVER,
            "expected_manager_firmware": image,
            "axi_isolation": "UNPROVEN_ACCEPTED_FOR_ONE_DEVELOPMENT_EXPERIMENT",
        }

    def write(self, firmware):
        self.writes.append(firmware)
        if self.raise_write == firmware:
            raise RuntimeError("INJECTED_FPGA_MANAGER_WRITE_FAILURE")
        self.current = firmware

    def run_child(self, args):
        self.native_reads += 1
        if self.raise_child:
            raise RuntimeError("INJECTED_SIGBUS_UNREAPED")
        self.assert_child_args(args)
        one_shot.record_json(stage.CHILD, {
            "observed": {str(k): v for k, v in f1b.IDENTITY.items()}})

    @staticmethod
    def assert_child_args(args):
        assert args[1:] == ["-m", "pl.hil.path2_f1b_minimal_stage",
                            "--identity-child"]


class MinimalStageTests(unittest.TestCase):
    def setUp(self):
        self.work = tempfile.TemporaryDirectory()
        self.addCleanup(self.work.cleanup)
        root = Path(self.work.name)
        self.hw = FakeHardware()
        self.real_trusted_local = stage.trusted_local
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(stage, "LEDGER", root / "f1b.json"))
        self.stack.enter_context(patch.object(stage, "CHILD", root / "identity.json"))
        self.stack.enter_context(patch.object(stage, "trusted_local",
                                              return_value=None))
        self.stack.enter_context(patch.object(stage.guard, "RootZ2TargetPort",
                                              return_value=self.hw))
        self.stack.enter_context(patch.object(stage, "risk_report",
                                              side_effect=self.hw.report))
        self.stack.enter_context(patch.object(one_shot, "manager_write",
                                              side_effect=self.hw.write))
        self.stack.enter_context(patch.object(one_shot, "run_child",
                                              side_effect=self.hw.run_child))
        self.stack.enter_context(patch.object(one_shot, "service_snapshot",
                                              return_value={"plasma-server": "active"}))
        self.stack.enter_context(patch.object(one_shot, "uio_snapshot",
                                              return_value=(("fabric", "True", "uio1"),)))

    def ledger(self):
        return lease.LeaseLedger(stage.LEDGER).snapshot()

    def test_three_manual_triggers_with_no_automatic_next_stage(self):
        d = stage.run("download")
        self.assertEqual(d["result"], "LOADED_AND_HELD")
        self.assertIs(d["auto_test"], False)
        self.assertEqual(self.hw.writes, [stage.CANDIDATE.name])
        self.assertEqual(self.hw.native_reads, 0)
        self.assertEqual(self.ledger()["load_attempts"], 1)
        t = stage.run("test")
        self.assertEqual(t["result"], "IDENTITY_PASS")
        self.assertIs(t["auto_restore"], False)
        self.assertEqual(self.hw.native_reads, 1)
        self.assertEqual(self.hw.writes, [stage.CANDIDATE.name])
        restored = stage.run("restore")
        self.assertEqual(restored["result"], "RESTORED_VERIFIED")
        self.assertEqual(self.hw.writes, [stage.CANDIDATE.name, "base.bin"])
        self.assertEqual(self.ledger()["status"], "RESTORED_VERIFIED")
        self.assertEqual(self.ledger()["load_attempts"], 1)
        self.assertEqual(self.ledger()["test_attempts"], 1)
        self.assertEqual(self.ledger()["restore_attempts"], 1)
        for name in ("download", "test", "restore"):
            with self.subTest(name=name), self.assertRaises(Exception):
                stage.run(name)
        self.assertEqual(len(self.hw.writes), 2)

    def test_testing_before_download_does_not_touch_hardware(self):
        with self.assertRaises(FileNotFoundError):
            stage.run("test")
        self.assertEqual(self.hw.writes, [])

    def test_restore_cannot_run_before_test(self):
        stage.run("download")
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "TEST_NOT_VERIFIED_RESTORE_DENIED"):
            stage.run("restore")
        self.assertEqual(self.hw.writes, [stage.CANDIDATE.name])

    def test_load_error_records_unknown_and_forbids_retry(self):
        self.hw.raise_write = stage.CANDIDATE.name
        with self.assertRaisesRegex(RuntimeError, "INJECTED"):
            stage.run("download")
        self.assertEqual(self.ledger()["status"], "UNKNOWN_MANUAL_RECOVERY")
        self.assertEqual(self.ledger()["load_attempts"], 1)
        with self.assertRaises(stage.LiveStageDenied):
            stage.run("download")
        self.assertEqual(self.hw.writes, [stage.CANDIDATE.name])

    def test_native_sigbus_blocks_restore(self):
        stage.run("download")
        self.hw.raise_child = True
        with self.assertRaisesRegex(RuntimeError, "INJECTED_SIGBUS"):
            stage.run("test")
        self.assertEqual(self.ledger()["status"], "UNKNOWN_MANUAL_RECOVERY")
        with self.assertRaises(stage.LiveStageDenied):
            stage.run("restore")
        self.assertEqual(self.hw.writes, [stage.CANDIDATE.name])

    def test_restore_fail_prevents_second_firmware_write(self):
        stage.run("download")
        stage.run("test")
        self.hw.raise_write = "base.bin"
        with self.assertRaisesRegex(RuntimeError, "INJECTED"):
            stage.run("restore")
        self.assertEqual(self.ledger()["status"], "UNKNOWN_MANUAL_RECOVERY")
        with self.assertRaises(stage.LiveStageDenied):
            stage.run("restore")
        self.assertEqual(self.hw.writes.count("base.bin"), 1)

    def test_changed_manager_image_boot_and_expiry_are_no_go(self):
        stage.run("download")
        self.hw.current = "base.bin"
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "MANAGER_LAST_LOAD_CHANGED"):
            stage.run("test")
        self.hw.current = stage.CANDIDATE.name
        self.hw.boot_id = "unexpected-reboot"
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "TARGET_BOOT_CHANGED"):
            stage.run("test")
        self.hw.boot_id = "reviewed-test-boot-id"
        self.hw.clock += 1000
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "LEASE_EXPIRED_MANUAL_REVIEW"):
            stage.run("test")
        self.assertEqual(self.hw.native_reads, 0)

    def test_second_testing_attempt_denied(self):
        stage.run("download")
        stage.run("test")
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "SECOND_IDENTITY_TEST_DENIED"):
            stage.run("test")
        self.assertEqual(self.hw.native_reads, 1)

    def test_ack_required_and_only_three_fixed_stage_words(self):
        with patch.object(stage, "trusted_local", wraps=None) as auth:
            auth.side_effect = stage.LiveStageDenied("ROOT_REQUIRED")
            with self.assertRaisesRegex(stage.LiveStageDenied, "ROOT_REQUIRED"):
                stage.run("download")
        self.assertEqual(self.hw.writes, [])
        for name in ("build", "download+test", "status;rm -rf /", ""):
            with self.assertRaisesRegex(stage.LiveStageDenied,
                                        "STAGE_NOT_ALLOWLISTED"):
                stage.run(name)
        self.assertEqual(self.hw.writes, [])

    def test_root_risk_ack_is_explicit_and_not_a_secret(self):
        with patch.object(stage, "trusted_local", self.real_trusted_local), \
             patch.object(stage.os, "geteuid", return_value=0), \
             patch.dict(stage.os.environ, {}, clear=True):
            with self.assertRaisesRegex(stage.LiveStageDenied,
                                        "EXPLICIT_SINGLE_EXPERIMENT"):
                stage.trusted_local()

    def test_no_dispatcher_registration_or_unattended_execution(self):
        source = (ROOT / "pl/hil/path2_f1b_minimal_stage.py").read_text()
        self.assertIn("if __name__ == \"__main__\"", source)
        self.assertNotIn("paramiko", source)
        self.assertNotIn("ssh ", source)
        self.assertNotIn("auto_run", source)
        integration = (ROOT / "scripts/plasma_path2_runtime_integration.py").read_text()
        self.assertIn("PATH2_LIVE_PROVIDER_NOT_REGISTERED", integration)


if __name__ == "__main__":
    unittest.main()

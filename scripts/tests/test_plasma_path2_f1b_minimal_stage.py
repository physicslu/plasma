#!/usr/bin/env python3
"""Host-only repeatable F1-B stage tests. Fake device; never touch /dev/mem."""
from __future__ import annotations

from contextlib import ExitStack, nullcontext
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from pl.hil import f1b
from pl.hil import path2_f1b_minimal_stage as stage
from pl.hil import path2_f1b_dev_risk as risk
from pl.hil.swd04 import one_shot


class FakeTarget:
    def __init__(self):
        self.boot = "test-boot-very-long-id"
        self.image = "base.bin"
        self.writes = []
        self.reads = 0
        self.fail_load = False
        self.fail_restore = False
        self.fail_child = False

    def exclusive(self):
        return nullcontext()

    def report(self, port, expected):
        if expected != self.image:
            raise stage.LiveStageDenied("MANAGER_LAST_LOAD_CHANGED")
        return {"site": 1, "target_boot_id": self.boot,
                "expected_manager_firmware": expected,
                "axi_isolation": "UNPROVEN_ACCEPTED_FOR_ONE_DEVELOPMENT_EXPERIMENT",
                "development_exception": risk.WAIVER}

    def manager_write(self, image):
        self.writes.append(image)
        if image == stage.CANDIDATE.name and self.fail_load:
            raise RuntimeError("INJECTED_LOAD_ERROR")
        if image == "base.bin" and self.fail_restore:
            raise RuntimeError("INJECTED_RESTORE_ERROR")
        self.image = image

    def run_child(self, cmd):
        self.reads += 1
        if self.fail_child:
            raise RuntimeError("INJECTED_SIGBUS")
        assert cmd[1:] == ["-m", "pl.hil.path2_f1b_minimal_stage",
                            "--identity-child"]
        one_shot.record_json(stage.CHILD, {
            "observed": {str(k): v for k, v in f1b.IDENTITY.items()}})


class RepeatableStageTests(unittest.TestCase):
    def setUp(self):
        self.t = tempfile.TemporaryDirectory()
        self.addCleanup(self.t.cleanup)
        self.target = FakeTarget()
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        root = Path(self.t.name)
        self.stack.enter_context(patch.object(stage, "STATE", root / "state.json"))
        self.stack.enter_context(patch.object(stage, "CHILD", root / "child.json"))
        self.stack.enter_context(patch.object(stage, "trusted_local"))
        self.stack.enter_context(patch.object(stage, "_state_file_trusted"))
        self.stack.enter_context(patch.object(stage.guard, "RootZ2TargetPort",
                                              return_value=self.target))
        self.stack.enter_context(patch.object(stage, "live_report",
                                              side_effect=self.target.report))
        self.stack.enter_context(patch.object(one_shot, "manager_write",
                                              side_effect=self.target.manager_write))
        self.stack.enter_context(patch.object(one_shot, "run_child",
                                              side_effect=self.target.run_child))
        self.stack.enter_context(patch.object(one_shot, "protected"))

    def state(self):
        return stage.read_state()

    def test_independently_triggered_repeatable_full_lifecycle(self):
        first = stage.run("download")
        self.assertEqual(first["result"], "LOADED_AND_HELD")
        self.assertIs(first["auto_test"], False)
        self.assertEqual(self.target.writes, [stage.CANDIDATE.name])
        # A deliberate second Download in the same session is permitted.
        second = stage.run("download")
        self.assertEqual(second["download_count"], 2)
        self.assertEqual(first["lease_id"], second["lease_id"])
        self.assertEqual(self.target.writes.count(stage.CANDIDATE.name), 2)
        # Testing may run repeatedly; no automatic next-stage selection.
        self.assertEqual(stage.run("test")["result"], "IDENTITY_PASS")
        read2 = stage.run("test")
        self.assertEqual(read2["test_count"], 2)
        self.assertEqual(self.target.reads, 2)
        self.assertEqual(len(self.target.writes), 2)
        self.assertEqual(stage.run("restore")["result"], "RESTORED_VERIFIED")
        self.assertEqual(stage.run("restore")["result"], "ALREADY_RESTORED")
        self.assertEqual(self.target.writes.count("base.bin"), 1)
        third = stage.run("download")
        self.assertEqual(third["download_count"], 3)
        self.assertEqual(third["lease_id"], first["lease_id"])
        self.assertEqual(stage.run("test")["test_count"], 3)
        self.assertEqual(stage.run("restore")["restore_count"], 2)
        self.assertEqual(self.state()["status"], "BASE")

    def test_no_prior_load_denies_readonly_testing_and_restore(self):
        for command in ("test", "restore"):
            with self.assertRaisesRegex(stage.LiveStageDenied,
                                        "DOWNLOAD_REQUIRED_BEFORE"):
                stage.run(command)
        self.assertEqual(self.target.writes, [])

    def test_restore_after_download_without_testing_is_manual_and_valid(self):
        stage.run("download")
        out = stage.run("restore")
        self.assertEqual(out["result"], "RESTORED_VERIFIED")
        self.assertEqual(self.target.writes,
                         [stage.CANDIDATE.name, "base.bin"])

    def test_failed_download_sets_unknown_without_blind_retry(self):
        self.target.fail_load = True
        with self.assertRaisesRegex(RuntimeError, "INJECTED_LOAD"):
            stage.run("download")
        self.assertEqual(self.state()["status"], "UNKNOWN")
        self.target.fail_load = False
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "UNCERTAIN_PRIOR_OPERATION"):
            stage.run("download")
        self.assertEqual(len(self.target.writes), 1)

    def test_failed_test_blocks_restore_without_blind_reload(self):
        stage.run("download")
        self.target.fail_child = True
        with self.assertRaisesRegex(RuntimeError, "INJECTED_SIGBUS"):
            stage.run("test")
        self.assertEqual(self.state()["status"], "UNKNOWN")
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "UNCERTAIN_PRIOR_OPERATION"):
            stage.run("restore")
        self.assertEqual(self.target.writes, [stage.CANDIDATE.name])

    def test_restore_error_forbids_blind_repeat(self):
        stage.run("download")
        self.target.fail_restore = True
        with self.assertRaisesRegex(RuntimeError, "INJECTED_RESTORE"):
            stage.run("restore")
        self.assertEqual(self.state()["status"], "UNKNOWN")
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "UNCERTAIN_PRIOR_OPERATION"):
            stage.run("restore")
        self.assertEqual(self.target.writes.count("base.bin"), 1)

    def test_loaded_manager_and_boot_are_refreshed_each_trigger(self):
        stage.run("download")
        self.target.image = "base.bin"
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "MANAGER_LAST_LOAD_CHANGED"):
            stage.run("test")
        self.target.image = stage.CANDIDATE.name
        self.target.boot = "different-boot-long-id"
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "BOOT_CHANGED_MANUAL_REVIEW"):
            stage.run("test")
        self.assertEqual(self.target.reads, 0)

    def test_state_persists_across_restarts_and_is_not_one_use(self):
        first = stage.run("download")
        self.assertTrue(stage.STATE.exists())
        loaded = json.loads(stage.STATE.read_text())
        self.assertEqual(loaded["status"], "F1B")
        self.assertEqual(loaded["session_id"], first["lease_id"])
        self.assertEqual(stage.run("test")["test_count"], 1)
        self.assertEqual(stage.run("restore")["result"], "RESTORED_VERIFIED")
        self.assertEqual(stage.run("download")["download_count"], 2)
        self.assertEqual(first["lease_id"], self.state()["session_id"])

    def test_unfinished_operation_after_crash_is_unknown(self):
        stage.run("download")
        record = self.state()
        record["status"] = "RESTORE_IN_FLIGHT"
        stage.write_state(record)
        with self.assertRaisesRegex(stage.LiveStageDenied,
                                    "UNCERTAIN_PRIOR_OPERATION"):
            stage.run("restore")
        self.assertEqual(self.target.writes, [stage.CANDIDATE.name])

    def test_abnormal_arm_runtime_denied_before_hardware(self):
        stage.native_runtime_preflight(
            version=(3, 12, 13), machine="armv7l", endian="little",
            executable="/opt/plasma/python/3.12.13/bin/python3")
        for change in ({"version": (3, 11, 0)}, {"machine": "x86_64"},
                       {"endian": "big"}, {"executable": "/usr/bin/python3"}):
            args = {"version": (3, 12, 13), "machine": "armv7l",
                    "endian": "little",
                    "executable": "/opt/plasma/python/3.12.13/bin/python3"}
            with self.assertRaisesRegex(stage.LiveStageDenied,
                                        "NATIVE_ARMV7_PYTHON_RUNTIME_REQUIRED"):
                stage.native_runtime_preflight(**(args | change))
        self.assertEqual(self.target.writes, [])

    def test_root_and_explicit_waiver_enforced(self):
        with patch.object(stage, "trusted_local", wraps=None) as gate:
            gate.side_effect = stage.LiveStageDenied("ROOT_REQUIRED")
            with self.assertRaisesRegex(stage.LiveStageDenied, "ROOT_REQUIRED"):
                stage.run("download")
        self.assertFalse(stage.STATE.exists())

    def test_no_arbitrary_stage_or_auto_chain_or_dispatch_registration(self):
        for stage_name in ("build", "download+test", "download;exit", ""):
            with self.assertRaisesRegex(stage.LiveStageDenied,
                                        "STAGE_NOT_ALLOWLISTED"):
                stage.run(stage_name)
        self.assertFalse(stage.STATE.exists())
        source = (ROOT / "pl/hil/path2_f1b_minimal_stage.py").read_text()
        self.assertNotIn("paramiko", source)
        self.assertNotIn("auto_run", source)
        integration = (ROOT / "scripts/plasma_path2_runtime_integration.py").read_text()
        self.assertIn("PATH2_LIVE_PROVIDER_NOT_REGISTERED", integration)


if __name__ == "__main__":
    unittest.main()

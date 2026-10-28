"""Host-only tests for SWPC A/B burn-in orchestration.

All OpenOCD, Z2, UART, Flash, Reset and credentials are mocked.
"""
import argparse
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
import pty
import termios
import time
from types import SimpleNamespace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[3] / "scripts/plasma_ab_burn_in.py"
spec = importlib.util.spec_from_file_location("plasma_ab_burn_in", SCRIPT)
app = importlib.util.module_from_spec(spec)
spec.loader.exec_module(app)


class ABOrchestrationTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix="plasma-ab-host-")
        self.addCleanup(temp.cleanup)
        self.path = Path(temp.name)
        self.args = argparse.Namespace(
            cycles=2, port="/dev/ttyACM0", frames=4, cdc_timeout=25.0,
            stop_file=str(self.path / "operator-stop"),
            output=str(self.path / "runs"),
        )

    def fake_engine(self, operation, image=None):
        receipt = {
            "operation": operation, "result": "PASS",
            "openocd_exit": 0, "bridge_exit": 0,
            "socket_released": True, "no_auto_retry": True,
            "no_reset_no_retry": True, "no_flash_write": True,
        }
        if operation == "preflight":
            receipt["hw_action"] = "NONE"
        if image:
            receipt.update({"image_sha256": image["sha256"],
                            "image_bytes": image["size"],
                            "readback_sha256": image["sha256"]})
        return {"receipt": receipt, "exit_code": 0, "pass": True,
                "elapsed_s": 0.25, "log": "mock-log"}

    def test_cycle_count_is_pairs_not_program_attempts(self):
        self.assertEqual(app.plan(1), ["v0.1", "v0.2"])
        self.assertEqual(app.plan(3), ["v0.1", "v0.2"] * 3)
        for n in (0, -1, 1001):
            with self.assertRaises(ValueError):
                app.plan(n)

    def test_receipt_validation_is_not_just_exit_zero(self):
        img = app.IMAGES["v0.1"]
        okay = self.fake_engine("program", img)["receipt"]
        okay["no_flash_write"] = False
        self.assertTrue(app.valid_receipt("program", okay, img))
        for mut in (
            {"readback_sha256": "0" * 64},
            {"openocd_exit": 1},
            {"bridge_exit": -15},
            {"socket_released": False},
            {"result": "NOT_RUN"},
            {"no_auto_retry": False},
            {"image_bytes": 123},
        ):
            receipt = {**okay, **mut}
            with self.subTest(mut=mut):
                self.assertFalse(app.valid_receipt("program", receipt, img))
        self.assertFalse(app.valid_receipt("reset-run", okay))
        self.assertFalse(app.valid_receipt("program", {"result": "PASS"}, img))
        self.assertFalse(app.valid_receipt("preflight",
                            {"result": "PASS", "operation": "preflight",
                             "hw_action": "NONE"}, img))
        self.assertEqual(app.parse_receipt("log\n" + json.dumps(okay)), okay)
        self.assertEqual(app.parse_receipt("not json")["result"], "FAIL")

    def test_successful_two_cycle_run_program_reset_and_cdc_in_order(self):
        ops = []
        runner = app.BurnIn(self.args)

        def engine(operation, image=None):
            ops.append((operation, image["version"] if image else None))
            return self.fake_engine(operation, image)

        def cdc(port, version, period, frames, timeout):
            ops.append(("cdc", version))
            self.assertEqual(port, "/dev/ttyACM0")
            self.assertEqual(period, 500 if version == "0.1" else 1000)
            return {"result": "PASS", "version": version}

        with patch.object(runner, "run_engine", side_effect=engine), \
             patch.object(app, "verify_cdc", side_effect=cdc), \
             patch.object(app.signal, "signal"), \
             redirect_stdout(io.StringIO()):
            exit_code = runner.run()
        self.assertEqual(exit_code, 0)
        self.assertEqual(runner.passed, 4)
        self.assertEqual(ops, [
            ("preflight", "0.1"), ("preflight", "0.2"),
            ("program", "0.1"), ("reset-run", None), ("cdc", "0.1"),
            ("program", "0.2"), ("reset-run", None), ("cdc", "0.2"),
            ("program", "0.1"), ("reset-run", None), ("cdc", "0.1"),
            ("program", "0.2"), ("reset-run", None), ("cdc", "0.2"),
        ])
        self.assertIn('"stage": "COMPLETE"', runner.status_file.read_text())
        events = [json.loads(v) for v in runner.record.read_text().splitlines()]
        self.assertEqual(sum(v["stage"] == "ATTEMPT_PASS" for v in events), 4)

    def test_flash_failure_diagnoses_without_reset_or_retry(self):
        runner = app.BurnIn(self.args)
        ops = []
        def engine(operation, image=None):
            ops.append(operation)
            if operation == "program":
                return {"receipt": {"result": "FAIL", "operation": "program",
                                    "socket_released": True,
                                    "evidence_directory": "/mock/z2/evidence"},
                        "exit_code": 1, "pass": False}
            return self.fake_engine(operation, image)
        with patch.object(runner, "run_engine", side_effect=engine), \
             patch.object(app, "verify_cdc", side_effect=AssertionError("CDC forbidden")), \
             patch.object(app.signal, "signal"), \
             redirect_stdout(io.StringIO()):
            result = runner.run()
        self.assertEqual(result, 1)
        self.assertEqual(ops, ["preflight", "preflight", "program", "register-read"])
        self.assertEqual(runner.failed, 1)
        self.assertEqual(runner.passed, 0)
        self.assertIn('"stage": "DIAG_PASS"', runner.status_file.read_text())

    def test_unreleased_owner_failure_fails_closed_no_reconnect(self):
        runner = app.BurnIn(self.args)
        ops = []
        def engine(operation, image=None):
            ops.append(operation)
            if operation == "program":
                return {"receipt": {"result": "FAIL", "operation": "program",
                                    "socket_released": False},
                        "exit_code": 1, "pass": False}
            return self.fake_engine(operation, image)
        with patch.object(runner, "run_engine", side_effect=engine), \
             patch.object(app.signal, "signal"), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(runner.run(), 1)
        self.assertEqual(ops, ["preflight", "preflight", "program"])
        self.assertIn("DIAG_NOT_RUN", runner.status_file.read_text())

    def test_cdc_failure_is_distinct_and_captures_read_only_registers(self):
        runner = app.BurnIn(self.args)
        ops = []
        def engine(operation, image=None):
            ops.append(operation)
            return self.fake_engine(operation, image)
        with patch.object(runner, "run_engine", side_effect=engine), \
             patch.object(app, "verify_cdc",
                          return_value={"result": "FAIL", "reason": "CDC_TIMEOUT"}), \
             patch.object(app.signal, "signal"), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(runner.run(), 1)
        self.assertEqual(ops, ["preflight", "preflight",
                               "program", "reset-run", "register-read"])
        self.assertEqual(runner.failed, 1)
        self.assertEqual(runner.passed, 0)

    def test_operator_stop_file_finishes_current_attempt_first(self):
        runner = app.BurnIn(self.args)
        ops = []
        def engine(operation, image=None):
            ops.append(operation)
            return self.fake_engine(operation, image)
        def cdc(*_args):
            Path(self.args.stop_file).touch()
            return {"result": "PASS"}
        with patch.object(runner, "run_engine", side_effect=engine), \
             patch.object(app, "verify_cdc", side_effect=cdc), \
             patch.object(app.signal, "signal"), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(runner.run(), 130)
        self.assertEqual(runner.passed, 1)
        self.assertEqual(ops, ["preflight", "preflight", "program", "reset-run"])
        self.assertIn("STOPPED", runner.status_file.read_text())

    def test_stale_stop_file_blocks_all_hardware_actions(self):
        Path(self.args.stop_file).touch()
        runner = app.BurnIn(self.args)
        with patch.object(runner, "run_engine",
                          side_effect=AssertionError("No hardware")), \
             patch.object(app.signal, "signal"), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(runner.run(), 2)



class ForegroundStopAndEvidenceTests(unittest.TestCase):
    """Host-only pseudo-TTY tests: no actual SWPC, Z2 or serial device."""

    def test_ctrl_q_key_is_consumed_and_terminal_settings_restored(self):
        master, slave = pty.openpty()
        self.addCleanup(os.close, master)
        stream = os.fdopen(slave, "rb", buffering=0, closefd=False)
        self.addCleanup(stream.close)
        self.addCleanup(os.close, slave)
        previous = termios.tcgetattr(slave)
        target = SimpleNamespace(stop_requested=False)
        with patch.object(app.sys, "stdin", stream), \
             redirect_stdout(io.StringIO()):
            with app.ForegroundStopHotkey(target):
                active = termios.tcgetattr(slave)
                self.assertEqual(active[0] & termios.IXON, 0)
                self.assertEqual(active[3] & termios.ICANON, 0)
                os.write(master, b"\x11")
                for _ in range(60):
                    if target.stop_requested:
                        break
                    time.sleep(0.02)
                self.assertTrue(target.stop_requested, "Ctrl+Q must request stop")
        restored = termios.tcgetattr(slave)
        self.assertEqual(restored, previous)

    def test_noninteractive_hotkey_noop_and_signal_fallback_preserved(self):
        target = SimpleNamespace(stop_requested=False)
        stream = io.StringIO()
        with patch.object(app.sys, "stdin", stream):
            with app.ForegroundStopHotkey(target) as key:
                self.assertIsNone(key.fd)
        self.assertFalse(target.stop_requested)

    def test_same_session_partial_registers_are_preserved_without_reattach(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            args = argparse.Namespace(
                cycles=2, port="/dev/ttyACM0", frames=4, cdc_timeout=25,
                stop_file=str(root / "operator-stop"), output=str(root / "runs"))
            runner = app.BurnIn(args)
            diagnostic = {"status": "PARTIAL", "source": "SAME_OPENOCD_SESSION",
                          "stage": "PROGRAM",
                          "memory_registers": {"FLASH_SR": "0x00000020"},
                          "core_registers": {},
                          "missing_core": ["pc", "sp", "lr", "xPSR"]}
            failed = {"receipt": {"result": "FAIL", "operation": "program",
                                  "socket_released": True,
                                  "failure_diagnostics": diagnostic},
                      "exit_code": 1, "pass": False}
            with patch.object(runner, "run_engine",
                              side_effect=AssertionError("no new attach allowed")), \
                 redirect_stdout(io.StringIO()):
                runner.capture_failure("v0.1", "PROGRAM_FAIL", failed)
            self.assertIn("DIAG_SAME_SESSION", runner.status_file.read_text())
            self.assertIn('"FLASH_SR": "0x00000020"',
                          runner.record.read_text())

if __name__ == "__main__":
    unittest.main()

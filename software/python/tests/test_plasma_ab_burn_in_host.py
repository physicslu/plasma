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
            readback=False,
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
                            "readback_enabled": self.args.readback and operation == "program",
                            "readback_sha256": image["sha256"] if self.args.readback and operation == "program" else None})
        if operation in ("program", "reset-run"):
            names = (("erase", "program", "verify") +
                     (("readback",) if self.args.readback else ())) if operation == "program" else ("reset",)
            size = image["size"] if image else 0
            erase = (size + 1023) // 1024 * 1024
            receipt["erase_bytes"] = erase
            receipt["performance"] = {
                "schema": "plasma.swd.performance.v1",
                "preflight": {"result": "PASS", "duration_s": 0.1},
                "stages": {name: {"result": "PASS", "duration_s": 0.1,
                                  "bytes": erase if name == "erase" else
                                           (0 if name == "reset" else size)} for name in names},
                "other_duration_s": 0.2,
                "total_duration_s": 0.3 + 0.1 * len(names),
                "counter_reconciliation": {"result": "PASS",
                    "total": {key: 10 for key in ("wire_bytes", "mmio_reads", "mmio_writes",
                                                  "dmb_count_derived", "socket_recv_calls",
                                                  "socket_sendall_calls")},
                    "stages_sum": {key: 8 for key in ("wire_bytes", "mmio_reads", "mmio_writes",
                                                       "dmb_count_derived", "socket_recv_calls",
                                                       "socket_sendall_calls")},
                    "other": {key: 2 for key in ("wire_bytes", "mmio_reads", "mmio_writes",
                                                  "dmb_count_derived", "socket_recv_calls",
                                                  "socket_sendall_calls")}},
            }
            receipt["versions"] = {name: "a" * 64 for name in (
                "engine_sha256", "bridge_session_sha256", "native_python_module_sha256",
                "stage_module_sha256", "rbb_module_sha256", "native_c_sha256",
                "openocd_sha256", "target_cfg_sha256")}
            if operation == "program" and not self.args.readback:
                receipt["performance"]["stages"]["readback"] = {"result": "SKIPPED", "bytes": 0}
        return {"receipt": receipt, "exit_code": 0, "pass": True,
                "elapsed_s": 0.25, "log": "mock-log"}

    def test_cycle_count_is_pairs_not_program_attempts(self):
        self.assertEqual(app.plan(1), ["v0.1", "v0.2"])
        self.assertEqual(app.plan(3), ["v0.1", "v0.2"] * 3)
        self.assertEqual(app.plan(1, "v02-first"), ["v0.2", "v0.1"])
        self.assertEqual(app.plan(3, "v02-first"), ["v0.2", "v0.1"] * 3)
        with self.assertRaisesRegex(ValueError, "order"):
            app.plan(1, "unknown")
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

    def test_opt_in_readback_requires_exact_sha_and_full_stage(self):
        self.args.readback = True
        image = app.IMAGES["v0.2"]
        receipt = self.fake_engine("program", image)["receipt"]
        self.assertTrue(app.valid_receipt("program", receipt, image,
                                          readback_enabled=True))
        self.assertFalse(app.valid_receipt("program", receipt, image))
        receipt["readback_sha256"] = "0" * 64
        self.assertFalse(app.valid_receipt("program", receipt, image,
                                           readback_enabled=True))

    def test_default_fast_rejects_missing_verify_or_forged_skip(self):
        import copy
        image = app.IMAGES["v0.1"]
        good = self.fake_engine("program", image)["receipt"]
        self.assertTrue(app.valid_receipt("program", good, image))
        for mutation in ("missing_verify", "not_skipped", "unexpected_hash", "wrong_mode"):
            bad = copy.deepcopy(good)
            if mutation == "missing_verify":
                bad["performance"]["stages"]["verify"]["result"] = "FAIL"
            elif mutation == "not_skipped":
                bad["performance"]["stages"]["readback"] = {"result": "PASS", "bytes": image["size"]}
            elif mutation == "unexpected_hash":
                bad["readback_sha256"] = image["sha256"]
            else:
                bad["readback_enabled"] = True
            with self.subTest(mutation=mutation):
                self.assertFalse(app.valid_receipt("program", bad, image))

    def test_performance_version_and_counter_mismatch_rejected(self):
        import copy
        image = app.IMAGES["v0.2"]
        original = self.fake_engine("program", image)["receipt"]
        self.assertTrue(app.valid_receipt("program", original, image,
                                          expected_source_sha="a" * 64))
        for change in ("source", "module", "counter", "missing_counter", "time"):
            receipt = copy.deepcopy(original)
            if change == "source":
                receipt["versions"]["engine_sha256"] = "b" * 64
            elif change == "module":
                receipt["versions"]["stage_module_sha256"] = "G" * 64
            elif change == "counter":
                receipt["performance"]["counter_reconciliation"]["other"]["wire_bytes"] = 3
            elif change == "missing_counter":
                del receipt["performance"]["counter_reconciliation"]["total"]["mmio_reads"]
            else:
                receipt["performance"]["total_duration_s"] = 999
            with self.subTest(change=change):
                self.assertFalse(app.valid_receipt("program", receipt, image,
                                                   expected_source_sha="a" * 64))

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

    def test_v02_first_respects_each_program_reset_cdc_gate(self):
        self.args.cycles = 1
        self.args.order = "v02-first"
        self.args.frames = 60
        self.args.cdc_timeout = None
        ops = []
        runner = app.BurnIn(self.args)

        def engine(operation, image=None):
            ops.append((operation, image["version"] if image else None))
            return self.fake_engine(operation, image)

        def cdc(port, version, period, frames, timeout):
            ops.append(("cdc", version))
            self.assertEqual(port, "/dev/ttyACM0")
            self.assertEqual(frames, 60)
            self.assertEqual(period, 1000 if version == "0.2" else 500)
            self.assertGreater(timeout, 60 if version == "0.2" else 30)
            return {"result": "PASS", "version": version}

        with patch.object(runner, "run_engine", side_effect=engine), \
             patch.object(app, "verify_cdc", side_effect=cdc), \
             patch.object(app.signal, "signal"), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(runner.run(), 0)
        self.assertEqual(ops, [
            ("preflight", "0.2"), ("preflight", "0.1"),
            ("program", "0.2"), ("reset-run", None), ("cdc", "0.2"),
            ("program", "0.1"), ("reset-run", None), ("cdc", "0.1"),
        ])
        self.assertEqual(runner.passed, 2)
        self.assertIn("order=v02-first", runner.log.read_text())

    def test_v02_first_failure_never_attempts_v01(self):
        self.args.cycles = 1
        self.args.order = "v02-first"
        runner = app.BurnIn(self.args)
        ops = []

        def engine(operation, image=None):
            ops.append((operation, image["version"] if image else None))
            if operation == "program":
                return {"receipt": {"result": "FAIL",
                                    "operation": "program",
                                    "failure_diagnostics": {
                                        "status": "COMPLETE",
                                        "source": "SAME_OPENOCD_SESSION",
                                        "stage": "PROGRAM"}},
                        "exit_code": 1, "pass": False}
            return self.fake_engine(operation, image)

        with patch.object(runner, "run_engine", side_effect=engine), \
             patch.object(app, "verify_cdc", side_effect=AssertionError("No CDC")), \
             patch.object(app.signal, "signal"), \
             redirect_stdout(io.StringIO()):
            self.assertEqual(runner.run(), 1)
        self.assertEqual(ops, [
            ("preflight", "0.2"), ("preflight", "0.1"),
            ("program", "0.2"),
        ])
        self.assertEqual(runner.passed, 0)
        self.assertEqual(runner.failed, 1)
        self.assertIn("DIAG_SAME_SESSION", runner.log.read_text())

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




class CDCFrameBudgetTests(unittest.TestCase):
    """Simulated CDC TTY transactions: no connected serial device or hardware."""

    def replay(self, lines, *, version="0.1", period_ms=500, frames=60):
        payload = "".join(lines).encode("ascii")
        chunks = [payload[i:i + 4096] for i in range(0, len(payload), 4096)]
        now = 0.0

        def clock():
            nonlocal now
            now += 0.25
            return now

        def readable(*_):
            return ([77], [], []) if chunks else ([], [], [])

        def read_chunk(*_):
            return chunks.pop(0)

        with patch.object(app.Path, "exists", return_value=True), \
             patch.object(app.Path, "is_char_device", return_value=True), \
             patch.object(app.subprocess, "run", return_value=SimpleNamespace(returncode=1)), \
             patch.object(app.os, "open", return_value=77), \
             patch.object(app.os, "read", side_effect=read_chunk), \
             patch.object(app.os, "close"), \
             patch.object(app.fcntl, "ioctl"), \
             patch.object(app.tty, "setraw"), \
             patch.object(app.termios, "tcgetattr", return_value=[0, 0, 0, 0, 0, 0, []]), \
             patch.object(app.termios, "tcsetattr"), \
             patch.object(app.select, "select", side_effect=readable), \
             patch.object(app.time, "monotonic", side_effect=clock):
            return app.verify_cdc("/dev/ttyACM0", version, period_ms, frames, 25.0)

    @staticmethod
    def heartbeats(n, *, version="0.1", period_ms=500, skip_seq_at=None):
        lines = []
        for i in range(1, n + 1):
            seq = i + (1 if skip_seq_at is not None and i >= skip_seq_at else 0)
            lines.append(f"HB version={version} seq={seq} uptime_ms={i * period_ms}\r\n")
        return lines

    def test_sixty_consecutive_frames_pass(self):
        result = self.replay(self.heartbeats(60))
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(len(result["frames"]), 60)
        self.assertEqual(result["frames"][-1]["seq"], 60)

    def test_fifty_nine_frames_do_not_pass(self):
        result = self.replay(self.heartbeats(59))
        self.assertEqual(result["result"], "FAIL")
        self.assertEqual(len(result["last_consecutive_samples"]), 59)

    def test_thousand_frame_upper_boundary(self):
        result = self.replay(self.heartbeats(1000, version="0.2", period_ms=1000),
                             version="0.2", period_ms=1000, frames=1000)
        self.assertEqual(result["result"], "PASS")
        self.assertEqual(len(result["frames"]), 1000)

    def test_wrong_version_and_sequence_gap_never_false_pass(self):
        wrong = self.replay(self.heartbeats(60, version="0.2"))
        self.assertEqual(wrong["result"], "FAIL")
        self.assertTrue(wrong["seen_versions"])
        gap = self.replay(self.heartbeats(60, skip_seq_at=31))
        self.assertEqual(gap["result"], "FAIL")
        self.assertLess(len(gap["last_consecutive_samples"]), 60)

    def test_adaptive_timeout_and_explicit_minimum(self):
        self.assertGreater(app.cdc_timeout_for(60, 500, None), 30)
        self.assertGreater(app.cdc_timeout_for(60, 1000, None), 60)
        self.assertGreater(app.cdc_timeout_for(1000, 1000, None), 1000)
        self.assertLessEqual(app.cdc_timeout_for(1000, 1000, None), 1800)
        self.assertEqual(app.cdc_timeout_for(60, 1000, 120.0), 120.0)
        with self.assertRaisesRegex(ValueError, "too short"):
            app.cdc_timeout_for(1000, 1000, 120.0)

    def test_cli_accepts_1000_defaults_to_60_and_rejects_invalid_before_hardware(self):
        with patch.object(app, "BurnIn") as runner, patch.object(app.os, "umask"):
            runner.return_value.run.return_value = 0
            self.assertEqual(app.main(["--cycles", "1"]), 0)
            self.assertEqual(runner.call_args.args[0].frames, 60)
            self.assertFalse(runner.call_args.args[0].readback)
            self.assertIsNone(runner.call_args.args[0].cdc_timeout)
            self.assertEqual(app.main(["--cycles", "1", "--readback"]), 0)
            self.assertTrue(runner.call_args.args[0].readback)
            self.assertEqual(app.main(["--cycles", "1", "--frames", "1000"]), 0)
            self.assertEqual(runner.call_args.args[0].frames, 1000)
            self.assertEqual(app.main(["--cycles", "1", "--order", "v02-first"]), 0)
            self.assertEqual(runner.call_args.args[0].order, "v02-first")
        for flags in (
            ["--order", "v03-first"],
            ["--frames", "1001"],
            ["--frames", "2"],
            ["--frames", "1000", "--cdc-timeout", "120"],
            ["--frames", "60", "--cdc-timeout", "1801"],
        ):
            with self.subTest(flags=flags), redirect_stdout(io.StringIO()), \
                 patch("sys.stderr", new_callable=io.StringIO), \
                 self.assertRaises(SystemExit) as caught:
                app.main(["--cycles", "1", *flags])
            self.assertEqual(caught.exception.code, 2)



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

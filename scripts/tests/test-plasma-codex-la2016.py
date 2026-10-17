#!/usr/bin/env python3
"""Host-only LA2016 real-Agent capability tests. Never opens USB or the Z2."""
from __future__ import annotations
import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import zipfile

MODULE = Path(__file__).resolve().parents[1] / "plasma-codex-la2016.py"
SPEC = importlib.util.spec_from_file_location("plasma_codex_la2016", MODULE)
assert SPEC and SPEC.loader
subject = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(subject)

def good_request():
    return {
        "schema": subject.SCHEMA,
        "operation": "execute_bounded_la2016_loopback",
        "fixture": "KINGST_PWM1_TO_SAME_KINGST_CH0",
        "cases": [{"frequency_hz": 1000, "duty_percent": 50},
                  {"frequency_hz": 2000, "duty_percent": 25}],
        "shutdown_check": "CAPTURE_LOW",
    }

def archive(path: Path, values: list[int], *, probe: str = "CH0") -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as file:
        file.writestr("metadata", "[global]\n"
                      "[device 1]\n"
                      "capturefile=logic-1\n"
                      "unitsize=2\n"
                      "samplerate=1 MHz\n"
                      + "probe1=" + probe + "\n")
        file.writestr("logic-1-1", b"".join(struct.pack("<H", value) for value in values))


class RealAgentLA2016Contract(unittest.TestCase):
    def test_allowed_request(self):
        self.assertEqual(subject.validate_agent_request(good_request()), good_request())

    def test_untrusted_requests_denied(self):
        changes = (
            ("operation", "run_shell"),
            ("fixture", "Z2_GPIO"),
            ("shutdown_check", "SKIP"),
            ("schema", "wrong.schema"),
            ("cases", [{"frequency_hz": 1000, "duty_percent": 50}]),
            ("cases", [{"frequency_hz": 1000, "duty_percent": 50},
                       {"frequency_hz": 2000, "duty_percent": 50}]),
            ("cases", [{"frequency_hz": True, "duty_percent": 50},
                       {"frequency_hz": 2000, "duty_percent": 25}]),
            ("cases", [{"frequency_hz": 1000, "duty_percent": 50},
                       {"frequency_hz": 2000, "duty_percent": 25},
                       {"frequency_hz": 5000, "duty_percent": 50}]),
        )
        for key, val in changes:
            request = good_request()
            request[key] = val
            with self.assertRaises(ValueError, msg=str((key, val))):
                subject.validate_agent_request(request)
        request = good_request()
        request["argv"] = "--driver other"
        with self.assertRaises(ValueError):
            subject.validate_agent_request(request)
        for bad in ([], "request", None, True):
            with self.assertRaises(ValueError):
                subject.validate_agent_request(bad)

    def test_agent_mount_scope_never_exposes_usb_and_cannot_forge_shutdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            (out / "agent").mkdir()
            with patch.object(subject.shutil, "which", side_effect=lambda x: {
                "bwrap": "/usr/bin/bwrap", "codex": "/usr/bin/codex"}.get(x)):
                with patch.object(subject.pwd, "getpwuid") as mock_pwd:
                    mock_pwd.return_value.pw_dir = tmp
                    (out / ".codex").mkdir()
                    args = subject.sandbox_args(out)
            self.assertIn("--dev", args)
            self.assertEqual(args[args.index("--dev") + 1], "/dev")
            self.assertIn("--ro-bind", args)
            self.assertIn("--bind", args)
            self.assertIn(str(out / "agent"), args)
            bind_targets = [args[i+2] for i, x in enumerate(args) if x == "--bind"]
            self.assertNotIn(str(out), bind_targets)
            self.assertIn(str(out / "agent"), bind_targets)
            self.assertNotIn(str(out / "pwm-off-confirmed"), " ".join(args))
            self.assertIn("read-only", args)
            self.assertEqual(args[args.index("--output-last-message")+1],
                             str(out / "agent" / "agent-request.json"))

    def test_matching_real_archive_layout_both_profiles(self):
        with tempfile.TemporaryDirectory() as temp:
            for freq, duty in subject.PROFILE:
                period = 1_000_000 // freq
                high = period * duty // 100
                values = ([0] * (period - high) + [1] * high) * 55
                path = Path(temp) / (str(freq) + ".sr")
                archive(path, values)
                recovered = subject.read_ch0(path)
                self.assertEqual(recovered, values)
                result, edges = subject.measure(recovered, freq, duty)
                self.assertEqual(result["result"], "PASS")
                self.assertEqual(result["requested_frequency_hz"], freq)
                self.assertEqual(result["measured_frequency_hz"], freq)
                self.assertEqual(result["measured_duty_percent"], duty)
                self.assertGreater(len(edges), 80)
                pathcsv = Path(temp) / (str(freq) + ".csv")
                subject.waveform_edges(pathcsv, recovered, edges)
                self.assertEqual(pathcsv.read_text().splitlines()[0], "sample_index,CH0")
                self.assertEqual(subject.sha256(path).count(""), 65)

    def test_invalid_signal_and_off_fail_closed(self):
        with self.assertRaises(ValueError):
            subject.measure([0] * 22000, 1000, 50)
        with self.assertRaises(ValueError):
            subject.measure(([0] * 300 + [1] * 700) * 30, 1000, 50)
        with self.assertRaises(ValueError):
            subject.off_low([0] * 19999)
        with self.assertRaises(ValueError):
            subject.off_low([0] * 25000 + [1])
        self.assertEqual(subject.off_low([0] * 22000), 22000)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "bad.sr"
            archive(path, [0] * 25000, probe="CH1")
            with self.assertRaises(ValueError):
                subject.read_ch0(path)

    def test_unapproved_pwm_cannot_call_sigrok(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(subject, "sigrok", side_effect=AssertionError):
                with self.assertRaises(ValueError):
                    subject.capture("1.2", Path(temp) / "unsafe.sr", freq=3000, duty=50)
            with patch.object(subject, "sigrok") as invoke:
                subject.turn_off("1.2")
                self.assertEqual(invoke.call_args.args[1:],
                                 ("--config", "channel_group=PWM1:enabled=off", "--set"))

    def test_hard_deadline_watchdog_attempts_off(self):
        with tempfile.TemporaryDirectory() as temp:
            out = Path(temp)
            with patch.object(subject, "worker_identity"):
                with patch.object(subject.time, "sleep") as sleeper:
                    with patch.object(subject, "trusted_appimage"):
                        with patch.object(subject, "turn_off") as off:
                            self.assertEqual(subject.watchdog(out, "1.2"), 0)
                            sleeper.assert_called_once_with(125)
                            off.assert_called_once_with("1.2")
                            self.assertTrue((out / "watchdog-armed").exists())
                            (out / "watchdog-armed").unlink()
                            (out / "pwm-off-confirmed").touch()
                            self.assertEqual(subject.watchdog(out, "1.2"), 0)
                            self.assertEqual(off.call_count, 1)


if __name__ == "__main__":
    unittest.main()

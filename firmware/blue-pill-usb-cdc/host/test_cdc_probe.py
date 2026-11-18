import contextlib
import io
import sys
import subprocess
from pathlib import Path
import types
import unittest
from unittest.mock import patch

from cdc_probe import HeartbeatMonitor, ReceptionWindow, is_firmware_id, parse_args, run_live


class FakeClock:
    def __init__(self):
        self.current = 0.0

    def monotonic(self):
        return self.current

    def sleep(self, seconds):
        self.current += seconds


class FakeSerial:
    def __init__(self, clock, events):
        self.clock = clock
        self.events = iter(events)
        self.writes = []
        self.closes = 0
        self.opens = 0

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def readline(self):
        try:
            timestamp, line = next(self.events)
        except StopIteration:
            self.clock.current += 1.0
            return b""
        self.clock.current = max(self.clock.current, timestamp)
        return (line + "\r\n").encode("ascii")

    def write(self, data):
        self.writes.append(data)

    def close(self):
        self.closes += 1

    def open(self):
        self.opens += 1


class MonitorTests(unittest.TestCase):
    def test_sequence_interval_uptime_and_interruption(self):
        monitor = HeartbeatMonitor()
        self.assertTrue(monitor.observe("HB version=0.1 seq=1 uptime_ms=500", 1.0))
        self.assertTrue(monitor.observe("HB version=0.1 seq=2 uptime_ms=1000", 1.5))
        self.assertTrue(monitor.observe("HB version=0.1 seq=5 uptime_ms=2500", 3.0,
                                        host_port_interrupted=True))
        self.assertTrue(monitor.observe("HB version=0.1 seq=6 uptime_ms=3000", 3.5))
        self.assertEqual(monitor.samples, 4)

    def test_rejects_sequence_interval_and_uptime_failures(self):
        for bad_line, bad_time in (
            ("HB version=0.1 seq=1 uptime_ms=1000", 1.5),
            ("HB version=0.1 seq=2 uptime_ms=400", 1.5),
            ("HB version=0.1 seq=2 uptime_ms=1000", 2.0),
            ("HB version=0.1 seq=3 uptime_ms=1000", 1.5),
        ):
            monitor = HeartbeatMonitor()
            monitor.observe("HB version=0.1 seq=1 uptime_ms=500", 1.0)
            with self.assertRaises(AssertionError):
                monitor.observe(bad_line, bad_time)

    def test_ignores_commands_and_other_versions(self):
        monitor = HeartbeatMonitor()
        self.assertFalse(monitor.observe("ID PLASMA_BLUE_PILL_CDC/0.1", 1.0))
        self.assertFalse(monitor.observe("HB version=0.2 seq=1 uptime_ms=500", 1.0))

    def test_firmware_identity(self):
        self.assertTrue(is_firmware_id("ID PLASMA_BLUE_PILL_CDC/0.1"))
        self.assertFalse(is_firmware_id("ID OTHER/0.1"))

    def test_optimized_python_refuses_before_importing_serial(self):
        result = subprocess.run(
            [sys.executable, "-O", "-c",
             "from cdc_probe import run_live; run_live('never-opened', 60, .2)"],
            cwd=Path(__file__).parent, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("probe requires assertions", result.stderr)

    def test_nonfinite_options_rejected(self):
        for flag, value in (("--duration", "nan"), ("--duration", "inf"),
                            ("--tolerance", "nan"), ("--host-port-pause-seconds", "inf")):
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parse_args(["--port", "unused", flag, value])

    def test_host_port_pause_is_opt_in(self):
        self.assertEqual(parse_args(["--port", "/dev/fake"]).host_port_pause_seconds, 0.0)
        self.assertEqual(parse_args(["--port", "/dev/fake", "--host-port-pause-seconds", "0.6"])
                         .host_port_pause_seconds, 0.6)

    def fake_run(self, events, pause_seconds=0.0, duration=2.6, version="0.1"):
        clock = FakeClock()
        serial = FakeSerial(clock, events)
        output = io.StringIO()
        with patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=lambda *_args, **_kw: serial)}), \
             patch("cdc_probe.time.monotonic", clock.monotonic), \
             patch("cdc_probe.time.sleep", clock.sleep), \
             contextlib.redirect_stdout(output):
            run_live("/dev/fake", duration, 0.2, pause_seconds, version=version)
        return serial, output.getvalue()

    def test_live_loop_prints_each_heartbeat_without_default_pause(self):
        serial, output = self.fake_run([
            (0.5, "HB version=0.1 seq=1 uptime_ms=500"),
            (0.6, "ID PLASMA_BLUE_PILL_CDC/0.1"),
            (1.0, "HB version=0.1 seq=2 uptime_ms=1000"),
            (1.5, "HB version=0.1 seq=3 uptime_ms=1500"),
            (2.0, "HB version=0.1 seq=4 uptime_ms=2000"),
        ])
        self.assertEqual(serial.writes, [b"ID\n"])
        self.assertEqual((serial.closes, serial.opens), (0, 0))
        self.assertEqual(output.count("HB version="), 4)
        self.assertIn("host_port_pause=NOT_RUN; physical_usb_disconnect=NOT_RUN", output)

    def test_opt_in_host_port_pause_allows_only_one_gap(self):
        serial, output = self.fake_run([
            (0.5, "HB version=0.1 seq=1 uptime_ms=500"),
            (0.6, "ID PLASMA_BLUE_PILL_CDC/0.1"),
            (1.0, "HB version=0.1 seq=2 uptime_ms=1000"),
            (2.0, "HB version=0.1 seq=4 uptime_ms=2000"),
            (2.5, "HB version=0.1 seq=5 uptime_ms=2500"),
            (3.0, "HB version=0.1 seq=6 uptime_ms=3000"),
            (3.5, "HB version=0.1 seq=7 uptime_ms=3500"),
            (4.0, "HB version=0.1 seq=8 uptime_ms=4000"),
            (4.5, "HB version=0.1 seq=9 uptime_ms=4500"),
        ], pause_seconds=0.6, duration=5.0)
        self.assertEqual((serial.closes, serial.opens), (1, 1))
        self.assertIn("HOST_PORT_PAUSE:", output)
        self.assertIn("host_port_pause=PASS; physical_usb_disconnect=NOT_RUN", output)

    @staticmethod
    def stream(period=0.5, stop=60.0):
        events = [(0.6, "ID PLASMA_BLUE_PILL_CDC/0.1")]
        n = 1
        while n * period <= stop:
            events.append((n * period,
                           f"HB version=0.1 seq={n} uptime_ms={int(n * period * 1000)}"))
            n += 1
        return sorted(events)

    def test_60s_continuous_coverage_passes(self):
        _, output = self.fake_run(self.stream(), duration=60)
        self.assertIn("PASS: 120 heartbeats", output)

    def test_60s_explicit_pause_passes_with_remaining_coverage(self):
        events = [(t, line) for t, line in self.stream() if t <= 1 or t >= 3.5]
        _, output = self.fake_run(events, pause_seconds=2, duration=60)
        self.assertIn("host_port_pause=PASS", output)

    def test_60s_sparse_but_interval_tolerant_stream_fails_coverage(self):
        with self.assertRaisesRegex(AssertionError, "insufficient heartbeat coverage"):
            self.fake_run(self.stream(period=0.69), duration=60)

    def test_silent_start_and_silent_tail_fail(self):
        with self.assertRaisesRegex(AssertionError, "startup timeout"):
            self.fake_run([], duration=60)
        with self.assertRaisesRegex(AssertionError, "prolonged heartbeat silence"):
            self.fake_run(self.stream(stop=2), duration=60)

    def test_missing_or_wrong_id_fails(self):
        for identity in ("", "ID OTHER/0.1"):
            events = [(t, identity if line.startswith("ID ") else line)
                      for t, line in self.stream()]
            with self.assertRaisesRegex(AssertionError, "ID reply absent"):
                self.fake_run(events, duration=60)

    def test_late_frame_cannot_hide_silence(self):
        window = ReceptionWindow(0, 60)
        window.heartbeat(0.5)
        with self.assertRaisesRegex(AssertionError, "prolonged heartbeat silence"):
            window.heartbeat(2.01)

    def test_startup_and_silence_boundaries(self):
        window = ReceptionWindow(0, 60)
        window.heartbeat(3.0)
        window.check(4.5)
        with self.assertRaisesRegex(AssertionError, "prolonged heartbeat silence"):
            window.check(4.501)
        with self.assertRaisesRegex(AssertionError, "startup timeout"):
            ReceptionWindow(0, 60).heartbeat(3.001)

    def test_pause_is_bounded_and_coverage_still_required(self):
        window = ReceptionWindow(0, 60)
        window.heartbeat(0.5)
        window.host_pause(1, 6)
        window.heartbeat(7.5)
        with self.assertRaisesRegex(AssertionError, "prolonged heartbeat silence"):
            window.check(9.001)
        window = ReceptionWindow(0, 60)
        window.heartbeat(0.5)
        window.host_pause(1, 6)
        with self.assertRaisesRegex(AssertionError, "silence after host-port reopen"):
            window.heartbeat(7.501)
        window.heartbeat(7)
        window.last_at = 60
        window.finish(60, 90)  # floor((60 - 3 - 5 - 1.5) * 2 * .9)
        with self.assertRaisesRegex(AssertionError, "insufficient heartbeat coverage"):
            window.finish(60, 89)

    def test_live_pause_requires_recovery_and_remaining_time(self):
        with self.assertRaisesRegex(AssertionError, "silence after host-port reopen"):
            self.fake_run(self.stream(stop=1), pause_seconds=2, duration=60)
        with self.assertRaisesRegex(AssertionError, "insufficient observation time"):
            self.fake_run(self.stream(stop=1), pause_seconds=59, duration=60)

    def test_v02_monitor_and_version_isolation(self):
        monitor = HeartbeatMonitor(period=1.0, version="0.2")
        self.assertFalse(monitor.observe("HB version=0.1 seq=1 uptime_ms=500", 1.0))
        self.assertTrue(monitor.observe("HB version=0.2 seq=1 uptime_ms=1000", 1.0))
        self.assertTrue(monitor.observe("HB version=0.2 seq=2 uptime_ms=2000", 2.0))
        with self.assertRaisesRegex(AssertionError, "interval"):
            monitor.observe("HB version=0.2 seq=3 uptime_ms=3000", 2.5)
        self.assertTrue(is_firmware_id("ID PLASMA_BLUE_PILL_CDC/0.2", "0.2"))
        self.assertFalse(is_firmware_id("ID PLASMA_BLUE_PILL_CDC/0.1", "0.2"))
        self.assertEqual(parse_args(["--port", "unused", "--version", "0.2"]).version, "0.2")

    def test_v02_live_coverage_and_wrong_id_rejection(self):
        events = [(1.0, "HB version=0.2 seq=1 uptime_ms=1000"),
                  (1.1, "ID PLASMA_BLUE_PILL_CDC/0.2")]
        events.extend((float(n), f"HB version=0.2 seq={n} uptime_ms={1000*n}")
                      for n in range(2, 6))
        _, output = self.fake_run(events, duration=5.5, version="0.2")
        self.assertIn("PASS: 5 heartbeats", output)
        wrong = [(t, "ID PLASMA_BLUE_PILL_CDC/0.1" if line.startswith("ID ") else line)
                 for t, line in events]
        with self.assertRaisesRegex(AssertionError, "ID reply absent"):
            self.fake_run(wrong, duration=5.5, version="0.2")

    def test_live_loop_rejects_uninterrupted_sequence_gap(self):
        with self.assertRaisesRegex(AssertionError, "sequence skipped"):
            self.fake_run([
                (0.5, "HB version=0.1 seq=1 uptime_ms=500"),
                (0.6, "ID PLASMA_BLUE_PILL_CDC/0.1"),
                (1.0, "HB version=0.1 seq=3 uptime_ms=1000"),
            ])


if __name__ == "__main__":
    unittest.main()

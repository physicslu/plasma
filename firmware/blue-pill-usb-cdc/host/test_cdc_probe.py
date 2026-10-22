import contextlib
import io
import sys
import types
import unittest
from unittest.mock import patch

from cdc_probe import HeartbeatMonitor, is_firmware_id, parse_args, run_live


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

    def test_host_port_pause_is_opt_in(self):
        self.assertEqual(parse_args(["--port", "/dev/fake"]).host_port_pause_seconds, 0.0)
        self.assertEqual(parse_args(["--port", "/dev/fake", "--host-port-pause-seconds", "0.6"])
                         .host_port_pause_seconds, 0.6)

    def fake_run(self, events, pause_seconds=0.0, duration=2.6):
        clock = FakeClock()
        serial = FakeSerial(clock, events)
        output = io.StringIO()
        with patch.dict(sys.modules, {"serial": types.SimpleNamespace(Serial=lambda *_args, **_kw: serial)}), \
             patch("cdc_probe.time.monotonic", clock.monotonic), \
             patch("cdc_probe.time.sleep", clock.sleep), \
             contextlib.redirect_stdout(output):
            run_live("/dev/fake", duration, 0.2, pause_seconds)
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
        ], pause_seconds=0.6)
        self.assertEqual((serial.closes, serial.opens), (1, 1))
        self.assertIn("HOST_PORT_PAUSE:", output)
        self.assertIn("host_port_pause=PASS; physical_usb_disconnect=NOT_RUN", output)

    def test_live_loop_rejects_uninterrupted_sequence_gap(self):
        with self.assertRaisesRegex(AssertionError, "sequence skipped"):
            self.fake_run([
                (0.5, "HB version=0.1 seq=1 uptime_ms=500"),
                (0.6, "ID PLASMA_BLUE_PILL_CDC/0.1"),
                (1.0, "HB version=0.1 seq=3 uptime_ms=1000"),
            ])


if __name__ == "__main__":
    unittest.main()

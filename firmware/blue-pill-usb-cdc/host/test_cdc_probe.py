import unittest

from cdc_probe import HeartbeatMonitor, is_firmware_id


class MonitorTests(unittest.TestCase):
    def test_sequence_interval_uptime_and_interruption(self):
        monitor = HeartbeatMonitor()
        self.assertTrue(monitor.observe("HB version=0.1 seq=1 uptime_ms=500", 1.0))
        self.assertTrue(monitor.observe("HB version=0.1 seq=2 uptime_ms=1000", 1.5))
        self.assertTrue(monitor.observe("HB version=0.1 seq=5 uptime_ms=2500", 3.0, interrupted=True))
        self.assertEqual(monitor.samples, 3)

    def test_rejects_sequence_interval_and_uptime_failures(self):
        for bad_line, bad_time in (
            ("HB version=0.1 seq=1 uptime_ms=1000", 1.5),
            ("HB version=0.1 seq=2 uptime_ms=400", 1.5),
            ("HB version=0.1 seq=2 uptime_ms=1000", 2.0),
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


if __name__ == "__main__":
    unittest.main()

"""Host-only stage evidence and private control-socket tests."""
import json
from pathlib import Path
import socket
import tempfile
import unittest

from plasma_interfaces.bluepill_remote_bitbang import SocketCallCounters
from plasma_interfaces.wordport_stage_monitor import StageMonitor, stage_report


class FakePort:
    def __init__(self):
        self.reads = 3
        self.writes = 0

    def counter_snapshot(self):
        return {"mmio_reads": self.reads, "mmio_writes": self.writes}


class StageEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="plasma-stage-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.root.chmod(0o700)

    def test_synchronous_markers_and_counter_reconciliation(self):
        port = FakePort()
        calls = SocketCallCounters()
        path = self.root / "stage.sock"
        evidence = self.root / "events.jsonl"
        with StageMonitor(path, evidence, port, calls):
            for stage in ("ERASE", "PROGRAM", "VERIFY", "READBACK"):
                self._send(path, "BEGIN " + stage)
                port.reads += 2
                port.writes += 4
                calls.recv_called()
                calls.received(5)
                calls.send_called()
                self._send(path, "END " + stage)
        self.assertFalse(path.exists())
        events = [json.loads(line) for line in evidence.read_text().splitlines()]
        report = stage_report(events, 62800, 63488, operation="program")
        self.assertEqual(sum(x["wire_bytes"] for x in report.values()), 20)
        self.assertEqual(sum(x["mmio_reads"] for x in report.values()), 8)
        self.assertEqual(sum(x["mmio_writes"] for x in report.values()), 16)
        self.assertEqual(sum(x["dmb_count_derived"] for x in report.values()), 24)
        self.assertEqual(sum(x["socket_recv_calls"] for x in report.values()), 4)
        self.assertEqual(sum(x["socket_sendall_calls"] for x in report.values()), 4)
        self.assertTrue(all(x["result"] == "PASS" and x["duration_s"] >= 0
                            for x in report.values()))
        self.assertEqual(report["erase"]["bytes"], 63488)
        self.assertEqual(report["readback"]["bytes"], 62800)

    def test_failure_and_interruption_are_not_pass(self):
        port = FakePort()
        calls = SocketCallCounters()
        path = self.root / "stage.sock"
        evidence = self.root / "events.jsonl"
        with StageMonitor(path, evidence, port, calls):
            self._send(path, "BEGIN ERASE")
            self._send(path, "FAIL ERASE")
        events = [json.loads(line) for line in evidence.read_text().splitlines()]
        report = stage_report(events, 18768, 19456, operation="program")
        self.assertEqual(report["erase"]["result"], "FAIL")
        self.assertEqual(report["program"]["result"], "NOT_OBSERVED")
        self.assertEqual(stage_report(events[:1], 18768, 19456,
                                      operation="program")["erase"]["result"], "INTERRUPTED")

    def test_reject_duplicate_or_decreasing_counters(self):
        base = {"stage": "RESET", "edge": "BEGIN", "monotonic_ns": 1,
                "utc_ns": 1, "wire_bytes": 5, "mmio_reads": 3, "mmio_writes": 4,
                "socket_recv_calls": 1, "socket_sendall_calls": 1}
        end = {**base, "edge": "END", "monotonic_ns": 2}
        with self.assertRaises(ValueError):
            stage_report([base, end, end], 0, 0, operation="reset-run")
        with self.assertRaises(ValueError):
            stage_report([base, {**end, "mmio_writes": 3}], 0, 0,
                         operation="reset-run")
        with self.assertRaises(ValueError):
            stage_report([{**base, "monotonic_ns": "1"}], 0, 0,
                         operation="reset-run")

    def test_marker_timeout_does_not_create_pass_event(self):
        port = FakePort()
        calls = SocketCallCounters()
        path = self.root / "stage.sock"
        evidence = self.root / "events.jsonl"
        with StageMonitor(path, evidence, port, calls):
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
                conn.connect(str(path))
                conn.sendall(b"BEGIN ")
                # The monitor's bounded 2-second read timeout must reject
                # the incomplete marker without recording a stage.
                conn.settimeout(3)
                self.assertEqual(conn.recv(16), b"ERROR\n")
        self.assertFalse(evidence.exists())

    def _send(self, path: Path, message: str):
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
            conn.connect(str(path))
            conn.sendall((message + "\n").encode())
            self.assertEqual(conn.recv(16), b"OK\n")


if __name__ == "__main__":
    unittest.main()

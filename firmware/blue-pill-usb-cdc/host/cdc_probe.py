#!/usr/bin/env python3
"""Future physical CDC acceptance tool; Phase A only runs parser self-tests."""

import argparse
import re
import time

FIRMWARE_ID = "PLASMA_BLUE_PILL_CDC/0.1"
HEARTBEAT = re.compile(r"^HB version=(0\.1) seq=(\d+) uptime_ms=(\d+)$")


def is_firmware_id(line):
    return line == f"ID {FIRMWARE_ID}"


class HeartbeatMonitor:
    def __init__(self, period=0.5, tolerance=0.2):
        self.period = period
        self.tolerance = tolerance
        self.previous = None
        self.samples = 0

    def observe(self, line, received_at, interrupted=False):
        match = HEARTBEAT.fullmatch(line)
        if not match:
            return False
        version, sequence, uptime = match.groups()
        assert version == "0.1"
        sequence, uptime = int(sequence), int(uptime)
        if self.previous:
            previous_seq, previous_uptime, previous_at = self.previous
            assert sequence > previous_seq, "heartbeat sequence did not advance"
            assert uptime >= previous_uptime, "MCU uptime moved backward"
            if not interrupted:
                elapsed = received_at - previous_at
                assert abs(elapsed - self.period) <= self.tolerance, (
                    f"heartbeat interval {elapsed:.3f}s outside tolerance"
                )
        self.previous = sequence, uptime, received_at
        self.samples += 1
        return True


def run_live(port, duration, tolerance, interrupt_seconds):
    import serial  # pyserial is needed only for a future physical test.

    monitor = HeartbeatMonitor(tolerance=tolerance)
    with serial.Serial(port, 115200, timeout=1) as device:
        deadline = time.monotonic() + duration
        sent_id = False
        got_id = False
        interrupted = False
        while time.monotonic() < deadline:
            line = device.readline().decode("ascii", errors="strict").strip()
            now = time.monotonic()
            if line.startswith("HB "):
                monitor.observe(line, now, interrupted=interrupted)
                interrupted = False
            elif is_firmware_id(line):
                got_id = True
            elif line:
                print(line)
            if not sent_id and monitor.samples:
                device.write(b"ID\n")
                sent_id = True
            if interrupt_seconds and monitor.samples >= 2 and not interrupted:
                # Closing the host port interrupts host reception; it does not
                # claim a physical USB disconnect or power cycle.
                device.close()
                time.sleep(interrupt_seconds)
                device.open()
                interrupted = True
                interrupt_seconds = 0
        assert monitor.samples >= 3, "too few unsolicited heartbeats"
        assert got_id, "firmware ID reply absent"
        print(f"PASS: {monitor.samples} heartbeats, firmware ID, host port interruption")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--tolerance", type=float, default=0.2)
    parser.add_argument("--interrupt-seconds", type=float, default=1.0)
    args = parser.parse_args()
    run_live(args.port, args.duration, args.tolerance, args.interrupt_seconds)


if __name__ == "__main__":
    main()

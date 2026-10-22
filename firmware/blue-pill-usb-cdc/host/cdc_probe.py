#!/usr/bin/env python3
"""Future CDC serial probe; Phase A runs host-only tests, never opens a port."""

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

    def observe(self, line, received_at, host_port_interrupted=False):
        """A host-port pause can lose frames; it does not mean USB disconnected."""
        match = HEARTBEAT.fullmatch(line)
        if not match:
            return False
        version, sequence, uptime = match.groups()
        assert version == "0.1"
        sequence, uptime = int(sequence), int(uptime)
        if self.previous:
            previous_seq, previous_uptime, previous_at = self.previous
            if host_port_interrupted:
                assert sequence > previous_seq, "sequence did not advance after host-port pause"
            else:
                assert sequence == previous_seq + 1, "heartbeat sequence skipped or repeated"
            assert uptime >= previous_uptime, "MCU uptime moved backward"
            if not host_port_interrupted:
                elapsed = received_at - previous_at
                assert abs(elapsed - self.period) <= self.tolerance, (
                    f"heartbeat interval {elapsed:.3f}s outside tolerance"
                )
        self.previous = sequence, uptime, received_at
        self.samples += 1
        return True


def run_live(port, duration, tolerance, host_port_pause_seconds=0):
    import serial  # pyserial is needed only for a future physical test.

    monitor = HeartbeatMonitor(tolerance=tolerance)
    with serial.Serial(port, 115200, timeout=1) as device:
        deadline = time.monotonic() + duration
        sent_id = False
        got_id = False
        pause_performed = False
        pending_host_port_gap = False
        resumed_after_pause = False
        while time.monotonic() < deadline:
            line = device.readline().decode("ascii", errors="strict").strip()
            now = time.monotonic()
            if line.startswith("HB "):
                print(line, flush=True)
                monitor.observe(line, now, host_port_interrupted=pending_host_port_gap)
                if pending_host_port_gap:
                    resumed_after_pause = True
                    pending_host_port_gap = False
            elif is_firmware_id(line):
                got_id = True
            elif line:
                print(line)
            if not sent_id and monitor.samples:
                device.write(b"ID\n")
                sent_id = True
            if host_port_pause_seconds > 0 and got_id and monitor.samples >= 2 and not pause_performed:
                # This only interrupts host reception. USB power and the MCU
                # remain connected; physical disconnect is a separate test.
                print("HOST_PORT_PAUSE: closing and reopening serial port", flush=True)
                device.close()
                time.sleep(host_port_pause_seconds)
                device.open()
                pause_performed = True
                pending_host_port_gap = True
        assert monitor.samples >= 3, "too few unsolicited heartbeats"
        assert got_id, "firmware ID reply absent"
        if pause_performed:
            assert resumed_after_pause, "no heartbeat after host-port reopen"
        pause_status = "PASS" if pause_performed else "NOT_RUN"
        print(f"PASS: {monitor.samples} heartbeats, firmware ID; "
              f"host_port_pause={pause_status}; physical_usb_disconnect=NOT_RUN", flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--duration", type=float, default=8.0)
    parser.add_argument("--tolerance", type=float, default=0.2)
    parser.add_argument("--host-port-pause-seconds", type=float, default=0.0,
                        help="opt-in host serial close/reopen; does not disconnect USB")
    args = parser.parse_args(argv)
    if args.duration <= 0 or args.tolerance < 0 or args.host_port_pause_seconds < 0:
        parser.error("duration must be positive; tolerance and pause must be nonnegative")
    return args


def main():
    args = parse_args()
    run_live(args.port, args.duration, args.tolerance, args.host_port_pause_seconds)


if __name__ == "__main__":
    main()

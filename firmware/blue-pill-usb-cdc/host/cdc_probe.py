#!/usr/bin/env python3
"""Future CDC serial probe; Phase A runs host-only tests, never opens a port."""

import argparse
import math
import re
import time

FIRMWARE_ID = "PLASMA_BLUE_PILL_CDC/0.1"
HEARTBEAT = re.compile(r"^HB version=(0\.[12]) seq=(\d+) uptime_ms=(\d+)$")


def is_firmware_id(line, version="0.1"):
    return line == f"ID PLASMA_BLUE_PILL_CDC/{version}"


class HeartbeatMonitor:
    def __init__(self, period=0.5, tolerance=0.2, version="0.1"):
        self.version = version
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
        if version != self.version:
            return False
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


class ReceptionWindow:
    """Wall-clock acceptance independent of sequence and per-frame timing.

    Allow 3s for initial enumeration/reception, then at most 1.5s silence.
    Require 90% of 2Hz coverage outside startup and one explicit port pause.
    """
    startup_grace = 3.0
    max_silence = 1.5
    coverage = 0.9

    def __init__(self, started_at, duration, period=0.5):
        self.period = period
        self.started_at = started_at
        self.duration = duration
        self.last_at = None
        self.resume_at = None
        self.excluded = 0.0

    def check(self, now):
        if self.resume_at is not None:
            assert now - self.resume_at <= self.max_silence, "silence after host-port reopen"
        elif self.last_at is None:
            assert now - self.started_at <= self.startup_grace, "first heartbeat startup timeout"
        else:
            assert now - self.last_at <= self.max_silence, "prolonged heartbeat silence"

    def heartbeat(self, now):
        self.check(now)  # A late frame must not erase an already excessive gap.
        self.last_at = now
        self.resume_at = None

    def host_pause(self, closed_at, reopened_at):
        self.check(closed_at)
        self.resume_at = reopened_at
        # Only the deliberate close/open and bounded reacquisition are exempt.
        self.excluded += reopened_at - closed_at + self.max_silence

    def finish(self, now, samples):
        self.check(now)
        active = max(0.0, self.duration - self.startup_grace - self.excluded)
        minimum = max(3, math.floor(active / self.period * self.coverage))
        assert samples >= minimum, f"insufficient heartbeat coverage: {samples} < {minimum}"


def run_live(port, duration, tolerance, host_port_pause_seconds=0, version="0.1"):
    if not __debug__:
        raise RuntimeError("probe requires assertions; run Python without -O")
    import serial  # pyserial is needed only for a future physical test.

    period = 0.5 if version == "0.1" else 1.0
    monitor = HeartbeatMonitor(period=period, tolerance=tolerance, version=version)
    with serial.Serial(port, 115200, timeout=0.1) as device:
        started_at = time.monotonic()
        deadline = started_at + duration
        window = ReceptionWindow(started_at, duration, period=period)
        sent_id = False
        got_id = False
        pause_performed = False
        pending_host_port_gap = False
        resumed_after_pause = False
        while time.monotonic() < deadline:
            line = device.readline().decode("ascii", errors="strict").strip()
            now = time.monotonic()
            window.check(min(now, deadline))
            if now > deadline:
                break
            if line.startswith("HB "):
                print(line, flush=True)
                assert monitor.observe(line, now, host_port_interrupted=pending_host_port_gap), "invalid heartbeat"
                window.heartbeat(now)
                if pending_host_port_gap:
                    resumed_after_pause = True
                    pending_host_port_gap = False
            elif is_firmware_id(line, version):
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
                closed_at = time.monotonic()
                device.close()
                time.sleep(host_port_pause_seconds)
                device.open()
                reopened_at = time.monotonic()
                assert reopened_at + window.max_silence + 1.0 < deadline, "host-port pause leaves insufficient observation time"
                window.host_pause(closed_at, reopened_at)
                pause_performed = True
                pending_host_port_gap = True
        window.finish(deadline, monitor.samples)
        assert got_id, "firmware ID reply absent"
        if host_port_pause_seconds > 0:
            assert pause_performed, "requested host-port pause not exercised"
            assert resumed_after_pause, "no heartbeat after host-port reopen"
        pause_status = "PASS" if pause_performed else "NOT_RUN"
        print(f"PASS: {monitor.samples} heartbeats, firmware ID; "
              f"host_port_pause={pause_status}; physical_usb_disconnect=NOT_RUN", flush=True)


def parse_args(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", required=True)
    parser.add_argument("--version", choices=("0.1", "0.2"), default="0.1",
                        help="expected Flash image variant (default: v0.1)")
    parser.add_argument("--duration", type=float, default=60.0)
    parser.add_argument("--tolerance", type=float, default=0.2)
    parser.add_argument("--host-port-pause-seconds", type=float, default=0.0,
                        help="opt-in host serial close/reopen; does not disconnect USB")
    args = parser.parse_args(argv)
    if (not all(math.isfinite(value) for value in
                (args.duration, args.tolerance, args.host_port_pause_seconds)) or
            args.duration <= 0 or args.tolerance < 0 or args.host_port_pause_seconds < 0):
        parser.error("duration must be positive; tolerance and pause must be nonnegative")
    return args


def main():
    args = parse_args()
    run_live(args.port, args.duration, args.tolerance, args.host_port_pause_seconds, version=args.version)


if __name__ == "__main__":
    main()

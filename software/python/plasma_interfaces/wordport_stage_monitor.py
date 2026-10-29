"""Read-only stage snapshots for the development WordPort experiment.

OpenOCD synchronously marks boundaries on a private UNIX socket. The monitor
never sends SWD commands, opens MMIO, or changes target state.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import socket
import stat
import threading
import time

STAGES = frozenset(("ERASE", "PROGRAM", "VERIFY", "READBACK", "RESET"))
EDGES = frozenset(("BEGIN", "END", "FAIL"))


class StageMonitor:
    def __init__(self, path: Path, evidence: Path, port, socket_counters) -> None:
        self.path = path
        self.evidence = evidence
        self.port = port
        self.socket_counters = socket_counters
        self.current: str | None = None
        self.events: list[dict] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._server: socket.socket | None = None

    def __enter__(self):
        parent = self.path.parent
        info = parent.stat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or info.st_mode & 0o077:
            raise ValueError("PRIVATE_STAGE_SOCKET_DIRECTORY_REQUIRED")
        if self.path.exists() or self.path.is_symlink() or len(os.fsencode(self.path)) >= 100:
            raise ValueError("FRESH_STAGE_SOCKET_REQUIRED")
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        try:
            self._server.bind(str(self.path))
            os.chmod(self.path, 0o600)
            self._server.listen(1)
            self._server.settimeout(0.2)
            self._thread = threading.Thread(target=self._serve, name="wordport-stage-monitor", daemon=True)
            self._thread.start()
        except BaseException:
            self._server.close()
            self.path.unlink(missing_ok=True)
            raise
        return self

    def __exit__(self, *_):
        self._stop.set()
        assert self._thread is not None and self._server is not None
        self._thread.join(timeout=2)
        self._server.close()
        self.path.unlink(missing_ok=True)
        if self._thread.is_alive():
            raise RuntimeError("STAGE_MONITOR_DID_NOT_CLOSE")

    def _mark(self, command: str) -> dict:
        parts = command.split()
        if len(parts) != 2 or parts[0] not in EDGES or parts[1] not in STAGES:
            raise ValueError("INVALID_STAGE_MARKER")
        edge, stage = parts
        if (edge == "BEGIN" and self.current is not None) or (edge != "BEGIN" and self.current != stage):
            raise ValueError("STAGE_SEQUENCE_MISMATCH")
        # The OpenOCD Tcl command waits for this receipt before continuing.
        # No Remote Bitbang wire command can cross this counter boundary.
        mmio = self.port.counter_snapshot()
        wire = self.socket_counters.snapshot()
        event = {"stage": stage, "edge": edge,
                 "monotonic_ns": time.monotonic_ns(), "utc_ns": time.time_ns(),
                 **mmio, **wire}
        with self.evidence.open("a", encoding="utf-8") as output:
            output.write(json.dumps(event, sort_keys=True) + "\n")
            output.flush()
        self.events.append(event)
        self.current = stage if edge == "BEGIN" else None
        return event

    def _serve(self) -> None:
        assert self._server is not None
        while not self._stop.is_set():
            try:
                conn, _ = self._server.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with conn:
                conn.settimeout(2)
                try:
                    message = bytearray()
                    while not message.endswith(b"\n") and len(message) < 64:
                        chunk = conn.recv(64 - len(message))
                        if not chunk:
                            break
                        message.extend(chunk)
                    self._mark(message.decode("ascii").strip())
                    conn.sendall(b"OK\n")
                except (OSError, ValueError, UnicodeError, RuntimeError):
                    try:
                        conn.sendall(b"ERROR\n")
                    except OSError:
                        pass


def stage_report(events: list[dict], image_bytes: int, erase_bytes: int,
                 *, operation: str, readback_enabled: bool = True) -> dict:
    """Validate the exact evidence schema; preserve partial runs truthfully."""
    if type(image_bytes) is not int or type(erase_bytes) is not int or image_bytes < 0 or erase_bytes < 0:
        raise ValueError("INVALID_STAGE_BYTE_COUNT")
    expected = (("ERASE", "PROGRAM", "VERIFY") + (("READBACK",) if readback_enabled else ())
                if operation == "program"
                else (("RESET",) if operation == "reset-run" else ()))
    keys = ("monotonic_ns", "utc_ns", "wire_bytes", "mmio_reads", "mmio_writes",
            "socket_recv_calls", "socket_sendall_calls")
    previous = None
    active = None
    seen = set()
    next_index = 0
    for event in events:
        if (not isinstance(event, dict) or event.get("stage") not in expected or
                event.get("edge") not in EDGES or
                any(type(event.get(key)) is not int or event[key] < 0 for key in keys)):
            raise ValueError("INVALID_STAGE_EVIDENCE_SCHEMA")
        marker = event["edge"], event["stage"]
        if marker in seen or (previous is not None and
                (event["monotonic_ns"] <= previous["monotonic_ns"] or
                 any(event[key] < previous[key] for key in keys[2:]))):
            raise ValueError("NON_MONOTONIC_STAGE_EVIDENCE")
        if (event["edge"] == "BEGIN" and active is not None) or (
                event["edge"] != "BEGIN" and active != event["stage"]):
            raise ValueError("STAGE_SEQUENCE_MISMATCH")
        if event["edge"] == "BEGIN":
            if next_index >= len(expected) or event["stage"] != expected[next_index]:
                raise ValueError("STAGE_ORDER_MISMATCH")
            next_index += 1
        active = event["stage"] if event["edge"] == "BEGIN" else None
        seen.add(marker)
        previous = event
    bytes_by_stage = {"ERASE": erase_bytes, "PROGRAM": image_bytes,
                      "VERIFY": image_bytes, "READBACK": image_bytes, "RESET": 0}
    result = {}
    for stage in expected:
        rows = [e for e in events if e.get("stage") == stage]
        start = next((e for e in rows if e.get("edge") == "BEGIN"), None)
        finish = next((e for e in rows if e.get("edge") in ("END", "FAIL")), None)
        if start is None:
            result[stage.lower()] = {"result": "NOT_OBSERVED", "bytes": bytes_by_stage[stage]}
            continue
        if finish is None:
            result[stage.lower()] = {"result": "INTERRUPTED", "bytes": bytes_by_stage[stage],
                                     "start_monotonic_ns": start["monotonic_ns"]}
            continue
        count_keys = keys[2:]
        deltas = {key: finish[key] - start[key] for key in count_keys}
        elapsed = finish["monotonic_ns"] - start["monotonic_ns"]
        if elapsed < 0 or any(value < 0 for value in deltas.values()):
            raise ValueError("NON_MONOTONIC_STAGE_EVIDENCE")
        size = bytes_by_stage[stage]
        result[stage.lower()] = {
            "result": "PASS" if finish["edge"] == "END" else "FAIL",
            "start_monotonic_ns": start["monotonic_ns"],
            "end_monotonic_ns": finish["monotonic_ns"],
            "start_utc_ns": start["utc_ns"], "end_utc_ns": finish["utc_ns"],
            "duration_s": elapsed / 1e9, "bytes": size,
            "effective_bytes_per_s": size / (elapsed / 1e9) if elapsed else None,
            **deltas,
            # One ARMv7 DMB per native drive and sample. Stage boundaries
            # occur after admission, so every stage read is a sample read.
            "dmb_count_derived": deltas["mmio_reads"] + deltas["mmio_writes"],
            "swd_wait": "NOT_OBSERVED", "swd_fault": "NOT_OBSERVED",
            "swd_retry": "NOT_OBSERVED",
        }
    if operation == "program" and not readback_enabled:
        result["readback"] = {"result": "SKIPPED", "bytes": 0}
    return result

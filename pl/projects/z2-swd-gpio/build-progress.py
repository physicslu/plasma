#!/usr/bin/env python3
"""Read-only SWPC Vivado build progress and elapsed-time reporter.

Consumes atomic status plus stage events from driver and Vivado console logs.
Never starts/stops Vivado, touches DUT or modifies build artifacts.
"""
from __future__ import annotations

import argparse
import datetime as dt
import re
import time
from pathlib import Path

EVENT = re.compile(r"^STAGE_EVENT ([A-Z_]+) (START|DONE) ([0-9]{13})$")
ORDER = (
    "ENVIRONMENT", "IDENTITY_PREPARE", "STALE_PROJECT_CLEANUP",
    "BLOCK_DESIGN", "SYNTHESIS", "IMPLEMENTATION", "TIMING_AND_REPORTS",
    "VIVADO", "ARTIFACT_FINALIZE", "SHA256_VERIFY",
)
LABELS = {
    "ENVIRONMENT": "Environment / Board",
    "IDENTITY_PREPARE": "Identity generation",
    "STALE_PROJECT_CLEANUP": "Old project cleanup",
    "BLOCK_DESIGN": "Block Design",
    "SYNTHESIS": "Synthesis",
    "IMPLEMENTATION": "Implementation + Bitstream",
    "TIMING_AND_REPORTS": "Timing / DRC reports",
    "VIVADO": "Vivado total",
    "ARTIFACT_FINALIZE": "Artifact packaging",
    "SHA256_VERIFY": "SHA-256 verification",
}


def read_status(path: Path) -> dict[str, str]:
    result: dict[str, str] = {}
    if path.is_file():
        for line in path.read_text(errors="replace").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                result[key] = value
    return result


def read_events(logdir: Path, since_ms: int) -> dict[str, dict[str, int]]:
    events: dict[str, dict[str, int]] = {}
    for filename in ("driver.log", "vivado-console.log"):
        path = logdir / filename
        if not path.is_file():
            continue
        for line in path.read_text(errors="replace").splitlines():
            match = EVENT.fullmatch(line.strip())
            if not match:
                continue
            stage, action, timestamp = match.groups()
            ms = int(timestamp)
            if ms < since_ms or stage not in LABELS:
                continue
            events.setdefault(stage, {})[action] = ms
    return events


def fmt(ms: int) -> str:
    secs = max(0, ms // 1000)
    return f"{secs // 3600:02d}:{(secs // 60) % 60:02d}:{secs % 60:02d}"


def render(logdir: Path, *, summary: bool = False, now_ms: int | None = None) -> str:
    now_ms = now_ms if now_ms is not None else time.time_ns() // 1_000_000
    status = read_status(logdir / "monitored-build.status")
    state = status.get("STATUS", "STARTING")
    # Freeze terminal elapsed time once the supervisor reaches its final state.
    if state in ("PASS", "FAIL", "TIMEOUT"):
        raw_end = status.get("UPDATED_EPOCH_MS", "")
        if raw_end.isdigit():
            now_ms = int(raw_end)
    raw_start = status.get("STARTED_EPOCH_MS", "")
    start = int(raw_start) if raw_start.isdigit() else now_ms
    events = read_events(logdir, start)
    stamp = dt.datetime.fromtimestamp(now_ms / 1000).strftime("%H:%M:%S")
    total = fmt(now_ms - start)
    active = [
        (v["START"], stage) for stage, v in events.items()
        if "START" in v and ("DONE" not in v or v["DONE"] < v["START"])
    ]
    active.sort()
    if active:
        phase_start, phase = active[-1]
        current = f"{LABELS[phase]} ({fmt(now_ms - phase_start)})"
    elif state == "RUNNING":
        current = "Starting / switching stages"
    else:
        current = "Idle"
    prefix = f"[{stamp}] {state} | total={total} | stage={current}"
    if not summary:
        return prefix

    output = [prefix, f"TOTAL_ELAPSED={total}"]
    for stage in ORDER:
        times = events.get(stage, {})
        if "START" not in times:
            output.append(f"STAGE {LABELS[stage]}: NOT_STARTED")
        elif "DONE" not in times:
            output.append(f"STAGE {LABELS[stage]}: INCOMPLETE ({fmt(now_ms - times['START'])})")
        else:
            output.append(f"STAGE {LABELS[stage]}: {fmt(times['DONE'] - times['START'])}")
    return "\n".join(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--logdir", required=True, type=Path)
    parser.add_argument("--summary", action="store_true")
    args = parser.parse_args()
    print(render(args.logdir, summary=args.summary), flush=True)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""PLASMA HIL timing measurement toolkit (stdlib only; observation only).

Reproduces the 2026-11-18 two-Site concurrency investigation
(docs/development/hil-timing-measurement.md):

  la-capture           record SWCLK/SWDIO of both Sites with a KINGST LA2016 (sigrok)
  la-analyze           per-Site SWD activity, SWCLK frequency and 2-Site overlap from a .sr
  proc-trace           (on the PPU, as root) sample /proc: process lifetimes + wchan
  proc-analyze         admission/OpenOCD lifetimes, lock waits, Runtime loop CPU from a trace
  preadmission-profile (on the PPU) time the Runtime's pre-admission verification steps
  summarize            text report from a Path 2 loading report, Job logs and LA analysis

No subcommand drives hardware, writes PPU state, or decides a Job outcome.
"""
from __future__ import annotations

import argparse
import configparser
import datetime as _dt
import gzip
import json
import os
import re
import statistics
import subprocess
import sys
import time
import zipfile
from pathlib import Path
from typing import Any, Iterable, Iterator

DEFAULT_SITES = {1: ("CH3", "CH4"), 2: ("CH0", "CH1")}  # (SWCLK, SWDIO) per Site
DEFAULT_SIGROK = "/opt/plasma/hil-tools/kingst-la2016-sigrok.AppImage"
TRACE_PATTERNS = ("plasma_swd_site_admission", "openocd", "ppu_site_worker",
                  "ppu.pyz server", "plasma-server", "plasma_server")
STAGE_COLUMNS = ("prepare_preflight", "preflight", "staged_manifest", "load_engine",
                 "worker_status", "qualify_reference", "stage_image", "open_session",
                 "bind_image", "worker_run")
SITE_WORKER_KEYS = ("admission_ms", "openocd_ms", "revoke_ms")


def _utc(seconds: float) -> str:
    return _dt.datetime.fromtimestamp(seconds, _dt.timezone.utc).strftime("%H:%M:%S.%f")[:-3]


def _write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=1, sort_keys=True) + "\n", encoding="utf-8")


# --------------------------------------------------------------------- la-capture

def sigrok_argv(sigrok: str, *, conn: str | None, channels: list[str], samplerate: str,
                threshold: str, seconds: float, output: Path) -> list[str]:
    argv = [sigrok]
    if sigrok.endswith(".AppImage"):
        argv.append("--appimage-extract-and-run")
    driver = "kingst-la2016" + (f":conn={conn}" if conn else "")
    return [*argv, "-d", driver, "-C", ",".join(channels),
            "--config", f"samplerate={samplerate}:voltage_threshold={threshold}-{threshold}",
            "--time", str(int(seconds * 1000)), "-o", str(output)]


def cmd_la_capture(args: argparse.Namespace) -> int:
    argv = sigrok_argv(args.sigrok, conn=args.conn, channels=args.channels.split(","),
                       samplerate=args.samplerate, threshold=args.threshold,
                       seconds=args.seconds, output=args.output)
    meta = {"schema": "plasma.hil-timing.la-capture.v1", "argv": argv,
            "start_unix_s": time.time()}
    _write_json(args.output.with_suffix(args.output.suffix + ".capture.json"), meta)
    print(json.dumps(meta), flush=True)
    if args.dry_run:
        return 0
    return subprocess.run(argv, stdin=subprocess.DEVNULL).returncode


# --------------------------------------------------------------------- la-analyze

def _samplerate(text: str) -> float:
    value, unit = text.split()
    return float(value) * {"Hz": 1, "kHz": 1e3, "MHz": 1e6, "GHz": 1e9}[unit]


def _sr_chunks(archive: zipfile.ZipFile, capturefile: str) -> list[str]:
    names = [n for n in archive.namelist() if n.startswith(capturefile + "-")]
    return sorted(names, key=lambda n: int(n.rsplit("-", 1)[1]))


def _bit_table(bit: int) -> bytes:
    return bytes((value >> bit) & 1 for value in range(256))


_RISE = re.compile(b"\x00\x01")


def analyze_sr(path: Path, sites: dict[int, tuple[str, str]] = DEFAULT_SITES,
               *, burst_gap_s: float = 0.01, max_period_s: float = 2e-6) -> dict[str, Any]:
    """Rising SWCLK edges per Site -> activity window, frequency, 2-Site overlap."""
    with zipfile.ZipFile(path) as archive:
        meta = configparser.ConfigParser()
        meta.read_string(archive.read("metadata").decode())
        device = meta["device 1"]
        rate = _samplerate(device["samplerate"])
        unit = int(device["unitsize"])
        probes = {device[k]: int(k[5:]) - 1 for k in device if k.startswith("probe")}
        wanted = {name for pair in sites.values() for name in pair}
        missing = sorted(wanted - set(probes))
        if missing:
            raise SystemExit(f"LA_CHANNELS_NOT_IN_CAPTURE: {missing}")
        plan = {name: (probes[name] // 8, _bit_table(probes[name] % 8)) for name in wanted}
        rises: dict[str, list[int]] = {name: [] for name in wanted}
        toggles: dict[str, int] = {name: 0 for name in wanted}
        last: dict[str, bytes] = {}
        total = 0
        carry = b""
        for name in _sr_chunks(archive, device.get("capturefile", "logic-1")):
            raw = carry + archive.read(name)
            usable = len(raw) - len(raw) % unit
            raw, carry = raw[:usable], raw[usable:]
            count = usable // unit
            for channel, (byte_index, table) in plan.items():
                stream = (raw if unit == 1 else raw[byte_index::unit]).translate(table)
                prefix = last.get(channel, b"")
                joined = prefix + stream
                offset = total - len(prefix)
                rises[channel].extend(m.start() + 1 + offset for m in _RISE.finditer(joined))
                toggles[channel] += joined.count(b"\x00\x01") + joined.count(b"\x01\x00")
                last[channel] = stream[-1:]
            total += count
    out: dict[str, Any] = {"schema": "plasma.hil-timing.la-analysis.v1",
                           "samplerate_hz": rate, "samples": total,
                           "duration_s": total / rate, "channels": {}}
    windows: dict[int, set[int]] = {}
    for site, (clock, data) in sorted(sites.items()):
        edges = rises[clock]
        info: dict[str, Any] = {"swclk": clock, "swdio": data,
                                "swclk_rising_edges": len(edges),
                                "swdio_edges": toggles[data]}
        if len(edges) > 2:
            # Periods inside a burst; longer gaps are SWD idle between transfers.
            periods = [b - a for a, b in zip(edges, edges[1:]) if b - a < rate * max_period_s]
            if periods:
                median = statistics.median(periods)
                info["period_samples_median"] = float(median)
                info["swclk_freq_median_hz"] = rate / median
            gap = int(rate * burst_gap_s)
            bursts, start = [], edges[0]
            for a, b in zip(edges, edges[1:]):
                if b - a > gap:
                    bursts.append([round(start / rate, 4), round(a / rate, 4)])
                    start = b
            bursts.append([round(start / rate, 4), round(edges[-1] / rate, 4)])
            info["active_first_s"] = edges[0] / rate
            info["active_last_s"] = edges[-1] / rate
            info["bursts"] = bursts[:20]
            per_ms = int(rate / 1000)
            windows[site] = {edge // per_ms for edge in edges}
            info["active_1ms_windows"] = len(windows[site])
        out["channels"][f"site{site}"] = info
    if len(windows) == 2:
        first, second = (out["channels"][f"site{s}"] for s in sorted(windows))
        lo = max(first["active_first_s"], second["active_first_s"])
        hi = min(first["active_last_s"], second["active_last_s"])
        a, b = (windows[s] for s in sorted(windows))
        out["overlap"] = {"interval_overlap_s": max(0.0, hi - lo),
                          "both_active_1ms_windows": len(a & b),
                          "start_gap_s": second["active_first_s"] - first["active_first_s"]}
    return out


def _sites_arg(values: list[str] | None) -> dict[int, tuple[str, str]]:
    if not values:
        return dict(DEFAULT_SITES)
    sites = {}
    for value in values:
        match = re.fullmatch(r"(\d+)=(CH\d+):(CH\d+)", value)
        if not match:
            raise SystemExit("--site must be N=CHclk:CHdio, e.g. 1=CH3:CH4")
        sites[int(match[1])] = (match[2], match[3])
    return sites


def cmd_la_analyze(args: argparse.Namespace) -> int:
    result = analyze_sr(args.capture, _sites_arg(args.site), burst_gap_s=args.burst_gap_ms / 1000,
                        max_period_s=args.max_period_us / 1e6)
    if args.output:
        _write_json(args.output, result)
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


# --------------------------------------------------------------------- proc-trace

def _read(path: str) -> bytes | None:
    try:
        with open(path, "rb") as stream:
            return stream.read()
    except OSError:
        return None


def proc_sample(patterns: Iterable[str] = TRACE_PATTERNS, proc: str = "/proc") -> list[list]:
    """One /proc snapshot: [pid, tid, state, ppid, starttime, cpu_ticks, wchan, cmd]."""
    rows = []
    for pid in os.listdir(proc):
        if not pid.isdigit():
            continue
        raw = _read(f"{proc}/{pid}/cmdline")
        if not raw:
            continue
        cmd = raw.replace(b"\0", b" ").decode("utf-8", "replace")[:160]
        if not any(p in cmd for p in patterns) or "plasma_hil_timing" in cmd:
            continue
        threaded = any(p in cmd for p in ("ppu_site_worker", "ppu.pyz server",
                                          "plasma-server", "plasma_server"))
        try:
            tids = os.listdir(f"{proc}/{pid}/task") if threaded else [pid]
        except OSError:
            continue
        for tid in tids:
            stat = _read(f"{proc}/{pid}/task/{tid}/stat")
            if not stat:
                continue
            fields = stat.rsplit(b")", 1)[1].split()
            wchan = (_read(f"{proc}/{pid}/task/{tid}/wchan") or b"").decode("ascii", "replace")
            rows.append([int(pid), int(tid), fields[0].decode(), int(fields[1]),
                         int(fields[19]), int(fields[11]) + int(fields[12]), wchan,
                         cmd if tid == pid else ""])
    return rows


def cmd_proc_trace(args: argparse.Namespace) -> int:
    opener = gzip.open if str(args.output).endswith(".gz") else open
    end = time.time() + args.seconds
    with opener(args.output, "wt") as out:
        while time.time() < end:
            started = time.time()
            out.write(json.dumps({"t": started, "r": proc_sample()}) + "\n")
            time.sleep(max(0.0, args.interval - (time.time() - started)))
    return 0


# --------------------------------------------------------------------- proc-analyze

def _trace_lines(path: Path) -> Iterator[dict]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt") as stream:
        for line in stream:
            if line.strip():
                yield json.loads(line)


def analyze_trace(path: Path, *, bucket_s: float = 0.5) -> dict[str, Any]:
    processes: dict[tuple[int, int], dict] = {}
    waits: dict[str, int] = {}
    server_cpu: dict[int, int] = {}
    previous_cpu: dict[tuple[int, int], int] = {}
    server_pid = None
    for sample in _trace_lines(path):
        t = sample["t"]
        for pid, tid, state, ppid, start, cpu, wchan, cmd in sample["r"]:
            if cmd and "ppu.pyz server" in cmd:
                server_pid = pid
            if ("lock" in wchan or state == "D") and wchan:
                waits[f"{state}:{wchan}"] = waits.get(f"{state}:{wchan}", 0) + 1
            if pid == tid and cmd:
                entry = processes.setdefault((pid, start), {
                    "pid": pid, "ppid": ppid, "cmd": cmd, "first_s": t, "last_s": t,
                    "states": []})
                entry["last_s"] = t
                if not entry["states"] or entry["states"][-1][1] != f"{state}:{wchan}":
                    entry["states"].append([round(t, 3), f"{state}:{wchan}"])
            if pid == tid == server_pid:
                key = (pid, tid)
                if key in previous_cpu:
                    bucket = int(t // bucket_s)
                    server_cpu[bucket] = server_cpu.get(bucket, 0) + cpu - previous_cpu[key]
                previous_cpu[key] = cpu
    lifetimes = []
    for entry in sorted(processes.values(), key=lambda e: e["first_s"]):
        kind = ("admission" if "plasma_swd_site_admission" in entry["cmd"]
                else "openocd" if "/bin/openocd" in entry["cmd"] else None)
        if kind is None:
            continue
        site = re.search(r"(?:admit|revoke) (\d)|site (\d)", entry["cmd"])
        lifetimes.append({
            "kind": kind, "pid": entry["pid"],
            "site": int(next(g for g in site.groups() if g)) if site else None,
            "action": ("revoke" if " revoke " in entry["cmd"] + " " else
                       "admit" if " admit " in entry["cmd"] + " " else None),
            "first_utc": _utc(entry["first_s"]), "last_utc": _utc(entry["last_s"]),
            "duration_s": round(entry["last_s"] - entry["first_s"], 3),
            "states": entry["states"][:12]})
    return {"schema": "plasma.hil-timing.proc-analysis.v1",
            "server_main_thread_cpu_ticks": [
                [_utc(b * bucket_s), ticks] for b, ticks in sorted(server_cpu.items()) if ticks],
            "lock_or_uninterruptible_waits": dict(sorted(waits.items(), key=lambda x: -x[1])),
            "processes": lifetimes}


def cmd_proc_analyze(args: argparse.Namespace) -> int:
    result = analyze_trace(args.trace, bucket_s=args.bucket_ms / 1000)
    if args.output:
        _write_json(args.output, result)
    print(json.dumps(result, indent=1, sort_keys=True))
    return 0


# ------------------------------------------------------------ preadmission-profile

def cmd_preadmission_profile(args: argparse.Namespace) -> int:
    """Read-only: time the Runtime's synchronous pre-admission checks on the PPU."""
    for path in reversed(args.module_path):
        sys.path.insert(0, path)
    import ppu_asset_set  # noqa: PLC0415 - deployed control-plane modules
    import ppu_opf_reference_openocd as reference  # noqa: PLC0415
    import ppu_site_engine  # noqa: PLC0415

    root = Path(args.product_root)
    binding = json.loads(Path(args.job_binding).read_text())
    timings: dict[str, Any] = {}

    def timed(name, fn):
        started = time.perf_counter()
        try:
            value, error = fn(), None
        except Exception as exc:  # noqa: BLE001 - report, never raise
            value, error = None, f"{type(exc).__name__}:{exc}"[:160]
        timings[name] = {"s": round(time.perf_counter() - started, 4), "error": error}
        return value

    for _ in range(args.repeat):
        active = timed("read_active", lambda: ppu_asset_set.read_active(root))
        if not active:
            break
        timed("preflight_runtime_flash", lambda: reference.preflight_runtime_flash(
            product_root=root, active_asset_set=active, target=binding["icpn"],
            site_id=binding["site_id"], image_size=binding["range"]["length"],
            job_binding=binding))
        timed("load_engine", lambda: ppu_site_engine.load_engine(require_root=True))
        print(json.dumps(timings, sort_keys=True), flush=True)
    return 0


# ---------------------------------------------------------------------- summarize

def read_job_log(path: Path) -> dict[str, Any]:
    events = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    job = {"job_id": None, "site_id": None, "events": {}, "phases": {}}
    for event in events:
        job["job_id"] = job["job_id"] or event.get("job_id")
        job["site_id"] = job["site_id"] or event.get("site_id")
        if event["event"] == "stage_timing":
            job["phases"].setdefault(event["phase"], event)
        else:
            job["events"].setdefault(event["event"], event)
    return job


def summarize(*, report: dict | None, jobs: list[dict], la: dict | None) -> str:
    lines: list[str] = []
    if report:
        lines += [f"outcome {report.get('outcome')}  batch {report.get('batch_id')}  "
                  f"start {report.get('start_id')}  source {report.get('source_sha')}"]
        for site in report.get("site_results", []):
            lines.append(f"  Site {site['site_id']} {site['job_id']} {site['result']} "
                         f"{site['elapsed_ms']} ms readback {site['readback_sha256'][:8]} "
                         f"safe_off {site['safe_off']}")
        throughput = report.get("throughput") or {}
        lines.append(f"  throughput {throughput.get('bytes')} B / "
                     f"{round(throughput.get('elapsed_s', 0), 2)} s = "
                     f"{round(throughput.get('bytes_per_s', 0))} B/s")
        comparison = report.get("comparison") or {}
        if "sampled_pid_overlap_s" in comparison:
            lines.append(f"  OpenOCD PID overlap {round(comparison['sampled_pid_overlap_s'], 2)} s"
                         f" (+/-{round(comparison.get('overlap_boundary_uncertainty_s', 0), 2)})")
        lines.append("  phase        n    CPU mean  CPU peak  RAM peak KiB")
        for name, phase in (comparison.get("phases") or {}).items():
            cpu, ram = phase.get("cpu_pct") or {}, phase.get("ram_used_kib") or {}
            mean = cpu.get("mean")
            lines.append(f"  {name:<12}{phase.get('n', 0):>4}  "
                         f"{'-' if mean is None else f'{mean:.1f}%':>8}  "
                         f"{'-' if cpu.get('peak') is None else str(cpu['peak']) + '%':>8}"
                         f"  {ram.get('peak', '-'):>12}")
    if jobs:
        jobs = sorted(jobs, key=lambda j: j["site_id"] or 0)
        lines.append("")
        lines.append("stage timing (duration_ms)" + "".join(f"  Site {j['site_id']:>8}" for j in jobs))
        for job in jobs:
            started = job["events"].get("job_started", {}).get("timestamp")
            lines.append(f"  Site {job['site_id']} job_started {started}")
        admission = [j["phases"].get("job_admission", {}) for j in jobs]
        for key in ("reserve_ms", "active_set_ms", "job_binding_ms", "route_admit_ms",
                    "write_state_ms"):
            lines.append(f"  admission.{key:<20}" + "".join(f"{a.get(key, '-'):>14}" for a in admission))
        for phase in ("queued", *STAGE_COLUMNS):
            values = [j["phases"].get(phase, {}).get("duration_ms", "-") for j in jobs]
            lines.append(f"  {phase:<30}" + "".join(f"{v:>14}" for v in values))
        workers = [j["phases"].get("site_worker", {}) for j in jobs]
        for key in (*SITE_WORKER_KEYS,
                    *sorted({k for w in workers for k in w if k.startswith("admission_root_")})):
            lines.append(f"  site_worker.{key:<18}" + "".join(f"{w.get(key, '-'):>14}" for w in workers))
        for name in ("load_engine_cache", "qualify_reference_cache"):
            hits = [j["phases"].get(name, {}).get("hit", "-") for j in jobs]
            if any(h != "-" for h in hits):
                lines.append(f"  {name + '.hit':<30}" + "".join(f"{str(h):>14}" for h in hits))
        starts = [w.get("openocd_start_unix_ms") for w in workers]
        if len(starts) == 2 and all(starts):
            lines.append(f"  openocd start gap {round((starts[1] - starts[0]) / 1000, 3)} s")
    if la:
        lines.append("")
        lines.append(f"LA {la['samplerate_hz'] / 1e6:g} MHz, {round(la['duration_s'], 1)} s")
        for name, info in la["channels"].items():
            freq = info.get("swclk_freq_median_hz")
            lines.append(f"  {name} SWCLK {'-' if freq is None else f'{freq / 1e6:.3f} MHz'}  "
                         f"active {round(info.get('active_first_s', 0), 3)} - "
                         f"{round(info.get('active_last_s', 0), 3)} s")
        if "overlap" in la:
            overlap = la["overlap"]
            gap = overlap.get("start_gap_s")
            lines.append(f"  both-active {round(overlap['interval_overlap_s'], 3)} s, "
                         f"{overlap['both_active_1ms_windows']} 1-ms windows"
                         + ("" if gap is None else f", start gap {round(gap, 3)} s"))
    return "\n".join(lines) + "\n"


def cmd_summarize(args: argparse.Namespace) -> int:
    report = json.loads(args.report.read_text()) if args.report else None
    jobs = [read_job_log(path) for path in args.job_log]
    la = json.loads(args.la.read_text()) if args.la else None
    text = summarize(report=report, jobs=jobs, la=la)
    if args.output:
        args.output.write_text(text, encoding="utf-8")
    print(text, end="")
    return 0


# --------------------------------------------------------------------------- main

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("la-capture", help="record both Sites' SWD with LA2016 via sigrok")
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--seconds", type=float, default=190.0)
    p.add_argument("--samplerate", default="20m")
    p.add_argument("--threshold", default="1.4")
    p.add_argument("--channels", default="CH0,CH1,CH3,CH4")
    p.add_argument("--conn", help="USB bus.device of the LA2016 (see la2016-tool-operations.md)")
    p.add_argument("--sigrok", default=os.environ.get("PLASMA_SIGROK_CLI", DEFAULT_SIGROK))
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(func=cmd_la_capture)

    p = sub.add_parser("la-analyze", help="per-Site SWD activity and overlap from a .sr capture")
    p.add_argument("capture", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--site", action="append", help="N=CHclk:CHdio (default 1=CH3:CH4 2=CH0:CH1)")
    p.add_argument("--burst-gap-ms", type=float, default=10.0)
    p.add_argument("--max-period-us", type=float, default=2.0,
                   help="longest SWCLK period counted as in-burst (default 2 us, >= 500 kHz)")
    p.set_defaults(func=cmd_la_analyze)

    p = sub.add_parser("proc-trace", help="sample /proc on the PPU (run as root)")
    p.add_argument("--seconds", type=float, default=200.0)
    p.add_argument("--interval", type=float, default=0.02)
    p.add_argument("--output", type=Path, required=True)
    p.set_defaults(func=cmd_proc_trace)

    p = sub.add_parser("proc-analyze", help="lifetimes, lock waits and Runtime CPU from a trace")
    p.add_argument("trace", type=Path)
    p.add_argument("--output", type=Path)
    p.add_argument("--bucket-ms", type=float, default=500.0)
    p.set_defaults(func=cmd_proc_analyze)

    p = sub.add_parser("preadmission-profile", help="time pre-admission checks on the PPU")
    p.add_argument("--product-root", default="/opt/plasma")
    p.add_argument("--job-binding", required=True, help="JSON file: a Job's job_binding")
    p.add_argument("--module-path", action="append",
                   default=["/opt/plasma/bootstrap", "/opt/plasma/current/runtime/ppu/ppu.pyz"])
    p.add_argument("--repeat", type=int, default=1)
    p.set_defaults(func=cmd_preadmission_profile)

    p = sub.add_parser("summarize", help="text report from loading report, Job logs, LA analysis")
    p.add_argument("--report", type=Path, help="Path 2 loading-benchmark report.json")
    p.add_argument("--job-log", type=Path, action="append", default=[],
                   help="PPU Job log (.jsonl) with stage_timing events")
    p.add_argument("--la", type=Path, help="la-analyze output")
    p.add_argument("--output", type=Path)
    p.set_defaults(func=cmd_summarize)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())

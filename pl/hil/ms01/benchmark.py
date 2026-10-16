"""MMIO-MS-01 PS concurrency benchmark; no implicit /dev/mem or FPGA access.

Only a trusted, supervised caller supplies already-admitted per-Site
LoopTestDriver instances. Thread workers call a distinct driver per Site.
Process-IPC workers exchange real payload bytes with one parent's per-Site
server threads. Process-IPC is NOT a direct-MMIO multiprocess test.
"""
from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
import json
import os
from pathlib import Path
import resource
import statistics
import threading
import time
from multiprocessing import get_context
from multiprocessing.connection import Connection
from typing import Mapping

from plasma_interfaces.mmio_loop_test import LoopTestDriver

MODES = ("thread", "process-ipc")
MAX_SITES = 8
MAX_PAYLOAD = 1024 * 1024


@dataclass(frozen=True)
class Case:
    site_id: int
    sequence: int
    bytes: int
    chunks: int
    read_words: int
    write_words: int
    latency_ns: int


def payload(site: int, sequence: int, length: int) -> bytes:
    """Unique per-Site/sequence deterministic bytes, including long transfers."""
    return bytes(((i * 37 + (i >> 5) + site * 71 + sequence * 19)
                  & 255) for i in range(length))


def _read_proc(pid: int) -> tuple[float, int | None, int | None] | None:
    """Return process CPU seconds, RSS bytes and PSS bytes (when available)."""
    try:
        # /proc/PID/stat comm may contain spaces or parentheses.
        stat = Path(f"/proc/{pid}/stat").read_text()
        fields = stat[stat.rfind(")") + 2:].split()
        ticks = int(fields[11]) + int(fields[12])  # utime/stime
        hz = os.sysconf("SC_CLK_TCK")
        status = Path(f"/proc/{pid}/status").read_text().splitlines()
        rss = next((int(x.split()[1]) * 1024 for x in status
                    if x.startswith("VmRSS:")), None)
        pss = None
        rollup = Path(f"/proc/{pid}/smaps_rollup")
        try:
            for line in rollup.read_text().splitlines():
                if line.startswith("Pss:"):
                    pss = int(line.split()[1]) * 1024
                    break
        except (OSError, PermissionError):
            pass
        return ticks / hz, rss, pss
    except (OSError, IndexError, ValueError, StopIteration):
        return None


class _Sampler:
    """Best-effort Linux /proc resource sampler; missing metrics remain null."""

    def __init__(self, processes: list) -> None:
        self.processes = processes
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._previous: tuple[float, float] | None = None
        self.samples = 0
        self.cpu_percent_peak: float | None = None
        self.rss_bytes_peak: int | None = None
        self.pss_bytes_peak: int | None = None
        self.pss_available = False
        self.rss_samples: list[int] = []
        self.pss_samples: list[int] = []
        self.cpu_samples: list[float] = []

    def start(self) -> None:
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=3)

    def _loop(self) -> None:
        while not self._stop.is_set():
            pids = {os.getpid()}
            pids.update(p.pid for p in self.processes if p.pid is not None
                        and p.is_alive())
            rows = [_read_proc(pid) for pid in pids]
            available = [r for r in rows if r is not None]
            now = time.monotonic()
            if available:
                self.samples += 1
                cpu = sum(r[0] for r in available)
                rss = [r[1] for r in available]
                pss = [r[2] for r in available]
                if all(v is not None for v in rss):
                    total_rss = sum(rss)
                    self.rss_samples.append(total_rss)
                    self.rss_bytes_peak = max(
                        self.rss_bytes_peak or 0, total_rss)
                if all(v is not None for v in pss):
                    self.pss_available = True
                    self.pss_samples.append(sum(pss))
                    self.pss_bytes_peak = max(
                        self.pss_bytes_peak or 0, sum(pss))
                if self._previous is not None:
                    earlier, earlier_cpu = self._previous
                    if now > earlier:
                        percent = max(0.0, 100 * (cpu - earlier_cpu)
                                      / (now - earlier))
                        self.cpu_samples.append(percent)
                        self.cpu_percent_peak = max(
                            self.cpu_percent_peak or 0.0, percent)
                self._previous = (now, cpu)
            self._stop.wait(0.1)


def _child_rusage() -> float:
    self_usage = resource.getrusage(resource.RUSAGE_SELF)
    child_usage = resource.getrusage(resource.RUSAGE_CHILDREN)
    return sum((self_usage.ru_utime, self_usage.ru_stime,
                child_usage.ru_utime, child_usage.ru_stime))


def _context_switches() -> int:
    own = resource.getrusage(resource.RUSAGE_SELF)
    children = resource.getrusage(resource.RUSAGE_CHILDREN)
    return sum((own.ru_nvcsw, own.ru_nivcsw,
                children.ru_nvcsw, children.ru_nivcsw))


def _case(driver: LoopTestDriver, site: int, sequence: int,
          data: bytes) -> Case:
    response = driver.echo(data)
    if response.payload != data or response.tx_crc32 != response.rx_crc32:
        raise RuntimeError(f"Site {site}: byte/CRC mismatch")
    if response.data_word_reads != response.data_word_writes:
        raise RuntimeError(f"Site {site}: counter mismatch")
    expected = sum((min(2048, len(data) - offset) + 3) // 4
                   for offset in range(0, len(data), 2048))
    if response.data_word_reads != expected:
        raise RuntimeError(f"Site {site}: incorrect hardware word counts")
    return Case(site, sequence, len(data), response.chunks,
                response.data_word_reads, response.data_word_writes,
                response.elapsed_ns)


def _ipc_child(conn: Connection, site: int, count: int,
               payload_bytes: int) -> None:
    """The process owns NO MMIO and never receives a LinuxMMIO object."""
    try:
        for seq in range(count):
            data = payload(site, seq, payload_bytes)
            conn.send(("echo", seq, data))
            kind, echoed = conn.recv()
            if kind != "ok" or echoed != data:
                raise RuntimeError(f"Site {site} IPC echo failed: {kind}")
        conn.send(("done",))
    except BaseException as exc:
        try:
            conn.send(("error", f"{type(exc).__name__}: {exc}"))
        except (BrokenPipeError, OSError):
            pass
        raise
    finally:
        conn.close()


def _percentile(values: list[int], pct: int) -> int:
    ordered = sorted(values)
    return ordered[(len(ordered) * pct + 99) // 100 - 1]


def run_benchmark(
    drivers: Mapping[int, LoopTestDriver], *,
    mode: str,
    payload_bytes: int = 2048,
    iterations: int = 8,
) -> dict:
    """Run one complete same-workload comparison cell (time/RAM/CPU included).

    Caller must verify candidate image, hardware ownership and recovery.
    No driver may be shared across Sites. All modes use identical payloads.
    Process IPC intentionally measures parent service + child IPC overhead.
    """
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    if (not drivers or len(drivers) > MAX_SITES or
            any(type(k) is not int or not 1 <= k <= MAX_SITES
                for k in drivers)):
        raise ValueError("Site IDs must be unique, one-based and <=8")
    if (type(payload_bytes) is not int or
            not 1 <= payload_bytes <= MAX_PAYLOAD):
        raise ValueError("payload must be 1..1048576 bytes")
    if type(iterations) is not int or not 1 <= iterations <= 10000:
        raise ValueError("iterations must be 1..10000")
    cases: list[Case] = []
    errors: list[str] = []
    gate = threading.Event()
    case_lock = threading.Lock()
    thread_list: list[threading.Thread] = []
    processes: list = []
    connections: list[Connection] = []
    ctx = get_context("spawn")
    sampler = _Sampler(processes)

    def record(item: Case) -> None:
        with case_lock:
            cases.append(item)

    def fail(exc: BaseException) -> None:
        with case_lock:
            errors.append(f"{type(exc).__name__}: {exc}")

    def thread_worker(site: int, driver: LoopTestDriver) -> None:
        gate.wait()
        try:
            for seq in range(iterations):
                if errors:
                    break
                record(_case(driver, site, seq,
                             payload(site, seq, payload_bytes)))
        except BaseException as exc:
            fail(exc)

    def ipc_server(site: int, driver: LoopTestDriver,
                   conn: Connection) -> None:
        gate.wait()
        try:
            while True:
                event = conn.recv()
                if event[0] == "done":
                    break
                if event[0] == "error":
                    raise RuntimeError(f"Site {site} child: {event[1]}")
                if event[0] != "echo":
                    raise RuntimeError("Unexpected IPC message")
                _, seq, data = event
                if (type(seq) is not int or not 0 <= seq < iterations or
                        data != payload(site, seq, payload_bytes)):
                    raise RuntimeError("Invalid IPC payload or sequence")
                record(_case(driver, site, seq, data))
                conn.send(("ok", data))
        except BaseException as exc:
            fail(exc)
            try:
                conn.send(("error", str(exc)))
            except (OSError, BrokenPipeError):
                pass
        finally:
            conn.close()

    cpu_before = _child_rusage()
    switches_before = _context_switches()
    start_ns = time.perf_counter_ns()
    try:
        if mode == "thread":
            for site, driver in drivers.items():
                thread_list.append(threading.Thread(
                    target=thread_worker, args=(site, driver),
                    name=f"ms01-thread-site-{site}"))
        else:
            for site, driver in drivers.items():
                parent, child = ctx.Pipe(duplex=True)
                process = ctx.Process(
                    target=_ipc_child,
                    args=(child, site, iterations, payload_bytes),
                    name=f"ms01-ipc-site-{site}")
                processes.append(process)
                connections.append(parent)
                thread_list.append(threading.Thread(
                    target=ipc_server, args=(site, driver, parent),
                    name=f"ms01-ipc-server-{site}"))
                process.start()
                child.close()
        sampler.start()
        for thread in thread_list:
            thread.start()
        gate.set()
        for thread in thread_list:
            thread.join(timeout=120)
            if thread.is_alive():
                fail(TimeoutError(f"{thread.name} did not exit; unsafe retry"))
        for process in processes:
            process.join(timeout=5)
            if process.is_alive():
                # Host process termination does NOT recover a stalled AXI bus.
                process.terminate()
                process.join(timeout=3)
                fail(TimeoutError(f"{process.name} stuck; check hardware"))
            if process.exitcode != 0:
                fail(RuntimeError(f"{process.name} exit={process.exitcode}"))
    finally:
        gate.set()
        sampler.stop()
        for connection in connections:
            connection.close()
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=3)
    elapsed_ns = time.perf_counter_ns() - start_ns
    cpu_seconds = max(0., _child_rusage() - cpu_before)
    expected_count = len(drivers) * iterations
    if errors or len(cases) != expected_count:
        raise RuntimeError("MS01 STOP; do not retry uncertain MMIO: " +
                           "; ".join(errors or
                                     [f"expected {expected_count} cases, got {len(cases)}"]))
    durations = [c.latency_ns for c in cases]
    total_bytes = sum(c.bytes for c in cases)
    elapsed_s = elapsed_ns / 1e9
    operations = sum(c.read_words + c.write_words for c in cases)
    site_metrics = []
    for site in sorted(drivers):
        site_cases = [c for c in cases if c.site_id == site]
        site_metrics.append({
            "site_id": site, "cases": len(site_cases),
            "bytes": sum(c.bytes for c in site_cases),
            "data_words_read": sum(c.read_words for c in site_cases),
            "data_words_written": sum(c.write_words for c in site_cases),
            "latency_p50_us": _percentile(
                [c.latency_ns for c in site_cases], 50) / 1000,
        })
    return {
        "status": "PASS",
        "evidence_scope": "supervised hardware only if caller verified real hardware",
        "mode": mode,
        "site_count": len(drivers),
        "payload_bytes": payload_bytes,
        "iterations_per_site": iterations,
        "case_count": len(cases),
        "elapsed_s": elapsed_s,
        "total_bytes": total_bytes,
        "throughput_mib_per_s": total_bytes / elapsed_s / 1048576,
        "data_word_ops_per_s": operations / elapsed_s,
        "cpu_percent_one_core_100": cpu_seconds / elapsed_s * 100,
        "cpu_percent_peak_sampled_one_core_100": sampler.cpu_percent_peak,
        "cpu_percent_avg_sampled_one_core_100": (
            statistics.mean(sampler.cpu_samples) if sampler.cpu_samples else None),
        "context_switches": max(0, _context_switches() - switches_before),
        "cpu_percent_machine_normalized": cpu_seconds / elapsed_s * 100 /
                                          (os.cpu_count() or 1),
        "ram_rss_peak_mib": (sampler.rss_bytes_peak / 1048576
                             if sampler.rss_bytes_peak is not None else None),
        "ram_pss_peak_mib": (sampler.pss_bytes_peak / 1048576
                             if sampler.pss_available else None),
        "ram_samples": sampler.samples,
        "ram_rss_avg_mib": (statistics.mean(sampler.rss_samples) / 1048576
                             if sampler.rss_samples else None),
        "ram_pss_avg_mib": (statistics.mean(sampler.pss_samples) / 1048576
                             if sampler.pss_samples else None),
        "latency_p50_us": _percentile(durations, 50) / 1000,
        "latency_p95_us": _percentile(durations, 95) / 1000,
        "latency_p99_us": _percentile(durations, 99) / 1000,
        "latency_max_us": max(durations) / 1000,
        "site_metrics": site_metrics,
        "cases": [asdict(c) for c in sorted(
            cases, key=lambda v: (v.site_id, v.sequence))],
    }


def save_reports(runs: list[dict], output: Path) -> None:
    """Persist immutable JSON/CSV plus dependency-free SVG comparison charts."""
    if output.exists():
        raise FileExistsError("Never overwrite benchmark evidence")
    output.mkdir(parents=True, mode=0o700)
    (output / "benchmark.json").write_text(
        json.dumps(runs, indent=2, sort_keys=True) + "\n")
    columns = (
        "mode", "site_count", "payload_bytes", "iterations_per_site",
        "elapsed_s", "throughput_mib_per_s", "data_word_ops_per_s",
        "cpu_percent_one_core_100", "cpu_percent_peak_sampled_one_core_100",
        "ram_rss_peak_mib", "ram_pss_peak_mib", "ram_rss_avg_mib",
        "ram_pss_avg_mib", "context_switches", "latency_p95_us",
    )
    with (output / "benchmark.csv").open("x", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()
        for item in runs:
            writer.writerow({k: item.get(k) for k in columns})
    for key, label in (
        ("elapsed_s", "Execution Time (s)"),
        ("throughput_mib_per_s", "Throughput (MiB/s)"),
        ("cpu_percent_one_core_100", "CPU utilization (one core=100%)"),
        ("ram_pss_peak_mib", "Memory PSS peak (MiB)"),
        ("latency_p95_us", "Latency P95 (us)"),
    ):
        # Categorical chart; independent Site count / mode labels.
        valid = [(f"{r['mode']}/{r['site_count']}", r.get(key))
                 for r in runs if isinstance(r.get(key), (int, float))]
        scale = max((float(v) for _, v in valid), default=0.0) or 1.0
        labels = "".join(
            f'<text x="10" y="{76 + i * 34}" font-size="12">{name}</text>'
            f'<rect x="165" y="{62 + i * 34}" height="18" '
            f'width="{max(0., float(value) / scale * 480):.2f}" fill="#3977aa"/>'
            f'<text x="{175 + float(value) / scale * 480:.2f}" '
            f'y="{76 + i * 34}" font-size="11">{float(value):.3f}</text>'
            for i, (name, value) in enumerate(valid))
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="860" '
               f'height="{max(130, 105 + len(valid) * 34)}">'
               f'<text x="10" y="29" font-size="17">{label}</text>'
               f'{labels}</svg>')
        (output / f"{key}.svg").write_text(svg)

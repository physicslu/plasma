"""plasma_hil_timing CLI: LA analysis, /proc trace analysis and summary (Host-only)."""
from __future__ import annotations

import gzip
import json
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "scripts"))
import plasma_hil_timing as timing  # noqa: E402

RATE = 1_000_000  # 1 MHz synthetic capture
PROBES = ("CH0", "CH1", "CH3", "CH4")  # bits 0..3 in capture order


def _write_sr(path: Path, samples: bytes, *, chunk: int = 777) -> None:
    metadata = "\n".join([
        "[global]", "sigrok version=0.6.0", "",
        "[device 1]", "capturefile=logic-1", f"total probes={len(PROBES)}",
        "samplerate=1 MHz", "total analog=0",
        *(f"probe{i + 1}={name}" for i, name in enumerate(PROBES)), "unitsize=1", ""])
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("version", "2")
        archive.writestr("metadata", metadata)
        for index, start in enumerate(range(0, len(samples), chunk), 1):
            archive.writestr(f"logic-1-{index}", samples[start:start + chunk])


def _two_site_capture(length: int, site1: range, site2: range) -> bytes:
    """Site 1 SWCLK=CH3(bit2)/SWDIO=CH4(bit3), Site 2 SWCLK=CH0(bit0)/SWDIO=CH1(bit1);
    a 250 kHz clock (period 4 samples) while each Site is active."""
    data = bytearray(length)
    for index in range(length):
        value = 0
        if index in site1:
            value |= (0b0100 if index % 4 >= 2 else 0) | (0b1000 if index % 16 >= 8 else 0)
        if index in site2:
            value |= (0b0001 if index % 4 >= 2 else 0) | (0b0010 if index % 16 >= 8 else 0)
        data[index] = value
    return bytes(data)


def test_la_analyze_reports_frequency_activity_and_overlap(tmp_path):
    capture = tmp_path / "la.sr"
    _write_sr(capture, _two_site_capture(60_000, range(10_000, 40_000), range(25_000, 50_000)))
    result = timing.analyze_sr(capture, max_period_s=10e-6)
    site1, site2 = result["channels"]["site1"], result["channels"]["site2"]
    assert site1["swclk_freq_median_hz"] == pytest.approx(250_000)
    assert site2["swclk_freq_median_hz"] == pytest.approx(250_000)
    assert site1["active_first_s"] == pytest.approx(0.010, abs=1e-5)
    assert site2["active_first_s"] == pytest.approx(0.025, abs=1e-5)
    assert site1["active_last_s"] == pytest.approx(0.040, abs=1e-5)
    overlap = result["overlap"]
    assert overlap["interval_overlap_s"] == pytest.approx(0.015, abs=1e-4)
    assert overlap["start_gap_s"] == pytest.approx(0.015, abs=1e-5)
    assert overlap["both_active_1ms_windows"] in (15, 16)
    # Chunk boundaries never lose or duplicate an edge.
    assert site1["swclk_rising_edges"] == 30_000 // 4
    assert site1["swdio_edges"] == 2 * 30_000 // 16


def test_la_analyze_matches_reference_numpy_analyzer(tmp_path):
    numpy = pytest.importorskip("numpy")  # the 2026-11-18 evidence analyzer used numpy
    capture = tmp_path / "la.sr"
    _write_sr(capture, _two_site_capture(20_000, range(1_000, 9_000), range(5_000, 15_000)))
    result = timing.analyze_sr(capture)
    data = numpy.frombuffer(b"".join(
        zipfile.ZipFile(capture).read(f"logic-1-{i}")
        for i in range(1, 20_000 // 777 + 2)), dtype=numpy.uint8)
    for site, bit in (("site1", 2), ("site2", 0)):
        rises = numpy.where(numpy.diff(((data >> bit) & 1).astype(numpy.int8)) == 1)[0] + 1
        assert result["channels"][site]["swclk_rising_edges"] == len(rises)
        assert result["channels"][site]["active_first_s"] == rises[0] / RATE


def test_la_analyze_refuses_a_capture_without_the_site_channels(tmp_path):
    capture = tmp_path / "la.sr"
    _write_sr(capture, bytes(100))
    with pytest.raises(SystemExit, match="LA_CHANNELS_NOT_IN_CAPTURE"):
        timing.analyze_sr(capture, {1: ("CH7", "CH8")})


def test_la_capture_dry_run_builds_the_documented_sigrok_command(tmp_path, capsys):
    out = tmp_path / "la.sr"
    assert timing.main(["la-capture", "--output", str(out), "--seconds", "2", "--conn", "1.9",
                        "--sigrok", "/opt/x/kingst.AppImage", "--dry-run"]) == 0
    meta = json.loads((tmp_path / "la.sr.capture.json").read_text())
    assert meta["argv"] == ["/opt/x/kingst.AppImage", "--appimage-extract-and-run",
                            "-d", "kingst-la2016:conn=1.9", "-C", "CH0,CH1,CH3,CH4",
                            "--config", "samplerate=20m:voltage_threshold=1.4-1.4",
                            "--time", "2000", "-o", str(out)]


def _fake_proc(root: Path, pid: int, cmd: str, *, state="R", wchan="0", cpu=5, tids=()):
    base = root / str(pid)
    (base / "task").mkdir(parents=True)
    (base / "cmdline").write_bytes(cmd.replace(" ", "\0").encode())
    for tid in (pid, *tids):
        task = base / "task" / str(tid)
        task.mkdir()
        fields = [state, "1"] + ["0"] * 9 + [str(cpu), "0"] + ["0"] * 6 + ["4242"]
        (task / "stat").write_text(f"{tid} (python3) " + " ".join(fields))
        (task / "wchan").write_text(wchan)


def test_proc_sample_reads_matching_processes_and_server_threads(tmp_path):
    _fake_proc(tmp_path, 10, "/opt/plasma/python3 /opt/plasma/current/runtime/ppu/ppu.pyz server",
               tids=(11,))
    _fake_proc(tmp_path, 20, "python3 plasma_swd_site_admission.py admit 1",
               state="S", wchan="flock_lock_inode_wait")
    _fake_proc(tmp_path, 30, "/usr/sbin/sshd -D")
    rows = timing.proc_sample(proc=str(tmp_path))
    assert sorted((r[0], r[1]) for r in rows) == [(10, 10), (10, 11), (20, 20)]
    admission = next(r for r in rows if r[0] == 20)
    assert admission[2] == "S" and admission[4] == 4242 and admission[6] == "flock_lock_inode_wait"


def test_proc_analyze_reports_lifetimes_waits_and_server_cpu(tmp_path):
    trace = tmp_path / "run.jsonl.gz"
    server = [10, 10, "R", 1, 100, 0, "0", "python3 ppu.pyz server --config x"]
    admit = [20, 20, "R", 9, 200, 0, "0", "python3 -I -B .../plasma_swd_site_admission.py admit 2"]
    samples = []
    for step in range(10):
        rows = [[*server[:5], step * 4, *server[6:]]]
        if 2 <= step <= 5:
            wchan = "flock_lock_inode_wait" if step == 3 else "0"
            rows.append([*admit[:6], wchan, admit[7]])
        samples.append({"t": 1_795_000_000 + step * 0.25, "r": rows})
    with gzip.open(trace, "wt") as stream:
        for sample in samples:
            stream.write(json.dumps(sample) + "\n")
    result = timing.analyze_trace(trace, bucket_s=0.5)
    (process,) = result["processes"]
    assert process["kind"] == "admission" and process["site"] == 2 and process["action"] == "admit"
    assert process["duration_s"] == pytest.approx(0.75)
    assert result["lock_or_uninterruptible_waits"] == {"R:flock_lock_inode_wait": 1}
    assert sum(ticks for _, ticks in result["server_main_thread_cpu_ticks"]) == 36


def _job_log(path: Path, site: int, start: str, phases: dict) -> Path:
    events = [{"event": "job_started", "timestamp": start, "job_id": f"job-{site}", "site_id": site}]
    events += [{"event": "stage_timing", "phase": name, "job_id": f"job-{site}",
                "site_id": site, **fields} for name, fields in phases.items()]
    path.write_text("\n".join(json.dumps(e) for e in events) + "\n")
    return path


def test_summarize_combines_report_job_logs_and_la(tmp_path):
    phases = {"job_admission": {"reserve_ms": 1.0, "active_set_ms": 150.0},
              "queued": {"duration_ms": 300.0}, "load_engine": {"duration_ms": 700.0},
              "load_engine_cache": {"hit": True},
              "site_worker": {"admission_ms": 4300.0, "openocd_ms": 5000.0, "revoke_ms": 500.0,
                              "openocd_start_unix_ms": 1000.0, "admission_root_total": 3300.0}}
    site2 = {**phases, "site_worker": {**phases["site_worker"], "openocd_start_unix_ms": 2200.0}}
    report = {"outcome": "PASS", "batch_id": "b" * 32, "start_id": "s" * 32, "source_sha": "c9e4",
              "site_results": [{"site_id": 1, "job_id": "job-1", "result": "PASS",
                                "elapsed_ms": 13823, "readback_sha256": "e691ab23" + "0" * 56,
                                "safe_off": True}],
              "throughput": {"bytes": 125600, "elapsed_s": 23.5, "bytes_per_s": 5344.7},
              "comparison": {"sampled_pid_overlap_s": 3.5, "overlap_boundary_uncertainty_s": 0.43,
                             "phases": {"idle": {"n": 101, "cpu_pct": {"mean": 50.47, "peak": 100.0},
                                                 "ram_used_kib": {"peak": 140836}}}}}
    (tmp_path / "report.json").write_text(json.dumps(report))
    la = {"samplerate_hz": 2e7, "duration_s": 190.0,
          "channels": {"site1": {"swclk_freq_median_hz": 2e6, "active_first_s": 86.34,
                                 "active_last_s": 91.275}},
          "overlap": {"interval_overlap_s": 3.8166, "both_active_1ms_windows": 1716,
                      "start_gap_s": 1.1184}}
    (tmp_path / "la.json").write_text(json.dumps(la))
    out = tmp_path / "summary.txt"
    assert timing.main([
        "summarize", "--report", str(tmp_path / "report.json"), "--la", str(tmp_path / "la.json"),
        "--job-log", str(_job_log(tmp_path / "2.jsonl", 2, "T2", site2)),
        "--job-log", str(_job_log(tmp_path / "1.jsonl", 1, "T1", phases)),
        "--output", str(out)]) == 0
    text = out.read_text()
    assert "outcome PASS" in text and "5345 B/s" in text
    assert "Site 1 job_started T1" in text.splitlines()[text.splitlines().index(
        next(line for line in text.splitlines() if line.startswith("stage timing"))) + 1]
    assert "site_worker.admission_ms" in text and "site_worker.admission_root_total" in text
    assert "load_engine_cache.hit" in text
    assert "openocd start gap 1.2 s" in text
    assert "SWCLK 2.000 MHz" in text and "start gap 1.118 s" in text

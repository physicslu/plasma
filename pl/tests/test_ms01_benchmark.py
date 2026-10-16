"""MMIO-MS-01 host-only tests. Never opens /dev/mem or accesses a board."""
from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from concurrent.futures import ThreadPoolExecutor

import pytest

from pl.hil.ms01.benchmark import MODES, payload, run_benchmark, save_reports
from plasma_interfaces.mmio_loop_test import (
    ABI_VERSION, CAPABILITIES, CAPACITY, MAGIC,
    REG_ABI, REG_CAPABILITIES, REG_CAPACITY, REG_MAGIC,
    REG_READS, REG_STATUS, REG_WRITES, WINDOW_START,
    LoopTestDriver,
)


class FakePort:
    """Independent 2-KiB register model, deliberately NOT simulated AXI RTL."""

    def __init__(self, base: int) -> None:
        self.base = base
        self.mem = {}
        self.reads = 0
        self.writes = 0
        self.lock = RLock()

    def read32(self, addr: int) -> int:
        offset = addr - self.base
        with self.lock:
            meta = {REG_MAGIC: MAGIC, REG_ABI: ABI_VERSION,
                    REG_CAPABILITIES: CAPABILITIES, REG_CAPACITY: CAPACITY,
                    REG_STATUS: 1, REG_READS: self.reads,
                    REG_WRITES: self.writes}
            if offset in meta:
                return meta[offset]
            if WINDOW_START <= offset < WINDOW_START + CAPACITY and offset % 4 == 0:
                self.reads += 1
                return self.mem[offset]
        raise AssertionError(f"unexpected fake read: {addr:#x}")

    def write32(self, addr: int, value: int) -> None:
        offset = addr - self.base
        with self.lock:
            if not WINDOW_START <= offset < WINDOW_START + CAPACITY or offset % 4:
                raise AssertionError("unexpected fake write")
            self.mem[offset] = value
            self.writes += 1


def drivers(n: int) -> tuple[dict[int, LoopTestDriver], list[FakePort]]:
    ports = [FakePort(0x40004000 + i * 0x1000) for i in range(n)]
    return {i + 1: LoopTestDriver(p, base=p.base, site_id=i + 1)
            for i, p in enumerate(ports)}, ports


@pytest.mark.parametrize("size", [1, 5, 2048, 2049, 8193])
def test_unique_deterministic_payloads(size):
    first = payload(1, 0, size)
    assert first == payload(1, 0, size)
    if size:
        assert first != payload(2, 0, size)
        assert first != payload(1, 1, size)


@pytest.mark.parametrize("mode", MODES)
def test_two_site_exact_echo_host(mode):
    site_drivers, ports = drivers(2)
    result = run_benchmark(site_drivers, mode=mode,
                           iterations=3, payload_bytes=2049)
    assert result["status"] == "PASS"
    assert result["site_count"] == 2
    assert result["case_count"] == 6
    assert result["total_bytes"] == 6 * 2049
    assert len(result["site_metrics"]) == 2
    assert len(result["cases"]) == 6
    assert result["cpu_percent_one_core_100"] >= 0
    assert result["elapsed_s"] > 0
    assert result["throughput_mib_per_s"] > 0
    expected_words = 512 + 1
    for p in ports:
        assert p.reads == p.writes == expected_words * 3


def test_eight_site_independent_host_threads():
    site_drivers, ports = drivers(8)
    result = run_benchmark(site_drivers, mode="thread",
                           iterations=2, payload_bytes=1025)
    assert result["case_count"] == 16
    assert result["site_count"] == 8
    assert all(p.reads == p.writes == 2 * 257 for p in ports)


def test_invalid_bounds_are_rejected_before_any_data_access():
    ds, ports = drivers(2)
    for kw in [
        dict(mode="direct", iterations=2, payload_bytes=2048),
        dict(mode="thread", iterations=0, payload_bytes=2048),
        dict(mode="thread", iterations=2, payload_bytes=0),
        dict(mode="thread", iterations=2, payload_bytes=1048577),
    ]:
        with pytest.raises(ValueError):
            run_benchmark(ds, **kw)
    assert all(p.reads == p.writes == 0 for p in ports)


def test_corrupted_hardware_counter_stops_without_retry():
    ds, ports = drivers(1)
    def missing_count(addr: int, value: int):
        ports[0].mem[addr - ports[0].base] = value
    ports[0].write32 = missing_count
    with pytest.raises(RuntimeError, match="STOP"):
        run_benchmark(ds, mode="thread", iterations=2, payload_bytes=4)
    assert ds[1].poisoned


def test_save_reports_is_immutable_and_renders_charts(tmp_path: Path):
    ds, _ = drivers(2)
    result = run_benchmark(ds, mode="thread", iterations=1, payload_bytes=5)
    output = tmp_path / "evidence"
    save_reports([result], output)
    assert json.loads((output / "benchmark.json").read_text())[0]["status"] == "PASS"
    assert "throughput_mib_per_s" in (output / "benchmark.csv").read_text()
    assert "<svg" in (output / "elapsed_s.svg").read_text()
    with pytest.raises(FileExistsError):
        save_reports([result], output)

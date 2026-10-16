"""Host-only injected-port tests for LT02-05 repeatable HIL vectors."""
from __future__ import annotations

import pytest
from pathlib import Path
import sys

# General PL source CI executes `pytest pl/tests` without installing the PPU
# package. Make the REAL production driver module importable in that runner.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "software/python"))

from pl.hil.lt02 import cases
from plasma_interfaces.mmio_loop_test import (
    MAGIC, ABI_VERSION, CAPABILITIES, CAPACITY, WINDOW_START,
    REG_MAGIC, REG_ABI, REG_CAPABILITIES, REG_CAPACITY,
    REG_STATUS, REG_WRITES, REG_READS, LoopTestError,
)


class MemoryPort:
    def __init__(self, *, corrupt=False):
        self.regs = {
            REG_MAGIC: MAGIC, REG_ABI: ABI_VERSION,
            REG_CAPABILITIES: CAPABILITIES, REG_CAPACITY: CAPACITY,
            REG_STATUS: 1,
        }
        self.data = {}
        self.reads = self.writes = 0
        self.corrupt = corrupt
        self.events = []

    def read32(self, address):
        offset = address - cases.BASE
        self.events.append(("read", offset))
        if offset == REG_WRITES:
            return self.writes
        if offset == REG_READS:
            return self.reads
        if WINDOW_START <= offset < WINDOW_START + CAPACITY:
            self.reads += 1
            word = self.data[offset]
            return word ^ (1 if self.corrupt else 0)
        return self.regs[offset]

    def write32(self, address, value):
        offset = address - cases.BASE
        assert WINDOW_START <= offset < WINDOW_START + CAPACITY
        self.events.append(("write", offset))
        self.writes += 1
        self.data[offset] = value


def test_vectors_production_driver_integrity_and_counter_evidence():
    hw = MemoryPort()
    result = cases.run_suite(hw)
    assert result["transport_suite"] == "PASS"
    assert result["real_hardware_proven"] is False
    assert result["original_image_restoration"] == "NOT_RUN"
    assert len(result["cases"]) == len(cases.CASES)
    assert [c["bytes"] for c in result["cases"]] == [
        1, 1023, 1024, 1025, 2048, 2049, 4097, 8192, 8192,
    ]
    words = sum(item["words"] for item in result["cases"])
    assert hw.writes == hw.reads == words
    assert all(r["result"] == "PASS" and r["crc32"] for r in result["cases"])
    assert result["cases"][-1]["crc32"] == result["cases"][-2]["crc32"]


def test_mismatch_stops_at_first_case_without_retried_writes():
    hw = MemoryPort(corrupt=True)
    with pytest.raises(LoopTestError, match="payload mismatch"):
        cases.run_suite(hw)
    assert hw.writes == 1
    assert hw.reads == 1


def test_wrong_identity_causes_zero_writes():
    hw = MemoryPort()
    hw.regs[REG_MAGIC] = 0
    with pytest.raises(LoopTestError, match="register"):
        cases.run_suite(hw)
    assert hw.writes == 0


def test_nonexistent_site_is_rejected_before_access():
    hw = MemoryPort()
    with pytest.raises(LoopTestError, match="Site 1"):
        cases.run_suite(hw, site_id=2)
    assert hw.events == []

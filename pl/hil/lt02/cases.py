"""Deterministic LT02-05 acceptance vectors for the production LoopTestDriver.

Pure injected-port function, not a /dev/mem or FPGA loading entrypoint.
A fixture test of this module is HOST ONLY; physical Z2 proof additionally
requires an operator-approved live harness and separate restoration evidence.
"""
from __future__ import annotations

import zlib

from plasma_interfaces.mmio_loop_test import LoopTestDriver, LoopTestError

BASE = 0x40004000
CASES = (
    ("single", 1, 17),
    ("boundary_1023", 1023, 31),
    ("boundary_1024", 1024, 47),
    ("boundary_1025", 1025, 63),
    ("full_window", 2048, 79),
    ("cross_window", 2049, 95),
    ("multi_window", 4097, 111),
    ("repeat_a", 8192, 127),
    ("repeat_b", 8192, 127),
)


def payload_bytes(length: int, seed: int) -> bytes:
    """Counterexample-friendly deterministic nonconstant bytes, no IO."""
    return bytes(((i * 131 + (i >> 3) * 17 + seed) & 0xFF)
                 for i in range(length))


def run_suite(port, *, site_id: int = 1) -> dict:
    """One HIL Site lease, one production driver, no retries or mock fallback.

    Caller MUST independently attest loaded image/ownership before injection.
    This function cannot prove which device implements the supplied port.
    """
    driver = LoopTestDriver(port, base=BASE, site_id=site_id)
    cases = []
    for label, length, seed in CASES:
        data = payload_bytes(length, seed)
        response = driver.echo(data)
        tx = f"{zlib.crc32(data):08x}"
        if (response.payload != data or
                response.payload_length != length or
                response.tx_crc32 != tx or response.rx_crc32 != tx or
                response.elapsed_ns < 0):
            raise LoopTestError("LT02 acceptance mismatch: " + label)
        expected_chunks = (length + 2047) // 2048
        expected_words = sum(
            (min(2048, length - i) + 3) // 4
            for i in range(0, length, 2048)
        )
        if (response.chunks != expected_chunks or
                response.data_word_writes != expected_words or
                response.data_word_reads != expected_words):
            raise LoopTestError("LT02 acceptance counter mismatch: " + label)
        throughput = (length * 1_000_000_000 / response.elapsed_ns
                      if response.elapsed_ns else None)
        cases.append({
            "name": label, "bytes": length, "crc32": tx,
            "chunks": expected_chunks, "words": expected_words,
            "elapsed_ns": response.elapsed_ns,
            "observed_bytes_per_second": throughput,
            "result": "PASS",
        })
    return {
        "qualification": "LT02-05",
        "source": "INJECTED_PRODUCTION_DRIVER_REQUIRES_SEPARATE_HARDWARE_PROOF",
        "site_id": site_id, "cases": cases,
        "transport_suite": "PASS", "original_image_restoration": "NOT_RUN",
        "real_hardware_proven": False, "electrical_dut": "NOT_RUN",
    }

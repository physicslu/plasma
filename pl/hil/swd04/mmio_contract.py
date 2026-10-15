"""SWD-04 bounded AXI MMIO test logic. No real hardware backend in this module.

A caller must independently establish FPGA ownership/loading, recovery
readiness and OS isolation before connecting this logic to real MMIO.
An OS timeout cannot guarantee recovery from a stalled AXI bus.
"""
from __future__ import annotations

import time
from typing import Protocol

from pl.hil.swd04.contract import (
    AXI_BASES, COMMAND, CONFIG, DPIDR, HALF, IDENTITY_OFFSETS, META,
    RDATA, READ_WHITELIST, READY, RESP_VALID, STATUS, WRITE_WHITELIST,
    SOURCE_SHA, SafetyError,
)


class MMIO(Protocol):
    def read32(self, address: int) -> int: ...
    def write32(self, address: int, value: int) -> None: ...


class RestrictedMMIO:
    """No unchecked address, command, config or data writes."""

    def __init__(self, backend: MMIO) -> None:
        self.backend = backend
        self.audit: list[tuple[str, int, int]] = []

    def read(self, address: int) -> int:
        if type(address) is not int or address not in READ_WHITELIST:
            raise SafetyError(f"MMIO read not whitelisted: {address!r}")
        value = self.backend.read32(address)
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise SafetyError("MMIO backend returned invalid 32-bit word")
        self.audit.append(("read", address, value))
        return value

    def write(self, address: int, value: int) -> None:
        if type(address) is not int or address not in WRITE_WHITELIST:
            raise SafetyError(f"MMIO write not whitelisted: {address!r}")
        if type(value) is not int or not 0 <= value <= 0xFFFFFFFF:
            raise SafetyError("MMIO write requires a 32-bit unsigned integer")
        allowed_values = {
            COMMAND: (1, 2, 4),  # START, ABORT, explicit RESPONSE ACK
            CONFIG: (0, 4, 5),  # DP write (fixture-only), DP read, line reset
            HALF: (2, 9),
        }
        if value not in allowed_values[address]:
            raise SafetyError("MMIO write value not whitelisted")
        self.backend.write32(address, value)
        self.audit.append(("write", address, value))


def _expect_equal(actual: int, expected: int, message: str) -> None:
    if actual != expected:
        raise SafetyError(
            f"{message}: expected=0x{expected:08X} actual=0x{actual:08X}")


def hil01_registers(io: RestrictedMMIO) -> dict[str, int]:
    """Read-only, exact-value register checks; no writes or speculative probes."""
    identity = AXI_BASES["identity_0"]
    expected = (
        0x504C534D, 0x00000100, 1, 0,
        *(int(SOURCE_SHA[i:i + 8], 16) for i in range(0, 32, 8)),
    )
    assert len(expected) == len(IDENTITY_OFFSETS)
    result: dict[str, int] = {}
    for offset, word in zip(IDENTITY_OFFSETS, expected):
        addr = identity + offset
        value = io.read(addr)
        _expect_equal(value, word, f"Identity +{offset:#x}")
        result[f"identity_0+{offset:02x}"] = value

    reads = (
        ("control_status", AXI_BASES["control_0"] + 0x04, 0xA5A55A5A),
        ("swd_waveform_abi", AXI_BASES["swd_0"], 1),
        ("swd_waveform_status", AXI_BASES["swd_0"] + 0x1C, 0),
        ("transaction_abi", AXI_BASES["transaction_0"], 1),
        ("transaction_config", CONFIG, 4),
        ("transaction_half", HALF, 2),
        ("transaction_turn", AXI_BASES["transaction_0"] + 0x14, 1),
        ("transaction_idle", AXI_BASES["transaction_0"] + 0x18, 8),
        ("transaction_retries", AXI_BASES["transaction_0"] + 0x1C, 0),
        ("transaction_timeout", AXI_BASES["transaction_0"] + 0x20, 1_000_000),
        ("transaction_status", STATUS, READY),
        ("transaction_meta", META, 0),
        ("transaction_rdata", RDATA, 0),
    )
    for name, addr, expected_value in reads:
        value = io.read(addr)
        _expect_equal(value, expected_value, name)
        result[name] = value
    return result


def _response(io: RestrictedMMIO, *, limit: int = 10000,
              sleep_seconds: float = 0.0005) -> tuple[int, int]:
    """A polling bound; DOES NOT bound a blocked physical AXI read."""
    if not 1 <= limit <= 10000 or not 0 <= sleep_seconds <= 0.01:
        raise ValueError("Invalid polling budget")
    for _ in range(limit):
        status = io.read(STATUS)
        if status & RESP_VALID:
            if status & READY:
                raise SafetyError("RESP_VALID and READY both set")
            meta = io.read(META)
            data = io.read(RDATA)
            for _ in range(3):
                _expect_equal(io.read(META), meta, "Held response metadata")
                _expect_equal(io.read(RDATA), data, "Held response data")
            return meta, data
        if sleep_seconds:
            time.sleep(sleep_seconds)
    raise SafetyError("SWD response poll budget exhausted; STOP, do not retry")


def _ack(io: RestrictedMMIO) -> None:
    io.write(COMMAND, 4)
    _expect_equal(io.read(STATUS) & (READY | RESP_VALID), READY,
                  "Response acknowledgment state")


def _run_reset(io: RestrictedMMIO) -> int:
    io.write(CONFIG, 5)
    io.write(COMMAND, 1)
    meta, data = _response(io)
    _expect_equal(meta & 0xF, 0, "Line reset completion")
    _expect_equal(data, 0, "Line reset RDATA")
    _ack(io)
    return meta


def _run_dpidr(io: RestrictedMMIO) -> tuple[int, int]:
    io.write(CONFIG, 4)
    io.write(COMMAND, 1)
    meta, data = _response(io)
    _expect_equal(meta & 0xF, 0, "DPIDR transport status")
    _expect_equal((meta >> 4) & 7, 1, "DPIDR ACK")
    _expect_equal((meta >> 7) & 1, 1, "DPIDR DATA_VALID")
    _expect_equal((meta >> 8) & 0x1FF, 1, "DPIDR transfer attempts")
    _expect_equal(data, DPIDR, "DPIDR response")
    _ack(io)
    return meta, data


def hil02_dpidr(io: RestrictedMMIO) -> dict[str, object]:
    _expect_equal(io.read(STATUS), READY, "Initial SWD-03 status")
    line_meta = _run_reset(io)
    dp_meta, dp_data = _run_dpidr(io)
    return {"line_reset": "PASS", "line_reset_meta": line_meta,
            "dpidr": f"0x{dp_data:08X}", "dpidr_meta": dp_meta,
            "dpidr_data_valid": (dp_meta >> 7) & 1,
            "response_retention": "PASS"}


def hil03_recovery(io: RestrictedMMIO) -> dict[str, object]:
    """Only internal fixture; never writes DUT flash or changes Z2 reset."""
    _expect_equal(io.read(STATUS) & (READY | RESP_VALID), READY,
                  "HIL-03 precondition")
    io.write(CONFIG, 0)  # DP write; no external target connected
    io.write(HALF, 9)  # allow deterministic in-flight ABORT observation
    io.write(COMMAND, 1)
    status = io.read(STATUS)
    if not status & 1:
        raise SafetyError("Expected BUSY before software ABORT")
    io.write(COMMAND, 2)
    meta, _ = _response(io)
    _expect_equal(meta & 0xF, 8, "ABORTED transport status")
    _ack(io)
    io.write(HALF, 2)
    reset_meta = _run_reset(io)
    dp_responses = [_run_dpidr(io) for _ in range(3)]
    return {"abort": "PASS", "aborted_meta": meta,
            "line_reset_recovery": "PASS", "line_reset_meta": reset_meta,
            "repeated_dpidr": len(dp_responses),
            "repeat_meta": [x[0] for x in dp_responses],
            "repeat_rdata": [f"0x{x[1]:08X}" for x in dp_responses]}


def run_all(io: RestrictedMMIO, *, include_hil03: bool = False) -> dict[str, object]:
    """Fail immediately on the first mismatch. No catch-and-retry."""
    result = {"HIL01": hil01_registers(io), "HIL02": hil02_dpidr(io)}
    if include_hil03:
        result["HIL03"] = hil03_recovery(io)
    return result

"""Exact PSPL-02/SWD-00 tests shared by Cocotb and an explicitly armed live runner.

No device backend is opened here. Poll limits cannot bound a stalled AXI access.
"""
from __future__ import annotations

import time
from pl.hil.pspl02.contract import SOURCE, SafetyError, _require

IDENTITY, CONTROL, SWD = 0x40000000, 0x40001000, 0x40002000
CMD, TX, COUNT, HALF, DRIVE, RX, STATUS, ERROR, MODE, PATTERN = (SWD+x for x in range(4, 44, 4))
READS = frozenset({IDENTITY+x for x in range(0, 32, 4)}
                  | {CONTROL, CONTROL+4} | {SWD+x for x in range(0, 44, 4)})
WRITES = frozenset({CONTROL, CMD, TX, COUNT, HALF, DRIVE, MODE, PATTERN})


class RestrictedMMIO:
    def __init__(self, backend, *, readonly=False):
        self.backend, self.readonly = backend, readonly
        self.audit = []

    def read(self, address):
        _require(type(address) is int and address in READS, "Unlisted MMIO read")
        self.audit.append({"op": "read", "address": address, "state": "attempted"})
        value = self.backend.read32(address)
        _require(type(value) is int and 0 <= value <= 0xffffffff, "Invalid MMIO result")
        self.audit[-1].update(state="completed", value=value)
        return value

    def write(self, address, value):
        _require(not self.readonly, "Read-only phase")
        _require(type(address) is int and address in WRITES, "Unlisted MMIO write")
        _require(type(value) is int and 0 <= value <= 0xffffffff, "Invalid MMIO word")
        allowed = {CMD: (1, 2, 4), COUNT: (1, 7, 8, 32), HALF: (2, 65535),
                   DRIVE: (0, 1), MODE: (0, 1)}
        _require(address not in allowed or value in allowed[address], "Unlisted MMIO value")
        self.audit.append({"op": "write", "address": address, "value": value,
                           "state": "attempted"})
        self.backend.write32(address, value)
        self.audit[-1]["state"] = "completed"


def expect(actual, expected, label):
    _require(actual == expected, f"{label}: expected {expected:#x}, got {actual:#x}")


def identity(io):
    words = [0x504c534d, 0x100, 1, 0]
    words += [int(SOURCE[i:i+8], 16) for i in range(0, 32, 8)]
    for i, word in enumerate(words):
        expect(io.read(IDENTITY + 4*i), word, "Identity")
    expect(io.read(SWD), 1, "SWD command ABI")
    return {"identity_words": words, "swd_abi": 1}


def pspl02(io):
    for value in (0, 0xffffffff, 0xaaaaaaaa, 0x55555555, 0x12345678, 0):
        io.write(CONTROL, value)
        expect(io.read(CONTROL), value, "CONTROL")
        expect(io.read(CONTROL+4), value ^ 0xa5a55a5a, "STATUS")
    return {"HIL-PSPL-02A": "PASS", "HIL-PSPL-02B": "PASS"}


def configure(io, *, tx, count, drive, mode, pattern, half=2):
    for address, value in ((TX, tx), (COUNT, count), (HALF, half), (DRIVE, drive),
                           (MODE, mode), (PATTERN, pattern)):
        io.write(address, value)


def completion(io, *, limit=1000, sleep_seconds=0.001):
    _require(type(limit) is int and 1 <= limit <= 1000
             and 0 <= sleep_seconds <= 0.001, "Invalid polling budget")
    for _ in range(limit):
        status = io.read(STATUS)
        _require(not status & 4, "Unexpected sticky ERROR")
        if status & 2:
            expect(status & 1, 0, "BUSY after DONE")
            return
        if sleep_seconds:
            time.sleep(sleep_seconds)
    raise SafetyError("Completion budget exhausted; stop without retry")


def swd00(io):
    results = []
    for tx, count, drive, mode, pattern in (
        (0xa6, 8, 1, 0, 0), (0x87654321, 32, 1, 1, 0x5ac3960f),
        (0x55, 7, 0, 1, 0x2d), (0, 32, 0, 0, 0),
    ):
        io.write(CMD, 2)
        expect(io.read(STATUS) & 7, 0, "CLEAR")
        configure(io, tx=tx, count=count, drive=drive, mode=mode, pattern=pattern)
        io.write(CMD, 1)
        completion(io)
        expected = (pattern if mode else tx if drive else 0xffffffff) & ((1 << count)-1)
        for _ in range(3):
            expect(io.read(STATUS) & 7, 2, "Persistent DONE")
            expect(io.read(RX), expected, "RX")
        io.write(CMD, 2)
        expect(io.read(STATUS) & 7, 0, "Explicit CLEAR")
        expect(io.read(RX), expected, "RX retained across CLEAR")
        results.append(expected)
    return {"HIL-SWD-00A": "PASS", "HIL-SWD-00B": "PASS", "rx_vectors": results}


def error_handling(io):
    """Expected SLVERR may abort a real CPU; runner must stop if it does.

    Cocotb consumes and checks SLVERR. A live backend does not promise an AXI
    response observation or catch SIGBUS. No invalid/unmapped address is used.
    """
    io.write(CMD, 4)  # Count resets to zero, intentionally invalid for START.
    io.write(CMD, 1)
    expect(io.read(STATUS) & 7, 4, "Rejected START ERROR")
    for _ in range(3):
        expect(io.read(ERROR), 3, "Persistent configuration error")
        expect(io.read(RX), 0, "Rejected START preserved RX")
    io.write(CMD, 2)
    expect(io.read(ERROR), 0, "CLEAR error")
    expect(io.read(STATUS) & 7, 0, "CLEAR flags")
    return {"HIL-SWD-00C": "PASS"}


def reset_recovery(io):
    # 32 * 2 * 65535 / 100MHz ~= 42ms. If scheduling misses BUSY, STOP.
    configure(io, tx=0xffffffff, count=32, drive=1, mode=0, pattern=0, half=65535)
    io.write(CMD, 1)
    _require(io.read(STATUS) & 1, "BUSY not observed; do not retry")
    io.write(CMD, 4)
    for address, expected in ((TX, 0), (COUNT, 0), (HALF, 2), (DRIVE, 0),
                              (RX, 0), (STATUS, 0), (ERROR, 0), (MODE, 0), (PATTERN, 0)):
        expect(io.read(address), expected, "RESET defaults")
    swd00(io)
    io.write(CMD, 4)
    return {"HIL-SWD-00D": "PASS"}


RUNNERS = {"IDENTITY": identity, "PSPL02": pspl02, "SWD00": swd00,
           "ERROR": error_handling, "RESET": reset_recovery}

"""Run the PRODUCTION C SWD FIFO core against the real ABI-v5 Site RTL.

pl/AGENTS.md §4A: one PS control implementation exercised by both the Z2
(Linux MMIO backend) and Cocotb (this AXI bus-functional-model backend).
``software/native/swd/plasma_swd_fifo_core.c`` is compiled unmodified into a
shared library; its ``struct plasma_swd_word_io`` read32/write32/
write_barrier callbacks are bound to AXI4-Lite transactions on the RTL.

Execution model: every C entry point runs in a ``cocotb.external`` thread.
Each MMIO callback blocks that thread on a ``cocotb.function`` AXI
transaction, so the C code sees an ordinary synchronous bus while the
simulator advances. Host-only: this proves C <-> RTL transaction behaviour,
NOT ARMv7 access width, PS7/AXI Interconnect, Linux mapping or Z2 HIL.
"""
import ctypes
import os
import sys
from ctypes import (CFUNCTYPE, POINTER, Structure, byref, c_bool, c_int,
                    c_size_t, c_uint, c_uint8, c_uint16, c_uint32, c_void_p)
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import FallingEdge, RisingEdge, Timer

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "models"))
from virtual_swd_target import VirtualSWDTarget  # noqa: E402

SITE2_BASE = 0x43C02000
MAX_QUEUE = 256

# enum plasma_swd_result
OK, BAD_ARG, NOT_READY, IO_UNCERTAIN = 0, -1, -2, -3
BAD_RESPONSE, ACK_WAIT, ACK_FAULT, QUEUE_FULL, UNSUPPORTED = -4, -5, -6, -7, -8

READ_CB = CFUNCTYPE(c_int, c_void_p, c_uint32, POINTER(c_uint32))
WRITE_CB = CFUNCTYPE(c_int, c_void_p, c_uint32, c_uint32)
BARRIER_CB = CFUNCTYPE(c_int, c_void_p)


class WordIO(Structure):
    _fields_ = [("ctx", c_void_p), ("read32", READ_CB),
                ("write32", WRITE_CB), ("write_barrier", BARRIER_CB)]


class QueueOp(Structure):
    _fields_ = [("private_command", c_uint8), ("is_swj", c_bool),
                ("read", c_bool), ("value", c_uint32),
                ("destination", POINTER(c_uint32)), ("bit_count", c_uint16),
                ("idle_cycles", c_uint8), ("swj_bytes", c_uint8 * 32)]


class Fifo(Structure):
    _fields_ = [("io", WordIO), ("base", c_uint32), ("max_polls", c_uint32),
                ("next_tag", c_uint32), ("count", c_uint32),
                ("idle_cycles", c_uint32), ("deferred_rc", c_int),
                ("discarded", c_bool), ("admitted", c_bool),
                ("blocked", c_bool), ("last_meta", c_uint32),
                ("last_levels", c_uint32),
                ("pending", QueueOp * MAX_QUEUE)]


class EdgePhaseTarget(VirtualSWDTarget):
    """VirtualSWDTarget with real-target / OpenOCD bitbang edge phase.

    The base fixture puts ACK[0] on the wire one SWCLK rising edge AFTER the
    turnaround edge (historical HIGH-end sampler). A real target drives
    ACK[0] from the turnaround rising edge, and the ABI-v5 RTL samples in the
    LOW window before the next rising edge (see test_swd_abi5_edge_phase).
    The leading turnaround slot therefore moves behind the ACK: ACK[2] is
    held through the clock in which the host samples it, then the write
    turnaround follows, and write data is sampled on the host's 33
    data/parity rising edges. Read data and parity keep their order.
    """

    def _response(self):
        super()._response()
        for _ in range(self.turnaround):
            assert self.pending[0][2] == "turn_in"
            self.pending.popleft()
        if self.after_response == "write":
            self.pending.extend([(False, 1, "turn_write")] * self.turnaround)


def load_library():
    path = os.environ["PLASMA_SWD_C_CORE_SO"]
    lib = ctypes.CDLL(path)
    lib.plasma_swd_test_layout.restype = c_size_t
    lib.plasma_swd_test_layout.argtypes = [c_uint]
    expected = [ctypes.sizeof(Fifo), ctypes.sizeof(QueueOp),
                Fifo.base.offset, Fifo.deferred_rc.offset,
                Fifo.blocked.offset, Fifo.last_meta.offset,
                Fifo.pending.offset]
    actual = [lib.plasma_swd_test_layout(i) for i in range(len(expected))]
    assert actual == expected, ("ctypes mirror drifted", actual, expected)
    fifo_p = POINTER(Fifo)
    signatures = {
        "plasma_swd_fifo_init": [fifo_p, POINTER(WordIO), c_uint, c_uint32],
        "plasma_swd_fifo_admit": [fifo_p],
        "plasma_swd_fifo_queue_read": [fifo_p, c_uint8, POINTER(c_uint32),
                                       c_uint32],
        "plasma_swd_fifo_queue_write": [fifo_p, c_uint8, c_uint32, c_uint32],
        "plasma_swd_fifo_set_half_period": [fifo_p, c_uint32],
        "plasma_swd_fifo_queue_swj": [fifo_p, POINTER(c_uint8), c_uint16],
        "plasma_swd_fifo_queue_line_reset": [fifo_p],
        "plasma_swd_fifo_recover_off": [fifo_p, POINTER(c_int)],
        "plasma_swd_fifo_run": [fifo_p],
    }
    for name, argtypes in signatures.items():
        fn = getattr(lib, name)
        fn.argtypes = argtypes
        fn.restype = c_int
    return lib


def slot(array, index):
    """uint32_t * to array[index] for an OpenOCD-style read destination."""
    return ctypes.cast(ctypes.addressof(array) + 4 * index, POINTER(c_uint32))


def swd_cmd(read, ap, reg):
    """OpenOCD 0.12 swd_cmd(): no START/STOP/PARK bits."""
    cmd = (0x02 if ap else 0) | (0x04 if read else 0) | ((reg & 0xC) << 1)
    if bin(cmd).count("1") & 1:
        cmd |= 0x20
    return cmd


DP_DPIDR_R = swd_cmd(True, False, 0)
DP_ABORT_W = swd_cmd(False, False, 0)
DP_CTRL_R = swd_cmd(True, False, 4)
DP_CTRL_W = swd_cmd(False, False, 4)
DP_SELECT_W = swd_cmd(False, False, 8)
DP_RDBUFF_R = swd_cmd(True, False, 0xC)
AP0_W = swd_cmd(False, True, 0)
AP0_R = swd_cmd(True, True, 0)


class Bench:
    """AXI BFM + clocked SWD target + ctypes-bound production C core."""

    def __init__(self, dut, lib):
        self.d = dut
        self.lib = lib
        self.target = EdgePhaseTarget()
        self.log = []          # (op, offset, value, resp) for every MMIO
        self.errors = []       # exceptions raised inside C callbacks
        self.max_cmd_level = 0
        self.swclk_rises = 0
        self._read_sync = cocotb.function(self._axi_read)
        self._write_sync = cocotb.function(self._axi_write)
        # Keep CFUNCTYPE objects alive for the C pointers' lifetime.
        self._cb_read = READ_CB(self._c_read32)
        self._cb_write = WRITE_CB(self._c_write32)
        self._cb_barrier = BARRIER_CB(self._c_barrier)
        self.io = WordIO(None, self._cb_read, self._cb_write,
                         self._cb_barrier)
        self.fifo = Fifo()

    # ---- simulator side -------------------------------------------------
    async def start(self):
        d = self.d
        cocotb.start_soon(Clock(d.clk, 10, units="ns").start())
        d.rst_n.value = 0
        for name in ("awaddr", "awprot", "awvalid", "wdata", "wstrb",
                     "wvalid", "bready", "araddr", "arprot", "arvalid",
                     "rready", "target_oe", "target_out"):
            getattr(d, name).value = 0
        for _ in range(4):
            await FallingEdge(d.clk)
        d.rst_n.value = 1
        await FallingEdge(d.clk)
        cocotb.start_soon(self._target_driver())

    async def _target_driver(self):
        d = self.d
        site = d.u_site
        last = 0
        while True:
            await RisingEdge(d.clk)
            await Timer(1, units="ns")
            level = int(site.cmd_level_q.value)
            self.max_cmd_level = max(self.max_cmd_level, level)
            host_oe = int(site.drive_oe.value)
            clock = int(d.swclk_io.value)
            if clock and not last:
                self.swclk_rises += 1
                drive, value = self.target.rising(host_oe,
                                                  int(site.drive_out.value))
                d.target_oe.value = int(drive)
                d.target_out.value = int(value)
            assert not (host_oe and int(d.target_oe.value)), \
                "SWDIO contention between RTL and target"
            last = clock

    async def _axi_write(self, address, value):
        d = self.d
        await FallingEdge(d.clk)
        d.awaddr.value = address
        d.awvalid.value = 1
        d.wdata.value = value
        d.wstrb.value = 0xF
        d.wvalid.value = 1
        d.bready.value = 1
        for _ in range(200):
            await Timer(1, units="ns")
            aw = int(d.awvalid.value) and int(d.awready.value)
            w = int(d.wvalid.value) and int(d.wready.value)
            b = int(d.bvalid.value)
            resp = int(d.bresp.value)
            await FallingEdge(d.clk)
            if aw:
                d.awvalid.value = 0
            if w:
                d.wvalid.value = 0
            if b:
                d.bready.value = 0
                return resp
        raise AssertionError("AXI write handshake timeout")

    async def _axi_read(self, address):
        d = self.d
        await FallingEdge(d.clk)
        d.araddr.value = address
        d.arvalid.value = 1
        d.rready.value = 1
        for _ in range(200):
            await Timer(1, units="ns")
            ar = int(d.arvalid.value) and int(d.arready.value)
            r = int(d.rvalid.value)
            data, resp = int(d.rdata.value), int(d.rresp.value)
            await FallingEdge(d.clk)
            if ar:
                d.arvalid.value = 0
            if r:
                d.rready.value = 0
                return resp, data
        raise AssertionError("AXI read handshake timeout")

    async def read(self, offset):
        return await self._axi_read(SITE2_BASE + offset)

    async def write(self, offset, value):
        return await self._axi_write(SITE2_BASE + offset, value)

    # ---- C callbacks (run in the cocotb.external thread) -----------------
    def _c_read32(self, _ctx, address, value_p):
        try:
            resp, data = self._read_sync(address)
            self.log.append(("r", address - SITE2_BASE, data, resp))
            if resp:
                return -1
            value_p[0] = data
            return 0
        except BaseException as exc:  # never let ctypes swallow a failure
            self.errors.append(exc)
            return -1

    def _c_write32(self, _ctx, address, value):
        try:
            resp = self._write_sync(address, value)
            self.log.append(("w", address - SITE2_BASE, value, resp))
            return -1 if resp else 0
        except BaseException as exc:
            self.errors.append(exc)
            return -1

    def _c_barrier(self, _ctx):
        # Each AXI write above already waited for its B response.
        self.log.append(("b", None, None, 0))
        return 0

    # ---- production C API ----------------------------------------------
    async def call(self, name, *args):
        fn = getattr(self.lib, name)
        fifo = byref(self.fifo)

        def blocking():  # ctypes pointers have no __qualname__ for external
            return fn(fifo, *args)
        rc = await cocotb.external(blocking)()
        assert not self.errors, self.errors
        return rc

    async def init(self, site_id=2, max_polls=200000):
        rc = self.lib.plasma_swd_fifo_init(byref(self.fifo), byref(self.io),
                                           site_id, max_polls)
        assert rc == OK, rc
        assert self.fifo.idle_cycles == 8

    def writes(self, offset, since=0):
        return [v for op, off, v, _ in self.log[since:]
                if op == "w" and off == offset]

    async def connect(self, half=4, ctrl=0x50000000):
        """admit, SWCLK, line reset, DPIDR, ABORT, CTRL/STAT, SELECT 0."""
        await self.init()
        assert await self.call("plasma_swd_fifo_admit") == OK
        assert await self.call("plasma_swd_fifo_set_half_period", half) == OK
        assert await self.reconnect(ctrl) == 0x2BA01477

    async def reconnect(self, ctrl=0x50000000):
        dpidr = c_uint32(0)
        assert await self.call("plasma_swd_fifo_queue_line_reset") == OK
        assert await self.call("plasma_swd_fifo_queue_read", DP_DPIDR_R,
                               byref(dpidr), 0) == OK
        for cmd, value in ((DP_ABORT_W, 0x1E), (DP_CTRL_W, ctrl),
                           (DP_SELECT_W, 0)):
            assert await self.call("plasma_swd_fifo_queue_write", cmd,
                                   value, 0) == OK
        rc = await self.call("plasma_swd_fifo_run")
        assert rc == OK, (rc, hex(self.fifo.last_meta), self.target.state,
                          [hex(v) for op, off, v, _ in self.log
                           if op == "r" and off == 0x18],
                          [(hex(off), hex(v)) for op, off, v, _ in self.log
                           if op == "w" and off in (0x10, 0x14)],
                          [hex(h) for h in self.target.headers])
        return dpidr.value

    async def quiesce(self):
        """Production recover_off must return the Site to MODE=OFF."""
        recovered = c_int(-1)
        rc = await self.call("plasma_swd_fifo_recover_off", byref(recovered))
        assert rc == OK, rc
        assert await self.read(0x38) == (0, 0)
        return recovered.value

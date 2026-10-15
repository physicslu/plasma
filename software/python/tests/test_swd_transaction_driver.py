"""SWD-05 isolated AXI/MMIO contract tests. NEVER opens device nodes.

The fake is deliberately register/transaction-level, not an implementation
of FPGA's SystemVerilog FSM. Timing, physical AXI RRESP and SWD pins remain
unqualified until hardware validation.
"""
from __future__ import annotations

from collections import deque
from dataclasses import replace

import pytest

from plasma_interfaces.swd_transaction import (
    SWDAck, SWDDriverError, SWDLink, SWDResponse, SWDStatus,
    SWDTiming, SWDTransactionDriver,
)


BASE = 0x40003000
DPIDR = 0x2BA01477


class FakeAXI:
    def __init__(self, *, base=BASE):
        self.base = base
        self.log = []
        self.regs = {
            0x00: 1, 0x08: 4, 0x0C: 0, 0x10: 2, 0x14: 1,
            0x18: 8, 0x1C: 0, 0x20: 1_000_000,
        }
        self.link = SWDLink.RESET_REQUIRED
        self.busy = False
        self.resp = False
        self.meta = 0
        self.data = 0
        self.pending_polls = 0
        self.hang = False
        self.fail_read_offset = None
        self.fail_write_offset = None
        self.fail_start_after_commit = False
        self.inject = deque()
        self.dp = {4: 0xA5A5A5A5, 8: 0x12345678, 12: 0}
        self.ap = {0: 0xCAFE0000, 4: 0xCAFE0004, 8: 0xCAFE0008, 12: 0xCAFE000C}
        self.pending_ap = 0

    def _addr(self, address):
        if address & 3 or address < self.base or address >= self.base+0x30:
            raise RuntimeError("Invalid register MMIO address")
        return address-self.base

    def read32(self, address):
        off = self._addr(address)
        self.log.append(("read", off))
        if self.fail_read_offset == off:
            raise OSError("AXI read transfer failed")
        if off == 0x24:
            if self.busy and not self.hang:
                if self.pending_polls > 0:
                    self.pending_polls -= 1
                else:
                    self.busy = False
                    self.resp = True
            return int(self.busy) | (2 if not self.busy and not self.resp else 0) \
                | (4 if self.resp else 0) | (int(self.link) << 3)
        if off == 0x28:
            return self.meta
        if off == 0x2C:
            return self.data
        return self.regs.get(off, 0)

    def write32(self, address, value):
        off = self._addr(address)
        self.log.append(("write", off, value))
        if self.fail_write_offset == off:
            raise OSError("AXI write transfer failed")
        if off == 0x04:
            if value == 1:
                if self.busy or self.resp:
                    raise OSError("START while not ready")
                cfg = self.regs[0x08]
                op, ap, rd = bool(cfg & 1), bool(cfg & 2), bool(cfg & 4)
                addr = (cfg >> 3) & 15
                if self.inject:
                    code, ack, valid, data, attempts = self.inject.popleft()
                elif op:
                    code, ack, valid, data, attempts = 0, 0, False, 0, 0
                    self.link = SWDLink.DPIDR_REQUIRED
                elif rd and not ap and addr == 0:
                    code, ack, valid, data, attempts = 0, 1, True, DPIDR, 1
                    self.link = SWDLink.CONNECTED
                elif rd and ap:
                    code, ack, valid, data, attempts = 0, 1, True, self.pending_ap, 1
                    self.pending_ap = self.ap[addr]
                elif rd:
                    code, ack, valid, data, attempts = 0, 1, True, \
                        self.pending_ap if addr == 12 else self.dp.get(addr, 0), 1
                elif not ap:
                    code, ack, valid, data, attempts = 0, 1, False, 0, 1
                    self.dp[addr] = self.regs[0x0C]
                else:
                    code, ack, valid, data, attempts = 0, 1, False, 0, 1
                    self.ap[addr] = self.regs[0x0C]
                if code in (5, 6, 7, 8, 9):
                    self.link = SWDLink.RESET_REQUIRED
                self.meta = code | (ack << 4) | (int(valid) << 7) | (attempts << 8)
                self.data = data
                self.busy = True
                self.pending_polls = 2
                if self.fail_start_after_commit:
                    raise OSError("Write reported failed, START might be committed")
            elif value == 4:
                if not self.resp:
                    raise OSError("ACK without response")
                self.resp = False
            elif value == 2:
                if not self.busy:
                    raise OSError("ABORT without active")
                self.meta = 8
                self.data = 0
                self.busy = False
                self.resp = True
                self.link = SWDLink.RESET_REQUIRED
            else:
                raise OSError("Invalid COMMAND encoding")
        else:
            if self.busy or self.resp:
                raise OSError("Cannot modify settings while active")
            self.regs[off] = value


def driver(hw=None, **kwargs):
    return SWDTransactionDriver(
        hw or FakeAXI(), poll_budget=20, poll_interval_s=0,
        clock=lambda: 0.0, max_poll_seconds=2, **kwargs
    )


def connect(d):
    d.line_reset()
    assert d.read_dp(0) == DPIDR


def command_writes(hw):
    return [entry[2] for entry in hw.log if entry[0] == "write" and entry[1] == 4]


def test_constructor_reads_abi_only_and_requires_injected_backend():
    hw = FakeAXI()
    d = driver(hw)
    assert d.site_id == 1 and d.poisoned is False
    assert hw.log == [("read", 0)]
    with pytest.raises(ValueError):
        driver(object())
    hw.regs[0] = 2
    with pytest.raises(SWDDriverError, match="ABI mismatch"):
        driver(hw)


@pytest.mark.parametrize("field,value", [
    ("half_period_cycles", 1), ("half_period_cycles", 65536),
    ("turnaround_cycles", 0), ("turnaround_cycles", 5),
    ("idle_cycles", 7), ("idle_cycles", 256),
    ("max_wait_retries", -1), ("max_wait_retries", 256),
    ("timeout_cycles", 0), ("timeout_cycles", 2**32),
    ("error_data_phase", 1)
])
def test_timing_contract_rejects_unsupported_config(field, value):
    with pytest.raises(ValueError):
        replace(SWDTiming(), **{field: value})


@pytest.mark.parametrize("kwargs", [
    {"base": 0x40003004}, {"base": -0x1000}, {"site_id": 0},
    {"site_id": 9}, {"site_id": True}, {"poll_budget": 0},
    {"poll_interval_s": 1.0}, {"max_poll_seconds": 0},
])
def test_invalid_driver_contract(kwargs):
    with pytest.raises(ValueError):
        driver(**kwargs)


def test_line_reset_then_dpidr_and_response_consumption():
    hw = FakeAXI()
    d = driver(hw)
    with pytest.raises(SWDDriverError, match="line_reset"):
        d.read_dp(0)
    line = d.line_reset()
    assert line.status is SWDStatus.OK
    assert line.attempts == 0
    assert line.link_state is SWDLink.DPIDR_REQUIRED
    assert not d.poisoned
    with pytest.raises(SWDDriverError, match="DPIDR"):
        d.read_dp(4)
    assert d.read_dp(0) == DPIDR
    assert d.read_dp(4) == 0xA5A5A5A5
    assert command_writes(hw) == [1, 4, 1, 4, 1, 4]
    assert hw.resp is False and hw.busy is False


def test_dp_write_is_explicit_and_never_replayed():
    hw = FakeAXI()
    d = driver(hw, timing=SWDTiming(max_wait_retries=3))
    connect(d)
    r = d.write_dp(4, 0xF0E0D0C0)
    assert r.status is SWDStatus.OK and r.data_valid is False
    assert d.read_dp(4) == 0xF0E0D0C0
    assert command_writes(hw).count(1) == 4
    assert hw.regs[0x1C] == 3


def test_raw_ap_posted_read_semantics_and_explicit_rdbuff():
    hw = FakeAXI()
    d = driver(hw)
    connect(d)
    assert d.read_ap_raw(4) == 0
    assert d.read_ap_posted(8) == 0xCAFE0008
    assert d.write_ap_raw(0, 0xBEEFFACE).ack == SWDAck.OK
    assert d.read_ap_posted(0) == 0xBEEFFACE


@pytest.mark.parametrize("code,ack,uncertain", [
    (SWDStatus.BAD_CONFIG, 0, False),
    (SWDStatus.NEED_RESET, 0, False),
    (SWDStatus.WAIT_LIMIT, 2, False),
    (SWDStatus.FAULT, 4, False),
    (SWDStatus.BAD_ACK, 7, False),
    (SWDStatus.PARITY, 1, False),
    (SWDStatus.TIMEOUT, 0, False),
    (SWDStatus.ABORTED, 0, False),
    (SWDStatus.PHY_ERROR, 0, False),
])
def test_error_status_surfaces_metadata_and_acks_once(code, ack, uncertain):
    hw = FakeAXI()
    d = driver(hw)
    connect(d)
    hw.inject.append((code, ack, False, 0, 2))
    before = command_writes(hw).count(1)
    with pytest.raises(SWDDriverError) as err:
        d.read_dp(4)
    assert err.value.response.status == code
    assert err.value.response.attempts == 2
    assert hw.resp is False
    assert command_writes(hw).count(1) == before + 1


@pytest.mark.parametrize("code,uncertain", [
    (SWDStatus.WAIT_LIMIT, False), (SWDStatus.FAULT, False),
    (SWDStatus.BAD_ACK, True), (SWDStatus.PARITY, True),
    (SWDStatus.TIMEOUT, True), (SWDStatus.ABORTED, True),
    (SWDStatus.PHY_ERROR, True),
])
def test_uncertain_write_result_and_no_automatic_replay(code, uncertain):
    hw = FakeAXI()
    d = driver(hw)
    connect(d)
    hw.inject.append((code, 1, False, 0, 1))
    count = command_writes(hw).count(1)
    with pytest.raises(SWDDriverError) as err:
        d.write_dp(4, 0x12345678)
    assert err.value.uncertain_target_effects is uncertain
    assert err.value.response.status == code
    assert command_writes(hw).count(1) == count + 1


def test_read_response_metadata_must_be_coherent():
    hw = FakeAXI()
    d = driver(hw)
    connect(d)
    hw.inject.append((0, 1, False, 0, 1))
    with pytest.raises(SWDDriverError, match="successful metadata"):
        d.read_dp(4)
    assert d.poisoned


def test_partial_axi_write_to_start_poisoned_and_not_replayed():
    hw = FakeAXI()
    d = driver(hw)
    connect(d)
    hw.fail_start_after_commit = True
    before = command_writes(hw).count(1)
    with pytest.raises(SWDDriverError) as err:
        d.write_dp(4, 0x12345678)
    assert err.value.uncertain_target_effects
    assert d.poisoned
    assert command_writes(hw).count(1) == before + 1
    with pytest.raises(SWDDriverError, match="poisoned"):
        d.line_reset()


def test_failed_register_read_poisoned_no_implicit_reset():
    hw = FakeAXI()
    d = driver(hw)
    hw.fail_read_offset = 0x24
    with pytest.raises(SWDDriverError, match="AXI MMIO read failed"):
        d.line_reset()
    assert d.poisoned
    assert command_writes(hw) == []


def test_stuck_busy_poll_budget_and_no_auto_abort():
    hw = FakeAXI()
    d = driver(hw)
    hw.hang = True
    with pytest.raises(SWDDriverError, match="polling deadline"):
        d.line_reset()
    assert d.poisoned
    assert command_writes(hw) == [1]
    assert not any(x == 2 for x in command_writes(hw))


def test_explicit_abort_requires_busy_and_no_implicit_command():
    hw = FakeAXI()
    d = driver(hw)
    with pytest.raises(SWDDriverError, match="ABORT only"):
        d.abort()
    assert command_writes(hw) == []
    hw.busy = True
    with pytest.raises(SWDDriverError) as err:
        d.abort()
    assert err.value.response.status is SWDStatus.ABORTED
    assert command_writes(hw) == [2, 4]


def test_two_site_instances_have_independent_command_states():
    a, b = FakeAXI(base=BASE), FakeAXI(base=BASE+0x1000)
    one = driver(a, site_id=1)
    two = driver(b, base=BASE+0x1000, site_id=2)
    one.line_reset()
    assert a.link == SWDLink.DPIDR_REQUIRED
    assert b.link == SWDLink.RESET_REQUIRED
    two.line_reset()
    assert one.read_dp(0) == two.read_dp(0) == DPIDR


@pytest.mark.parametrize("addr", [-4, 2, 16, 1, True])
def test_invalid_swd_register_address_never_starts(addr):
    hw = FakeAXI()
    d = driver(hw)
    connect(d)
    initial = len(command_writes(hw))
    with pytest.raises(ValueError):
        d.read_dp(addr)
    assert len(command_writes(hw)) == initial


def test_invalid_write_data_never_starts():
    hw = FakeAXI()
    d = driver(hw)
    connect(d)
    count = len(command_writes(hw))
    with pytest.raises(ValueError):
        d.write_dp(0, 2**32)
    assert len(command_writes(hw)) == count


def test_response_stale_before_start_is_not_acknowledged_or_replayed():
    hw = FakeAXI()
    d = driver(hw)
    hw.resp = True
    with pytest.raises(SWDDriverError, match="not idle"):
        d.line_reset()
    assert command_writes(hw) == []
    assert hw.resp


def test_not_a_flash_programming_api():
    d = driver()
    for name in ("erase", "flash", "program", "verify", "power_on", "reset_target"):
        assert not hasattr(d, name)

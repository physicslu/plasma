"""Offline consistency and adversarial simulation-driver acceptance only."""
import asyncio
import json
from pathlib import Path

import pytest

from pl.verification.models.fixed_swd_site_driver import (
    FixedSWDSiteSimDriver, FixedSWDSliceError,
)

PL = Path(__file__).resolve().parents[1]
SPEC = PL / "verification/fixed_image_abi_v1_gate1.json"
RTL = PL / "rtl/bus/fixed_fpga_swd_site_axi_lite.sv"


class FakeAxi:
    def __init__(self, *, mismatched_seq=False, bad_axi_at=None):
        self.log = []
        self.done = False
        self.seq = 0
        self.opcode = 0
        self.mismatched_seq = mismatched_seq
        self.bad_axi_at = bad_axi_at
        self.status = 0

    async def read(self, offset):
        self.log.append(("read", offset))
        if offset == self.bad_axi_at:
            return (2, 0)
        return (0, {0: 1, 4: 0x10000, 8: 1,
                    0x0C: 4 if self.done else 1,
                    0x48: self.seq+1 if self.mismatched_seq else self.seq,
                    0x4C: self.status, 0x60: 0x2BA01477}.get(offset, 0))

    async def write(self, offset, value, strb=15):
        self.log.append(("write", offset, value))
        if offset == self.bad_axi_at:
            return 2
        if offset == 0x24:
            self.seq = value
        elif offset == 0x20:
            self.opcode = value
            self.done = True
        elif offset == 0x64:
            if value == self.seq and self.done:
                self.done = False
            else:
                return 2
        return 0


def go(task):
    return asyncio.run(task)


def test_site1_wire_offsets_match_reviewed_machine_contract():
    spec = json.loads(SPEC.read_text())
    site = spec["regions"][4]
    assert site["site_id"] == 1 and site["base"] == 0x4000
    regs = {r["name"]: r["offset"] for r in site["registers"]}
    assert regs["COMMAND"] == 0x20
    assert regs["SEQUENCE"] == 0x24
    assert regs["DONE_SEQ"] == 0x48
    assert regs["DONE_STATUS"] == 0x4C
    assert regs["ACK_SEQ"] == 0x64
    assert regs["DONE_DATA"] == 0x60
    assert spec["hardware"]["runtime_fpga_reload_supported"] is False


def test_rtl_is_isolated_site1_no_manager_or_os_device():
    src = RTL.read_text()
    assert "module fixed_fpga_swd_site_axi_lite" in src
    assert "swd_transaction_master master" in src
    assert "32'h40004000" in src
    assert "wstrb!=4'hf" in src
    assert "s_axi_bresp<=SLVERR" in src
    assert "FPGA Manager" in src  # comment expressly rules it out
    for forbidden in ("$system", "$fopen", "$readmemh", "fpga_manager_load"):
        assert forbidden not in src


def test_host_sim_driver_sequence_and_command_commit_last():
    bus = FakeAxi()
    d = FixedSWDSiteSimDriver(bus)
    result = go(d.transact(sequence=17, opcode=2, bit_count=64))
    assert result.sequence == 17 and result.status == 0
    writes = [x for x in bus.log if x[0] == "write"]
    assert writes[0] == ("write", 0x24, 17)
    assert writes[8] == ("write", 0x20, 2)
    assert writes[-1] == ("write", 0x64, 17)
    with pytest.raises(ValueError):
        go(d.transact(sequence=17, opcode=2, bit_count=64))


def test_sim_driver_rejects_unsupported_spi_before_any_io():
    bus = FakeAxi()
    d = FixedSWDSiteSimDriver(bus)
    with pytest.raises(ValueError):
        go(d.transact(sequence=18, opcode=3, bit_count=8))
    assert bus.log == []


def test_sim_driver_poisoned_on_stale_completion():
    bus = FakeAxi(mismatched_seq=True)
    d = FixedSWDSiteSimDriver(bus)
    with pytest.raises(FixedSWDSliceError, match="completion"):
        go(d.transact(sequence=19, opcode=2, bit_count=64))
    assert d.poisoned
    count = len(bus.log)
    with pytest.raises(FixedSWDSliceError, match="poisoned"):
        go(d.transact(sequence=20, opcode=2, bit_count=64))
    assert len(bus.log) == count


def test_sim_driver_poisoned_on_axilite_error():
    bus = FakeAxi(bad_axi_at=0x28)
    d = FixedSWDSiteSimDriver(bus)
    with pytest.raises(FixedSWDSliceError, match="AXI write"):
        go(d.transact(sequence=21, opcode=2, bit_count=64))
    assert d.poisoned
    assert not any(x[:2] == ("write", 0x20) for x in bus.log)


def test_sim_driver_refuses_invalid_line_reset_range_as_unimplemented_subset():
    bus = FakeAxi()
    d = FixedSWDSiteSimDriver(bus)
    with pytest.raises(ValueError, match="64-bit"):
        go(d.transact(sequence=22, opcode=2, bit_count=50))
    assert bus.log == []

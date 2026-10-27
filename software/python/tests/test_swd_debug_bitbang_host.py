"""Source-locked opcode compatibility checks, no OpenOCD process or DUT."""
import pytest

from plasma_interfaces.swd_debug_bitbang import (
    BitbangProtocolError, SwdDebugBitbangCore,
)
from plasma_interfaces.swd_site import SITE_BASES, SiteAccessError


class FakeDevice:
    def __init__(self):
        self.regs = {}
        self.writes = []
        self.fail = False
        for site, base in SITE_BASES.items():
            self.regs[base] = 0x30000 | site
            self.regs[base + 0x38] = 0
            self.regs[base + 0x40] = site - 1

    def read32(self, address):
        return self.regs.get(address, 0)

    def write32(self, address, value):
        self.writes.append((address, value))
        if self.fail:
            raise OSError("uncertain device write")
        self.regs[address] = value

    def write_barrier(self):
        if self.fail:
            raise OSError("barrier failure")


def test_swd_opcodes_obey_low_clock_data_setup_and_site_ownership():
    port = FakeDevice()
    a = SwdDebugBitbangCore(port, site_id=1, lease_check=lambda: None)
    b = SwdDebugBitbangCore(port, site_id=2, lease_check=lambda: None)
    assert port.writes == []
    a.begin()
    b.begin()
    assert a.handle(b"O") == b""
    assert a.handle(b"e") == b""
    assert a.handle(b"g") == b""
    with pytest.raises(BitbangProtocolError, match="SWCLK HIGH"):
        a.handle(b"f")  # same high clock with different SWDIO is illegal
    assert a.handle(b"d") == b""  # low first, then alter data
    assert a.handle(b"o") == b""
    assert a.handle(b"c") == b"0"
    assert b.handle(b"c") == b"1"  # truly separate Site input
    assert a.handle(b"Q") == b""
    assert port.regs[SITE_BASES[1] + 0x38] == 0
    assert port.regs[SITE_BASES[2] + 0x38] == 2
    assert [v for addr, v in port.writes if addr == SITE_BASES[1] + 0x3C] == [
        4, 6, 7, 6, 4, 0,
    ]
    b.handle(b"Q")


@pytest.mark.parametrize("opcode", [b"B", b"R", b"0", b"r", b"Z", b"z", b"D", b"x", b""])
def test_jtag_reset_sleep_and_unknown_commands_fail_closed(opcode):
    port = FakeDevice()
    session = SwdDebugBitbangCore(port, site_id=1, lease_check=lambda: None)
    session.begin()
    with pytest.raises(BitbangProtocolError):
        session.handle(opcode)
    assert not any(addr == SITE_BASES[1] + 0x3C for addr, _ in port.writes)
    session.close()


def test_no_mode_fallback_or_device_retry_on_lost_lease_and_write_failure():
    port = FakeDevice()
    held = [True]

    def lease():
        if not held[0]:
            raise PermissionError("lease revoked")

    session = SwdDebugBitbangCore(port, site_id=1, lease_check=lease)
    session.begin()
    held[0] = False
    with pytest.raises(BitbangProtocolError, match="lease lost"):
        session.handle(b"O")
    assert session.poisoned
    with pytest.raises(BitbangProtocolError):
        session.handle(b"d")
    assert not any(addr == SITE_BASES[1] + 0x3C for addr, _ in port.writes)

    port2 = FakeDevice()
    another = SwdDebugBitbangCore(port2, site_id=2, lease_check=lambda: None)
    another.begin()
    port2.fail = True
    with pytest.raises(SiteAccessError, match="Uncertain"):
        another.handle(b"O")
    original_count = len(port2.writes)
    with pytest.raises(BitbangProtocolError):
        another.handle(b"O")
    assert len(port2.writes) == original_count


def test_incorrect_site_abi_rejected_before_debug_drive():
    port = FakeDevice()
    port.regs[SITE_BASES[1]] = 0x20001  # transitional old single-response ABI
    session = SwdDebugBitbangCore(port, site_id=1, lease_check=lambda: None)
    with pytest.raises(BitbangProtocolError, match="ABI"):
        session.begin()
    assert session.poisoned
    assert port.writes == []

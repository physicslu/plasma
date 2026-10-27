"""Inert control-layer regression, NOT ARMv7 MMIO or DUT qualification."""
import pytest

from plasma_interfaces.swd_site import (
    SITE_BASES, SiteAccessError, SiteStatus, SwdSiteController,
    decode_completion, encode_swj, encode_transfer,
)


class VirtualSites:
    """Deterministic register/trace stub, not a model of AXI timing."""

    def __init__(self):
        self.regs = {}
        self.writes = []
        self.reads = []
        self.barriers = 0
        self.fail_write = False
        for site, base in SITE_BASES.items():
            self.regs[base] = 0x40000 | site
            self.regs[base + 0x38] = 0
            self.regs[base + 0x08] = 500
            self.regs[base + 0x24] = 0
            self.regs[base + 0x2C] = 0
            self.regs[base + 0x34] = 0

    def read32(self, address):
        self.reads.append(address)
        return self.regs.get(address, 0)

    def write32(self, address, value):
        self.writes.append((address, value))
        if self.fail_write:
            raise OSError("uncertain MMIO acceptance")
        base = address & ~0xFFF
        offset = address - base
        if offset == 0x28:
            self.regs[base + 4] = (self.regs.get(base + 4, 0) & ~1) | value
        elif offset == 0x14:
            tag = value >> 16
            self.regs[base + 0x18] = (tag << 16) | (1 << 12)
            self.regs[base + 0x1C] = 0
            self.regs[base + 0x24] = 2 | (1 << 17)
            self.regs[base + 0x34] = 1
        elif offset == 0x20:
            assert value == self.regs[base + 0x18] >> 16
            self.regs[base + 0x24] = 0
        elif offset == 0x34 and value == 1:
            self.regs[address] = 0
        else:
            self.regs[address] = value

    def write_barrier(self):
        self.barriers += 1


def test_inert_probe_and_independent_site_addresses():
    port = VirtualSites()
    first = SwdSiteController(port, site_id=1)
    second = SwdSiteController(port, site_id=2)
    assert not port.reads and not port.writes
    first.probe()
    second.probe()
    first.enter_normal(irq=True)
    second.enter_normal()
    assert (SITE_BASES[1] + 0x38, 1) in port.writes
    assert (SITE_BASES[2] + 0x38, 1) in port.writes
    assert (SITE_BASES[1] + 0x30, 1) in port.writes
    assert port.barriers == len(port.writes)


def test_speed_rounding_no_unsupported_fast_clock_or_unbounded_slow_clock():
    port = VirtualSites()
    driver = SwdSiteController(port, site_id=1)
    driver.enter_normal()
    assert driver.set_clock_hz(12_500_000) == 12_500_000
    assert driver.set_clock_hz(1_000_000) == 1_000_000
    assert driver.set_clock_hz(7_000_000) <= 7_000_000
    with pytest.raises(ValueError):
        driver.set_clock_hz(25_000_000)
    with pytest.raises(ValueError):
        driver.set_clock_hz(100)


def test_reset_then_dp_read_encoding_and_single_tagged_consumption():
    assert encode_swj(0) == 0x100
    assert encode_swj(16) == 0x110
    assert encode_transfer(ap=False, read=True, address=0) == 0x02
    assert encode_transfer(ap=True, read=False, address=12) == 0x0D
    port = VirtualSites()
    driver = SwdSiteController(port, site_id=1)
    driver.enter_normal(irq=True)
    driver.enqueue(tag=1, command=encode_swj(0))
    response = driver.next_completion()
    assert response.tag == 1 and response.status == SiteStatus.OK
    driver.ack_irq()
    assert port.regs[driver.base + 0x34] == 0
    driver.enqueue(tag=2, command=encode_transfer(ap=False, read=True, address=0))
    assert driver.next_completion().tag == 2
    assert (driver.base + 0x14, (2 << 16) | 0x02) in port.writes
    with pytest.raises(ValueError):
        driver.enqueue(tag=2, command=0x100)
    driver.disable_if_idle()


def test_invalid_command_and_unknown_results_fail_closed():
    for bad in (-1, 257, 1000, True):
        with pytest.raises(ValueError):
            encode_swj(bad)
    with pytest.raises(ValueError):
        encode_transfer(ap=False, read=True, address=3)
    with pytest.raises(SiteAccessError):
        decode_completion(0x0001000F, 0)
    port = VirtualSites()
    driver = SwdSiteController(port, site_id=1)
    driver.enter_normal()
    with pytest.raises(ValueError):
        driver.enqueue(tag=1, command=0x121)
    with pytest.raises(ValueError):
        driver.enqueue(tag=0, command=0x100)
    driver.enqueue(tag=4, command=0x100)
    port.regs[driver.base + 0x18] = (5 << 16)
    with pytest.raises(SiteAccessError, match="tag/order"):
        driver.next_completion()
    assert driver.poisoned


def test_uncertain_write_never_retried_and_poisoned():
    port = VirtualSites()
    driver = SwdSiteController(port, site_id=1)
    driver.enter_normal()
    port.fail_write = True
    with pytest.raises(SiteAccessError, match="no replay"):
        driver.enqueue(tag=99, command=encode_swj(0))
    count = len(port.writes)
    with pytest.raises(SiteAccessError, match="uncertain"):
        driver.enqueue(tag=99, command=encode_swj(0))
    assert len(port.writes) == count


def test_bounded_completion_timeout_poison_prevents_new_writes():
    port = VirtualSites()
    driver = SwdSiteController(port, site_id=2, max_polls=3)
    driver.enter_normal()
    with pytest.raises(SiteAccessError, match="bounded"):
        driver.next_completion()
    assert driver.poisoned
    prior = len(port.writes)
    with pytest.raises(SiteAccessError, match="uncertain"):
        driver.enqueue(tag=7, command=encode_swj(0))
    assert len(port.writes) == prior


def test_256bit_swj_is_one_tagged_command_and_all_words_staged_in_order():
    port = VirtualSites()
    driver = SwdSiteController(port, site_id=2)
    driver.probe()
    driver.enter_normal()
    bits = int.from_bytes(bytes(range(32)), "little")
    driver.enqueue_swj(tag=77, bit_count=256, bits=bits)
    relevant = [(addr-driver.base, val) for addr, val in port.writes
                if driver.base + 0x44 <= addr <= driver.base + 0x64 or addr == driver.base + 0x14]
    assert relevant == [(0x44 + 4*i, (bits >> (32*i)) & 0xFFFFFFFF)
                        for i in range(8)] + [(0x64, 256), (0x14, (77 << 16) | 0x100)]
    assert driver.next_completion().tag == 77
    with pytest.raises(ValueError):
        driver.enqueue_swj(tag=78, bit_count=256, bits=1 << 256)
    assert encode_swj(33) == 0x121
    assert encode_swj(256) == 0x100


def test_extended_swj_uncertain_staging_write_poison_prevents_replay():
    port = VirtualSites()
    driver = SwdSiteController(port, site_id=1)
    driver.enter_normal()
    port.fail_write = True
    with pytest.raises(SiteAccessError, match="no replay"):
        driver.enqueue_swj(tag=10, bit_count=256, bits=1)
    count = len(port.writes)
    with pytest.raises(SiteAccessError, match="uncertain"):
        driver.enqueue_swj(tag=10, bit_count=256, bits=1)
    assert len(port.writes) == count

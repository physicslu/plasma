"""Host-only SWD NORMAL: no OpenOCD executable, DUT or device accesses."""
import pytest

from plasma_interfaces.swd_native_normal_contract import (
    SwdNativeNormalContract, SwdNormalAdapterError, OperationKind,
)
from plasma_interfaces.swd_site import SITE_BASES, SwdSiteController, SiteStatus


class FakeSites:
    def __init__(self):
        self.regs, self.calls = {}, []
        self.status = {}
        self.ack = {}
        self.fail = False
        for site, base in SITE_BASES.items():
            self.regs.update({
                base: 0x50000 | site, base + 0x38: 0,
                base + 0x04: 0, base + 0x24: 0, base + 0x2C: 0,
            })

    def read32(self, addr):
        self.calls.append(("read", addr))
        return self.regs.get(addr, 0)

    def write32(self, addr, value):
        self.calls.append(("write", addr, value))
        if self.fail:
            raise OSError("Injected uncertain write")
        base, off = addr & ~0xFFF, addr & 0xFFF
        if off == 0x28:
            self.regs[base + 0x04] = value & 1
        elif off == 0x14:
            tag, cmd = value >> 16, value & 0x1FF
            swj = bool(cmd & 0x100)
            reading = bool(cmd & 0x02) and not swj
            raw_ack = self.ack.get(base, 0 if swj else 1)
            status = self.status.get(base, SiteStatus.OK)
            self.regs[base + 0x18] = (
                (tag << 16) | (int(reading) << 7) | (raw_ack << 4) | int(status))
            self.regs[base + 0x1C] = 0x2BA01477 if reading else 0
            self.regs[base + 0x24] = 2
        elif off == 0x20:
            assert value == self.regs[base + 0x18] >> 16
            self.regs[base + 0x24] = 0
        else:
            self.regs[addr] = value

    def write_barrier(self):
        self.calls.append(("barrier",))


def normal(fake, site=1):
    driver = SwdSiteController(fake, site_id=site)
    driver.probe()
    driver.enter_normal()
    return SwdNativeNormalContract(driver)


def pushes(fake):
    return [(addr, value) for item in fake.calls
            if len(item) == 3 and item[0] == "write"
            for _, addr, value in [item] if addr & 0xFFF == 0x14]


def test_dp_read_ap_write_and_line_reset_keep_order_and_exact_raw_ack():
    fake = FakeSites()
    adapter = normal(fake)
    adapter.switch_seq(bit_count=0)
    adapter.read_reg(ap=False, address=0)
    adapter.write_reg(ap=True, address=12, value=0x11223344)
    results = adapter.run()
    assert [(r.tag, r.kind, r.ack, r.data) for r in results] == [
        (1, OperationKind.SWJ, 0, None),
        (2, OperationKind.READ, 1, 0x2BA01477),
        (3, OperationKind.WRITE, 1, None),
    ]
    assert pushes(fake) == [
        (SITE_BASES[1] + 0x14, (1 << 16) | 0x100),
        (SITE_BASES[1] + 0x14, (2 << 16) | 0x02),
        (SITE_BASES[1] + 0x14, (3 << 16) | 0x0D),
    ]
    assert adapter.run() == ()
    assert len(pushes(fake)) == 3


def test_two_independent_sites_no_cross_site_mmio_or_synthetic_ap_posted_read():
    fake = FakeSites()
    a, b = normal(fake, 1), normal(fake, 2)
    a.read_reg(ap=True, address=12)
    b.switch_seq(bit_count=16, bits=0xE79E)
    assert a.run()[0].data == 0x2BA01477
    assert b.run()[0].data is None
    assert {addr for addr, _ in pushes(fake)} == {
        SITE_BASES[1] + 0x14, SITE_BASES[2] + 0x14,
    }
    assert len(pushes(fake)) == 2  # No synthesized DP RDBUFF transfer


@pytest.mark.parametrize("status,ack", [(SiteStatus.WAIT, 2), (SiteStatus.FAULT, 4)])
def test_raw_wait_or_fault_blocks_adapter_without_replaying_write(status, ack):
    fake = FakeSites()
    adapter = normal(fake)
    fake.status[SITE_BASES[1]] = status
    fake.ack[SITE_BASES[1]] = ack
    adapter.write_reg(ap=False, address=4, value=0xDEADBEEF)
    adapter.read_reg(ap=False, address=0)
    with pytest.raises(SwdNormalAdapterError, match=status.name) as err:
        adapter.run()
    assert err.value.completion.status == status
    total = len(pushes(fake))
    with pytest.raises(SwdNormalAdapterError, match="blocked"):
        adapter.run()
    assert len(pushes(fake)) == total == 1


def test_invalid_ack_and_uncertain_mmio_do_not_trigger_automatic_retry():
    fake = FakeSites()
    adapter = normal(fake)
    fake.ack[SITE_BASES[1]] = 0
    adapter.read_reg(ap=False, address=0)
    with pytest.raises(SwdNormalAdapterError, match="ACK"):
        adapter.run()
    assert len(pushes(fake)) == 1
    fake2 = FakeSites()
    other = normal(fake2)
    other.write_reg(ap=False, address=0, value=5)
    fake2.fail = True
    with pytest.raises(SwdNormalAdapterError, match="never auto-replay"):
        other.run()
    count = len(pushes(fake2))
    with pytest.raises(SwdNormalAdapterError, match="blocked"):
        other.run()
    assert len(pushes(fake2)) == count


def test_bounded_queue_strict_validation_and_256bit_atomic_staging():
    fake = FakeSites()
    adapter = SwdNativeNormalContract(normal(fake)._site, max_queue=1)
    before = len(fake.calls)
    with pytest.raises(ValueError):
        adapter.switch_seq(bit_count=257)
    with pytest.raises(ValueError):
        adapter.switch_seq(bit_count=16, bits=(1 << 16))
    with pytest.raises(ValueError):
        adapter.write_reg(ap=False, address=3, value=0)
    with pytest.raises(ValueError):
        adapter.write_reg(ap=False, address=0, value=True)
    assert len(fake.calls) == before
    adapter.switch_seq(bit_count=256, bits=(1 << 255) | 1)
    with pytest.raises(SwdNormalAdapterError, match="full"):
        adapter.read_reg(ap=False, address=0)
    assert adapter.run()[0].kind is OperationKind.SWJ
    assert (SITE_BASES[1] + 0x64, 256) in [
        (addr, value) for item in fake.calls if len(item) == 3
        for _, addr, value in [item]]

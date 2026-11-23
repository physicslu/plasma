"""Host-only OPP common register API tests. No device access."""
import pytest

from plasma_interfaces.opp_common_registers import OPPCommonRegisters, MAGIC, ABI_VERSION


class FakePort:
    def __init__(self, *, base=0x10000000):
        self.base = base
        self.regs = {base: MAGIC, base + 4: ABI_VERSION, base + 0x40: 0xABCDEF12}
        self.writes = []
        self.fail_readback = False
        self.scratch_reads = 0

    def read32(self, addr):
        if addr == self.base + 0x40:
            self.scratch_reads += 1
            if self.fail_readback and self.scratch_reads == 2:
                return 0xDEADBEEF
        return self.regs.get(addr, 0)

    def write32(self, addr, value):
        assert addr == self.base + 0x40
        self.writes.append((addr, value))
        self.regs[addr] = value

    def write_barrier(self):
        pass


def test_identity_and_four_site_bitmaps():
    p = FakePort()
    p.regs[p.base + 0x30] = 0xF
    p.regs[p.base + 0x34] = 0x5
    api = OPPCommonRegisters(p, base=p.base)
    info = api.get_fpga_info()
    assert info.site_present == 0xF
    assert info.site_ready == 0x5
    assert info.image_id == 0


def test_rejects_unknown_image_and_invalid_site_bitmap():
    p = FakePort()
    api = OPPCommonRegisters(p, base=p.base)
    p.regs[p.base] = 0
    with pytest.raises(RuntimeError, match="MAGIC"):
        api.check_compatibility()
    p.regs[p.base] = MAGIC
    p.regs[p.base + 0x34] = 1
    with pytest.raises(RuntimeError, match="READY"):
        api.get_fpga_info()
    p.regs[p.base + 0x34] = 0
    p.regs[p.base + 0x30] = 0x10
    with pytest.raises(RuntimeError, match="four Sites"):
        api.get_fpga_info()


def test_scratch_restored_after_success():
    p = FakePort()
    OPPCommonRegisters(p, base=p.base).register_self_test()
    assert p.regs[p.base + 0x40] == 0xABCDEF12
    assert len(p.writes) == 6


def test_scratch_restored_after_failed_comparison():
    p = FakePort()
    p.fail_readback = True
    with pytest.raises(RuntimeError, match="readback mismatch"):
        OPPCommonRegisters(p, base=p.base).register_self_test()
    assert p.regs[p.base + 0x40] == 0xABCDEF12
    assert p.writes[-1] == (p.base + 0x40, 0xABCDEF12)


def test_bad_base_rejected_before_access():
    with pytest.raises(ValueError):
        OPPCommonRegisters(FakePort(), base=0x10000001)

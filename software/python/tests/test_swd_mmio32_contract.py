"""Host-only aligned word-window tests. No /dev/mem, mmap or Z2."""
import pytest

from plasma_interfaces.swd_mmio32_contract import Word32MappedWindow
from plasma_interfaces.swd_site import SwdSiteController, SITE_BASES, SiteAccessError


class FakeWordMemory:
    def __init__(self, site):
        self.data = {0: 0x50000 | site, 0x04: 0, 0x24: 0,
                     0x2C: 0, 0x38: 0}
        self.calls = []
        self.fail = False

    def read_word(self, offset):
        self.calls.append(("LDR32", offset))
        if self.fail:
            raise OSError("unmapped device")
        return self.data.get(offset, 0)

    def write_word(self, offset, value):
        self.calls.append(("STR32", offset, value))
        if self.fail:
            raise OSError("uncertain write")
        if offset == 0x28:
            self.data[0x04] = value & 1
        else:
            self.data[offset] = value

    def read_barrier(self):
        self.calls.append(("read_DMB",))

    def write_barrier(self):
        self.calls.append(("write_DMB",))


def test_per_site_word_alignment_and_barrier_call_order():
    mem1, mem2 = FakeWordMemory(1), FakeWordMemory(2)
    a = Word32MappedWindow(mem1, site_id=1)
    b = Word32MappedWindow(mem2, site_id=2)
    first = SwdSiteController(a, site_id=1)
    second = SwdSiteController(b, site_id=2)
    first.probe()
    second.probe()
    first.enter_normal()
    second.enter_normal()
    assert mem1.calls[:2] == [("LDR32", 0), ("read_DMB",)]
    assert mem2.calls[:2] == [("LDR32", 0), ("read_DMB",)]
    for m in (mem1, mem2):
        writes = [call for call in m.calls if call[0] == "STR32"]
        assert writes and m.calls.count(("write_DMB",)) == len(writes)
        assert ("STR32", 0x38, 1) in writes
        assert m.data[0x38] == 1


def test_invalid_window_addresses_and_nonword_data_reject_without_io():
    mem = FakeWordMemory(1)
    port = Word32MappedWindow(mem, site_id=1)
    for bad in (SITE_BASES[1] - 4, SITE_BASES[2],
                SITE_BASES[1] + 4096, SITE_BASES[1] + 1, True, 3.3):
        with pytest.raises(ValueError):
            port.read32(bad)
    for bad in (-1, True, 0x1_0000_0000, 3.3):
        with pytest.raises(ValueError):
            port.write32(SITE_BASES[1] + 0x10, bad)
    assert not mem.calls


def test_missing_native_read_write_barriers_do_not_admit_mmio():
    with pytest.raises(TypeError, match="barriers"):
        Word32MappedWindow(object(), site_id=1)
    with pytest.raises(ValueError):
        Word32MappedWindow(FakeWordMemory(1), site_id=0)


def test_uncertain_word_store_poison_controller_and_forbid_replay():
    mem = FakeWordMemory(1)
    ctl = SwdSiteController(Word32MappedWindow(mem, site_id=1), site_id=1)
    ctl.probe()
    ctl.enter_normal()
    mem.fail = True
    with pytest.raises(SiteAccessError, match="no replay"):
        ctl.set_clock_hz(100_000)
    assert ctl.poisoned
    before = len(mem.calls)
    with pytest.raises(SiteAccessError):
        ctl.set_clock_hz(100_000)
    assert len(mem.calls) == before

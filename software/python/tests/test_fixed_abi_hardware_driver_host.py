"""Host-only negative admission and per-Site boundary contract checks."""
import pytest

from plasma_interfaces.fixed_abi_hardware_driver import (
    FixedABIHardwareDriver, FixedABISitePort, HardwareABIAdmissionError,
)


BASE = 0x40000000
IMAGE = (0x11112222, 0x33334444, 0x55556666, 0x77778888)
BUILD = (0xABCDE001, 0xABCDE002, 0xABCDE003, 0xABCDE004)


class WordPort:
    def __init__(self):
        self.memory = {
            BASE: 0x4D534C50, BASE + 4: 0x10000,
            BASE + 0x28: 1, BASE + 0x2C: 0,
            BASE + 0x30: 3, BASE + 0x34: 3,
            BASE + 0x44: 1, BASE + 0x48: 4096,
        }
        for i, word in enumerate(IMAGE + BUILD):
            self.memory[BASE + 8 + 4 * i] = word
        for site in (1, 2):
            addr = BASE + 0x4000 + (site - 1) * 0x1000
            self.memory.update({addr: site, addr + 4: 0x10000,
                                addr + 8: 1, addr + 12: 1})
        self.operations = []

    def read32(self, address):
        self.operations.append(("r", address))
        return self.memory.get(address, 0)

    def write32(self, address, value):
        self.operations.append(("w", address, value))

    def write_barrier(self):
        self.operations.append(("barrier",))


def make_driver(port=None, **kw):
    opts = dict(ppu_base=BASE, image_id=IMAGE, build_id=BUILD, site_bitmap=3)
    opts.update(kw)
    return FixedABIHardwareDriver(port if port is not None else WordPort(), **opts)


def test_two_sites_admitted_without_implicit_io_and_hard_scoped():
    bus = WordPort()
    driver = make_driver(bus)
    assert bus.operations == []
    with pytest.raises(HardwareABIAdmissionError):
        driver.open_site(1)
    driver.admit()
    first, second = driver.open_site(1), driver.open_site(2)
    assert (first.base, second.base) == (BASE + 0x4000, BASE + 0x5000)
    assert first.site_id == 1 and second.site_id == 2
    assert second.read32(second.base) == 2
    first.write32(first.base + 0x24, 55)
    second.write32(second.base + 0x24, 66)
    first.write_barrier()
    assert ("w", first.base + 0x24, 55) in bus.operations
    assert ("w", second.base + 0x24, 66) in bus.operations
    assert bus.operations[-1] == ("barrier",)
    forged = FixedABISitePort(driver, base=BASE + 0x6000, site_id=3)
    with pytest.raises(HardwareABIAdmissionError):
        forged.write32(forged.base + 0x24, 1)
    forged_same_id = FixedABISitePort(driver, base=first.base, site_id=1)
    with pytest.raises(HardwareABIAdmissionError):
        forged_same_id.read32(first.base)
    for site, other in ((first, second), (second, first)):
        for addr in (other.base + 0x24, site.base + 0x21,
                     site.base + 0x800, site.base + 0x1000):
            with pytest.raises(HardwareABIAdmissionError):
                site.write32(addr, 1)
        with pytest.raises(HardwareABIAdmissionError):
            site.read32(site.base + 0x20)  # WO command
        with pytest.raises(HardwareABIAdmissionError):
            site.write32(site.base + 0x00, 1)  # RO identity
    with pytest.raises(HardwareABIAdmissionError):
        driver.open_site(1)
    with pytest.raises(HardwareABIAdmissionError):
        driver.open_site(3)
    with pytest.raises(HardwareABIAdmissionError):
        driver.admit()  # no implicit owner-epoch reset


@pytest.mark.parametrize("broken", [
    (0x00, 0), (0x04, 2), (0x08, 0), (0x18, 0),
    (0x28, 3), (0x2C, 1), (0x30, 1), (0x30, 7),
    (0x34, 7), (0x44, 2), (0x48, 2048),
])
def test_manifest_identity_capabilities_presence_mismatch_poison(broken):
    bus = WordPort()
    offset, bad = broken
    bus.memory[BASE + offset] = bad
    driver = make_driver(bus)
    with pytest.raises(HardwareABIAdmissionError):
        driver.admit()
    with pytest.raises(HardwareABIAdmissionError):
        driver.open_site(1)
    assert not any(row[0] == "w" for row in bus.operations)


@pytest.mark.parametrize("broken", [(0, 9), (4, 2), (8, 0), (12, 8)])
def test_site2_identity_version_capability_status_fails_closed(broken):
    bus = WordPort()
    offset, value = broken
    bus.memory[BASE + 0x5000 + offset] = value
    driver = make_driver(bus)
    driver.admit()
    driver.open_site(1)
    with pytest.raises(HardwareABIAdmissionError):
        driver.open_site(2)
    with pytest.raises(HardwareABIAdmissionError):
        driver.open_site(1)  # epoch poisoned, no silent re-admission


@pytest.mark.parametrize("kwargs", [
    {"ppu_base": BASE + 1}, {"ppu_base": -1},
    {"site_bitmap": 0}, {"site_bitmap": 256},
    {"image_id": (1, 2, 3)}, {"build_id": (1, 2, 3, False)},
])
def test_reject_invalid_trusted_manifest_before_io(kwargs):
    bus = WordPort()
    with pytest.raises(ValueError):
        make_driver(bus, **kwargs)
    assert bus.operations == []


def test_reject_unadmitted_site_and_nonnumeric_word_without_side_effects():
    bus = WordPort()
    driver = make_driver(bus)
    driver.admit()
    for site in (0, 9, True):
        with pytest.raises(ValueError):
            driver.open_site(site)
    site = driver.open_site(2)
    prior = list(bus.operations)
    with pytest.raises(ValueError):
        site.write32(site.base + 0x24, True)
    with pytest.raises(ValueError):
        site.write32(site.base + 0x24, -1)
    assert bus.operations == prior


def test_broken_read32_fail_closed_without_any_command_write():
    class BrokenPort(WordPort):
        def read32(self, address):
            if address == BASE + 0x30:
                raise OSError("Uncertain bus read")
            return super().read32(address)

    bus = BrokenPort()
    driver = make_driver(bus)
    with pytest.raises(HardwareABIAdmissionError):
        driver.admit()
    with pytest.raises(HardwareABIAdmissionError):
        driver.open_site(2)
    assert not any(op[0] == "w" for op in bus.operations)

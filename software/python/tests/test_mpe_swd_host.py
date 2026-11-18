"""Inert Host-only MPE PS transaction control tests, no /dev/mem or DUT."""
from __future__ import annotations

import pytest

from plasma_interfaces.mpe_swd import (
    MPE_ABI, MPE_BASE, MPE_MAGIC, MpeAccessError,
    MpeSWDController, MpeStatus,
)


class VirtualWordPort:
    def __init__(self, *, status=MpeStatus.OK, data=0x1BA01477, ack=1,
                 data_valid=True):
        self.storage = {
            MPE_BASE: MPE_MAGIC,
            MPE_BASE + 4: MPE_ABI,
            MPE_BASE + 8: 3,
        }
        self.stimulus = status
        self.data = data
        self.ack = ack
        self.data_valid = data_valid
        self.write_log = []
        self.barriers = 0
        self.calls = 0
        for n in (1, 2):
            base = MPE_BASE + n * 0x1000
            self.storage[base] = 0x10000 | n
            self.storage[base + 4] = 0  # disabled, idle

    def read32(self, address):
        self.calls += 1
        return self.storage.get(address, 0)

    def write32(self, address, value):
        self.write_log.append((address, value))
        base = address & ~0xFFF
        offset = address - base
        if offset == 0x28:
            self.storage[base + 4] = 1 if value & 1 else 0
        elif offset == 0x14:
            tag = value >> 16
            word = (
                tag << 16 |
                1 << 12 | 1 << 8 |
                int(self.data_valid) << 7 |
                self.ack << 4 | int(self.stimulus)
            )
            self.storage[base + 0x18] = word
            self.storage[base + 0x1C] = self.data if self.data_valid else 0
            self.storage[base + 4] = 5  # enabled+done
        elif offset == 0x20:
            assert value == self.storage[base + 0x18] >> 16
            self.storage[base + 4] = 1
        else:
            self.storage[address] = value

    def write_barrier(self):
        self.barriers += 1


def test_mpe_controller_is_inert_until_explicit_probe_or_enable():
    backend = VirtualWordPort()
    controller = MpeSWDController(backend, site_id=1)
    assert not backend.write_log and not backend.calls
    controller.probe()
    assert backend.calls == 4
    controller.enable()
    assert (MPE_BASE + 0x1028, 1) in backend.write_log


def test_site1_reset_and_dpidr_are_transaction_commands_not_bitbang():
    backend = VirtualWordPort()
    driver = MpeSWDController(backend, site_id=1)
    driver.enable()
    # Reset: virtual backend MUST say data-invalid; no synthesized DPIDR.
    backend.data_valid = False
    backend.ack = 0
    reset = driver.transact(tag=11, line_reset=True, half=500)
    assert reset.status == MpeStatus.OK
    assert not reset.data_valid
    assert backend.write_log[-1] == (driver.base + 0x20, 11)
    backend.data_valid = True
    backend.ack = 1
    read = driver.transact(tag=12, read=True, address=0, half=100)
    assert read.site_id == 1 and read.tag == 12
    assert read.status == MpeStatus.OK
    assert read.ack == 1 and read.data_valid
    assert read.data == 0x1BA01477
    assert backend.write_log[-1] == (driver.base + 0x20, 12)
    assert (driver.base + 0x14, (11 << 16) | 0x100) in backend.write_log
    assert (driver.base + 0x14, (12 << 16) | 0x2) in backend.write_log
    assert backend.barriers >= 7
    # No individual SWCLK or SWDIO drive register writes.
    assert all(off not in (driver.base + 0x100, driver.base + 0x104)
               for off, _ in backend.write_log)


def test_two_site_controllers_have_disjoint_mmio_command_addresses():
    backend = VirtualWordPort(data_valid=False, ack=0)
    a = MpeSWDController(backend, site_id=1)
    b = MpeSWDController(backend, site_id=2)
    a.enable()
    b.enable()
    assert a.transact(tag=1, line_reset=True).site_id == 1
    assert b.transact(tag=1, line_reset=True).site_id == 2
    assert (a.base + 0x14, (1 << 16) | 0x100) in backend.write_log
    assert (b.base + 0x14, (1 << 16) | 0x100) in backend.write_log
    assert a.base != b.base


def test_wait_response_never_automatically_retries():
    backend = VirtualWordPort(status=MpeStatus.SWD_WAIT, data_valid=False, ack=2)
    controller = MpeSWDController(backend, site_id=2)
    controller.enable()
    got = controller.transact(tag=8, read=True)
    assert got.status == MpeStatus.SWD_WAIT
    assert got.ack == 2 and not got.data_valid
    assert not controller.poisoned
    pushes = [x for x in backend.write_log if x[0] == controller.base + 0x14]
    assert len(pushes) == 1


def test_parity_is_fatal_in_owner_epoch():
    backend = VirtualWordPort(status=MpeStatus.PARITY, data_valid=False, ack=1)
    controller = MpeSWDController(backend, site_id=1)
    controller.enable()
    got = controller.transact(tag=1, read=True)
    assert got.status == MpeStatus.PARITY and controller.poisoned
    with pytest.raises(MpeAccessError):
        controller.transact(tag=2, read=True)


@pytest.mark.parametrize("site", [0, 3, True, "1"])
def test_invalid_site_never_accesses_mmio(site):
    port = VirtualWordPort()
    with pytest.raises(ValueError):
        MpeSWDController(port, site_id=site)
    assert port.calls == 0


@pytest.mark.parametrize("kwargs", [
    {"tag": 0}, {"tag": 65536}, {"tag": True},
    {"tag": 1, "half": 1},
    {"tag": 1, "timeout": 0},
    {"tag": 1, "address": 2},
    {"tag": 1, "read": True, "data": 1},
    {"tag": 1, "line_reset": True, "read": True},
    {"tag": 1, "ap": 1},
])
def test_invalid_request_is_rejected_before_io(kwargs):
    port = VirtualWordPort()
    ctl = MpeSWDController(port, site_id=1)
    with pytest.raises((ValueError, TypeError)):
        ctl.transact(**kwargs)
    assert port.calls == 0 and not port.write_log


def test_abi_mismatch_poison_no_command():
    port = VirtualWordPort()
    port.storage[MPE_BASE] = 0x50425357  # historical bitbang identity
    ctl = MpeSWDController(port, site_id=1)
    with pytest.raises(MpeAccessError, match="identity"):
        ctl.enable()
    assert ctl.poisoned
    assert not port.write_log


def test_tag_reuse_forbidden_without_any_new_hardware_io():
    port = VirtualWordPort(data_valid=False, ack=0)
    ctl = MpeSWDController(port, site_id=1)
    ctl.enable()
    ctl.transact(tag=20, line_reset=True)
    prior = port.calls
    with pytest.raises(ValueError, match="unique"):
        ctl.transact(tag=20, line_reset=True)
    assert port.calls == prior


def test_bounded_poll_failure_poison_without_replay():
    port = VirtualWordPort()
    ctl = MpeSWDController(port, site_id=1, max_polls=3)
    ctl.enable()
    # Host-only injected backend that does not complete a pushed command.
    original = port.write32

    def never_complete(address, value):
        original(address, value)
        if address == ctl.base + 0x14:
            port.storage[ctl.base + 4] = 3

    port.write32 = never_complete
    with pytest.raises(MpeAccessError, match="budget"):
        ctl.transact(tag=1, line_reset=True)
    assert ctl.poisoned
    assert len([x for x in port.write_log if x[0] == ctl.base + 0x14]) == 1

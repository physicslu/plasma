"""Host-only shared LinuxMMIO/SiteMMIO adapter tests; NO hardware devices.

A sparse regular file stands in for two memory-mapped pages. It does NOT
emulate AXI timing or prove ARMv7 LDR/STR, DMB, PS7 or DUT qualification.
"""
from __future__ import annotations

import struct

import pytest

from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOAperture, MMIOClosed, MMIOError
from plasma_interfaces.swd_native_linux_mmio import (
    SwdNativeLinuxMMIOPort, swd_site_aperture,
)
from plasma_interfaces.swd_site import SITE_BASES, SwdSiteController, SiteAccessError


@pytest.fixture
def fake_axi(tmp_path):
    path = tmp_path / "sparse-two-site-AXI-fixture"
    with path.open("wb") as handle:
        handle.truncate(SITE_BASES[2] + 4096)
        for site, base in SITE_BASES.items():
            handle.seek(base)
            handle.write(struct.pack("<I", 0x00050000 | site))
            handle.seek(base + 0x04)
            handle.write(struct.pack("<I", 1))  # static fake, not AXI FSM
    return path, tmp_path / "mmio-owner.lock"


def mmio(fake_axi, *, apertures=None, readonly=False, device=None):
    path, lock = fake_axi
    return LinuxMMIO(
        apertures or (swd_site_aperture(1), swd_site_aperture(2)),
        device=str(device or path), owner_lock=str(lock), readonly=readonly,
    )


def test_exact_read_write_register_policy_excludes_retired_debug():
    a, b = swd_site_aperture(1), swd_site_aperture(2)
    assert a.base == 0x43C01000 and b.base == 0x43C02000
    assert a.size == b.size == 4096
    assert 0x38 in a.readable and 0x38 in a.writable
    assert 0x14 in a.writable and 0x14 not in a.readable
    assert 0x18 in a.readable and 0x18 not in a.writable
    assert 0x44 in a.writable and 0x44 not in a.readable
    for retired in (0x3C, 0x40):
        assert retired not in a.readable | a.writable
        assert retired not in b.readable | b.writable
    for bad in (0, 3, True, "1", 1.0):
        with pytest.raises(MMIOError):
            swd_site_aperture(bad)


def test_two_real_site_leases_over_one_fake_file_and_v5_probe(fake_axi):
    barriers = []
    with mmio(fake_axi) as backend:
        with backend.claim_site(1, SITE_BASES[1]) as lease1:
            with backend.claim_site(2, SITE_BASES[2]) as lease2:
                a = SwdNativeLinuxMMIOPort(
                    lease1, host_test_barrier=lambda: barriers.append(1))
                b = SwdNativeLinuxMMIOPort(
                    lease2, host_test_barrier=lambda: barriers.append(2))
                site1 = SwdSiteController(a, site_id=1)
                site2 = SwdSiteController(b, site_id=2)
                site1.probe()
                site2.probe()
                site1.enter_normal()
                site2.enter_normal(irq=True)
                assert a.read32(SITE_BASES[1] + 0x38) == 1
                assert b.read32(SITE_BASES[2] + 0x38) == 1
                assert a.read32(SITE_BASES[1]) == 0x50001
                assert b.read32(SITE_BASES[2]) == 0x50002
                assert 1 in barriers and 2 in barriers
                assert backend.stats().write32 == len(barriers)
                with pytest.raises(MMIOError):
                    a.read32(SITE_BASES[2])
                with pytest.raises(MMIOError):
                    b.write32(SITE_BASES[1] + 0x28, 1)
                with pytest.raises(MMIOError, match="claimed"):
                    backend.claim_site(1, SITE_BASES[2])
                with pytest.raises(MMIOError, match="claimed"):
                    backend.claim_site(2, SITE_BASES[1])


def test_unsupported_offsets_and_invalid_fullword_never_touch_mapping(fake_axi):
    with mmio(fake_axi) as backend:
        with backend.claim_site(1, SITE_BASES[1]) as lease:
            port = SwdNativeLinuxMMIOPort(lease, host_test_barrier=lambda: None)
            for offset in (0x10, 0x14, 0x20, 0x3C, 0x40, 0x44, 0x64):
                with pytest.raises(MMIOError):
                    port.read32(port.base + offset)
            for offset in (0x00, 0x04, 0x18, 0x1C, 0x24, 0x3C, 0x40):
                with pytest.raises(MMIOError):
                    port.write32(port.base + offset, 1)
            for address in (port.base + 1, port.base + 4096,
                            SITE_BASES[2], True, "0x43C01000"):
                with pytest.raises(MMIOError):
                    port.read32(address)
            for value in (-1, True, 0x1_0000_0000, "1"):
                with pytest.raises(MMIOError):
                    port.write32(port.base + 0x10, value)
            assert backend.stats().read32 == 0
            assert backend.stats().write32 == 0
            assert backend._pages == {}


def test_wrong_lease_policy_and_missing_barrier_fail_closed(fake_axi):
    with mmio(fake_axi) as backend:
        with backend.claim_site(2, SITE_BASES[1]) as mismatched:
            with pytest.raises(MMIOError, match="mismatch"):
                SwdNativeLinuxMMIOPort(
                    mismatched, host_test_barrier=lambda: None)
        with backend.claim_site(1, SITE_BASES[1]) as lease:
            with pytest.raises(MMIOError, match="exactly one"):
                SwdNativeLinuxMMIOPort(lease)
            with pytest.raises(MMIOError, match="SHA-checked"):
                SwdNativeLinuxMMIOPort(lease, barrier=lambda: None)
            with pytest.raises(MMIOError, match="callable"):
                SwdNativeLinuxMMIOPort(lease, host_test_barrier=42)
            with pytest.raises(MMIOError, match="exactly one"):
                SwdNativeLinuxMMIOPort(
                    lease, barrier=object(), host_test_barrier=lambda: None)
        with pytest.raises(MMIOError, match="SiteMMIO"):
            SwdNativeLinuxMMIOPort(object(), host_test_barrier=lambda: None)
    bad = MMIOAperture(
        SITE_BASES[1], readable=frozenset((0, 4)),
        writable=frozenset((0x38,)))
    with mmio(fake_axi, apertures=(bad,)) as backend:
        with backend.claim_site(1, SITE_BASES[1]) as lease:
            with pytest.raises(MMIOError, match="Exact ABI-v5"):
                SwdNativeLinuxMMIOPort(
                    lease, host_test_barrier=lambda: None)
    with mmio(fake_axi, readonly=True) as backend:
        with backend.claim_site(1, SITE_BASES[1]) as lease:
            with pytest.raises(MMIOError, match="writable"):
                SwdNativeLinuxMMIOPort(
                    lease, host_test_barrier=lambda: None)


def test_fake_only_barrier_rejects_symlink_not_native_device(fake_axi, tmp_path):
    alias = tmp_path / "fake-link"
    alias.symlink_to(fake_axi[0])
    with mmio(fake_axi, device=alias) as backend:
        with backend.claim_site(1, SITE_BASES[1]) as lease:
            with pytest.raises(MMIOError, match="device or symlink"):
                SwdNativeLinuxMMIOPort(
                    lease, host_test_barrier=lambda: None)


def test_barrier_failure_poison_shared_parent_and_both_owners(fake_axi):
    attempts = []

    def bad_barrier():
        attempts.append("call")
        raise RuntimeError("indeterminate AXI write ordering")

    with mmio(fake_axi) as backend:
        with backend.claim_site(1, SITE_BASES[1]) as first:
            with backend.claim_site(2, SITE_BASES[2]) as second:
                a = SwdNativeLinuxMMIOPort(
                    first, host_test_barrier=bad_barrier)
                b = SwdNativeLinuxMMIOPort(
                    second, host_test_barrier=lambda: None)
                controller = SwdSiteController(a, site_id=1)
                controller.probe()
                with pytest.raises(SiteAccessError, match="no replay"):
                    controller.enter_normal()
                assert controller.poisoned
                assert attempts == ["call"]
                stats = backend.stats()
                with pytest.raises(MMIOError, match="poisoned"):
                    b.read32(SITE_BASES[2])
                with pytest.raises(MMIOError, match="poisoned"):
                    a.write32(SITE_BASES[1] + 0x38, 0)
                assert backend.stats() == stats


def test_released_site_cannot_regain_authority_from_stale_port(fake_axi):
    with mmio(fake_axi) as backend:
        lease = backend.claim_site(1, SITE_BASES[1])
        port = SwdNativeLinuxMMIOPort(lease, host_test_barrier=lambda: None)
        lease.close()
        with pytest.raises(MMIOClosed):
            port.read32(SITE_BASES[1])
        with pytest.raises(MMIOClosed):
            port.write32(SITE_BASES[1] + 0x38, 1)
        with pytest.raises(MMIOClosed):
            port.write_barrier()


def test_stale_v4_identity_is_rejected_before_any_write(fake_axi):
    with mmio(fake_axi) as backend:
        with backend.claim_site(1, SITE_BASES[1]) as lease:
            port = SwdNativeLinuxMMIOPort(
                lease, host_test_barrier=lambda: None)
            # This is a synthetic ordinary file; only the host fixture may
            # change the read-only identity, never a real AXI control path.
            with fake_axi[0].open("r+b") as f:
                f.seek(SITE_BASES[1])
                f.write(struct.pack("<I", 0x00040001))
            driver = SwdSiteController(port, site_id=1)
            with pytest.raises(SiteAccessError, match="identity"):
                driver.probe()
            assert driver.poisoned and backend.stats().write32 == 0

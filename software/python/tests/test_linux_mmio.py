"""Host-only PLASMA native MMIO tests. Uses regular files; NEVER /dev/mem."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
import sys
from threading import Event, Thread

import pytest

from plasma_interfaces.linux_mmio import (
    LinuxMMIO, MMIOAperture, MMIOClosed, MMIOError, MMIOStats, swd03_aperture,
)
from plasma_interfaces.swd_transaction import SWDTransactionDriver


def ap(base=0x1000):
    return MMIOAperture(
        base=base, readable=frozenset({0, 4, 8}),
        writable=frozenset({0, 4, 8}),
    )


@pytest.fixture
def ram(tmp_path):
    device = tmp_path / "ordinary-file-not-devmem"
    with device.open("wb") as f:
        f.truncate(0x20000)
    return str(device), str(tmp_path / "owner.lock")


def backend(ram, *apertures, readonly=False):
    device, lock = ram
    return LinuxMMIO(apertures or (ap(),), device=device,
                     owner_lock=lock, readonly=readonly)


def test_native_u32_read_write_and_adjacent_words(ram):
    with backend(ram) as mmio:
        assert mmio.read32(0x1000) == 0
        mmio.write32(0x1000, 0x12345678)
        mmio.write32(0x1004, 0x87654321)
        mmio.write32(0x1008, 0x00000000)
        assert mmio.read32(0x1000) == 0x12345678
        assert mmio.read32(0x1004) == 0x87654321
        view = mmio._words[0x1000]
        page = mmio._pages[0x1000]
        assert view.itemsize == 4
    assert page.closed and mmio._words == {} and mmio._pages == {}
    with open(ram[0], "rb") as file:
        file.seek(0x1000)
        assert file.read(12) == bytes.fromhex("785634122143658700000000")


def test_policy_rejects_invalid_before_mapping(ram):
    with backend(ram) as mmio:
        for address in (0x1001, 0x1002, 0x1003, 0x100C, 0x2000,
                        -1, 0x100000000, True, None, "4096"):
            with pytest.raises(MMIOError):
                mmio.read32(address)
            with pytest.raises(MMIOError):
                mmio.write32(address, 1)
        for value in (True, None, -1, 1 << 32, "1", 1.5):
            with pytest.raises(MMIOError):
                mmio.write32(0x1000, value)
        assert mmio._pages == {} and mmio._words == {}
        mmio.write32(0x1000, 1)


@pytest.mark.parametrize("bad", [
    MMIOAperture(0x1000, frozenset({0}), frozenset({0})),
])
def test_valid_aperture_reference(bad):
    assert bad.base == 0x1000


@pytest.mark.parametrize("spec", [
    dict(base=0x1001, readable=frozenset({0}), writable=frozenset()),
    dict(base=0x1000, readable=frozenset({1}), writable=frozenset()),
    dict(base=0x1000, readable=frozenset({4094}), writable=frozenset()),
    dict(base=0x1000, readable=frozenset(), writable=frozenset()),
    dict(base=0x1000, readable={0}, writable=frozenset()),
    dict(base=0x1000, readable=frozenset({True}), writable=frozenset()),
    dict(base=True, readable=frozenset({0}), writable=frozenset()),
])
def test_invalid_apertures_denied(spec):
    with pytest.raises(MMIOError):
        MMIOAperture(**spec)


def test_overlapping_or_unconfigured_aperture_refused(ram):
    with pytest.raises(MMIOError):
        backend(ram, ap(), ap())
    with pytest.raises(MMIOError):
        LinuxMMIO([], device=ram[0], owner_lock=ram[1])


def test_readonly_maps_prot_read_and_denies_write(ram):
    with backend(ram, readonly=True) as mmio:
        with pytest.raises(MMIOError, match="read-only"):
            mmio.write32(0x1000, 0)
        assert mmio._pages == {}
        assert mmio.read32(0x1000) == 0
        assert mmio._words[0x1000].readonly
        page = mmio._pages[0x1000]
    assert page.closed


def test_process_lock_denies_second_instance_and_releases(ram):
    first = backend(ram)
    second = backend(ram)
    with first:
        with pytest.raises(MMIOError, match="owned"):
            second.open()
        first.write32(0x1000, 5)
    with backend(ram) as new:
        assert new.read32(0x1000) == 5


def test_site_leases_isolate_two_apertures(ram):
    with backend(ram, ap(0x1000), ap(0x2000)) as mmio:
        with mmio.claim_site(1, 0x1000) as site1:
            with mmio.claim_site(2, 0x2000) as site2:
                site1.write32(0x1000, 0xAABBCCDD)
                site2.write32(0x2000, 0x55667788)
                assert site1.read32(0x1000) == 0xAABBCCDD
                assert site2.read32(0x2000) == 0x55667788
                with pytest.raises(MMIOError, match="escapes"):
                    site1.read32(0x2000)
                with pytest.raises(MMIOError, match="escapes"):
                    site2.write32(0x1000, 0)
                with pytest.raises(MMIOError, match="claimed"):
                    mmio.claim_site(3, 0x1000)
                with pytest.raises(MMIOError, match="claimed"):
                    mmio.claim_site(1, 0x2000)
        with pytest.raises(MMIOClosed):
            site1.read32(0x1000)
        with mmio.claim_site(1, 0x1000) as again:
            assert again.read32(0x1000) == 0xAABBCCDD


def test_close_invalidates_leases_without_buffer_error(ram):
    with backend(ram) as mmio:
        lease = mmio.claim_site(1, 0x1000)
        lease.write32(0x1000, 1)
        page = mmio._pages[0x1000]
        mmio.close()
        mmio.close()  # idempotent close
        assert page.closed
        with pytest.raises(MMIOClosed):
            lease.read32(0x1000)
        with pytest.raises(MMIOClosed):
            mmio.read32(0x1000)
        with pytest.raises(MMIOClosed):
            mmio.open()
    with backend(ram) as new:
        assert new.read32(0x1000) == 1


def test_reload_is_fail_closed_while_claims_live(ram):
    with backend(ram) as mmio:
        lease = mmio.claim_site(1, 0x1000)
        with pytest.raises(MMIOError, match="active Site"):
            mmio.quiesce_for_reload()
        lease.close()
        mmio.quiesce_for_reload()
        with pytest.raises(MMIOClosed):
            mmio.read32(0x1000)


def test_swd05_accepts_real_native_lease_without_touching_pl(ram):
    # SWD-05 constructor reads only ABI; file-backed regular RAM is NOT RTL.
    with open(ram[0], "r+b") as f:
        f.seek(0x1000)
        f.write((1).to_bytes(4, sys.byteorder))
    with backend(ram, swd03_aperture(0x1000)) as mmio:
        with mmio.claim_site(1, 0x1000) as port:
            driver = SWDTransactionDriver(port, base=0x1000, site_id=1)
            assert driver.base == 0x1000
            assert mmio.read32(0x1000) == 1
            with pytest.raises(MMIOError):
                port.write32(0x1000, 1)  # ABI register is read-only
            with pytest.raises(MMIOError):
                port.read32(0x1004)      # COMMAND register is write-only


def test_eight_site_concurrent_access_and_no_cross_site_pollution(ram):
    bases = [0x1000 + i * 0x1000 for i in range(8)]
    with backend(ram, *(ap(base) for base in bases)) as mmio:
        ports = [mmio.claim_site(i + 1, base) for i, base in enumerate(bases)]

        def worker(idx):
            port = ports[idx]
            value = (idx + 1) << 24
            for n in range(1200):
                port.write32(port.base, value | n)
                assert port.read32(port.base) == value | n
            return port.read32(port.base)

        with ThreadPoolExecutor(max_workers=8) as pool:
            observed = list(pool.map(worker, range(8)))
        assert observed == [((i + 1) << 24) | 1199 for i in range(8)]
        # Access counters are shared, lock-protected and exclude the snapshot.
        assert mmio.stats() == MMIOStats(read32=8 * 1201, write32=8 * 1200)
        for port in ports:
            port.close()


def test_thread_close_race_never_dereferences_unmapped_memory(ram):
    # Synchronization of a single MMIO call vs close; not a transaction lock.
    with backend(ram) as mmio:
        port = mmio.claim_site(1, 0x1000)
        entered = Event()
        results = []

        def writer():
            entered.set()
            for n in range(200000):
                try:
                    port.write32(0x1000, n)
                except MMIOClosed:
                    results.append("closed")
                    return
            results.append("finished")

        thread = Thread(target=writer)
        thread.start()
        assert entered.wait(timeout=2)
        mmio.close()
        thread.join(timeout=5)
        assert not thread.is_alive()
        assert results in (["closed"], ["finished"])


def test_read_write_permissions_independent(ram):
    cfg = MMIOAperture(
        base=0x1000, readable=frozenset({0, 8}),
        writable=frozenset({4, 8}),
    )
    with backend(ram, cfg) as mmio:
        mmio.write32(0x1004, 0x1234)
        assert mmio.read32(0x1000) == 0
        with pytest.raises(MMIOError):
            mmio.read32(0x1004)
        with pytest.raises(MMIOError):
            mmio.write32(0x1000, 1)


def test_concurrent_process_owner_scope_is_advisory(ram):
    # The lock file prevents cooperating instances, NOT uncooperative root.
    with backend(ram) as owner:
        assert os.path.exists(ram[1])
        owner.write32(0x1000, 0x55)



def test_lifetime_safe_mmio_stats_count_only_successful_word_accesses(ram):
    driver = backend(ram)
    assert driver.stats() == MMIOStats(read32=0, write32=0)
    with driver:
        driver.write32(0x1000, 0x12345678)
        assert driver.read32(0x1000) == 0x12345678
        # Invalid offsets, alignment and values cannot increment counts.
        for call in (
            lambda: driver.read32(0x1001),
            lambda: driver.write32(0x100C, 1),
            lambda: driver.write32(0x1000, True),
        ):
            with pytest.raises(MMIOError):
                call()
        snap = driver.stats()
        assert snap == MMIOStats(read32=1, write32=1)
        assert driver.stats() == snap  # observing metrics must be inert
    assert driver.stats() == MMIOStats(read32=1, write32=1)
    with pytest.raises(MMIOClosed):
        driver.read32(0x1000)
    assert driver.stats() == snap

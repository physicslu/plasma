"""Phase 2A UIOBackend Host-only regression — ordinary files and fake sysfs.

These tests never open a Linux character device, run AXI, or use real Z2.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import os
from pathlib import Path
import sys
from threading import Event, Thread

import pytest

from plasma_interfaces.linux_mmio import (
    LinuxMMIO, MMIOAperture, MMIOClosed, MMIOError, MMIOStats,
)
from plasma_interfaces.uio_backend import UIOBackend, UIOPin
from plasma_interfaces.swd_transaction import SWDTransactionDriver


def ap(base=0x40004000):
    return MMIOAperture(
        base=base,
        readable=frozenset({0, 4, 8}),
        writable=frozenset({4, 8}),
    )


@pytest.fixture
def fixture(tmp_path):
    sysroot = tmp_path / "sys"
    uio = sysroot / "class/uio/uio3"
    mapping = uio / "maps/map0"
    mapping.mkdir(parents=True)
    for key, value in (
        ("addr", "0x40000000"), ("size", "0x10000"),
        ("offset", "0x0"), ("name", "fabric-map")
    ):
        (mapping / key).write_text(value)
    (uio / "name").write_text("fabric")
    platform = tmp_path / "platform/40000000.fabric"
    driver = tmp_path / "drivers/uio_pdrv_genirq"
    platform.mkdir(parents=True)
    driver.mkdir(parents=True)
    (platform / "driver").symlink_to(driver, target_is_directory=True)
    (uio / "device").symlink_to(platform, target_is_directory=True)
    mock = tmp_path / "ordinary-file-mock-not-a-uio-device"
    with mock.open("wb") as fp:
        fp.truncate(0x20000)
    pin = UIOPin("uio3", "fabric", "40000000.fabric",
                 "uio_pdrv_genirq", 0, 0x40000000, 0x10000)
    return dict(sysroot=sysroot, uio=uio, map=mapping, mock=mock, pin=pin,
                lock=tmp_path / "ppu-mmio.lock", platform=platform,
                driver=driver)


def backend(fixture, *aps, readonly=False, generation=5, **override):
    values = dict(
        pin=fixture["pin"],
        apertures=tuple(aps or (ap(),)),
        sysroot=fixture["sysroot"],
        device_file=fixture["mock"],
        owner_lock=fixture["lock"],
        readonly=readonly, generation=generation,
    )
    values.update(override)
    return UIOBackend(**values)


def test_pinned_map0_native_u32_reads_writes_and_no_byte_pack(fixture):
    with backend(fixture) as b:
        with b.claim_site(1, 0x40004000) as port:
            port.write32(0x40004004, 0x12345678)
            port.write32(0x40004008, 0x87654321)
            assert port.read32(0x40004004) == 0x12345678
            assert port.read32(0x40004008) == 0x87654321
            assert b.stats() == MMIOStats(read32=2, write32=2)
            mapped = b._map
            assert b._words.itemsize == 4
            assert b._map is not None
    assert mapped.closed
    with fixture["mock"].open("rb") as fp:
        fp.seek(0x4004)
        assert fp.read(8) == b"\x78\x56\x34\x12\x21\x43\x65\x87"


def test_site_whitelist_and_invalid_args_before_mapping(fixture):
    with backend(fixture) as b:
        port = b.claim_site(1, 0x40004000)
        for invalid in (0x40004001, 0x4000400C, 0x40005000,
                        True, None, -1, 0x100000000, "0x40004004"):
            with pytest.raises(MMIOError):
                port.read32(invalid)
        for invalid in (True, None, -1, 0x100000000, "1"):
            with pytest.raises(MMIOError):
                port.write32(0x40004004, invalid)
        with pytest.raises(MMIOError):
            port.write32(0x40004000, 5)  # read-only register
        assert b._map is None
        port.write32(0x40004004, 123)
        port.close()
        with pytest.raises(MMIOClosed):
            port.read32(0x40004000)


def test_site_claim_duplicate_rejected_and_close_invalidates(fixture):
    with backend(fixture, ap(), ap(0x40005000)) as b:
        one = b.claim_site(1, 0x40004000)
        two = b.claim_site(2, 0x40005000)
        with pytest.raises(MMIOError, match="already claimed"):
            b.claim_site(1, 0x40005000)
        with pytest.raises(MMIOError, match="already claimed"):
            b.claim_site(3, 0x40004000)
        with pytest.raises(MMIOError, match="allowlist"):
            one.write32(0x40005004, 1)
        with pytest.raises(MMIOError, match="allowlist"):
            two.read32(0x40004000)
        with pytest.raises(MMIOError, match="active Site"):
            b.quiesce_for_reload()
        one.close()
        two.close()
        b.quiesce_for_reload()
        assert b.generation == 6
        with pytest.raises(MMIOClosed):
            one.read32(0x40004000)
        with pytest.raises(MMIOClosed):
            b.open()
        b.close()  # final idempotent close


def test_forked_process_inherits_no_valid_owner(monkeypatch, fixture):
    with backend(fixture) as b:
        p = b.claim_site(1, 0x40004000)
        real_pid = os.getpid()
        monkeypatch.setattr("plasma_interfaces.uio_backend.os.getpid", lambda: real_pid + 1)
        with pytest.raises(MMIOClosed, match="fork"):
            p.read32(0x40004000)


def test_two_and_eight_site_independent_physical_apertures(fixture):
    bases = tuple(0x40004000 + x * 0x1000 for x in range(8))
    with backend(fixture, *(ap(x) for x in bases)) as b:
        ports = [b.claim_site(i + 1, base) for i, base in enumerate(bases)]
        def worker(i):
            port = ports[i]
            for n in range(50):
                port.write32(port.base + 4, ((i + 1) << 24) | n)
                assert port.read32(port.base + 4) == ((i + 1) << 24) | n
            return port.read32(port.base + 4)
        with ThreadPoolExecutor(max_workers=8) as pool:
            assert list(pool.map(worker, range(8))) == [
                ((i + 1) << 24) | 49 for i in range(8)
            ]
        assert b.stats() == MMIOStats(read32=8 * 51, write32=8 * 50)
        for port in ports:
            port.close()


def test_quiesce_and_close_race_without_dangling_mmap(fixture):
    with backend(fixture) as b:
        port = b.claim_site(1, 0x40004000)
        done = Event()
        result = []
        def writer():
            done.set()
            for n in range(5000):
                try:
                    port.write32(0x40004004, n)
                except MMIOClosed:
                    result.append("closed")
                    return
            result.append("finished")
        t = Thread(target=writer)
        t.start()
        assert done.wait(timeout=2)
        b.close()
        t.join(timeout=5)
        assert not t.is_alive()
        assert result in (["closed"], ["finished"])
        with pytest.raises(MMIOClosed):
            port.write32(0x40004004, 1)


def test_same_lock_file_conflicts_between_uio_backends(fixture):
    first, second = backend(fixture), backend(fixture)
    with first:
        with pytest.raises(MMIOError, match="owner refused"):
            second.open()
    with backend(fixture) as third:
        assert third.claim_site(1, 0x40004000).read32(0x40004000) == 0


def test_shared_flock_boundary_with_existing_linux_devmem_backend(fixture):
    # Both run against ordinary files; demonstrates cooperative lock only.
    with LinuxMMIO([ap()], device=str(fixture["mock"]),
                   owner_lock=str(fixture["lock"])) as legacy:
        with pytest.raises(MMIOError, match="owner refused"):
            backend(fixture).open()
    with backend(fixture) as b:
        with pytest.raises(MMIOError, match="owned"):
            LinuxMMIO([ap()], device=str(fixture["mock"]),
                      owner_lock=str(fixture["lock"])).open()
        assert b.stats() == MMIOStats(0, 0)


def test_readonly_default_denies_write_without_mapping(fixture):
    b = UIOBackend(fixture["pin"], (ap(),), sysroot=fixture["sysroot"],
                   device_file=fixture["mock"], owner_lock=fixture["lock"],
                   generation=1)
    with b:
        p = b.claim_site(1, 0x40004000)
        with pytest.raises(MMIOError, match="Read-only"):
            p.write32(0x40004004, 1)
        assert b._map is None
        assert p.read32(0x40004000) == 0
        assert b._words.readonly


def test_uio_map2_selector_and_nonzero_physical_page_offset(tmp_path, fixture):
    map0 = fixture["map"]
    for item in ("addr", "size", "offset"):
        (map0 / item).unlink()
    map0.rmdir() if not (map0 / "name").exists() else (map0 / "name").unlink()
    if map0.exists():
        map0.rmdir()
    map2 = map0.parent / "map2"
    map2.mkdir()
    for k, v in (("addr", "0x50000180"), ("size", "0x3800"),
                 ("offset", "0x180"), ("name", "non-aligned")):
        (map2 / k).write_text(v)
    pin = UIOPin("uio3", "fabric", "40000000.fabric",
                 "uio_pdrv_genirq", 2, 0x50000180, 0x3800, 0x180)
    cfg = ap(0x50001000)
    # Index inside mmap = physical 0x50001000 - (base - offset 0x50000000) = 0x1000.
    with backend(fixture, cfg, pin=pin) as b:
        port = b.claim_site(1, 0x50001000)
        port.write32(0x50001004, 0xC0FFEE)
        assert port.read32(0x50001004) == 0xC0FFEE
        assert b._map is not None
    with fixture["mock"].open("rb") as fp:
        fp.seek(2 * 4096 + 0x1004)
        assert int.from_bytes(fp.read(4), "little") == 0xC0FFEE


@pytest.mark.parametrize("field,bad", [
    ("addr", "0x40001000"), ("size", "0x2000"),
    ("offset", "0x4"), ("size", "0"), ("size", "not_hex"),
])
def test_pinned_resource_drift_rejected_before_device_open(fixture, field, bad):
    (fixture["map"] / field).write_text(bad)
    b = backend(fixture)
    with pytest.raises(MMIOError):
        b.open()
    assert b._fd is None
    assert b._map is None


def test_driver_identity_changed_fails_before_open(fixture):
    (fixture["platform"] / "driver").unlink()
    with pytest.raises(MMIOError, match="binding"):
        backend(fixture).open()


def test_sysfs_resource_changes_during_operations_poison_backend(fixture):
    with backend(fixture) as b:
        port = b.claim_site(1, 0x40004000)
        assert port.read32(0x40004000) == 0
        (fixture["map"] / "size").write_text("0x2000")
        with pytest.raises(MMIOError, match="uncertain"):
            port.read32(0x40004000)
        with pytest.raises(MMIOError, match="poisoned"):
            port.read32(0x40004000)
        assert b.stats() == MMIOStats(1, 0)


def test_overlapping_second_uio_resource_rejected(fixture):
    other = fixture["sysroot"] / "class/uio/uio7/maps/map0"
    other.mkdir(parents=True)
    for k, v in (("addr", "0x4000F000"), ("size", "0x1000"),
                 ("offset", "0")):
        (other / k).write_text(v)
    with pytest.raises(MMIOError, match="overlap"):
        backend(fixture).open()


def test_unreadable_unknown_uio_map_fails_closed(fixture):
    other = fixture["sysroot"] / "class/uio/uio7"
    other.mkdir()
    with pytest.raises(MMIOError, match="inventory"):
        backend(fixture).open()


@pytest.mark.parametrize("bad", [
    dict(device_name="UIO3"),
    dict(map_index=8),
    dict(physical_base=0x40000004),
    dict(byte_offset=4),
    dict(size=0),
    dict(size=True),
])
def test_invalid_uio_pin_fail_closed(fixture, bad):
    values = fixture["pin"].__dict__.copy()
    values.update(bad)
    with pytest.raises(MMIOError):
        UIOPin(**values)


@pytest.mark.parametrize("bad", [
    "overlap", "missing", "generation", "bool_gen",
])
def test_invalid_runtime_configuration_fails_before_open(fixture, bad):
    vals = {}
    aps = (ap(),)
    if bad == "overlap":
        aps = (ap(), ap())
    elif bad == "missing":
        vals["apertures"] = tuple()
    elif bad == "generation":
        vals["generation"] = 0
    else:
        vals["generation"] = True
    with pytest.raises(MMIOError):
        backend(fixture, *aps, **vals)


def test_host_character_device_and_symlink_denied(fixture):
    symlink = fixture["mock"].parent / "mock-device-symlink"
    symlink.symlink_to(fixture["mock"])
    with pytest.raises(MMIOError, match="ordinary test files"):
        backend(fixture, device_file=symlink).open()
    # /dev/null is a character device: blocked at constructor without opening.
    with pytest.raises(MMIOError, match="forbids real"):
        backend(fixture, device_file=Path("/dev/null"))


def test_swd05_transport_accepts_site_lease_without_real_hardware(fixture):
    from plasma_interfaces.linux_mmio import swd03_aperture
    cfg = swd03_aperture(0x40004000)
    with fixture["mock"].open("r+b") as fp:
        fp.seek(0x4000)
        fp.write((1).to_bytes(4, "little"))
    with backend(fixture, cfg) as b:
        with b.claim_site(1, 0x40004000) as port:
            swd = SWDTransactionDriver(port, base=0x40004000, site_id=1)
            assert swd.base == 0x40004000
            with pytest.raises(MMIOError):
                port.write32(0x40004000, 1)
            with pytest.raises(MMIOError):
                port.read32(0x40004004)


def test_io_fault_poisoned_and_no_automatic_retry(monkeypatch, fixture):
    import plasma_interfaces.uio_backend as module
    b = backend(fixture)
    with b:
        p = b.claim_site(1, 0x40004000)
        def fail(*args, **kwargs):
            raise OSError("injected map failure")
        monkeypatch.setattr(module.mmap, "mmap", fail)
        with pytest.raises(MMIOError, match="uncertain"):
            p.read32(0x40004000)
        with pytest.raises(MMIOError, match="poisoned"):
            p.read32(0x40004000)
        assert b.stats() == MMIOStats(0, 0)

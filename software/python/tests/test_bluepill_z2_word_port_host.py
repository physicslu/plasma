"""Inert 32-bit LinuxMMIO file-backed SWD port tests: no real devices."""
from __future__ import annotations

from pathlib import Path
import pytest

from plasma_interfaces.bluepill_z2_word_port import (
    BLUEPILL_SWD_BASE, bluepill_z2_aperture, BluepillZ2WordPort,
)
from plasma_interfaces.bluepill_remote_bitbang import RemoteBitbangSWD, SWDBitbangError
from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOAperture, MMIOError, MMIOClosed

BASE = BLUEPILL_SWD_BASE


@pytest.fixture
def port_fixture(tmp_path):
    file = tmp_path / "sparse-regular-file-mmio"
    with file.open("wb") as f:
        f.truncate(BASE + 4096)  # sparse, never a device
    with LinuxMMIO((bluepill_z2_aperture(),), device=str(file),
                   owner_lock=str(tmp_path / "owner.lock")) as mmio:
        with mmio.claim_site(1, BASE) as lease:
            yield file, mmio, lease


def word(file: Path, offset: int, value: int) -> None:
    with file.open("r+b") as f:
        f.seek(BASE + offset)
        f.write(value.to_bytes(4, "little"))


def read_word(file: Path, offset: int) -> int:
    with file.open("rb") as f:
        f.seek(BASE + offset)
        return int.from_bytes(f.read(4), "little")


def test_bridge_uses_real_native_file_word_port_and_explicit_barriers(port_fixture):
    f, mmio, lease = port_fixture
    barriers = []
    word(f, 0x00, RemoteBitbangSWD.MAGIC)
    word(f, 0x04, RemoteBitbangSWD.VERSION)
    word(f, 0x0C, 0x8)  # reset SWDIO OUT=1, OE=0, SWCLK=0
    port = BluepillZ2WordPort(lease, host_test_barrier=lambda: barriers.append(1))
    bridge = RemoteBitbangSWD(port, base=BASE)
    bridge.admit()
    bridge.exchange(b"Odf")
    assert read_word(f, 0x08) == 7
    bridge.exchange(b"oQ")
    assert read_word(f, 0x08) == 2
    assert len(barriers) >= 4
    assert mmio._words[BASE].itemsize == 4


def test_no_implicit_hardware_admission_or_test_barrier_on_unknown_backend(port_fixture):
    _, _, lease = port_fixture
    with pytest.raises(MMIOError, match="exactly one"):
        BluepillZ2WordPort(lease)
    with pytest.raises(MMIOError, match="verified native"):
        BluepillZ2WordPort(lease, barrier=object())


@pytest.mark.parametrize("address", [
    BASE - 4, BASE + 1, BASE + 8, BASE + 0x10, BASE + 0x1000,
    -1, True, "0x40008000",
])
def test_reject_non_readable_and_unaligned_before_access(port_fixture, address):
    _, mmio, lease = port_fixture
    port = BluepillZ2WordPort(lease, host_test_barrier=lambda: None)
    with pytest.raises(MMIOError):
        port.read32(address)
    assert mmio._pages == {}


@pytest.mark.parametrize("value", [-1, 8, 0x100, True, "3"])
def test_write_rejects_reserved_drive_bits(port_fixture, value):
    _, mmio, lease = port_fixture
    port = BluepillZ2WordPort(lease, host_test_barrier=lambda: None)
    with pytest.raises(MMIOError):
        port.write32(BASE + 8, value)
    assert mmio._pages == {}


def test_readonly_writeonly_and_ownership_release(port_fixture):
    f, _, lease = port_fixture
    port = BluepillZ2WordPort(lease, host_test_barrier=lambda: None)
    with pytest.raises(MMIOError):
        port.write32(BASE, 1)
    with pytest.raises(MMIOError):
        port.read32(BASE + 8)
    lease.close()
    with pytest.raises(MMIOClosed):
        port.write_barrier()


def test_refuse_wrong_site_and_nonexact_aperture(tmp_path):
    f = tmp_path / "sparse"
    with f.open("wb") as fd:
        fd.truncate(BASE + 4096)
    wrong = MMIOAperture(BASE, frozenset({0, 4, 12, 16}), frozenset({8}))
    with LinuxMMIO((wrong,), device=str(f),
                   owner_lock=str(tmp_path / "owner1.lock")) as mmio:
        with mmio.claim_site(1, BASE) as lease:
            with pytest.raises(MMIOError, match="Exact Blue Pill"):
                BluepillZ2WordPort(lease, host_test_barrier=lambda: None)
    with LinuxMMIO((bluepill_z2_aperture(),), device=str(f),
                   owner_lock=str(tmp_path / "owner2.lock")) as mmio:
        with mmio.claim_site(2, BASE) as lease:
            with pytest.raises(MMIOError, match="Site 1"):
                BluepillZ2WordPort(lease, host_test_barrier=lambda: None)


def test_host_barrier_rejects_symlink(port_fixture, tmp_path):
    f, _, _ = port_fixture
    alias = tmp_path / "alias"
    alias.symlink_to(f)
    with LinuxMMIO((bluepill_z2_aperture(),), device=str(alias),
                   owner_lock=str(tmp_path / "other.lock")) as mmio:
        with mmio.claim_site(1, BASE) as lease:
            with pytest.raises(MMIOError, match="regular file"):
                BluepillZ2WordPort(lease, host_test_barrier=lambda: None)


def test_barrier_failure_poison_and_fail_closed(port_fixture):
    _, mmio, lease = port_fixture
    def fail():
        raise RuntimeError("DMB failed")
    port = BluepillZ2WordPort(lease, host_test_barrier=fail)
    with pytest.raises(RuntimeError, match="DMB"):
        port.write_barrier()
    with pytest.raises(MMIOError, match="poisoned"):
        port.read32(BASE)
    assert mmio._poisoned

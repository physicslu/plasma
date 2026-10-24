"""P0 Fixed ABI Site 1 Host-only native MMIO adapter contracts.

ALL access is to tmp_path REGULAR FILES. No /dev/mem, /dev/uio,
FPGA reload, Z2, SWPC or external DUT is touched.
"""
from __future__ import annotations

import ctypes
import hashlib
import json
import mmap
from pathlib import Path
import platform
import sys

import pytest

from plasma_interfaces.fixed_abi_mmio_port import (
    ARMv7DMBBarrier, FixedABISite1WordPort,
    _FIXED_SITE1_READ, _FIXED_SITE1_WRITE, fixed_abi_site1_aperture,
)
from plasma_interfaces.fixed_abi_swd import FixedABISWDController, FixedABIError
from plasma_interfaces.linux_mmio import LinuxMMIO, MMIOError, MMIOClosed, MMIOAperture

SITE_BASE = 0x4000
ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def file_mmio(tmp_path):
    data = tmp_path / "synthetic-mmio-words"
    with data.open("wb") as stream:
        stream.truncate(0x10000)
    lock = tmp_path / "synthetic-mmio-owner.lock"
    with LinuxMMIO((fixed_abi_site1_aperture(SITE_BASE),),
                   device=str(data), owner_lock=str(lock)) as mmio:
        with mmio.claim_site(1, SITE_BASE) as lease:
            yield data, mmio, lease


def write_fixture_word(path: Path, off: int, value: int):
    with path.open("r+b") as f:
        f.seek(SITE_BASE + off)
        f.write(value.to_bytes(4, "little"))


def read_fixture_word(path: Path, off: int) -> int:
    with path.open("rb") as f:
        f.seek(SITE_BASE + off)
        return int.from_bytes(f.read(4), "little")


def test_exact_fixed_abi_site1_register_allowlist_matches_machine_json():
    abi = json.loads((ROOT / "pl/verification/fixed_image_abi_v1_gate1.json").read_text())
    spec = next(item for item in abi["regions"] if item["name"] == "site_1")
    assert spec["base"] == 0x4000
    assert _FIXED_SITE1_READ == frozenset(
        r["offset"] for r in spec["registers"] if r["access"] in ("ro", "rw"))
    assert _FIXED_SITE1_WRITE == frozenset(
        r["offset"] for r in spec["registers"] if r["access"] in ("wo", "rw"))


def test_file_backed_word_port_has_no_default_barrier(file_mmio):
    _, _, lease = file_mmio
    with pytest.raises(MMIOError, match="exactly one"):
        FixedABISite1WordPort(lease)
    with pytest.raises(MMIOError, match="exactly one"):
        FixedABISite1WordPort(lease, host_test_barrier=lambda: None,
                             barrier=object())


def test_host_file_read_write_are_native_words_and_restrict_access(file_mmio):
    path, mmio, lease = file_mmio
    calls = []
    port = FixedABISite1WordPort(lease, host_test_barrier=lambda: calls.append("DMB"))
    write_fixture_word(path, 0x00, 1)
    assert port.read32(SITE_BASE) == 1
    port.write32(SITE_BASE + 0x24, 0x11223344)
    assert read_fixture_word(path, 0x24) == 0x11223344
    assert mmio._words[SITE_BASE].itemsize == 4
    port.write_barrier()
    assert calls == ["DMB"]


@pytest.mark.parametrize("bad", [
    SITE_BASE + 1, SITE_BASE + 0x7C, SITE_BASE + 0x1000,
    SITE_BASE - 4, -1, 0x100000000, True, "0x4020",
])
def test_illegal_word_address_refused_before_mmio_access(file_mmio, bad):
    _, mmio, lease = file_mmio
    port = FixedABISite1WordPort(lease, host_test_barrier=lambda: None)
    with pytest.raises(MMIOError):
        port.read32(bad)
    with pytest.raises(MMIOError):
        port.write32(bad, 1)
    assert mmio._pages == {}


def test_read_only_and_write_only_registers_never_cross(file_mmio):
    _, _, lease = file_mmio
    port = FixedABISite1WordPort(lease, host_test_barrier=lambda: None)
    with pytest.raises(MMIOError):
        port.write32(SITE_BASE + 0x00, 1)  # ID is RO
    with pytest.raises(MMIOError):
        port.read32(SITE_BASE + 0x20)      # COMMAND is WO


def test_wrong_site_lease_and_incomplete_aperture_refused(tmp_path):
    data = tmp_path / "synthetic-mmio"
    data.write_bytes(bytes(0x10000))
    one = MMIOAperture(SITE_BASE, frozenset({0}), frozenset({0x20}))
    with LinuxMMIO((one,), device=str(data), owner_lock=str(tmp_path / "owner.lock")) as mmio:
        lease = mmio.claim_site(1, SITE_BASE)
        with pytest.raises(MMIOError, match="access policy"):
            FixedABISite1WordPort(lease, host_test_barrier=lambda: None)
    with LinuxMMIO((fixed_abi_site1_aperture(SITE_BASE),),
                   device=str(data), owner_lock=str(tmp_path / "other.lock")) as mmio:
        other_site = mmio.claim_site(2, SITE_BASE)
        with pytest.raises(MMIOError, match="Site 1"):
            FixedABISite1WordPort(other_site, host_test_barrier=lambda: None)


def test_host_test_barrier_refuses_symlink_device(tmp_path):
    raw = tmp_path / "synthetic-mmio"
    raw.write_bytes(bytes(0x10000))
    link = tmp_path / "aliased-synthetic-mmio"
    link.symlink_to(raw)
    with LinuxMMIO((fixed_abi_site1_aperture(SITE_BASE),),
                   device=str(link), owner_lock=str(tmp_path / "owner.lock")) as mmio:
        lease = mmio.claim_site(1, SITE_BASE)
        with pytest.raises(MMIOError, match="non-regular"):
            FixedABISite1WordPort(lease, host_test_barrier=lambda: None)


def test_barrier_denied_after_lease_closes(file_mmio):
    _, _, lease = file_mmio
    called = []
    port = FixedABISite1WordPort(lease, host_test_barrier=lambda: called.append(1))
    lease.close()
    with pytest.raises(MMIOClosed):
        port.write_barrier()
    assert called == []


def test_real_swd_controller_command_after_barrier_and_exact_words(file_mmio, monkeypatch):
    path, mmio, lease = file_mmio
    events = []
    write_fixture_word(path, 0x00, 1)           # Site 1
    write_fixture_word(path, 0x04, 0x00010000)  # ABI v1
    write_fixture_word(path, 0x08, 1)           # CAP_SWD
    write_fixture_word(path, 0x0C, 1)          # IDLE

    def barrier():
        events.append("dmb")

    old_write32 = lease.write32

    def write32(address, value):
        offset = address - SITE_BASE
        events.append(("w", offset, value))
        old_write32(address, value)
        if offset == 0x20:
            # Simulated completion fixture after real native-word COMMAND write.
            # Not real RTL, not an external DUT.
            write_fixture_word(path, 0x0C, 4)   # DONE
            write_fixture_word(path, 0x48, 33)  # sequence
            write_fixture_word(path, 0x4C, 0)   # OK
            write_fixture_word(path, 0x60, 0)   # no data
            write_fixture_word(path, 0x6C, 0)   # empty non-SWD-data meta
            write_fixture_word(path, 0x70, 0)   # raw status

    monkeypatch.setattr(lease, "write32", write32)
    port = FixedABISite1WordPort(lease, host_test_barrier=barrier)
    controller = FixedABISWDController(port, base=SITE_BASE, site_id=1)
    result = controller.transact(sequence=33, opcode=2, bit_count=64)
    assert result.sequence == 33
    assert result.status == 0
    assert read_fixture_word(path, 0x20) == 2
    assert events.index("dmb") < events.index(("w", 0x20, 2))
    assert [e[1] for e in events if isinstance(e, tuple)][:8] == [
        0x24, 0x28, 0x2C, 0x30, 0x34, 0x38, 0x3C, 0x5C,
    ]
    assert read_fixture_word(path, 0x64) == 33
    assert mmio.stats().write32 == 10  # 8 setup + COMMAND + matching ACK


def test_barrier_failure_prevents_command_and_poison_controller(file_mmio):
    path, mmio, lease = file_mmio
    for off, value in ((0x00, 1), (0x04, 0x10000), (0x08, 1), (0x0C, 1)):
        write_fixture_word(path, off, value)

    def fail_barrier():
        raise RuntimeError("injected DMB failure")

    port = FixedABISite1WordPort(lease, host_test_barrier=fail_barrier)
    controller = FixedABISWDController(port, base=SITE_BASE, site_id=1)
    with pytest.raises(FixedABIError, match="Ordering barrier failed"):
        controller.transact(sequence=1, opcode=2, bit_count=64)
    assert controller.poisoned
    assert mmio._poisoned
    assert read_fixture_word(path, 0x20) == 0  # COMMAND was never emitted
    with pytest.raises(FixedABIError, match="poisoned"):
        controller.transact(sequence=2, opcode=2, bit_count=64)


def test_native_barrier_refused_on_unqualified_host_architecture(tmp_path, monkeypatch):
    library = tmp_path / "untrusted.so"
    library.write_bytes(b"not a qualified ARMv7 ELF")
    sha = hashlib.sha256(library.read_bytes()).hexdigest()
    monkeypatch.setattr(platform, "machine", lambda: "x86_64")
    with pytest.raises(MMIOError, match="ARMv7-A"):
        ARMv7DMBBarrier(str(library), sha256=sha)
    with pytest.raises(MMIOError, match="SHA256"):
        ARMv7DMBBarrier(str(library), sha256="not-a-sha")
    with pytest.raises(MMIOError, match="absolute"):
        ARMv7DMBBarrier("relative.so", sha256=sha)


def test_dmb_native_source_is_arm_only_and_no_python_noop():
    c = (ROOT / "software/python/native/armv7_mmio_barrier.c").read_text()
    assert "__ARM_ARCH_7A__" in c
    assert '"dmb sy"' in c
    assert "__volatile__" in c
    assert "libplasma_mmio_barrier.so" in c

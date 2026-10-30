"""LT02 host transport tests use a synthetic WordPort, never /dev/mem/FPGA."""
import zlib
from concurrent.futures import ThreadPoolExecutor
from time import sleep

import pytest

from plasma_interfaces.mmio_loop_test import (
    ABI_VERSION, CAPABILITIES, CAPACITY, MAGIC,
    MAX_CASE_BYTES, REG_ABI, REG_CAPABILITIES, REG_CAPACITY, REG_MAGIC,
    REG_READS, REG_STATUS, REG_WRITES, WINDOW_START,
    LoopTestDriver, LoopTestError, loopback_aperture,
)

BASE = 0x40004000


class FakeLT02:
    """Contract fake only: not AXI RTL, electrical evidence or target HIL."""

    def __init__(self, *, corrupt=False, miss_write=False, miss_read=False):
        self.reg = {
            REG_MAGIC: MAGIC, REG_ABI: ABI_VERSION, REG_CAPABILITIES: CAPABILITIES,
            REG_CAPACITY: CAPACITY, REG_STATUS: 1,
        }
        self.ram = {}
        self.writes = 0
        self.reads = 0
        self.corrupt = corrupt
        self.miss_write = miss_write
        self.miss_read = miss_read

    def read32(self, addr):
        offset = addr - BASE
        if offset == REG_WRITES:
            return self.writes & 0xFFFFFFFF
        if offset == REG_READS:
            return self.reads & 0xFFFFFFFF
        if WINDOW_START <= offset < WINDOW_START + CAPACITY:
            if not self.miss_read:
                self.reads += 1
            value = self.ram.get(offset, 0)
            return value ^ (1 if self.corrupt and offset == WINDOW_START else 0)
        return self.reg[offset]

    def write32(self, addr, word):
        offset = addr - BASE
        assert WINDOW_START <= offset < WINDOW_START + CAPACITY
        assert offset % 4 == 0
        self.ram[offset] = word
        if not self.miss_write:
            self.writes += 1


@pytest.mark.parametrize("size", [1, 2, 3, 4, 5, 1023, 1024, 1025,
                                   2047, 2048, 2049, 4095, 4096, 4097])
def test_echo_exact_payload_and_word_counters(size):
    port = FakeLT02()
    runner = LoopTestDriver(port, base=BASE)
    data = bytes(((i * 131 + 17) & 255) for i in range(size))
    result = runner.echo(data)
    expected_words = sum((min(CAPACITY, size - n) + 3) // 4
                         for n in range(0, size, CAPACITY))
    assert result.payload == data
    assert result.payload_length == size
    assert result.chunks == (size + CAPACITY - 1) // CAPACITY
    assert result.data_word_reads == expected_words
    assert result.data_word_writes == expected_words
    assert port.reads == port.writes == expected_words
    assert result.tx_crc32 == f"{zlib.crc32(data):08x}" == result.rx_crc32
    assert result.elapsed_ns >= 0


def test_no_implicit_counter_reset_and_uint32_wrap():
    port = FakeLT02()
    port.writes = port.reads = 0xFFFFFFFE
    runner = LoopTestDriver(port, base=BASE)
    assert runner.echo(b"wrap").payload == b"wrap"
    assert port.writes == port.reads == 0xFFFFFFFF
    assert runner.echo(b"wrap2").payload == b"wrap2"
    assert port.writes == port.reads == 0x100000001


@pytest.mark.parametrize("flag,error", [
    ("corrupt", "payload mismatch"),
    ("miss_write", "DATA write count mismatch"),
    ("miss_read", "DATA read count mismatch"),
])
def test_mismatch_fails_without_retry(flag, error):
    port = FakeLT02(**{flag: True})
    runner = LoopTestDriver(port, base=BASE)
    with pytest.raises(LoopTestError, match=error):
        runner.echo(b"wrong-data")
    assert set(port.ram) == {WINDOW_START, WINDOW_START + 4, WINDOW_START + 8}
    assert runner.poisoned
    # Clearing the synthetic fault is NOT implicit recovery. No second write.
    written_before = port.writes
    port.corrupt = port.miss_write = port.miss_read = False
    with pytest.raises(LoopTestError, match="poisoned"):
        runner.echo(b"must-not-replay")
    assert port.writes == written_before


@pytest.mark.parametrize("offset,bad", [
    (REG_MAGIC, 0x00), (REG_ABI, 2), (REG_CAPABILITIES, 0),
    (REG_CAPACITY, 1024), (REG_STATUS, 0),
])
def test_wrong_hardware_rejected_before_writing(offset, bad):
    port = FakeLT02()
    port.reg[offset] = bad
    with pytest.raises(LoopTestError):
        LoopTestDriver(port, base=BASE)
    assert port.ram == {}


def test_site_identity_and_payload_bounds():
    port = FakeLT02()
    for invalid in (0, 9, True, None, "2"):
        with pytest.raises(LoopTestError, match="Site ID"):
            LoopTestDriver(port, base=BASE, site_id=invalid)
    # Software supports IDs 1..8, but only independently verified HWH may
    # authorize Site 2 or above on actual FPGA hardware.
    assert LoopTestDriver(port, base=BASE, site_id=2).site_id == 2
    runner = LoopTestDriver(port, base=BASE)
    for bad in (b"", b"x" * (MAX_CASE_BYTES + 1)):
        with pytest.raises(ValueError, match="payload length"):
            runner.echo(bad)
    with pytest.raises(TypeError):
        runner.echo(bytearray(b"x"))
    assert port.ram == {}
    assert not runner.poisoned  # rejected inputs did not access hardware


def test_aperture_allowlist_and_address_alignment():
    ap = loopback_aperture(BASE)
    assert ap.base == BASE
    assert WINDOW_START in ap.readable and WINDOW_START in ap.writable
    assert WINDOW_START + CAPACITY - 4 in ap.readable
    assert WINDOW_START + CAPACITY - 4 in ap.writable
    assert REG_MAGIC in ap.readable and REG_MAGIC not in ap.writable
    assert 0x10 in ap.writable and 0x10 not in ap.readable
    assert 0x0FC not in ap.readable and 0x900 not in ap.readable
    for bad in (-1, BASE + 4, 0x1_0000_0000, None, True):
        with pytest.raises(ValueError, match="4KiB"):
            loopback_aperture(bad)


def test_large_multichunk_case_is_bounded_and_exact():
    port = FakeLT02()
    runner = LoopTestDriver(port, base=BASE)
    data = bytes(range(256)) * 16 + b"finish"
    result = runner.echo(data)
    assert result.payload == data
    assert result.chunks == 3
    assert result.data_word_reads == 512 * 2 + 2


def test_parallel_echoes_on_one_driver_never_interleave_scratchpad_cases():
    class YieldingPort(FakeLT02):
        def write32(self, address, word):
            super().write32(address, word)
            sleep(0)  # Encourage a context switch between MMIO operations.

    port = YieldingPort()
    runner = LoopTestDriver(port, base=BASE)
    payloads = [bytes([(i * 17 + j) & 255 for j in range(2049 + i)])
                for i in range(8)]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(runner.echo, payloads))
    assert all(result.payload == data and
               result.tx_crc32 == result.rx_crc32
               for result, data in zip(results, payloads))
    expected_words = sum((min(CAPACITY, len(data) - origin) + 3) // 4
                         for data in payloads
                         for origin in range(0, len(data), CAPACITY))
    assert port.writes == port.reads == expected_words
    assert not runner.poisoned


def test_mmio_exception_poisoning_prevents_second_case_even_after_fault_removed():
    class FailingPort(FakeLT02):
        fail = True
        def write32(self, addr, word):
            if self.fail:
                self.fail = False
                raise OSError("synthetic bus write failure")
            return super().write32(addr, word)

    port = FailingPort()
    runner = LoopTestDriver(port, base=BASE)
    with pytest.raises(OSError, match="synthetic"):
        runner.echo(b"uncertain")
    assert runner.poisoned
    with pytest.raises(LoopTestError, match="poisoned"):
        runner.echo(b"not retried")
    assert port.writes == 0

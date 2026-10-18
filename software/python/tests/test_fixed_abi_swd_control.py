"""Host-only contract tests for real fixed ABI control code.

The in-memory bus is a deterministic test double for validation checks.
End-to-end AXI-Lite RTL evidence lives in the Cocotb Site-1 suite.
"""
import pytest

from plasma_interfaces.fixed_abi_swd import (
    FixedABIError, FixedABISWDController, FixedABIStatus,
)


BASE = 0x40004000


class WordPort:
    def __init__(self):
        self.words = {0: 1, 4: 0x10000, 8: 1, 0x0C: 1}
        self.log = []
        self.barriers = 0
        self.starts = 0
        self.bad_sequence = False
        self.bad_meta = False
        self.sticky_fault = False
        self.reject_write = None

    def read32(self, address):
        assert address >= BASE and (address - BASE) % 4 == 0
        offset = address - BASE
        self.log.append(("read", offset))
        if offset == 0x48 and self.bad_sequence:
            return self.words.get(offset, 0) + 1
        if offset == 0x6C and self.bad_meta:
            return 0x80000000
        return self.words.get(offset, 0)

    def write32(self, address, word):
        assert address >= BASE and (address - BASE) % 4 == 0
        offset = address - BASE
        self.log.append(("write", offset, word))
        if offset == self.reject_write:
            raise OSError("Injected SLVERR")
        self.words[offset] = word
        if offset == 0x20:
            assert self.barriers == self.starts + 1
            self.starts += 1
            self.words[0x48] = self.words[0x24]
            self.words[0x4C] = 5 if self.sticky_fault else 0
            self.words[0x0C] = 8 if self.sticky_fault else 4
            self.words[0x70] = 7 if self.sticky_fault else 0
            self.words[0x6C] = (1 << 13 if word == 2
                                else (2 << 13) | (1 << 4) | (1 << 3) | 1)
        if offset == 0x64:
            if not self.sticky_fault:
                self.words[0x0C] = 1

    def write_barrier(self):
        self.log.append(("barrier",))
        self.barriers += 1


def driver(port=None, **kwargs):
    p = port if port is not None else WordPort()
    return p, FixedABISWDController(p, base=BASE, site_id=1, **kwargs)


def test_no_implicit_io_constructor_then_exact_commit_ack_order():
    p, d = driver()
    assert p.log == []
    out = d.transact(sequence=101, opcode=2, bit_count=64)
    assert out.sequence == 101 and out.status == FixedABIStatus.OK
    assert out.link_state == 1 and not out.data_valid
    assert not d.poisoned and p.starts == 1
    barrier = p.log.index(("barrier",))
    command = p.log.index(("write", 0x20, 2))
    ack = p.log.index(("write", 0x64, 101))
    assert barrier < command < ack
    assert p.log[barrier - 1] == ("write", 0x5C, 2)
    assert p.words[0x0C] == 1
    with pytest.raises(ValueError, match="reuse"):
        d.transact(sequence=101, opcode=2, bit_count=64)
    assert p.starts == 1


@pytest.mark.parametrize("kwargs", [
    dict(sequence=0, opcode=2, bit_count=64),
    dict(sequence=True, opcode=2, bit_count=64),
    dict(sequence=1, opcode=3, bit_count=64),
    dict(sequence=1, opcode=2, bit_count=50),
    dict(sequence=1, opcode=2, bit_count=64, arg0=1),
    dict(sequence=1, opcode=1, bit_count=32, arg0=2, wdata=1),
    dict(sequence=1, opcode=1, bit_count=64),
    dict(sequence=1, opcode=2, bit_count=64, clock_div=1),
    dict(sequence=1, opcode=2, bit_count=64, timeout_ticks=0),
])
def test_invalid_commands_fail_before_any_io(kwargs):
    p, d = driver()
    with pytest.raises(ValueError):
        d.transact(**kwargs)
    assert p.log == [] and p.starts == 0


def test_missing_ordering_port_is_rejected():
    with pytest.raises(ValueError, match="write_barrier"):
        FixedABISWDController(object(), base=BASE, site_id=1)


def test_identity_capability_mismatch_fails_without_writes():
    p = WordPort()
    p.words[8] = 0
    _, d = driver(p)
    with pytest.raises(FixedABIError, match="identity"):
        d.transact(sequence=3, opcode=2, bit_count=64)
    assert d.poisoned and not any(a[0] == "write" for a in p.log)


def test_nonidle_site_fails_closed_before_command():
    p = WordPort()
    p.words[0x0C] = 2
    _, d = driver(p)
    with pytest.raises(FixedABIError, match="not IDLE"):
        d.transact(sequence=4, opcode=2, bit_count=64)
    assert d.poisoned and p.starts == 0


def test_partial_register_write_error_poison_and_no_launch():
    p = WordPort()
    p.reject_write = 0x24
    _, d = driver(p)
    with pytest.raises(FixedABIError, match="AXI write uncertain"):
        d.transact(sequence=5, opcode=2, bit_count=64)
    assert d.poisoned and p.starts == 0
    assert p.barriers == 0
    with pytest.raises(FixedABIError, match="poisoned"):
        d.transact(sequence=6, opcode=2, bit_count=64)


@pytest.mark.parametrize("mutator", ["bad_sequence", "bad_meta"])
def test_unstable_or_reserved_completion_never_ack(mutator):
    p = WordPort()
    setattr(p, mutator, True)
    _, d = driver(p)
    with pytest.raises(FixedABIError, match="completion"):
        d.transact(sequence=7, opcode=2, bit_count=64)
    assert d.poisoned and p.starts == 1
    assert not any(a[:2] == ("write", 0x64) for a in p.log)


def test_hardware_timeout_latches_fault_even_after_matching_ack():
    p = WordPort()
    p.sticky_fault = True
    _, d = driver(p)
    with pytest.raises(FixedABIError, match="independent recovery required") as e:
        d.transact(sequence=8, opcode=2, bit_count=64, timeout_ticks=1)
    assert e.value.result is not None
    assert e.value.result.sequence == 8
    assert e.value.result.status == FixedABIStatus.TIMEOUT
    assert e.value.uncertain_target_effects
    assert p.words[0x0C] == 8 and p.words[0x4C] == 5
    assert ("write", 0x64, 8) in p.log
    with pytest.raises(FixedABIError, match="poisoned"):
        d.transact(sequence=9, opcode=2, bit_count=64)
    assert p.starts == 1

"""Pinned OpenOCD 5088db4c SWD command-byte decoder, Host-only."""
import pytest

from plasma_interfaces.swd_opencd_5088_command_contract import (
    OpenOcd5088HostContract, OpenOcdSwdCommand,
    decode_opencd_5088_swd_cmd,
)


class SpyNormalQueue:
    def __init__(self):
        self.calls = []

    def read_reg(self, *, ap, address):
        self.calls.append(("read", ap, address))

    def write_reg(self, *, ap, address, value):
        self.calls.append(("write", ap, address, value))

    def switch_seq(self, *, bit_count, bits=0):
        self.calls.append(("swj", bit_count, bits))

    def run(self):
        return (("host-only", tuple(self.calls)),)


def swd_cmd(*, ap, read, address):
    assert address in (0, 4, 8, 12)
    byte = (int(ap) << 1) | (int(read) << 2) | ((address >> 2) << 3)
    return byte | (((byte & 0x1E).bit_count() & 1) << 5)


def test_all_16_valid_opencd_commands_decode_and_retire_private_encoding_mixup():
    for ap in (False, True):
        for read in (False, True):
            for address in (0, 4, 8, 12):
                cmd = swd_cmd(ap=ap, read=read, address=address)
                assert decode_opencd_5088_swd_cmd(cmd) == OpenOcdSwdCommand(
                    ap=ap, read=read, address=address)
    # OpenOCD uses 0x24 for DP IDCODE read, whereas FPGA private command=0x02.
    assert swd_cmd(ap=False, read=True, address=0) == 0x24
    assert swd_cmd(ap=True, read=False, address=12) == 0x3A


@pytest.mark.parametrize("invalid", [-1, 256, True, "0x24", 0x04, 0x25, 0x64, 0xA4])
def test_malformed_or_unframed_swd_byte_denied(invalid):
    with pytest.raises(ValueError):
        decode_opencd_5088_swd_cmd(invalid)


def test_queue_mapping_preserves_callback_kind_address_and_value():
    normal = SpyNormalQueue()
    adapter = OpenOcd5088HostContract(normal)
    adapter.read_reg(swd_cmd(ap=False, read=True, address=0))
    adapter.read_reg(swd_cmd(ap=True, read=True, address=8))
    adapter.write_reg(swd_cmd(ap=True, read=False, address=12), 0xDEADBEEF)
    assert normal.calls == [
        ("read", False, 0),
        ("read", True, 8),
        ("write", True, 12, 0xDEADBEEF),
    ]
    assert adapter.run() == (("host-only", tuple(normal.calls)),)


def test_nonzero_ap_delay_and_no_ack_targetsel_rejected_before_enqueue():
    normal = SpyNormalQueue()
    a = OpenOcd5088HostContract(normal)
    for hint in (1, 8, 100, 0xFFFFFFFF):
        with pytest.raises(NotImplementedError, match="AP delay"):
            a.read_reg(swd_cmd(ap=True, read=True, address=0),
                       ap_delay_hint=hint)
    for invalid in (-1, True, 1.5, "0"):
        with pytest.raises(ValueError, match="delay"):
            a.read_reg(swd_cmd(ap=False, read=True, address=0),
                       ap_delay_hint=invalid)
    with pytest.raises(NotImplementedError, match="TARGETSEL"):
        a.write_reg(swd_cmd(ap=False, read=False, address=12), 0x11223344)
    with pytest.raises(ValueError, match="direction"):
        a.read_reg(swd_cmd(ap=False, read=False, address=0))
    with pytest.raises(ValueError, match="direction"):
        a.write_reg(swd_cmd(ap=False, read=True, address=0), 0)
    assert not normal.calls


def test_atomic_bit_sequences_cover_opencd_64_136_224_bit_requirements():
    normal = SpyNormalQueue()
    a = OpenOcd5088HostContract(normal)
    reset = bytes.fromhex("ffffffffffffff00")  # swd.h length=64
    a.swj_bits(bit_count=64, payload=reset)
    jtag_to_swd = bytes([0xff]*7 + [0x9e, 0xe7] + [0xff]*7 + [0x00])
    a.swj_bits(bit_count=136, payload=jtag_to_swd)
    payload = bytes(range(28))
    a.swj_bits(bit_count=224, payload=payload)
    assert normal.calls == [
        ("swj", 64, int.from_bytes(reset, "little")),
        ("swj", 136, int.from_bytes(jtag_to_swd, "little")),
        ("swj", 224, int.from_bytes(payload, "little")),
    ]
    for count, bits in ((0, b""), (257, b"\x00"*33), (16, b"\x00"),
                        (9, b"\x00\x80"), (8, b"\x00\x00")):
        with pytest.raises(ValueError):
            a.swj_bits(bit_count=count, payload=bits)
    with pytest.raises(TypeError):
        a.swj_bits(bit_count=8, payload=bytearray(b"\x00"))
    assert len(normal.calls) == 3


def test_invalid_adapter_has_no_implicit_fallback():
    with pytest.raises(TypeError):
        OpenOcd5088HostContract(object())

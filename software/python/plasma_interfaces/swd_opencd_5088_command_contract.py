"""Host-only SWD command-byte translation for pinned OpenOCD 5088db4c.

Source: OpenOCD 0.12.0+dev commit
5088db4c9154ca833c6d558381074b33672e127a, src/jtag/swd.h.
This is a restricted software compatibility CONTRACT, NOT the actual C
adapter, loaded FPGA Image, /dev/mem driver or SWD programming qualification.

OpenOCD SWD_CMD_* bits [1..5] differ from PLASMA's private 9-bit command.
This module never clocks a pin, guesses AP posted-read values, retries a
DUT write, or silently discards nonzero AP delay hints / no-ACK TARGETSEL.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .swd_site import encode_transfer


@dataclass(frozen=True)
class OpenOcdSwdCommand:
    ap: bool
    read: bool
    address: int


def decode_opencd_5088_swd_cmd(cmd: int) -> OpenOcdSwdCommand:
    """Validate swd_cmd() format; the caller must supply direction callback."""
    if type(cmd) is not int or not 0 <= cmd <= 0xFF:
        raise ValueError("OpenOCD SWD command must be one unsigned byte")
    # SWD_CMD_START/PARK and bit 6 are NOT present in OpenOCD swd_cmd().
    if cmd & 0xC1:
        raise ValueError("OpenOCD swd_cmd cannot contain START/STOP/PARK")
    if bool(cmd & 0x20) != bool((cmd & 0x1E).bit_count() & 1):
        raise ValueError("OpenOCD SWD command parity mismatch")
    return OpenOcdSwdCommand(
        ap=bool(cmd & 0x02), read=bool(cmd & 0x04),
        address=((cmd >> 3) & 3) * 4,
    )


class _NormalQueue(Protocol):
    def read_reg(self, *, ap: bool, address: int) -> None: ...
    def write_reg(self, *, ap: bool, address: int, value: int) -> None: ...
    def switch_seq(self, *, bit_count: int, bits: int = 0) -> None: ...
    def run(self) -> tuple[object, ...]: ...


class OpenOcd5088HostContract:
    """A strict host-only facade on the existing per-Site NORMAL queue.

    It does not implement OpenOCD's enum swd_special_seq C callback, pointer
    retention, AP posted-read handling or physical HIL. The C layer must
    convert its enumerated sequence to exact LSB-first bits before queuing.
    """

    def __init__(self, normal_queue: _NormalQueue) -> None:
        if not all(callable(getattr(normal_queue, n, None)) for n in
                   ("read_reg", "write_reg", "switch_seq", "run")):
            raise TypeError("Existing NORMAL transfer queue required")
        self._normal = normal_queue

    @staticmethod
    def _validate(cmd: int, *, is_read: bool, ap_delay_hint: int) -> OpenOcdSwdCommand:
        op = decode_opencd_5088_swd_cmd(cmd)
        if op.read is not is_read:
            raise ValueError("OpenOCD SWD read/write callback direction mismatch")
        if type(ap_delay_hint) is not int or ap_delay_hint < 0:
            raise ValueError("OpenOCD AP delay must be a nonnegative integer")
        if ap_delay_hint:
            # FPGA currently hardcodes idle cycles=8 and has no arbitrary
            # per-command AP idle delay; never silently truncate the hint.
            raise NotImplementedError("Nonzero OpenOCD AP delay not yet supported")
        if not op.ap and not op.read and op.address == 12:
            # swd.h swd_cmd_returns_ack(): DPv2 TARGETSEL is no-ACK.
            # Current NORMAL engine requires ACK; cannot misreport success.
            raise NotImplementedError("DPv2 TARGETSEL no-ACK transfer not supported")
        return op

    def read_reg(self, cmd: int, *, ap_delay_hint: int = 0) -> None:
        op = self._validate(cmd, is_read=True, ap_delay_hint=ap_delay_hint)
        self._normal.read_reg(ap=op.ap, address=op.address)

    def write_reg(self, cmd: int, value: int, *, ap_delay_hint: int = 0) -> None:
        op = self._validate(cmd, is_read=False, ap_delay_hint=ap_delay_hint)
        self._normal.write_reg(ap=op.ap, address=op.address, value=value)

    def swj_bits(self, *, bit_count: int, payload: bytes) -> None:
        # Real C adapter must map enum swd_special_seq to its source-locked
        # sequence; no enum-to-bytes mapping/fabricated line reset here.
        if type(payload) is not bytes or type(bit_count) is not int:
            raise TypeError("Exact LSB-first SWJ bytes and bit count required")
        if not 1 <= bit_count <= 256 or len(payload) != (bit_count + 7) // 8:
            raise ValueError("Atomic 1..256-bit SWJ data length required")
        bits = int.from_bytes(payload, "little")
        if bits >> bit_count:
            raise ValueError("Nonzero padding bits beyond SWJ bit count")
        self._normal.switch_seq(bit_count=bit_count, bits=bits)

    def run(self) -> tuple[object, ...]:
        return self._normal.run()

"""Pure transaction oracle. No DUT, clock handling or Virtual Target imports."""
from dataclasses import dataclass

OK, WAIT, FAULT = 1, 2, 4
DPIDR = 0x2BA01477  # synthetic DPv1 fixture, not a detected physical IC
AP_IDR = 0x00000001  # synthetic AP fixture, explicitly not a MEM-AP
POISON = 0xDEADBEEF  # chosen fixture value for architecturally UNKNOWN data


def parity(word):
    return (word & 0xFFFFFFFF).bit_count() & 1


@dataclass(frozen=True)
class Request:
    ap: bool
    read: bool
    address: int

    def header(self):
        if self.address not in (0, 4, 8, 12):
            raise ValueError('SWD register offset must be 0,4,8,12')
        fields = int(self.ap) | (int(self.read) << 1) | (self.address << 0)
        return 0x81 | (fields << 1) | ((fields.bit_count() & 1) << 5)


def decode_header(header):
    if not 0 <= header <= 255 or header & 0xC1 != 0x81 or (header >> 1 & 0x1F).bit_count() & 1:
        raise ValueError('invalid request framing or parity')
    return Request(bool(header & 2), bool(header & 4), (header >> 1) & 12)


class DPReference:
    """Explicit DP subset plus synthetic AP scratch/IDR and posted pipeline."""
    def __init__(self):
        self.select = 0
        self.control = 0
        self.posted = POISON
        self.resend = POISON
        self.scratch = 0

    def read(self, request):
        assert request.read
        if request.ap:
            if self.select >> 24:
                raise ValueError('only synthetic AP0 implemented')
            address = (self.select & 0xF0) | request.address
            value = {0: self.scratch, 0xFC: AP_IDR}[address]
            old, self.posted = self.posted, value
            self.resend = old
            self.control |= 1 << 6
            return old
        if request.address == 0:
            return DPIDR
        if request.address == 4:
            if self.select & 15:
                raise ValueError('banked DP registers not implemented')
            return self.control
        if request.address == 8:
            return self.resend
        self.resend = self.posted
        self.control |= 1 << 6
        return self.posted

    def write(self, request, data):
        assert not request.read
        # Writes discard any outstanding posted result (ADIv5 B4.2.2).
        self.posted = POISON
        if request.ap:
            if self.select & 0xFF0000F0 or request.address != 0:
                raise ValueError('only synthetic AP0 scratch is writable')
            self.scratch = data
        elif request.address == 0:
            for abort_bit, status_bit in [(1,4),(2,5),(3,7),(4,1)]:
                if data & (1 << abort_bit):
                    self.control &= ~(1 << status_bit)
        elif request.address == 4:
            if self.select & 15:
                raise ValueError('banked DP registers not implemented')
            self.control = (self.control & 0xF2) | (data & 0x50000001) | ((data & 0x50000000) << 1)
        elif request.address == 8:
            self.select = data & 0xFF0000FF
        else:
            raise ValueError('TARGETSEL/SWDv2 not implemented')


def attempts_for(acks, retries):
    """Independent bounded WAIT policy, no automatic FAULT/protocol replay."""
    for attempt, ack in enumerate(acks, 1):
        if ack != WAIT or attempt > retries:
            return attempt, ack
    raise ValueError('incomplete ACK scenario')

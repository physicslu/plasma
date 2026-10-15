"""Independent edge-level SWDv1 fixture; no golden-model or DUT state access.

Host bits are sampled on rising edges. Target bits are updated after rising
edges, allowing host capture later in HIGH. Unsupported DP/AP features fail
closed. Scripted ACK/parity faults are deliberate test injection, not a claim
that a conforming target would generate those responses for every register.
"""
from collections import deque


class VirtualSWDTarget:
    def __init__(self):
        self.turnaround = 1
        self.select = 0
        self.control = 0
        self.scratch = 0
        self.posted = self.resend = 0xDEADBEEF
        self.connected = False
        self.state = 'unsynchronized'
        self.ones = self.zeros = 0
        self.drive = False
        self.value = 1
        self.ack_script = deque()
        self.parity_fault = False
        self.silent = False
        self.headers = []
        self.writes = []
        self.events = []
        self.wire = []
        self.resets = 0
        self.request_bits = []
        self.pending = deque()

    def _ack(self):
        ap, read, addr = self.request
        exempt = not ap and (addr == 0 or (read and addr == 4))
        if self.ack_script:
            ack = self.ack_script.popleft()
        elif not exempt and self.control & 0xB2:
            ack = 4
        elif ap and (self.select >> 24 or ((self.select & 0xF0) | addr) not in (0, 0xFC) or (not read and addr != 0)):
            self.control |= 32
            ack = 4
        elif (not ap and addr == 4 and self.select & 15) or (not ap and not read and addr == 12):
            # This fixture does not advertise banked DP or TARGETSEL support.
            self.control |= 32
            ack = 4
        else:
            ack = 1
        if ack in (2, 4) and self.control & 1:
            self.control |= 2
        if read and (ap or addr == 12) and ack != 1:
            self.control &= ~64
        return ack

    def _read_value(self):
        ap, _, addr = self.request
        if ap:
            result = self.posted
            self.posted = self.scratch if ((self.select & 0xF0) | addr) == 0 else 1
            self.resend = result
            self.control |= 64
        elif addr == 0:
            self.connected = True
            result = 0x2BA01477
        elif addr == 4:
            result = self.control
        elif addr == 8:
            result = self.resend
        else:
            self.resend = result = self.posted
            self.control |= 64
        return result

    def _commit_write(self, data):
        ap, _, addr = self.request
        self.writes.append((ap, addr, data))
        self.posted = 0xDEADBEEF  # deliberately UNKNOWN after a write
        if ap:
            self.scratch = data
        elif addr == 0:
            clear = ((data & 16) >> 3) | ((data & 8) << 4) | ((data & 4) << 3) | ((data & 2) << 3)
            self.control &= ~clear
        elif addr == 4:
            requests = data & 0x50000000
            self.control = (self.control & 0xF2) | (data & 1) | requests | (requests << 1)
        elif addr == 8:
            self.select = data & 0xFF0000FF

    @staticmethod
    def _bits(value, count):
        return [(value >> i) & 1 for i in range(count)]

    def _response(self):
        self.ack = self._ack()
        ap, read, _ = self.request
        self.pending = deque([(False, 1, 'turn_in')] * self.turnaround)
        self.pending.extend((True, b, 'ack') for b in self._bits(self.ack, 3))
        data_phase = self.ack == 1 or (self.ack in (2, 4) and bool(self.control & 1))
        if self.ack not in (1, 2, 4):
            # Invalid-ACK injection models a silent/malformed target, no effects.
            data_phase = False
        if data_phase and read:
            data = self._read_value() if self.ack == 1 else 0
            parity = sum(self._bits(data, 32)) % 2
            if self.ack == 1 and self.parity_fault:
                parity ^= 1
                self.parity_fault = False
            # WAIT/FAULT+ORUNDETECT: float throughout ignored read data phase.
            drive = self.ack == 1
            self.pending.extend((drive, b, 'rdata') for b in self._bits(data, 32))
            self.pending.append((drive, parity, 'rparity'))
            self.pending.extend([(False, 1, 'turn_out')] * self.turnaround)
            self.after_response = 'header'
        elif data_phase:
            self.pending.extend([(False, 1, 'turn_write')] * self.turnaround)
            self.after_response = 'write'
        else:
            self.pending.extend([(False, 1, 'turn_out')] * self.turnaround)
            self.after_response = 'header' if self.ack in (2, 4) else 'lockout'
        self.state = 'response'

    def rising(self, host_oe, host_value):
        """One SWCLK rising edge. Returns new target ownership/value."""
        self.wire.append((bool(host_oe), int(host_value), self.state))
        if self.silent:
            self.drive = False
            return False, 1
        if host_oe and host_value:
            self.ones += 1
        else:
            if self.ones >= 50:
                self.state = 'reset_tail'
                self.zeros = 0
                self.events.append(('reset_high', self.ones))
            self.ones = 0
        if self.ones >= 50:
            self.drive = False
            self.pending.clear()
            self.state = 'reset_high'
            self.connected = False
            return False, 1
        if self.state == 'reset_tail':
            if host_oe and host_value == 0:
                self.zeros += 1
                if self.zeros == 2:
                    self.resets += 1
                    if self.control & 1:
                        self.control |= 2
                    self.turnaround = 1
                    self.request_bits = []
                    self.state = 'header'
            else:
                self.zeros = 0
            self.drive = False
            return False, 1
        if self.state in ('reset_high', 'unsynchronized', 'lockout'):
            self.drive = False
            return False, 1
        if self.state == 'response':
            drive, value, phase = self.pending.popleft()
            if phase.startswith('turn') or phase in ('ack', 'rdata', 'rparity'):
                assert not host_oe, f'Host drove {phase}'
            self.events.append((phase, value, drive))
            self.drive, self.value = drive, value
            if not self.pending:
                self.state = self.after_response
                self.request_bits = []
                self.write_bits = []
            return drive, value
        self.drive = False
        if self.state == 'write':
            # Recovery can drain an interrupted write while host floats.
            # Its effect is deliberately not rolled back or reported as safe.
            self.write_bits.append(int(host_value) if host_oe else 1)
            if len(self.write_bits) == 33:
                data = sum(b << i for i, b in enumerate(self.write_bits[:32]))
                if sum(self.write_bits) % 2:
                    self.control |= 128
                    if self.control & 1:
                        self.control |= 2
                elif self.ack == 1:
                    self._commit_write(data)
                self.state = 'header'
                self.request_bits = []
            return False, 1
        # Idle zeros are not request starts; released line is not a header.
        if not self.request_bits and (not host_oe or host_value == 0):
            return False, 1
        # A target samples the line, not host OE. An interrupted header is
        # completed with the fixture pull-up value during recovery clocks.
        if not host_oe:
            self.events.append(('floating_header', len(self.request_bits)))
        self.request_bits.append(int(host_value) if host_oe else 1)
        if len(self.request_bits) == 8:
            b = self.request_bits
            self.headers.append(sum(v << i for i, v in enumerate(b)))
            if b[0] != 1 or b[6:] != [0, 1] or sum(b[1:6]) % 2:
                self.state = 'lockout'
                if self.control & 1:
                    self.control |= 2
                self.events.append(('malformed_header', self.headers[-1]))
            else:
                self.request = (bool(b[1]), bool(b[2]), (b[3] << 2) | (b[4] << 3))
                if not self.connected and self.request != (False, True, 0):
                    self.state = 'lockout'
                else:
                    self._response()
        return False, 1

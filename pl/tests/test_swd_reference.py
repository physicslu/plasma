"""Protocol oracle/target checks independent of RTL and simulator availability."""
import pytest
from pl.verification.models.swd_reference import Request, decode_header, parity, DPReference, POISON
from pl.verification.models.virtual_swd_target import VirtualSWDTarget


@pytest.mark.parametrize('ap,read,address,header', [
    (0,0,0,0x81),(0,1,0,0xA5),(1,0,0,0xA3),(1,1,0,0x87),
    (0,1,4,0x8D),(0,1,8,0x95),(0,1,12,0xBD),(0,0,8,0xB1),
])
def test_independent_known_header_vectors(ap, read, address, header):
    request=Request(bool(ap),bool(read),address)
    assert request.header()==header
    assert decode_header(header)==request


@pytest.mark.parametrize('bit', [0,1,2,3,4,5,6,7])
def test_header_single_bit_corruption_rejected(bit):
    with pytest.raises(ValueError): decode_header(0xA5 ^ (1<<bit))


def test_header_and_parity_boundaries():
    for address in (1,3,16):
        with pytest.raises(ValueError): Request(False,True,address).header()
    for header in (-1,0x1A5):
        with pytest.raises(ValueError): decode_header(header)
    assert [parity(x) for x in (0,1,0x80000000,0xFFFFFFFF,0x87654321)]==[0,1,1,0,1]


def test_posted_read_write_invalidation_and_dp_read_preservation():
    ref=DPReference()
    ref.write(Request(True,False,0),0x12345678)
    assert ref.read(Request(True,True,0))==POISON
    ref.read(Request(False,True,4))  # intervening DP read preserves pending data
    assert ref.read(Request(False,True,12))==0x12345678
    ref.read(Request(True,True,0))
    ref.write(Request(False,False,8),0)
    assert ref.read(Request(False,True,12))==POISON


def line_reset(target):
    for _ in range(64): target.rising(True,1)
    for _ in range(8): target.rising(True,0)


def read_packet(target, header=0xA5):
    for i in range(8): target.rising(True,(header>>i)&1)
    response=[target.rising(False,1) for _ in range(38)]
    for _ in range(8): target.rising(True,0)
    return response


def test_virtual_target_line_reset_dpidr_and_wire_order():
    target=VirtualSWDTarget()
    line_reset(target)
    bits=read_packet(target)
    assert bits[0]==(False,1)
    assert bits[1:4]==[(True,1),(True,0),(True,0)]
    data=sum(value<<i for i,(_,value) in enumerate(bits[4:36]))
    assert data==0x2BA01477
    assert bits[36]==(True, data.bit_count()%2)
    assert bits[37]==(False,1)


@pytest.mark.parametrize('bit', [5,6,7])
def test_virtual_target_malformed_header_requires_reset(bit):
    target=VirtualSWDTarget()
    line_reset(target)
    response=read_packet(target, 0xA5 ^ (1<<bit))
    assert not any(oe for oe,_ in response)
    assert target.state=='lockout'
    line_reset(target)
    assert read_packet(target)[1:4]==[(True,1),(True,0),(True,0)]


def test_line_reset_does_not_clear_dp_sticky_state():
    target=VirtualSWDTarget()
    target.control=0xA1
    target.select=0xF0
    line_reset(target)
    assert target.control==0xA3
    assert target.select==0xF0
    assert target.turnaround==1


@pytest.mark.parametrize('ap,read,addr,ack', [
    (False, True, 0, 1), (False, False, 0, 1),
    (False, True, 4, 1), (False, False, 4, 4),
    (False, False, 8, 4), (True, True, 0, 4),
])
def test_sticky_fault_exemptions(ap, read, addr, ack):
    target = VirtualSWDTarget()
    target.control = 32  # STICKYERR
    target.request = (ap, read, addr)
    assert target._ack() == ack

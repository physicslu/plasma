"""Socketpair-only tests, never an OpenOCD process, listener, or DUT."""
import socket
from contextlib import contextmanager


@contextmanager
def local_socketpair():
    client, server = socket.socketpair()
    try:
        yield client, server
    finally:
        client.close()
        server.close()

import pytest

from plasma_interfaces.swd_debug_bitbang import (
    BitbangProtocolError, SwdDebugBitbangCore,
)
from plasma_interfaces.swd_debug_socket import serve_connected_unix
from plasma_interfaces.swd_site import SITE_BASES


class FakePort:
    def __init__(self):
        self.registers = {}
        self.writes = []
        for site, base in SITE_BASES.items():
            self.registers[base] = 0x40000 | site
            self.registers[base + 0x38] = 0
            self.registers[base + 0x40] = 1

    def read32(self, address):
        return self.registers.get(address, 0)

    def write32(self, address, value):
        self.writes.append((address, value))
        self.registers[address] = value

    def write_barrier(self):
        return None


def make_core(port, site_id=1, lease=lambda: None):
    return SwdDebugBitbangCore(port, site_id=site_id, lease_check=lease)


def test_connected_unix_socketpair_single_byte_swd_roundtrip_and_clean_q():
    port = FakePort()
    core = make_core(port)
    with local_socketpair() as (client, server):
        client.sendall(b"OedgcQ")
        assert serve_connected_unix(core, server, max_commands=16) == 6
        assert client.recv(1) == b"1"
    assert not core.open and not core.poisoned
    assert port.registers[SITE_BASES[1] + 0x38] == 0
    assert any(address == SITE_BASES[1] + 0x3C for address, _ in port.writes)
    assert all(address < SITE_BASES[2] for address, _ in port.writes)


@pytest.mark.parametrize("payload", [b"B", b"R", b"Z", b"0"])
def test_unsupported_jtag_reset_or_sleep_byte_quiesces_mode(payload):
    port = FakePort()
    core = make_core(port)
    with local_socketpair() as (client, server):
        client.sendall(payload)
        with pytest.raises(BitbangProtocolError, match="Unsupported"):
            serve_connected_unix(core, server)
    assert not core.open
    assert port.registers[SITE_BASES[1] + 0x38] == 0
    assert not any(addr == SITE_BASES[1] + 0x3C and val & 1
                   for addr, val in port.writes)


def test_eof_without_q_fails_closed_and_quiesces():
    port = FakePort()
    core = make_core(port)
    client, server = socket.socketpair()
    try:
        client.close()
        with pytest.raises(BitbangProtocolError, match="disconnected"):
            serve_connected_unix(core, server)
    finally:
        server.close()
    assert port.registers[SITE_BASES[1] + 0x38] == 0


def test_request_limit_rejects_nonterminating_protocol():
    port = FakePort()
    core = make_core(port)
    with local_socketpair() as (client, server):
        client.sendall(b"OOQ")
        with pytest.raises(BitbangProtocolError, match="limit"):
            serve_connected_unix(core, server, max_commands=1)
    assert not core.open and port.registers[SITE_BASES[1] + 0x38] == 0


def test_tcp_socket_and_bad_resource_limits_rejected_before_mode_or_mmio():
    port = FakePort()
    core = make_core(port)
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as tcp:
        with pytest.raises(BitbangProtocolError, match="TCP forbidden"):
            serve_connected_unix(core, tcp)
    with local_socketpair() as (_, server):
        with pytest.raises(ValueError, match="limit"):
            serve_connected_unix(core, server, max_commands=0)
        with pytest.raises(ValueError, match="timeout"):
            serve_connected_unix(core, server, timeout_seconds=float("inf"))
    assert not port.writes


def test_lease_denial_does_not_start_debug_transport():
    port = FakePort()
    core = make_core(port, lease=lambda: (_ for _ in ()).throw(PermissionError()))
    with local_socketpair() as (_, server):
        with pytest.raises(BitbangProtocolError, match="lease"):
            serve_connected_unix(core, server)
    assert core.poisoned and not port.writes

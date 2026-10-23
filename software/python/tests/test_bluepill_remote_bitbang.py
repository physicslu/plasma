"""Fail-closed SWD remote_bitbang wire/PL-port contract: no real hardware."""
import socket
import threading
import time

import pytest

from plasma_interfaces.bluepill_remote_bitbang import (
    RemoteBitbangSWD, SWDBitbangError, serve_connection, serve_local_unix_once,
)


BASE = 0x40008000


class FakePL:
    def __init__(self):
        self.regs = {BASE: RemoteBitbangSWD.MAGIC,
                     BASE + 4: RemoteBitbangSWD.VERSION}
        self.drive = 2  # default SWDIO high, clock low, OE disabled
        self.sample = 1
        self.writes = []
        self.barriers = 0
        self.fail = False

    def read32(self, addr):
        if self.fail:
            raise OSError("AXI unavailable")
        if addr == BASE + 12:
            return self.sample | ((self.drive & 1) << 1) | (
                (self.drive & 4)) | ((self.drive & 2) << 2)
        return self.regs[addr]

    def write32(self, addr, value):
        if self.fail:
            raise OSError("AXI unavailable")
        assert addr == BASE + 8
        assert 0 <= value <= 7
        self.drive = value
        self.writes.append(value)

    def write_barrier(self):
        if self.fail:
            raise OSError("AXI unavailable")
        self.barriers += 1


def bridge(port=None):
    p = port or FakePL()
    b = RemoteBitbangSWD(p, base=BASE)
    return b, p


def test_explicit_admission_and_exact_wire_edges():
    b, port = bridge()
    assert port.writes == []
    with pytest.raises(SWDBitbangError):
        b.exchange(b"df")
    b.admit()
    assert port.writes == []
    assert b.exchange(b"Odefgc") == b"1"
    assert port.writes[:5] == [6, 4, 6, 5, 7]
    assert port.barriers >= 2
    assert b.exchange(b"o") == b""
    assert port.drive == 3
    assert b.exchange(b"Q") == b""
    assert port.drive == 2
    assert b.closed and not b.admitted
    with pytest.raises(SWDBitbangError):
        b.exchange(b"c")


@pytest.mark.parametrize("payload", [b"s", b"t", b"u", b"R", b"0", b"Z", b"z", b"x"])
def test_unsupported_reset_jtag_delay_and_unknown_fail_closed(payload):
    b, p = bridge()
    b.admit()
    b.exchange(b"O")
    with pytest.raises(SWDBitbangError):
        b.exchange(payload)
    assert b.closed and p.drive == 2


def test_ignore_only_reset_deassert_and_led_without_touching_target():
    b, p = bridge()
    b.admit()
    assert b.exchange(b"rBb") == b""
    assert not p.writes
    b.close()


def test_wrong_pl_abi_refuses_before_pin_write():
    for key, value in ((BASE, 0), (BASE + 4, 9)):
        b, p = bridge()
        p.regs[key] = value
        with pytest.raises(SWDBitbangError):
            b.admit()
        assert b.poisoned and p.writes == []


def test_unsafe_initial_pin_state_rejected():
    b, p = bridge()
    p.drive = 6  # SWDIO output enabled at start
    with pytest.raises(SWDBitbangError):
        b.admit()
    assert b.poisoned and not p.writes


def test_axi_error_poison_and_no_blind_retry():
    b, p = bridge()
    b.admit()
    p.fail = True
    with pytest.raises(SWDBitbangError):
        b.exchange(b"O")
    assert b.poisoned
    with pytest.raises(SWDBitbangError):
        b.exchange(b"O")
    assert len(p.writes) == 0


def test_no_quit_tail_commands_or_second_admission():
    b, p = bridge()
    b.admit()
    with pytest.raises(SWDBitbangError):
        b.exchange(b"QO")
    assert b.closed and p.drive == 2
    with pytest.raises(SWDBitbangError):
        b.admit()


def test_local_socket_pumps_read_sample_and_quits():
    server, client = socket.socketpair()
    b, p = bridge()
    outcomes = []

    def worker():
        with server:
            try:
                outcomes.append(serve_connection(server, b))
            except Exception as exc:
                outcomes.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    with client:
        client.settimeout(2)
        client.sendall(b"Odc")
        assert client.recv(1) == b"1"
        client.sendall(b"oQ")
    thread.join(timeout=2)
    assert outcomes == [5]
    assert p.drive == 2


def test_connection_budget_and_eof_fails_closed():
    b, p = bridge()
    server, client = socket.socketpair()
    client.sendall(b"Oooo")
    with pytest.raises(SWDBitbangError):
        serve_connection(server, b, command_limit=2)
    assert p.drive == 2
    server.close()
    client.close()
    b, p = bridge()
    server, client = socket.socketpair()
    client.close()
    with pytest.raises(SWDBitbangError):
        serve_connection(server, b)
    assert p.drive == 2
    server.close()


def test_one_shot_owner_private_socket_and_cleanup(tmp_path):
    directory = tmp_path / "private"
    directory.mkdir(mode=0o700)
    path = directory / "swd.sock"
    b, port = bridge()
    outcomes = []

    def worker():
        try:
            outcomes.append(serve_local_unix_once(path, b, idle_timeout_s=3))
        except Exception as exc:
            outcomes.append(exc)

    thread = threading.Thread(target=worker, daemon=True)
    thread.start()
    deadline = time.monotonic() + 3
    while not path.exists() and time.monotonic() < deadline:
        time.sleep(0.01)
    assert path.is_socket()
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as cli:
        cli.connect(str(path))
        cli.settimeout(2)
        cli.sendall(b"Odc")
        assert cli.recv(1) == b"1"
        cli.sendall(b"oQ")
    thread.join(timeout=3)
    assert outcomes == [5]
    assert not path.exists()
    assert port.drive == 2
    b, _ = bridge()
    # An existing path must be rejected *before* creating a listener.
    stale = directory / "occupied.sock"
    stale.write_text("not a socket", encoding="utf-8")
    with pytest.raises(ValueError):
        serve_local_unix_once(stale, b)


def test_absolute_user_owned_socket_required(tmp_path):
    b, _ = bridge()
    with pytest.raises(ValueError):
        serve_local_unix_once("relative.sock", b)
    parent = tmp_path / "shared"
    parent.mkdir(mode=0o777)
    parent.chmod(0o777)
    with pytest.raises(ValueError):
        serve_local_unix_once(parent / "swd.sock", b)
